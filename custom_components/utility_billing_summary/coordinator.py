"""Data coordinator aggregating utility costs per month and year."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    COST_AMOUNT,
    COST_NAME,
    DEFAULT_CURRENCY,
    DOMAIN,
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


@dataclass
class BillData:
    """Snapshot produced by the coordinator."""

    currency: str
    month: date
    month_lines: list[UtilityLine] = field(default_factory=list)
    month_fixed: list[dict[str, Any]] = field(default_factory=list)
    month_total: float = 0.0
    last_month: date | None = None
    last_month_lines: list[UtilityLine] = field(default_factory=list)
    last_month_fixed: list[dict[str, Any]] = field(default_factory=list)
    last_month_total: float = 0.0
    year_total: float = 0.0


class UtilityBillCoordinator(DataUpdateCoordinator[BillData]):
    """Aggregates monthly and yearly utility cost data."""

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
        previous_month = (current_month - timedelta(days=1)).replace(day=1)

        data = BillData(
            currency=self.currency,
            month=current_month,
            last_month=previous_month,
        )

        data.month_lines = await self._collect_lines(current_month)
        data.month_fixed = self._fixed_costs_snapshot()
        data.month_total = sum(line.cost for line in data.month_lines) + sum(
            float(c.get(COST_AMOUNT, 0.0)) for c in data.month_fixed
        )

        data.last_month_lines = await self._collect_lines(previous_month)
        data.last_month_fixed = self._fixed_costs_snapshot()
        data.last_month_total = sum(line.cost for line in data.last_month_lines) + sum(
            float(c.get(COST_AMOUNT, 0.0)) for c in data.last_month_fixed
        )

        data.year_total = await self._collect_year_total(now.year)
        return data

    async def _collect_lines(self, month: date) -> list[UtilityLine]:
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
                )
            )
        return lines

    def _fixed_costs_snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                COST_NAME: c.get(COST_NAME, ""),
                COST_AMOUNT: float(c.get(COST_AMOUNT, 0.0)),
            }
            for c in self.fixed_costs
        ]

    async def _collect_year_total(self, year: int) -> float:
        total = 0.0
        month = date(year, 1, 1)
        today = dt_util.now().date()
        while month <= today:
            lines = await self._collect_lines(month)
            total += sum(line.cost for line in lines)
            total += sum(float(c.get(COST_AMOUNT, 0.0)) for c in self.fixed_costs)
            if month.month == 12:
                break
            month = date(year, month.month + 1, 1)
        return round(total, 2)

    async def async_generate_report(self, month: date) -> dict[str, Any]:
        """Return a serializable snapshot used by the email renderer."""
        lines = await self._collect_lines(month)
        fixed = self._fixed_costs_snapshot()
        total = sum(line.cost for line in lines) + sum(
            float(c.get(COST_AMOUNT, 0.0)) for c in fixed
        )
        return {
            "month": month.isoformat(),
            "currency": self.currency,
            "lines": [line.__dict__ for line in lines],
            "fixed_costs": fixed,
            "total": round(total, 2),
        }
