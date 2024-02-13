from typing import TypedDict

from .device_modification import DeviceModification


class DeviceToolsConfigEntryData(TypedDict):
    """Device Tools config entry."""

    device_modification: DeviceModification
