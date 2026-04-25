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
    BILLING_PREPAID,
    CONF_SMTP_HOST,
    CONF_SMTP_PASSWORD,
    CONF_SMTP_PORT,
    CONF_SMTP_SENDER,
    CONF_SMTP_TLS,
    CONF_SMTP_USER,
)

_LOGGER = logging.getLogger(__name__)

_PL_MONTHS = [
    "styczeń",
    "luty",
    "marzec",
    "kwiecień",
    "maj",
    "czerwiec",
    "lipiec",
    "sierpień",
    "wrzesień",
    "październik",
    "listopad",
    "grudzień",
]
_PL_MONTHS_GEN = [  # "za styczeń"
    "styczeń",
    "luty",
    "marzec",
    "kwiecień",
    "maj",
    "czerwiec",
    "lipiec",
    "sierpień",
    "wrzesień",
    "październik",
    "listopad",
    "grudzień",
]


def _fmt_money(value: float, currency: str) -> str:
    return f"{value:,.2f} {currency}".replace(",", " ").replace(".", ",")


def _fmt_iso_month(iso_month: str) -> str:
    """Format YYYY-MM or YYYY-MM-DD as 'styczeń 2026'."""
    try:
        if len(iso_month) == 7:  # YYYY-MM
            year, month = iso_month.split("-")
            return f"{_PL_MONTHS[int(month) - 1]} {year}"
        parsed = datetime.strptime(iso_month, "%Y-%m-%d").date()
        return f"{_PL_MONTHS[parsed.month - 1]} {parsed.year}"
    except (ValueError, IndexError):
        return iso_month


def _fmt_period_range(start_iso: str, end_iso: str) -> str:
    """Format 'od 1 do 30 kwietnia 2026' from two ISO dates."""
    try:
        s = datetime.strptime(start_iso, "%Y-%m-%d").date()
        e = datetime.strptime(end_iso, "%Y-%m-%d").date()
    except ValueError:
        return f"{start_iso} – {end_iso}"
    if s.month == e.month and s.year == e.year:
        return f"od {s.day} do {e.day} {_PL_MONTHS_GEN[s.month - 1]} {s.year}"
    return (
        f"od {s.day} {_PL_MONTHS_GEN[s.month - 1]} {s.year} "
        f"do {e.day} {_PL_MONTHS_GEN[e.month - 1]} {e.year}"
    )


def _comparison_sentence(comparison: dict[str, Any], currency: str) -> str:
    prev = _fmt_iso_month(comparison.get("previous_month", ""))
    diff = float(comparison.get("diff", 0.0))
    if comparison.get("direction") == "saved":
        return (
            f"W tym miesiącu zaoszczędziłeś {_fmt_money(abs(diff), currency)} "
            f"w porównaniu z miesiącem {prev}."
        )
    if comparison.get("direction") == "spent_more":
        return (
            f"W tym miesiącu wydałeś o {_fmt_money(abs(diff), currency)} więcej "
            f"niż w miesiącu {prev}."
        )
    return f"Wydatki są takie same jak w miesiącu {prev}."


