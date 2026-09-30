"""Rheem EcoNet tankless integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DP_ENABLE,
    DP_SETPOINT,
    DP_TEMP_IN,
    DP_TEMP_OUT,
    UPDATE_INTERVAL,
)
from .protocol import EcoNetProtocolError, EcoNetSerialClient

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration from config entries."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Rheem serial connection."""
    client = EcoNetSerialClient(
        port=entry.options.get("port", entry.data["port"]),
        source_address=entry.data["source_address"],
        destination_address=entry.data["destination_address"],
    )

    async def async_update_data() -> dict[str, float | int | str]:
        try:
            data = await hass.async_add_executor_job(client.poll)
            missing = {DP_TEMP_IN, DP_TEMP_OUT, DP_SETPOINT, DP_ENABLE} - data.keys()
            if missing:
                raise EcoNetProtocolError(
                    "Heater response omitted required datapoints: "
                    + ", ".join(sorted(missing))
                )
            return data
        except EcoNetProtocolError as err:
            raise UpdateFailed(str(err)) from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Rheem EcoNet Tankless",
        update_method=async_update_data,
        update_interval=timedelta(
            seconds=entry.options.get(
                "scan_interval", entry.data.get("scan_interval", UPDATE_INTERVAL)
            )
        ),
    )
    # Load the config entry and entities even before the heater or adapter is
    # connected. A failed refresh marks them unavailable; scheduled polling
    # will recover automatically once the serial device responds.
    coordinator.data = {}
    await coordinator.async_refresh()
    entry.runtime_data = (coordinator, client)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload after options change."""
    await hass.config_entries.async_reload(entry.entry_id)
