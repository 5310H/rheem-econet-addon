"""Climate control representing the tankless water heater."""

from __future__ import annotations

from typing import Any, ClassVar

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONTROLLER_REVISION,
    DOMAIN,
    DP_ENABLE,
    DP_SETPOINT,
    DP_TEMP_OUT,
    MANUFACTURER,
    MAX_TEMPERATURE,
    MIN_TEMPERATURE,
    MODEL,
)
from .protocol import EcoNetSerialClient


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create the water-heater climate entity."""
    coordinator, client = entry.runtime_data
    async_add_entities([RheemTanklessClimate(coordinator, client, entry)])


class RheemTanklessClimate(CoordinatorEntity, ClimateEntity):
    """Expose enable and water temperature setpoint."""

    _attr_has_entity_name = True
    _attr_name = "Water heater"
    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_min_temp = MIN_TEMPERATURE
    _attr_max_temp = MAX_TEMPERATURE
    _attr_target_temperature_step = 1
    _attr_hvac_modes: ClassVar[list[HVACMode]] = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    def __init__(
        self, coordinator, client: EcoNetSerialClient, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_tankless"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "manufacturer": MANUFACTURER,
            "model": MODEL,
            "hw_version": CONTROLLER_REVISION,
            "name": "Rheem Prestige Tankless Water Heater",
        }

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Expose the setpoint control supported by the tankless profile."""
        return ClimateEntityFeature.TARGET_TEMPERATURE

    @property
    def current_temperature(self) -> float | None:
        return self.coordinator.data.get(DP_TEMP_OUT)

    @property
    def target_temperature(self) -> float | None:
        return self.coordinator.data.get(DP_SETPOINT)

    @property
    def hvac_mode(self) -> HVACMode:
        return (
            HVACMode.HEAT if self.coordinator.data.get(DP_ENABLE) == 1 else HVACMode.OFF
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get("temperature")
        if temperature is None:
            return
        if not MIN_TEMPERATURE <= temperature <= MAX_TEMPERATURE:
            raise ValueError(
                f"Temperature must be {MIN_TEMPERATURE}–{MAX_TEMPERATURE} °F"
            )
        if DP_SETPOINT not in self.coordinator.data:
            raise ValueError(
                "The heater has not reported its setpoint; refusing to write"
            )
        await self.hass.async_add_executor_job(
            self._client.write_float, DP_SETPOINT, float(temperature)
        )
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode not in self._attr_hvac_modes:
            raise ValueError(f"Unsupported mode: {hvac_mode}")
        if DP_ENABLE not in self.coordinator.data:
            raise ValueError(
                "The heater has not reported its enable state; refusing to write"
            )
        # WHTRENAB is an enum datapoint, written as an integer enum value.
        await self.hass.async_add_executor_job(
            self._client.write_enum, DP_ENABLE, 1 if hvac_mode == HVACMode.HEAT else 0
        )
        await self.coordinator.async_request_refresh()

    @property
    def available(self) -> bool:
        return super().available
