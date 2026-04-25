"""Render utility summary as HTML and deliver via async SMTP."""
from __future__ import annotations

import logging
from datetime import date, datetime
from email.message import EmailMessage
from html import escape
from typing import Any, Iterable

import aiosmtplib
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_SMTP_HOST,
    CONF_SMTP_PASSWORD,
    CONF_SMTP_PORT,
    CONF_SMTP_SENDER,
    CONF_SMTP_TLS,
    CONF_SMTP_USER,
)

_LOGGER = logging.getLogger(__name__)

_PL_MONTHS = [
    "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
    "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
]


def _fmt_money(value: float, currency: str) -> str:
    return f"{value:,.2f} {currency}".replace(",", " ").replace(".", ",")


def _fmt_month(iso_month: str) -> str:
    parsed = datetime.strptime(iso_month, "%Y-%m-%d").date()
    return f"{_PL_MONTHS[parsed.month - 1]} {parsed.year}"


def render_report_html(report: dict[str, Any]) -> str:
    """Return an invoice-styled HTML document for the given report snapshot."""
    currency = report.get("currency", "PLN")
    lines = report.get("lines", [])
    fixed = report.get("fixed_costs", [])
    total = float(report.get("total", 0.0))
    period = _fmt_month(report.get("month", date.today().isoformat()))

    rows_html = "".join(
        f"""
        <tr>
          <td>{escape(str(line.get("name", "")))}</td>
          <td class="num">{line.get("consumption", 0):.2f} {escape(str(line.get("unit", "")))}</td>
          <td class="num">{_fmt_money(float(line.get("rate", 0)), currency)}</td>
          <td class="num strong">{_fmt_money(float(line.get("cost", 0)), currency)}</td>
        </tr>
        """
        for line in lines
    )
    fixed_html = "".join(
        f"""
        <tr>
          <td>{escape(str(cost.get("name", "")))}</td>
          <td class="num" colspan="2">—</td>
          <td class="num strong">{_fmt_money(float(cost.get("amount", 0)), currency)}</td>
        </tr>
        """
        for cost in fixed
    )

    return f"""<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><title>Rachunek {escape(period)}</title>
<style>
  body {{ font-family: "Helvetica Neue", Arial, sans-serif; color: #222; background: #f6f5f0; margin: 0; padding: 24px; }}
  .invoice {{ max-width: 640px; margin: 0 auto; background: #fffaf0; border: 1px solid #d8cfa8;
    padding: 32px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); }}
  h1 {{ font-size: 22px; letter-spacing: 2px; text-transform: uppercase; margin: 0 0 8px; }}
  .period {{ color: #6a5a2a; margin-bottom: 24px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ padding: 10px 8px; border-bottom: 1px dashed #c8b978; text-align: left; }}
  th {{ font-size: 12px; letter-spacing: 1px; text-transform: uppercase; color: #6a5a2a; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .strong {{ font-weight: 600; }}
  .total {{ margin-top: 24px; text-align: right; font-size: 20px; border-top: 2px solid #222; padding-top: 12px; }}
  .footer {{ margin-top: 24px; font-size: 11px; color: #8a7f55; text-align: center; }}
</style></head>
<body><div class="invoice">
  <h1>Rachunek za media</h1>
  <div class="period">Okres: {escape(period)}</div>
  <table>
    <thead><tr><th>Pozycja</th><th class="num">Zużycie</th><th class="num">Stawka</th><th class="num">Kwota</th></tr></thead>
    <tbody>{rows_html}{fixed_html}</tbody>
  </table>
  <div class="total">Razem: {_fmt_money(total, currency)}</div>
  <div class="footer">Wygenerowano przez Utility Bill Summary · Home Assistant</div>
</div></body></html>"""


async def async_send_report(
    hass: HomeAssistant,
    entry: ConfigEntry,
    report: dict[str, Any],
    recipients: Iterable[str],
) -> None:
    """Compose and send the HTML report via the configured SMTP server."""
    data = entry.data
    host = data.get(CONF_SMTP_HOST)
    port = int(data.get(CONF_SMTP_PORT, 587))
    user = data.get(CONF_SMTP_USER)
    password = data.get(CONF_SMTP_PASSWORD)
    use_tls = bool(data.get(CONF_SMTP_TLS, True))
    sender = data.get(CONF_SMTP_SENDER) or user

    if not host or not sender:
        _LOGGER.warning("SMTP not configured — skipping send")
        return

    to_list = [r for r in recipients if r]
    if not to_list:
        _LOGGER.warning("No recipients provided — skipping send")
        return

    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(to_list)
    message["Subject"] = f"Rachunek za media — {_fmt_month(report.get('month', ''))}"
    message.set_content("Twój klient pocztowy nie obsługuje wersji HTML.")
    message.add_alternative(render_report_html(report), subtype="html")

    try:
        await aiosmtplib.send(
            message,
            hostname=host,
            port=port,
            username=user or None,
            password=password or None,
            start_tls=use_tls and port != 465,
            use_tls=port == 465,
        )
        _LOGGER.info("Utility summary email sent to %s", to_list)
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("Failed to send utility summary email: %s", err)
        raise
