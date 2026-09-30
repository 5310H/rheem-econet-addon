"""Rheem EcoNet tankless integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    DP_ENABLE,
    DP_SETPOINT,
    DP_TEMP_IN,
    DP_TEMP_OUT,
    UPDATE_INTERVAL,
)
from .protocol import EcoNetProtocolError, EcoNetSerialClient

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
_LOGGER = logging.getLogger(__name__)
_PANEL_PATH = "rheem-water-heater"
_PANEL_JS_URL = "/rheem_econet/panel.js?v=0.2.2"
_STATIC_REGISTERED = "frontend_static_registered"
_PANEL_REGISTERED = "frontend_panel_registered"


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Register the dedicated Rheem sidebar page and its JavaScript module."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get(_STATIC_REGISTERED):
        panel_file = Path(__file__).parent / "www" / "panel.js"
        await hass.http.async_register_static_paths(
            [StaticPathConfig("/rheem_econet/panel.js", str(panel_file), False)]
        )
        domain_data[_STATIC_REGISTERED] = True

    if not domain_data.get(_PANEL_REGISTERED) and _PANEL_PATH not in hass.data.get(
        "frontend_panels", {}
    ):
        async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title="Rheem Water Heater",
            sidebar_icon="mdi:water-boiler",
            frontend_url_path=_PANEL_PATH,
            config={
                "_panel_custom": {
                    "name": "rheem-econet-panel",
                    "module_url": _PANEL_JS_URL,
                    "embed_iframe": False,
                    "trust_external": False,
                }
            },
            require_admin=True,
        )
    domain_data[_PANEL_REGISTERED] = True


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
    await _async_register_panel(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    other_entries = [
        item
        for item in hass.config_entries.async_entries(DOMAIN)
        if item.entry_id != entry.entry_id
    ]
    if unloaded and not other_entries:
        async_remove_panel(hass, _PANEL_PATH, warn_if_unknown=False)
        hass.data.get(DOMAIN, {}).pop(_PANEL_REGISTERED, None)
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload after options change."""
    await hass.config_entries.async_reload(entry.entry_id)
