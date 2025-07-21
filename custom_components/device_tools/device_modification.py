"""Class to handle a device modification."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr

from .device_listener import DeviceListener
from .modification import Modification


class DeviceModification(Modification):
    """Class to handle a device modification."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        listener: DeviceListener,
    ) -> None:
        """Initialize the modification."""
        super().__init__(
            hass=hass,
            config_entry=config_entry,
        )

        self._registry = dr.async_get(hass)
        self._listener: DeviceListener = listener

        self._listener.register_callback(
            self.modification_entry_id,
            self._on_entry_updated,
        )

    async def apply(self) -> None:
        """Apply modification."""
        self._listener.unregister_callback(
            self.modification_entry_id,
            self._on_entry_updated,
        )
        self._registry.async_update_device(
            self.modification_entry_id,
            add_config_entry_id=self._config_entry.entry_id,
            **self.modification_data,
        )
        self._listener.register_callback(
            self.modification_entry_id,
            self._on_entry_updated,
        )

    async def revert(self) -> None:
        """Revert modification."""
        self._listener.unregister_callback(
            self.modification_entry_id,
            self._on_entry_updated,
        )
        if (device := self._registry.async_get(self.modification_entry_id)) and len(
            device.config_entries
        ) > 1:
            self._registry.async_update_device(
                self.modification_entry_id,
                remove_config_entry_id=self._config_entry.entry_id,
                **self._overwritten_original_data,
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
        modification_original_data = dict(self.modification_original_data)
        modification_original_data.update(
            {key: new_data[key] for key in event.data["changes"] if key in new_data}
        )
        self._update_modification_original_data(modification_original_data)

        await self.apply()
