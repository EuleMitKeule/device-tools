"""Class to handle a device modification."""

from collections.abc import Callable
import logging
from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr

from .device_listener import DeviceListener
from .entry_modification import EntryModification

_LOGGER = logging.getLogger(__name__)


class DeviceModification(EntryModification):
    """Class to handle a device modification."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry[Any],
        listener: DeviceListener,
        modification_entry_id: str | None = None,
        modification_entry_data: MappingProxyType[str, Any] | None = None,
        func_get_modification_original_data: Callable[
            [ConfigEntry[Any]], MappingProxyType[str, Any]
        ]
        | None = None,
        func_update_modification_original_data: Callable[
            [ConfigEntry[Any], dict[str, Any]], None
        ]
        | None = None,
    ) -> None:
        """Initialize the modification."""
        super().__init__(
            hass=hass,
            config_entry=config_entry,
            modification_entry_id=modification_entry_id,
            modification_entry_data=modification_entry_data,
            func_get_modification_original_data=func_get_modification_original_data,
            func_update_modification_original_data=func_update_modification_original_data,
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
        _LOGGER.debug(
            "Applying device modification %s with data: %s",
            self.modification_entry_id,
            self.modification_data,
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
