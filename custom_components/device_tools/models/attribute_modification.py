from homeassistant.helpers.device_registry import (
    DeviceEntry,
)

from custom_components.device_tools.const import ModificationType

from .device_modification import DeviceModification


class AttributeModification(DeviceModification):
    """Attribute modification data class."""

    manufacturer: str
    model: str
    sw_version: str
    hw_version: str
    serial_number: str
    via_device_id: str

    @classmethod
    def from_device(cls, name: str, device: DeviceEntry) -> "AttributeModification":
        """Create attribute modification from device."""

        return cls(
            {
                "device_id": device.id,
                "device_name": device.name,
                "modification_type": ModificationType.ATTRIBUTES,
                "modification_name": name,
                "manufacturer": device.manufacturer or "",
                "model": device.model or "",
                "sw_version": device.sw_version or "",
                "hw_version": device.hw_version or "",
                "serial_number": device.serial_number or "",
                "via_device_id": device.via_device_id or "",
            }
        )
