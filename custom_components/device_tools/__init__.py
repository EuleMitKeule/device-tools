"""Device tools for Home Assistant."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN
from .device_listener import DeviceListener
from .device_modification_registry import (
    DeviceModificationRegistry,
)
from .device_tools import DeviceTools
from .models import DeviceModification, DeviceToolsHistoryData


@dataclass(slots=True)
class DeviceToolsData:
    """Device Tools config entry."""

    device_tools: DeviceTools
    device_modification_registry: DeviceModificationRegistry
    device_tools_history_data: DeviceToolsHistoryData


_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


DATA_KEY: HassKey[DeviceToolsData] = HassKey(DOMAIN)


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Set up the Device Tools component."""
    device_modification_registry = DeviceModificationRegistry()
    device_tools_history_data = DeviceToolsHistoryData()
    device_listener = DeviceListener(hass)
    DeviceTools(
        hass,
        device_modification_registry,
        device_tools_history_data,
        device_listener,
    )

    hass.data[DATA_KEY] = DeviceToolsData(
        device_tools=DeviceTools,
        device_modification_registry=device_modification_registry,
        device_tools_history_data=device_tools_history_data,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up the from a config entry."""
    _LOGGER.debug("Setting up Device Tools config entry %s", config_entry.entry_id)

    device_modification_registry: DeviceModificationRegistry = hass.data[
        DATA_KEY
    ].device_modification_registry
    device_modification: DeviceModification = config_entry.data["device_modification"]

    await device_modification_registry.add_entry(
        config_entry.entry_id, device_modification
    )

    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))

    return True


async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.debug("Updating Device Tools config entry %s", config_entry.entry_id)

    device_modification_registry: DeviceModificationRegistry = hass.data[
        DATA_KEY
    ].device_modification_registry
    device_modification: DeviceModification = config_entry.data["device_modification"]

    await device_modification_registry.remove_entry(config_entry.entry_id)
    await device_modification_registry.add_entry(
        config_entry.entry_id, device_modification
    )


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Handle config entry unload."""
    _LOGGER.debug("Unloading Device Tools config entry %s", config_entry.entry_id)

    device_modification_registry: DeviceModificationRegistry = hass.data[
        DATA_KEY
    ].device_modification_registry

    await device_modification_registry.remove_entry(config_entry.entry_id)

    return True
