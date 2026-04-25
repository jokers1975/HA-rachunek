"""Sensor entities exposing monthly and yearly cost aggregates."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, UTIL_ENTITY_ID, UTIL_NAME
from .coordinator import BillData, UtilityBillCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create cost sensors based on configured utilities."""
    coordinator: UtilityBillCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    entities: list[SensorEntity] = [
        MonthTotalSensor(coordinator, entry),
        YearTotalSensor(coordinator, entry),
        LastMonthTotalSensor(coordinator, entry),
    ]
    for row in coordinator.utilities:
        entities.append(UtilityCostSensor(coordinator, entry, row))
    async_add_entities(entities)


class _BaseBillSensor(CoordinatorEntity[UtilityBillCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator: UtilityBillCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry

    @property
    def native_unit_of_measurement(self) -> str:
        return self.coordinator.currency


class MonthTotalSensor(_BaseBillSensor):
    _attr_translation_key = "month_total"
    _attr_icon = "mdi:receipt-text"

    def __init__(self, coordinator: UtilityBillCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_month_total"

    @property
    def native_value(self) -> float | None:
        data: BillData | None = self.coordinator.data
        return None if data is None else data.month_total

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data: BillData | None = self.coordinator.data
        if data is None:
            return {}
        return {
            "month": data.month.isoformat(),
            "currency": data.currency,
            "breakdown": [line.__dict__ for line in data.month_lines],
            "fixed_costs": data.month_fixed,
        }


class LastMonthTotalSensor(_BaseBillSensor):
    _attr_translation_key = "last_month_total"
    _attr_icon = "mdi:receipt-text-outline"

    def __init__(self, coordinator: UtilityBillCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_last_month_total"

    @property
    def native_value(self) -> float | None:
        data: BillData | None = self.coordinator.data
        return None if data is None else data.last_month_total

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data: BillData | None = self.coordinator.data
        if data is None or data.last_month is None:
            return {}
        return {
            "month": data.last_month.isoformat(),
            "currency": data.currency,
            "breakdown": [line.__dict__ for line in data.last_month_lines],
            "fixed_costs": data.last_month_fixed,
        }


class YearTotalSensor(_BaseBillSensor):
    _attr_translation_key = "year_total"
    _attr_icon = "mdi:calendar-text"

    def __init__(self, coordinator: UtilityBillCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_year_total"

    @property
    def native_value(self) -> float | None:
        data: BillData | None = self.coordinator.data
        return None if data is None else data.year_total

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data: BillData | None = self.coordinator.data
        if data is None:
            return {}
        return {"year": data.month.year, "currency": data.currency}


class UtilityCostSensor(_BaseBillSensor):
    _attr_icon = "mdi:meter-electric"

    def __init__(
        self,
        coordinator: UtilityBillCoordinator,
        entry: ConfigEntry,
        row: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, entry)
        self._row_entity = row[UTIL_ENTITY_ID]
        self._attr_name = row.get(UTIL_NAME) or row[UTIL_ENTITY_ID]
        self._attr_unique_id = f"{entry.entry_id}_{row[UTIL_ENTITY_ID]}"

    @property
    def native_value(self) -> float | None:
        data: BillData | None = self.coordinator.data
        if data is None:
            return None
        for line in data.month_lines:
            if line.entity_id == self._row_entity:
                return line.cost
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data: BillData | None = self.coordinator.data
        if data is None:
            return {}
        for line in data.month_lines:
            if line.entity_id == self._row_entity:
                return {
                    "consumption": line.consumption,
                    "unit": line.unit,
                    "rate": line.rate,
                    "category": line.category,
                    "source_entity": line.entity_id,
                }
        return {}
