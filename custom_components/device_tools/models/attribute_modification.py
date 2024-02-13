from .device_modification import DeviceModification


class AttributeModification(DeviceModification):
    """Attribute modification data class."""

    manufacturer: str | None
    model: str | None
    sw_version: str | None
    hw_version: str | None
    serial_number: str | None
    via_device: str | None
    connections: list[tuple[str, str]] | None
