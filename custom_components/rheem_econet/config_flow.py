"""Config flow for Rheem EcoNet tankless heaters."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DEFAULT_DESTINATION_ADDRESS,
    DEFAULT_SOURCE_ADDRESS,
    DOMAIN,
    UPDATE_INTERVAL,
)


class RheemEcoNetConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure the serial port and protocol addresses."""
        errors: dict[str, str] = {}
        if user_input is not None:
            port = user_input["port"].strip()
            if not port:
                errors["base"] = "invalid_port"
            try:
                source_address = _parse_address(user_input["source_address"])
                destination_address = _parse_address(user_input["destination_address"])
                if (
                    not 0 <= source_address <= 0xFFFFFF
                    or not 0 <= destination_address <= 0xFFFFFF
                ):
                    raise ValueError("EcoNet addresses must be 24-bit values")
                if source_address == destination_address:
                    raise ValueError("Source and destination addresses must differ")
            except ValueError:
                errors["base"] = "invalid_address"
            else:
                if errors:
                    return self.async_show_form(
                        step_id="user",
                        data_schema=_config_schema(),
                        errors=errors,
                    )
                user_input = {
                    **user_input,
                    "port": port,
                    "source_address": source_address,
                    "destination_address": destination_address,
                }
                await self.async_set_unique_id(f"{port}:{destination_address:06X}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Rheem Prestige Tankless",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user", data_schema=_config_schema(), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> RheemEcoNetOptionsFlow:
        """Create the options flow."""
        return RheemEcoNetOptionsFlow()


class RheemEcoNetOptionsFlow(config_entries.OptionsFlow):
    """Allow changing serial path and scan frequency after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Update the serial device path and polling interval."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("port", default=current["port"]): str,
                    vol.Required(
                        "scan_interval",
                        default=current.get("scan_interval", UPDATE_INTERVAL),
                    ): vol.All(int, vol.Range(min=5, max=60)),
                }
            ),
        )


def _parse_address(value: str) -> int:
    """Parse a decimal or hexadecimal EcoNet address."""
    return int(value, 0)


def _config_schema() -> vol.Schema:
    """Build the user configuration form, allowing an adapter path to be typed."""
    return vol.Schema(
        {
            vol.Required("port", default="/dev/serial/by-id/"): str,
            vol.Required(
                "source_address", default=f"0x{DEFAULT_SOURCE_ADDRESS:03X}"
            ): str,
            vol.Required(
                "destination_address",
                default=f"0x{DEFAULT_DESTINATION_ADDRESS:04X}",
            ): str,
            vol.Required("scan_interval", default=UPDATE_INTERVAL): vol.All(
                int, vol.Range(min=5, max=60)
            ),
        }
    )
