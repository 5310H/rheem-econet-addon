"""Sensors for Rheem EcoNet tankless heaters."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONTROLLER_REVISION,
    DOMAIN,
    DP_BTUS,
    DP_FLOW_RATE,
    DP_IGNITION_CYCLES,
    DP_TEMP_IN,
    DP_TEMP_OUT,
    DP_WATER_USED,
    MANUFACTURER,
    MODEL,
)


@dataclass(frozen=True, kw_only=True)
class RheemSensorDescription(SensorEntityDescription):
    """Describe a sensor and its source EcoNet object."""

    datapoint: str
    multiplier: float = 1.0


SENSORS: tuple[RheemSensorDescription, ...] = (
    RheemSensorDescription(
        key=DP_TEMP_IN,
        name="Inlet temperature",
        datapoint=DP_TEMP_IN,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    RheemSensorDescription(
        key=DP_TEMP_OUT,
        name="Outlet temperature",
        datapoint=DP_TEMP_OUT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    RheemSensorDescription(
        key=DP_FLOW_RATE,
        name="Flow rate",
        datapoint=DP_FLOW_RATE,
        multiplier=0.264172,
        native_unit_of_measurement="gal/min",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    RheemSensorDescription(
        key=DP_WATER_USED,
        name="Water used",
        datapoint=DP_WATER_USED,
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    RheemSensorDescription(
        key=DP_BTUS,
        name="Gas energy used",
        datapoint=DP_BTUS,
        native_unit_of_measurement="kBtu",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    RheemSensorDescription(
        key=DP_IGNITION_CYCLES,
        name="Ignition cycles",
        datapoint=DP_IGNITION_CYCLES,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up tankless sensors."""
    coordinator, _client = entry.runtime_data
    async_add_entities(
        RheemEcoNetSensor(coordinator, description, entry) for description in SENSORS
    )


class RheemEcoNetSensor(CoordinatorEntity, SensorEntity):
    """Coordinator-backed EcoNet datapoint sensor."""

    entity_description: RheemSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self, coordinator, description: RheemSensorDescription, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key.lower()}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "manufacturer": MANUFACTURER,
            "model": MODEL,
            "hw_version": CONTROLLER_REVISION,
            "name": "Rheem Prestige Tankless Water Heater",
        }

    @property
    def native_value(self) -> float | int | str | None:
        value = self.coordinator.data.get(self.entity_description.datapoint)
        if isinstance(value, (int, float)):
            return value * self.entity_description.multiplier
        return value
