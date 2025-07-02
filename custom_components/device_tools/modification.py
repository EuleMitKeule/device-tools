"""Class to handle a modification."""

from abc import ABC, abstractmethod
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_MODIFICATION_DATA, CONF_MODIFICATION_ENTRY_ID
from .device_listener import DeviceListener
from .entity_listener import EntityListener
from .models import DeviceData, EntityData
from .storage import Storage


class Modification[
    TData: (DeviceData | EntityData),
    TListener: (DeviceListener | EntityListener),
](ABC):
    """Class to handle a modification."""

    def __init__(
        self,
        hass: HomeAssistant,
        listener: TListener,
        storage: Storage,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the modification."""
        self._hass = hass
        self._listener: TListener = listener
        self._storage = storage

        self._entry_id: str = config_entry.data[CONF_MODIFICATION_ENTRY_ID]
        self._data: TData = config_entry.options[CONF_MODIFICATION_DATA]

    @abstractmethod
    async def apply(self) -> None:
        """Apply modification."""

    @abstractmethod
    async def revert(self) -> None:
        """Revert modification."""

    @property
    def _relevant_original_data(self) -> dict[str, Any]:
        """Return relevant original data."""
        return {
            key: value
            for key, value in self._storage.get_entry_data(self._entry_id).items()
            if key in self._data
        }