def render_report_html(report: dict[str, Any]) -> str:
    """Return an invoice-styled HTML document for the given report snapshot."""
    currency = report.get("currency", "PLN")
    lines = report.get("lines", [])
    fixed = report.get("fixed_costs", [])
    total = float(report.get("total", 0.0))
    period_label = _fmt_iso_month(report.get("month", date.today().isoformat()))
    is_test = bool(report.get("is_test"))
    comparison = report.get("comparison")
    report_number = datetime.strptime(
        report.get("month", date.today().isoformat())[:10], "%Y-%m-%d"
    ).strftime("%Y%m")

    lines_html = "".join(
        f"""
        <tr>
          <td>
            <div class="name">{escape(str(line.get("name", "")))}</div>
            <div class="period">okres: {escape(_fmt_period_range(line.get("period_start", ""), line.get("period_end", "")))}</div>
          </td>
          <td class="num">{line.get("consumption", 0):.2f} {escape(str(line.get("unit", "")))}</td>
          <td class="num">{_fmt_money(float(line.get("rate", 0)), currency)}</td>
          <td class="num strong">{_fmt_money(float(line.get("cost", 0)), currency)}</td>
        </tr>
        """
        for line in lines
    )

    def _cost_label(cost: dict[str, Any]) -> str:
        period = _fmt_iso_month(cost.get("period_month", ""))
        mode = cost.get("billing_mode", "postpaid")
        if mode == BILLING_PREPAID:
            return f"opłata z góry — za {period}"
        return f"opłata z dołu — za {period}"

    fixed_html = "".join(
        f"""
        <tr>
          <td>
            <div class="name">{escape(str(cost.get("name", "")))}</div>
            <div class="period">{escape(_cost_label(cost))}</div>
          </td>
          <td class="num" colspan="2">—</td>
          <td class="num strong">{_fmt_money(float(cost.get("amount", 0)), currency)}</td>
        </tr>
        """
        for cost in fixed
    )

    comparison_html = ""
    if comparison:
        sentence = _comparison_sentence(comparison, currency)
        direction = comparison.get("direction", "equal")
        cls = "saved" if direction == "saved" else "spent" if direction == "spent_more" else "equal"
        comparison_html = f"""
        <div class="comparison {cls}">
          <div class="cmp-title">Porównanie z poprzednim miesiącem</div>
          <div class="cmp-body">{escape(sentence)}</div>
        </div>
        """

    badge = '<span class="badge">TEST</span>' if is_test else ""

    return f"""<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><title>Rachunek {escape(period_label)}</title>
<style>
  body {{ font-family: "Helvetica Neue", Arial, sans-serif; color: #222; background: #f1ede1; margin: 0; padding: 24px; }}
  .invoice {{ max-width: 680px; margin: 0 auto; background: #fffaf0; border: 1px solid #d8cfa8;
    padding: 32px; box-shadow: 0 2px 14px rgba(0,0,0,0.08); }}
  header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }}
  h1 {{ font-size: 22px; letter-spacing: 2px; text-transform: uppercase; margin: 0 0 4px; }}
  .period {{ color: #6a5a2a; font-size: 13px; }}
  .meta {{ text-align: right; font-size: 12px; color: #6a5a2a; }}
  .meta .num {{ font-size: 14px; color: #222; font-weight: 600; }}
  .badge {{ display: inline-block; background: #b22; color: #fff; padding: 2px 8px; border-radius: 3px;
    font-size: 11px; letter-spacing: 2px; margin-left: 8px; vertical-align: middle; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ padding: 10px 8px; border-bottom: 1px dashed #c8b978; text-align: left; vertical-align: top; }}
  th {{ font-size: 11px; letter-spacing: 1px; text-transform: uppercase; color: #6a5a2a; border-bottom: 2px solid #6a5a2a; }}
  td .name {{ font-weight: 500; }}
  td .period {{ font-size: 11px; color: #8a7f55; margin-top: 2px; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
  .strong {{ font-weight: 600; }}
  .total {{ margin-top: 22px; display: flex; justify-content: space-between; align-items: baseline;
    font-size: 20px; border-top: 2px solid #222; padding-top: 12px; }}
  .total .label {{ letter-spacing: 2px; text-transform: uppercase; font-size: 12px; }}
  .comparison {{ margin-top: 18px; padding: 12px 14px; border-radius: 4px; font-size: 13px;
    border-left: 4px solid #6a5a2a; background: #f5eed6; }}
  .comparison.saved {{ border-left-color: #2a7a2a; background: #eaf6e4; }}
  .comparison.spent {{ border-left-color: #b55; background: #fbe9e5; }}
  .comparison .cmp-title {{ font-weight: 600; font-size: 11px; letter-spacing: 1px;
    text-transform: uppercase; margin-bottom: 4px; }}
  .footer {{ margin-top: 22px; font-size: 11px; color: #8a7f55; text-align: center; }}
</style></head>
<body><div class="invoice">
  <header>
    <div>
      <h1>Rachunek za media {badge}</h1>
      <div class="period">Okres rozliczenia: {escape(period_label)}</div>
    </div>
    <div class="meta">
      Numer<br><span class="num">UBS/{report_number}</span>
    </div>
  </header>
  <table>
    <thead><tr>
      <th>Pozycja</th><th class="num">Zużycie</th><th class="num">Stawka</th><th class="num">Kwota</th>
    </tr></thead>
    <tbody>{lines_html}{fixed_html}</tbody>
  </table>
  <div class="total"><span class="label">Razem do zapłaty</span><span>{_fmt_money(total, currency)}</span></div>
  {comparison_html}
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

    period_label = _fmt_iso_month(report.get("month", ""))
    subject_prefix = "[TEST] " if report.get("is_test") else ""

    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(to_list)
    message["Subject"] = f"{subject_prefix}Rachunek za media — {period_label}"
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
