"""Device tools for Home Assistant."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .device_tools import DeviceTools

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Device Tools component."""

    device_tools = DeviceTools(hass, _LOGGER)
    hass.data[DOMAIN] = device_tools

    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up the from a config entry."""

    device_tools: DeviceTools = hass.data[DOMAIN]
    device_tools.async_get_entries()

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry update."""

    await hass.config_entries.async_reload(entry.entry_id)

    device_tools: DeviceTools = hass.data[DOMAIN]
    device_tools.async_get_entries()


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Handle config entry unload."""

    device_tools: DeviceTools = hass.data[DOMAIN]
    device_tools.async_get_entries()

    return True
