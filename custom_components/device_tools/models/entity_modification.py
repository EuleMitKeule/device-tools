from .device_modification import DeviceModification


class EntityModification(DeviceModification):
    """Entity modification data class."""

    entities: set[str] | None
