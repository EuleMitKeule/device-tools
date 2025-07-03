"""Class to handle a modification."""

from abc import ABC, abstractmethod
from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_ORIGINAL_DATA,
    CONF_MODIFICATION_TYPE,
    MODIFIABLE_ATTRIBUTES,
    ModificationType,
)
from .device_listener import DeviceListener
from .entity_listener import EntityListener


class Modification[TListener: (DeviceListener | EntityListener)](ABC):
    """Class to handle a modification."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        listener: TListener,
    ) -> None:
        """Initialize the modification."""
        self._hass = hass
        self._config_entry: ConfigEntry = config_entry
        self._listener: TListener = listener

    @abstractmethod
    async def apply(self) -> None:
        """Apply modification."""

    @abstractmethod
    async def revert(self) -> None:
        """Revert modification."""

    @property
    def modification_entry_id(self) -> str:
        """Return the modification entry ID."""
        return self._config_entry.data[CONF_MODIFICATION_ENTRY_ID]

    @property
    def modification_type(self) -> ModificationType:
        """Return the modification type."""
        return self._config_entry.data.get(CONF_MODIFICATION_TYPE)

    @property
    def modification_original_data(self) -> MappingProxyType[str, Any]:
        """Return the original data before modification."""
        return MappingProxyType(
            self._config_entry.data.get(CONF_MODIFICATION_ORIGINAL_DATA)
        )

    @property
    def modification_data(self) -> MappingProxyType[str, Any]:
        """Return the modification data."""
        return MappingProxyType(self._config_entry.options.get(CONF_MODIFICATION_DATA))

    @property
    def _overwritten_original_data(self) -> MappingProxyType[str, Any]:
        """Return relevant original data."""
        return MappingProxyType(
            {
                key: value
                for key, value in self.modification_original_data.items()
                if key in self.modification_data
            }
        )

    def _update_modification_original_data(self, data: dict[str, Any]) -> None:
        """Update the original data in the config entry."""
        self._hass.config_entries.async_update_entry(
            self._config_entry,
            data={
                **self._config_entry.data,
                CONF_MODIFICATION_ORIGINAL_DATA: {
                    k: v
                    for k, v in data.items()
                    if k in MODIFIABLE_ATTRIBUTES[self.modification_type]
                },
            },
        )
