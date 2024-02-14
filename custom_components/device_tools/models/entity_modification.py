from homeassistant.helpers.device_registry import DeviceEntry

from custom_components.device_tools.const import ModificationType

from .device_modification import DeviceModification


class EntityModification(DeviceModification):
    """Entity modification data class."""

    entities: set[str] | None

    @classmethod
    def from_device(
        cls, name: str, device: DeviceEntry, entities: set[str] | None = None
    ) -> "EntityModification":
        """Create entity modification from device."""

        return cls(
            {
                "device_id": device.id,
                "device_name": device.name,
                "modification_type": ModificationType.ENTITIES,
                "modification_name": name,
                "entities": entities or set(),
            }
        )
