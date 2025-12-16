"""Utility functions for Device Tools."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    CONF_DEVICE_ID,
    CONF_ENTITIES,
    CONF_MODIFICATION_ORIGINAL_DATA,
    CONF_MODIFICATION_TYPE,
    DOMAIN,
    ModificationType,
)


def string_to_registry_entry_disabler(value: str) -> er.RegistryEntryDisabler | None:
    """Convert a string to a RegistryEntryDisabler or None."""
    try:
        return er.RegistryEntryDisabler(value)
    except ValueError:
        return None


def string_to_device_entry_disabler(value: str) -> dr.DeviceEntryDisabler | None:
    """Convert a string to a DeviceEntryDisabler or None."""
    try:
        return dr.DeviceEntryDisabler(value)
    except ValueError:
        return None


def is_entity_in_merge_modification(
    hass: HomeAssistant,
    entity_id: str,
) -> bool:
    """Check if an entity is already part of a merge modification."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get(CONF_MODIFICATION_TYPE) == ModificationType.MERGE:
            original_data = entry.data.get(CONF_MODIFICATION_ORIGINAL_DATA, {})
            for device_data in original_data.values():
                entities = device_data.get(CONF_ENTITIES, {})
                if entity_id in entities:
                    return True
    return False


def check_merge_conflicts(
    hass: HomeAssistant,
    merge_device_ids: list[str],
) -> bool:
    """Check if any entities on devices being merged have entity modifications."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get(CONF_MODIFICATION_TYPE) == ModificationType.ENTITY:
            original_data = entry.data.get(CONF_MODIFICATION_ORIGINAL_DATA, {})
            original_device_id = original_data.get(CONF_DEVICE_ID)

            if original_device_id in merge_device_ids:
                return True
    return False


def get_default_config_entry_title(
    modification_type: ModificationType,
    modification_entry_name: str,
) -> str:
    """Get the default title for a config entry title."""
    return f"{modification_type.friendly_name}: {modification_entry_name}"


def name_for_device(device: dr.DeviceEntry) -> str:
    """Return the name for a device."""
    return device.name_by_user or device.name or device.id


def name_for_entity(entity: er.RegistryEntry) -> str:
    """Return the name for an entity."""
    return entity.name or entity.original_name or entity.entity_id
