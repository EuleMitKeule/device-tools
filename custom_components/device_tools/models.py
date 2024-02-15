"""Models for device tools."""

from typing import TypedDict


class AttributeModification(TypedDict):
    """Attribute modification data class."""

    manufacturer: str | None
    model: str | None
    sw_version: str | None
    hw_version: str | None
    serial_number: str | None
    via_device_id: str | None


class EntityModification(TypedDict):
    """Entity modification data class."""

    entities: set[str]


class DeviceModification(TypedDict):
    """Device modification data class."""

    modification_name: str
    device_id: str | None
    device_name: str
    attribute_modification: AttributeModification | None
    entity_modification: EntityModification | None


class DeviceToolsConfigEntryData(TypedDict):
    """Device Tools config entry."""

    device_modification: DeviceModification
