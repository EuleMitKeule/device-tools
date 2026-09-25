"""Device tools for Home Assistant."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import CONF_MODIFICATION_ENTRY_ID, CONF_MODIFICATION_ENTRY_NAME, DOMAIN
from .data import DATA_KEY, DeviceToolsData
from .engine import ModificationEngine, async_resolve_references
from .migration import async_migrate_entry
from .original_data_store import OriginalDataStore
from .utils import (
    modification_entry_id,
    modification_is_custom_entry,
    modification_type,
    name_for_device,
)

__all__ = ["async_migrate_entry"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Set up the device tools component."""
    store = OriginalDataStore(hass)
    engine = ModificationEngine(hass, store)
    hass.data[DATA_KEY] = DeviceToolsData(engine=engine, store=store)

    await engine.async_start()
    return True


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry[Any]
) -> bool:
    """Set up a modification."""
    _LOGGER.debug(
        "Setting up modification %s with data %s and options %s",
        config_entry.title,
        config_entry.data,
        config_entry.options,
    )

    if (updates := async_resolve_references(hass, config_entry)) is not None:
        hass.config_entries.async_update_entry(config_entry, **updates)

    if modification_is_custom_entry(config_entry):
        _async_setup_custom_device(hass, config_entry)

    _async_remove_stray_devices(hass, config_entry)

    hass.data[DATA_KEY].engine.async_on_entry_loaded(config_entry)
    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))
    return True


async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry[Any]) -> None:
    """Handle a modification being changed."""
    _LOGGER.debug("Updating modification %s", config_entry.title)
    hass.data[DATA_KEY].engine.async_on_entry_updated(config_entry)


async def async_unload_entry(
    hass: HomeAssistant, config_entry: ConfigEntry[Any]
) -> bool:
    """Unload a modification and restore the original state."""
    _LOGGER.debug("Unloading modification %s", config_entry.title)
    hass.data[DATA_KEY].engine.async_on_entry_unloaded(config_entry)
    return True


async def async_remove_entry(
    hass: HomeAssistant, config_entry: ConfigEntry[Any]
) -> None:
    """Handle a modification being removed."""
    _LOGGER.debug("Removing modification %s", config_entry.title)
    hass.data[DATA_KEY].engine.async_on_entry_removed(config_entry)


@callback
def _async_setup_custom_device(
    hass: HomeAssistant, config_entry: ConfigEntry[Any]
) -> None:
    """Create or update the device a modification created."""
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, config_entry.entry_id)},
        name=config_entry.data[CONF_MODIFICATION_ENTRY_NAME],
    )
    if device.id == modification_entry_id(config_entry):
        return
    hass.config_entries.async_update_entry(
        config_entry,
        data={**config_entry.data, CONF_MODIFICATION_ENTRY_ID: device.id},
        unique_id=f"{modification_type(config_entry)}_{device.id}",
    )


@callback
def _async_remove_stray_devices(
    hass: HomeAssistant, config_entry: ConfigEntry[Any]
) -> None:
    """Remove devices owned by a modification which it did not create.

    Previous versions added their config entry to modified devices. Home Assistant
    2026.8 split those into one device per config entry, which leaves empty
    duplicates of the modified devices behind.
    """
    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(
        device_registry, config_entry.entry_id
    ):
        if modification_is_custom_entry(config_entry) and (
            device.id == modification_entry_id(config_entry)
        ):
            continue
        _LOGGER.info(
            "Removing leftover duplicate device %s (%s) of modification %s",
            name_for_device(device),
            device.id,
            config_entry.title,
        )
        device_registry.async_remove_device(device.id)
