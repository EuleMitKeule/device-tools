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


class MergeModification(TypedDict):
    """Merge modification data class."""

    devices: set[str]


class DeviceModification(TypedDict):
    """Device modification data class."""

    modification_name: str
    device_id: str | None
    device_name: str
    attribute_modification: AttributeModification | None
    entity_modification: EntityModification | None
    merge_modification: MergeModification | None


class OriginalEntityConfig(TypedDict):
    """Entity original config data class."""

    device_id: str | None


class OriginalDeviceConfig(TypedDict):
    """Device original config data class."""

    manufacturer: str | None
    model: str | None
    sw_version: str | None
    hw_version: str | None
    serial_number: str | None
    via_device_id: str | None
    config_entries: set[str]
    config_entries_set_by_device_tools: set[str]


class DeviceToolsConfigEntryData(TypedDict):
    """Device Tools config entry."""

    device_modification: DeviceModification


class DeviceToolsData(TypedDict):
    """Device Tools data class."""

    original_entity_configs: dict[str, OriginalEntityConfig]
    original_device_configs: dict[str, OriginalDeviceConfig]
