"""Class to handle a device modification."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr

from .device_listener import DeviceListener
from .models import DeviceData, PersistentModificationData
from .modification import Modification
from .storage import Storage


class DeviceModification(Modification[DeviceData, DeviceListener]):
    """Class to handle a device modification."""

    def __init__(
        self,
        hass: HomeAssistant,
        listener: DeviceListener,
        storage: Storage,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the modification."""
        super().__init__(
            hass=hass,
            listener=listener,
            storage=storage,
            config_entry=config_entry,
        )

        self._registry = dr.async_get(hass)

        device = self._registry.async_get(self._entry_id)
        if device is None:
            raise ValueError(f"Device with ID {self._entry_id} not found")

        self._storage.init_entry_data(
            self._entry_id, PersistentModificationData(original_data=device.dict_repr)
        )

        self._listener.register_callback(self._entry_id, self._on_entry_updated)

    async def apply(self) -> None:
        """Apply modification."""
        self._listener.unregister_callback(self._entry_id, self._on_entry_updated)
        self._registry.async_update_device(
            self._entry_id,
            **self._data,
        )
        self._listener.register_callback(self._entry_id, self._on_entry_updated)

    async def revert(self) -> None:
        """Revert modification."""
        self._listener.unregister_callback(self._entry_id, self._on_entry_updated)
        self._registry.async_update_device(
            self._entry_id,
            **self._relevant_original_data,
        )

    async def _on_entry_updated(
        self,
        device: dr.DeviceEntry,
        event: Event[dr.EventDeviceRegistryUpdatedData],
    ) -> None:
        """Handle entry updated by another integration."""
        if event.data["action"] != "update":
            return

        new_data = device.dict_repr
        current_data = self._storage.get_entry_data(self._entry_id)
        current_data.update(
            {key: new_data[key] for key in event.data["changes"] if key in new_data}
        )
        self._storage.set_entry_data(self._entry_id, current_data)

        await self.apply()
