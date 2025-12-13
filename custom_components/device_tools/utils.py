"""Utility functions for Device Tools."""

from homeassistant.helpers import device_registry as dr, entity_registry as er


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
