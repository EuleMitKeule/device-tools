"""Utility functions for Device Tools."""

from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import ModificationType


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


def get_default_config_entry_title(
    modification_type: ModificationType,
    modification_entry_name: str,
) -> str:
    """Return the default title for a config entry."""
    return f"{modification_type.friendly_name}: {modification_entry_name}"


def name_for_device(device: dr.DeviceEntry) -> str:
    """Return the name for a device."""
    return device.name_by_user or device.name or device.id


def name_for_entity(entity: er.RegistryEntry) -> str:
    """Return the name for an entity."""
    return entity.name or entity.original_name or entity.entity_id
