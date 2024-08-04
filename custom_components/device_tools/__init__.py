"""Device tools for Home Assistant."""

from __future__ import annotations
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .device_tools import DeviceTools

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Device Tools component."""

    device_tools = DeviceTools(hass, _LOGGER)
    hass.data[DOMAIN] = device_tools

    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up the from a config entry."""

    device_tools: DeviceTools = hass.data[DOMAIN]
    device_tools.async_get_entries(add_entry=config_entry)
    await device_tools.async_update()

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry update."""

    await hass.config_entries.async_reload(entry.entry_id)

    device_tools: DeviceTools = hass.data[DOMAIN]
    device_tools.async_get_entries()
    await device_tools.async_update()


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Handle config entry unload."""

    device_tools: DeviceTools = hass.data[DOMAIN]
    device_tools.async_get_entries(remove_entry=config_entry)
    await device_tools.async_update()

    return True
