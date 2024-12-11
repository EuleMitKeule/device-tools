"""Models for device tools."""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, TypedDict

from custom_components.device_tools.const import IGNORED_ATTRIBUTES


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


@dataclass
class DeviceToolsHistoryData:
    """Device Tools data class."""

    device_attribute_history: defaultdict[str, dict[str, Any]] = field(
        default_factory=lambda: defaultdict(dict)
    )

    def update_attribute_history(
        self, device_id: str, attributes: dict[str, Any]
    ) -> None:
        """Save device attributes."""
        for attribute, value in attributes.items():
            if attribute in IGNORED_ATTRIBUTES:
                continue

            self.device_attribute_history[device_id][attribute] = value
