"""Models for device tools."""

from typing import TypedDict


class DeviceData(TypedDict):
    """Device data class."""

    manufacturer: str | None
    model: str | None
    sw_version: str | None
    hw_version: str | None
    serial_number: str | None
    via_device_id: str | None


class EntityData(TypedDict):
    """Entity data class."""

    device_id: str | None


class PersistentModificationData(TypedDict):
    """Data for a config entry that is persisted between reboots.

    When this is changed, we need to increment STORAGE_VERSION.
    """

    original_data: dict[str, str]
