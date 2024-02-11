"""Device tools for Home Assistant."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.device_registry import async_get as async_get_device_registry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up the from a config entry."""

    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))

    dr = async_get_device_registry(hass)
    google_home_device = dr.async_get_device(
        identifiers={("google_home", "78ae633e-b259-4804-9b43-79b2f086fe27")}
    )
    chromecast_device = dr.async_get_device(
        identifiers={("cast", "3e7573d80740e683a28bdfa7aa4fcab1")}
    )

    if google_home_device is None or chromecast_device is None:
        _LOGGER.error("Devices not found")

        raise ConfigEntryNotReady()

    dr.async_update_device(
        google_home_device.id,
        merge_connections={(CONNECTION_NETWORK_MAC, "f0:ef:86:75:e1:bf")},
    )
    dr.async_update_device(
        chromecast_device.id,
        merge_connections={(CONNECTION_NETWORK_MAC, "f0:ef:86:75:e1:bf")},
    )

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry update."""

    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Handle config entry unload."""

    return True
