"""Data coordinator aggregating utility costs per month, year and history."""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    BILLING_POSTPAID,
    BILLING_PREPAID,
    COST_AMOUNT,
    COST_BILLING_MODE,
    COST_NAME,
    DEFAULT_BILLING_MODE,
    DEFAULT_CURRENCY,
    DOMAIN,
    HISTORY_MONTHS,
    OPT_CURRENCY,
    OPT_FIXED_COSTS,
    OPT_UTILITIES,
    UPDATE_INTERVAL_HOURS,
    UTIL_CATEGORY,
    UTIL_ENTITY_ID,
    UTIL_NAME,
    UTIL_RATE,
    UTIL_UNIT,
)
from .statistics import async_monthly_sum

_LOGGER = logging.getLogger(__name__)


@dataclass
class UtilityLine:
    """Single utility breakdown line item."""

    entity_id: str
    name: str
    category: str
    unit: str
    rate: float
    consumption: float
    cost: float
    period_start: str  # ISO date
    period_end: str  # ISO date (inclusive last day)


@dataclass
class FixedCost:
    """Serialisable fixed cost row with period metadata."""

    name: str
    amount: float
    billing_mode: str  # prepaid | postpaid
    period_month: str  # "YYYY-MM" that the charge covers


@dataclass
class BillData:
    """Snapshot produced by the coordinator."""

    currency: str
    month: date
    month_lines: list[UtilityLine] = field(default_factory=list)
    month_fixed: list[FixedCost] = field(default_factory=list)
    month_total: float = 0.0
    last_month: date | None = None
    last_month_total: float = 0.0
    year_total: float = 0.0
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "month": self.month.isoformat(),
            "month_lines": [line.__dict__ for line in self.month_lines],
            "month_fixed": [f.__dict__ for f in self.month_fixed],
            "month_total": self.month_total,
            "last_month": self.last_month.isoformat() if self.last_month else None,
            "last_month_total": self.last_month_total,
            "year_total": self.year_total,
            "history": self.history,
        }


def _month_period(month: date) -> tuple[str, str]:
    last = calendar.monthrange(month.year, month.month)[1]
    return month.isoformat(), date(month.year, month.month, last).isoformat()


def _next_month(month: date) -> date:
    if month.month == 12:
        return date(month.year + 1, 1, 1)
    return date(month.year, month.month + 1, 1)


def _previous_month(month: date) -> date:
    first = month.replace(day=1)
    return (first - timedelta(days=1)).replace(day=1)


