"""Module containing the device modification registry for the device-tools integration."""

from collections.abc import Awaitable, Callable

from custom_components.device_tools.models import (
    DeviceModification,
    OriginalDeviceConfig,
    OriginalEntityConfig,
)


class DeviceModificationRegistry:
    """Device modification registry.

    Keeps track of device modifications and provides methods to add, remove and get device modifications.
    Stores original device configurations and original entity configurations.
    """

    def __init__(self) -> None:
        """Initialize the device modification registry."""
        self._device_modifications: dict[str, DeviceModification] = {}
        self._original_entity_configs: dict[str, OriginalEntityConfig] = {}
        self._original_device_configs: dict[str, OriginalDeviceConfig] = {}
        self._modification_added_callbacks: list[
            Callable[[DeviceModification], Awaitable[None]]
        ] = []
        self._modification_removed_callbacks: list[
            Callable[[DeviceModification], Awaitable[None]]
        ] = []

    async def add_entry(
        self, entry_id: str, device_modification: DeviceModification
    ) -> None:
        """Register a device modification."""
        if entry_id in self._device_modifications:
            raise ValueError(
                f"Device modification with entry_id {entry_id} already exists"
            )

        if device_modification["device_id"] in [
            device_modification["device_id"]
            for device_modification in self._device_modifications.values()
        ]:
            raise ValueError(
                f"Device modification for device_id {device_modification['device_id']} already exists"
            )

        self._device_modifications[entry_id] = device_modification

        for callback in self._modification_added_callbacks:
            await callback(device_modification)

    async def remove_entry(self, entry_id: str) -> None:
        """Unregister a device modification."""
        if entry_id not in self._device_modifications:
            raise ValueError(
                f"Device modification with entry_id {entry_id} does not exist"
            )

        device_modification = self._device_modifications.pop(entry_id)

        for callback in self._modification_removed_callbacks:
            await callback(device_modification)

    def register_callbacks(
        self,
        modification_added_callback: Callable[[DeviceModification], Awaitable[None]],
        modification_removed_callback: Callable[[DeviceModification], Awaitable[None]],
    ) -> None:
        """Register callbacks for when a device modification is added or removed."""
        if modification_added_callback not in self._modification_added_callbacks:
            self._modification_added_callbacks.append(modification_added_callback)
        if modification_removed_callback not in self._modification_removed_callbacks:
            self._modification_removed_callbacks.append(modification_removed_callback)

    def get_modification_for_device(self, device_id: str) -> DeviceModification | None:
        """Get all modifications for a device."""
        return next(
            (
                device_modification
                for device_modification in self._device_modifications.values()
                if device_modification["device_id"] == device_id
            ),
            None,
        )
