"""Utility functions for Device Tools."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    CONF_ASSIGNED_ENTITIES,
    CONF_ENTITIES,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_IS_CUSTOM_ENTRY,
    CONF_MODIFICATION_ORIGINAL_DATA,
    CONF_MODIFICATION_TYPE,
    CONFIGURATION_URL_SCHEMES,
    DOMAIN,
    ModificationType,
)


def get_default_config_entry_title(
    modification_type: ModificationType,
    modification_entry_name: str,
) -> str:
    """Return the default title for a config entry."""
    return f"{modification_type.friendly_name}: {modification_entry_name}"


def name_for_device(device: dr.AnyDeviceEntry) -> str:
    """Return the name for a device."""
    return device.name_by_user or device.name or device.id


def name_for_entity(entity: er.RegistryEntry) -> str:
    """Return the name for an entity."""
    return entity.name or entity.original_name or entity.entity_id


def is_valid_configuration_url(value: str) -> bool:
    """Return whether a configuration url is accepted by the device registry."""
    try:
        url = urlparse(value)
    except ValueError:
        return False
    if url.scheme not in CONFIGURATION_URL_SCHEMES:
        return False
    return url.scheme == "homeassistant" or bool(url.netloc)


def modification_type(config_entry: ConfigEntry[Any]) -> ModificationType:
    """Return the modification type of a config entry."""
    return ModificationType(config_entry.data[CONF_MODIFICATION_TYPE])


def modification_entry_id(config_entry: ConfigEntry[Any]) -> str:
    """Return the id of the modified device or entity."""
    return str(config_entry.data[CONF_MODIFICATION_ENTRY_ID])


def modification_is_custom_entry(config_entry: ConfigEntry[Any]) -> bool:
    """Return whether the modified device was created by Device Tools."""
    return bool(config_entry.data.get(CONF_MODIFICATION_IS_CUSTOM_ENTRY, False))


def modification_data(config_entry: ConfigEntry[Any]) -> dict[str, Any]:
    """Return the modification data of a config entry."""
    return dict(config_entry.options.get(CONF_MODIFICATION_DATA, {}))


def merge_sources(config_entry: ConfigEntry[Any]) -> dict[str, list[str]]:
    """Return the merged device ids and the entity ids taken from each of them."""
    original_data: dict[str, Any] = config_entry.data.get(
        CONF_MODIFICATION_ORIGINAL_DATA, {}
    )
    return {
        device_id: list(device_data.get(CONF_ENTITIES, {}))
        for device_id, device_data in original_data.items()
    }


def assigned_entities(config_entry: ConfigEntry[Any]) -> list[str]:
    """Return the entity ids assigned to the device of a device modification."""
    return list(modification_data(config_entry).get(CONF_ASSIGNED_ENTITIES, []))


@callback
def async_get_device(hass: HomeAssistant, device_id: str) -> dr.AnyDeviceEntry | None:
    """Return a registered device, ignoring pre-2026.8 composite device ids."""
    return dr.async_get(hass).async_get(device_id, include_composite_devices=False)


@callback
def async_resolve_device_id(
    hass: HomeAssistant,
    device_id: str | None,
    owner_config_entry_id: str | None = None,
) -> str | None:
    """Return the id of the registered device a stored device id refers to.

    Home Assistant 2026.8 split devices that belonged to multiple config entries
    into one device per config entry, each with a new id. Device Tools used to add
    its own config entry to modified devices, so stored device ids may refer to
    such a split composite device. Returns None for unknown ids.
    """
    if device_id is None:
        return None
    if async_get_device(hass, device_id) is not None:
        return device_id

    device_registry = dr.async_get(hass)
    if not (
        splits := device_registry.async_get_devices_for_composite_device_id(device_id)
    ):
        return None

    def priority(split: dr.DeviceEntry) -> int:
        """Return how well a split device matches, lower is better."""
        if split.config_entry_id == owner_config_entry_id:
            return 0
        if (DOMAIN, split.config_entry_id) in split.identifiers:
            return 1
        config_entry = hass.config_entries.async_get_entry(split.config_entry_id)
        if config_entry is not None and config_entry.domain == DOMAIN:
            return 4
        if split.config_entry_id == split.composite_primary_config_entry:
            return 2
        return 3

    return min(splits, key=priority).id