class UtilityBillCoordinator(DataUpdateCoordinator[BillData]):
    """Aggregates monthly, yearly and historical utility cost data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(hours=UPDATE_INTERVAL_HOURS),
        )
        self.entry = entry

    @property
    def currency(self) -> str:
        return self.entry.options.get(OPT_CURRENCY, DEFAULT_CURRENCY)

    @property
    def utilities(self) -> list[dict[str, Any]]:
        return list(self.entry.options.get(OPT_UTILITIES, []))

    @property
    def fixed_costs(self) -> list[dict[str, Any]]:
        return list(self.entry.options.get(OPT_FIXED_COSTS, []))

    async def _async_update_data(self) -> BillData:
        now = dt_util.now()
        current_month = now.date().replace(day=1)
        prev_month = _previous_month(current_month)

        data = BillData(
            currency=self.currency,
            month=current_month,
            last_month=prev_month,
        )
        data.month_lines = await self._collect_lines(current_month)
        data.month_fixed = self._fixed_costs_for(current_month)
        data.month_total = self._sum_all(data.month_lines, data.month_fixed)

        prev_lines = await self._collect_lines(prev_month)
        prev_fixed = self._fixed_costs_for(prev_month)
        data.last_month_total = self._sum_all(prev_lines, prev_fixed)

        data.history = await self._collect_history(current_month)
        data.year_total = sum(
            float(entry["total"])
            for entry in data.history
            if entry["month"].startswith(f"{current_month.year}-")
        )
        return data

    def _sum_all(
        self, lines: list[UtilityLine], fixed: list[FixedCost]
    ) -> float:
        total = sum(line.cost for line in lines) + sum(f.amount for f in fixed)
        return round(total, 2)

    async def _collect_lines(self, month: date) -> list[UtilityLine]:
        period_start, period_end = _month_period(month)
        lines: list[UtilityLine] = []
        for row in self.utilities:
            entity_id = row.get(UTIL_ENTITY_ID)
            if not entity_id:
                continue
            rate = float(row.get(UTIL_RATE, 0.0))
            consumption = await async_monthly_sum(
                self.hass, entity_id, month, self.entry.entry_id
            )
            consumption = consumption or 0.0
            lines.append(
                UtilityLine(
                    entity_id=entity_id,
                    name=row.get(UTIL_NAME) or entity_id,
                    category=row.get(UTIL_CATEGORY, "other"),
                    unit=row.get(UTIL_UNIT, ""),
                    rate=rate,
                    consumption=consumption,
                    cost=round(consumption * rate, 2),
                    period_start=period_start,
                    period_end=period_end,
                )
            )
        return lines

    def _fixed_costs_for(self, report_month: date) -> list[FixedCost]:
        """Return fixed-cost rows stamped with the period they cover.

        Prepaid costs billed in the report period cover the *next* calendar
        month; postpaid costs cover the report month itself.
        """
        result: list[FixedCost] = []
        for c in self.fixed_costs:
            mode = c.get(COST_BILLING_MODE, DEFAULT_BILLING_MODE)
            if mode not in (BILLING_PREPAID, BILLING_POSTPAID):
                mode = DEFAULT_BILLING_MODE
            covered = (
                _next_month(report_month)
                if mode == BILLING_PREPAID
                else report_month
            )
            result.append(
                FixedCost(
                    name=c.get(COST_NAME, ""),
                    amount=float(c.get(COST_AMOUNT, 0.0)),
                    billing_mode=mode,
                    period_month=covered.strftime("%Y-%m"),
                )
            )
        return result

    async def _collect_history(self, anchor: date) -> list[dict[str, Any]]:
        """Totals for the last HISTORY_MONTHS months ending at ``anchor``."""
        history: list[dict[str, Any]] = []
        month = anchor
        for _ in range(HISTORY_MONTHS):
            lines = await self._collect_lines(month)
            fixed = self._fixed_costs_for(month)
            total = self._sum_all(lines, fixed)
            history.append(
                {
                    "month": month.strftime("%Y-%m"),
                    "total": total,
                    "utilities_total": round(
                        sum(line.cost for line in lines), 2
                    ),
                    "fixed_total": round(sum(f.amount for f in fixed), 2),
                }
            )
            month = _previous_month(month)
        history.reverse()
        return history

    async def async_generate_report(self, month: date) -> dict[str, Any]:
        """Return a serializable snapshot used by the email renderer."""
        lines = await self._collect_lines(month)
        fixed = self._fixed_costs_for(month)
        total = self._sum_all(lines, fixed)

        prev = _previous_month(month)
        prev_lines = await self._collect_lines(prev)
        prev_fixed = self._fixed_costs_for(prev)
        prev_total = self._sum_all(prev_lines, prev_fixed)

        comparison: dict[str, Any] | None = None
        if prev_total > 0:
            diff = round(total - prev_total, 2)
            comparison = {
                "previous_month": prev.strftime("%Y-%m"),
                "previous_total": prev_total,
                "diff": diff,
                "direction": "saved" if diff < 0 else "spent_more" if diff > 0 else "equal",
            }

        return {
            "month": month.isoformat(),
            "currency": self.currency,
            "lines": [line.__dict__ for line in lines],
            "fixed_costs": [f.__dict__ for f in fixed],
            "total": total,
            "comparison": comparison,
        }
