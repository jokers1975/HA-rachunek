"""Utility Bill Summary integration setup."""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import (
    CARD_FILENAME,
    CARD_URL_PATH,
    DEFAULT_AUTO_SEND,
    DOMAIN,
    OPT_AUTO_SEND,
    OPT_RECIPIENTS,
    PLATFORMS,
    REPORT_DAY,
    REPORT_HOUR,
    REPORT_MINUTE,
    SERVICE_GENERATE_PREVIEW,
    SERVICE_SEND_MONTHLY_REPORT,
)
from .coordinator import UtilityBillCoordinator
from .email_report import async_send_report, render_report_html

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_SCHEMA = vol.Schema(
    {
        vol.Optional("recipients"): vol.All(list, [str]),
        vol.Optional("month"): str,  # "YYYY-MM"
    }
)

SERVICE_PREVIEW_SCHEMA = vol.Schema(
    {
        vol.Optional("month"): str,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry."""
    coordinator = UtilityBillCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coordinator}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await _async_register_frontend_card(hass)
    _async_register_services(hass)

    # Built-in monthly scheduler — fires daily at 09:00, guarded by day == 1.
    async def _scheduled_check(now):
        if now.day != REPORT_DAY:
            return
        if not entry.options.get(OPT_AUTO_SEND, DEFAULT_AUTO_SEND):
            return
        await _async_run_monthly_job(hass, entry)

    unsub = async_track_time_change(
        hass, _scheduled_check, hour=REPORT_HOUR, minute=REPORT_MINUTE, second=0
    )
    hass.data[DOMAIN][entry.entry_id]["unsub_schedule"] = unsub

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    entry_data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if entry_data and (unsub := entry_data.get("unsub_schedule")):
        unsub()
    if not hass.data.get(DOMAIN):
        for service in (SERVICE_SEND_MONTHLY_REPORT, SERVICE_GENERATE_PREVIEW):
            if hass.services.has_service(DOMAIN, service):
                hass.services.async_remove(DOMAIN, service)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_frontend_card(hass: HomeAssistant) -> None:
    """Serve the custom Lovelace card and register it as an extra module."""
    if hass.data[DOMAIN].get("_card_registered"):
        return
    # www/ lives at the repo root; manifest directory is custom_components/<domain>/
    component_dir = os.path.dirname(__file__)
    repo_root = os.path.abspath(os.path.join(component_dir, "..", ".."))
    card_path = os.path.join(repo_root, "www", CARD_FILENAME)
    if not os.path.exists(card_path):
        _LOGGER.warning("Card file not found at %s", card_path)
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL_PATH, card_path, cache_headers=False)]
    )
    add_extra_js_url(hass, CARD_URL_PATH)
    hass.data[DOMAIN]["_card_registered"] = True


def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_MONTHLY_REPORT):
        return

    async def _send_report(call: ServiceCall) -> None:
        month = _parse_month(call.data.get("month"))
        recipients = call.data.get("recipients")
        for entry_id in list(hass.data.get(DOMAIN, {}).keys()):
            if entry_id.startswith("_"):
                continue
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is None:
                continue
            await _async_run_monthly_job(hass, entry, month=month, recipients=recipients)

    async def _generate_preview(call: ServiceCall) -> dict[str, Any]:
        month = _parse_month(call.data.get("month"))
        for entry_id, bundle in hass.data.get(DOMAIN, {}).items():
            if entry_id.startswith("_"):
                continue
            coordinator: UtilityBillCoordinator = bundle["coordinator"]
            target = month or _previous_month(dt_util.now().date())
            report = await coordinator.async_generate_report(target)
            return {"html": render_report_html(report), "report": report}
        return {"html": "", "report": {}}

    hass.services.async_register(
        DOMAIN, SERVICE_SEND_MONTHLY_REPORT, _send_report, schema=SERVICE_SEND_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GENERATE_PREVIEW,
        _generate_preview,
        schema=SERVICE_PREVIEW_SCHEMA,
        supports_response=True,
    )


async def _async_run_monthly_job(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    month: date | None = None,
    recipients: list[str] | None = None,
) -> None:
    bundle = hass.data[DOMAIN].get(entry.entry_id)
    if not bundle:
        return
    coordinator: UtilityBillCoordinator = bundle["coordinator"]
    target = month or _previous_month(dt_util.now().date())
    report = await coordinator.async_generate_report(target)
    to = recipients or entry.options.get(OPT_RECIPIENTS, [])
    if not to:
        _LOGGER.warning("No recipients configured; skipping email send")
        return
    await async_send_report(hass, entry, report, to)


def _previous_month(today: date) -> date:
    first = today.replace(day=1)
    return (first - timedelta(days=1)).replace(day=1)


def _parse_month(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        year, month = raw.split("-")
        return date(int(year), int(month), 1)
    except (ValueError, AttributeError):
        _LOGGER.warning("Invalid month format %s (expected YYYY-MM)", raw)
        return None
