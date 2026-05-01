"""Bridge to Home Assistant's Energy Dashboard: discover priced sources and listen for pref changes."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from homeassistant.core import HomeAssistant

from .const import (
    CATEGORY_ELECTRICITY,
    CATEGORY_GAS,
    CATEGORY_OTHER,
    CATEGORY_WATER,
)

_LOGGER = logging.getLogger(__name__)

# Map Energy Dashboard source type → our internal category
_TYPE_TO_CATEGORY = {
    "grid": CATEGORY_ELECTRICITY,
    "gas": CATEGORY_GAS,
    "water": CATEGORY_WATER,
}

# Default unit label per category (user can override per row)
_DEFAULT_UNITS = {
    CATEGORY_ELECTRICITY: "kWh",
    CATEGORY_GAS: "m³",
    CATEGORY_WATER: "m³",
    CATEGORY_OTHER: "",
}


async def async_available_sources(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Return priced energy/gas/water sources from the Energy Dashboard.

    Each entry:
      {
        "stat_energy_from": "<sensor id>",    # source meter
        "stat_cost": "<statistic id>",        # effective cost statistic
        "category": "electricity|gas|water",
        "unit": "kWh|m³|...",
        "name": "<human-friendly>",
      }

    Sources without any price configuration (no explicit stat_cost and no
    entity_energy_price / number_energy_price) are skipped — we can't produce
    a cost for them.
    """
    try:
        from homeassistant.components.energy import async_get_manager
    except ImportError:
        _LOGGER.debug("Energy component unavailable")
        return []

    try:
        manager = await async_get_manager(hass)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Cannot access energy manager: %s", err)
        return []

    prefs = getattr(manager, "data", None)
    if not prefs:
        return []

    result: list[dict[str, Any]] = []
    for src in prefs.get("energy_sources", []):
        src_type = src.get("type")
        category = _TYPE_TO_CATEGORY.get(src_type)
        if not category:
            continue
        stat_energy = src.get("stat_energy_from")
        if not stat_energy:
            continue
        stat_cost = src.get("stat_cost") or f"{stat_energy}_cost"
        has_price = bool(
            src.get("stat_cost")
            or src.get("entity_energy_price")
            or src.get("number_energy_price") is not None
        )
        if not has_price:
            # No way to obtain a cost → not useful for a bill.
            continue
        result.append(
            {
                "stat_energy_from": stat_energy,
                "stat_cost": stat_cost,
                "category": category,
                "unit": _DEFAULT_UNITS.get(category, ""),
                "name": _friendly_name(hass, stat_energy),
            }
        )
    return result


def _friendly_name(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    if state and (friendly := state.attributes.get("friendly_name")):
        return str(friendly)
    return entity_id


async def async_register_prefs_listener(
    hass: HomeAssistant, callback: Callable[[], Awaitable[None]]
) -> Callable[[], None] | None:
    """Register a callback that fires whenever Energy Dashboard prefs are saved.

    Returns an unsubscribe callable, or None when Energy is unavailable.
    """
    try:
        from homeassistant.components.energy import async_get_manager
    except ImportError:
        return None

    try:
        manager = await async_get_manager(hass)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Cannot attach energy prefs listener: %s", err)
        return None

    listen = getattr(manager, "async_listen_updates", None)
    if listen is None:
        return None
    return listen(callback)
