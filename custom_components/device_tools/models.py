"""Models for device tools."""

from typing import TypedDict


class AttributeModification(TypedDict):
    """Attribute modification data class."""

    manufacturer: str
    model: str
    sw_version: str
    hw_version: str
    serial_number: str
    via_device_id: str


class EntityModification(TypedDict):
    """Entity modification data class."""

    entities: set[str]


class DeviceModification(TypedDict):
    """Device modification data class."""

    modification_name: str
    device_id: str
    device_name: str
    attribute_modification: AttributeModification | None
    entity_modification: EntityModification | None


class DeviceToolsConfigEntryData(TypedDict):
    """Device Tools config entry."""

    device_modification: DeviceModification
