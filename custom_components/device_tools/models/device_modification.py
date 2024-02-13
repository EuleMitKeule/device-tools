from typing import TypedDict

from ..const import ModificationType


class DeviceModification(TypedDict):
    """Device modification data class."""

    modification_name: str
    modification_type: ModificationType
    device_id: str
    device_name: str
