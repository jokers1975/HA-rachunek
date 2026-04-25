"""Monthly consumption source with statistics-first, state-fallback strategy."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, STORAGE_KEY_PREFIX, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


def _month_bounds(month: date) -> tuple[datetime, datetime]:
    """Return the inclusive start and exclusive end of the given month in local tz."""
    tz = dt_util.DEFAULT_TIME_ZONE
    start = datetime(month.year, month.month, 1, tzinfo=tz)
    if month.month == 12:
        end = datetime(month.year + 1, 1, 1, tzinfo=tz)
    else:
        end = datetime(month.year, month.month + 1, 1, tzinfo=tz)
    return start, end


async def async_monthly_sum(
    hass: HomeAssistant,
    entity_id: str,
    month: date,
    entry_id: str,
) -> float | None:
    """Return total consumption for ``entity_id`` during ``month``.

    Tries long-term statistics first; falls back to stored state snapshots.
    """
    value = await _try_statistics(hass, entity_id, month)
    if value is not None:
        return value
    return await _try_state_fallback(hass, entity_id, month, entry_id)


async def _try_statistics(
    hass: HomeAssistant, entity_id: str, month: date
) -> float | None:
    start, end = _month_bounds(month)
    recorder = get_instance(hass)
    try:
        stats: dict[str, list[dict[str, Any]]] = await recorder.async_add_executor_job(
            statistics_during_period,
            hass,
            start,
            end,
            {entity_id},
            "month",
            None,
            {"sum", "state", "change"},
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Statistics query failed for %s: %s", entity_id, err)
        return None

    rows = stats.get(entity_id) or []
    if not rows:
        return None

    row = rows[0]
    # Prefer 'change' (delta over period) when present; fall back to 'sum'.
    if (change := row.get("change")) is not None:
        return float(change)
    if (total := row.get("sum")) is not None:
        return float(total)
    return None


async def _try_state_fallback(
    hass: HomeAssistant, entity_id: str, month: date, entry_id: str
) -> float | None:
    """Use stored month-start snapshots to compute delta vs current state."""
    store: Store[dict[str, dict[str, float]]] = Store(
        hass,
        STORAGE_VERSION,
        f"{STORAGE_KEY_PREFIX}.{entry_id}",
    )
    data = await store.async_load() or {}
    month_key = month.strftime("%Y-%m")

    state = hass.states.get(entity_id)
    if state is None:
        return None
    try:
        current = float(state.state)
    except (TypeError, ValueError):
        return None

    snapshot = data.setdefault(month_key, {})
    if entity_id not in snapshot:
        # First observation — record baseline, return 0 for this cycle.
        snapshot[entity_id] = current
        await store.async_save(data)
        return 0.0

    baseline = snapshot[entity_id]
    delta = current - baseline
    return max(delta, 0.0)


async def async_reset_snapshot(
    hass: HomeAssistant, entry_id: str, month: date
) -> None:
    """Clear the fallback baseline for a new month."""
    store: Store[dict[str, dict[str, float]]] = Store(
        hass,
        STORAGE_VERSION,
        f"{STORAGE_KEY_PREFIX}.{entry_id}",
    )
    data = await store.async_load() or {}
    month_key = month.strftime("%Y-%m")
    if month_key in data:
        del data[month_key]
        await store.async_save(data)
