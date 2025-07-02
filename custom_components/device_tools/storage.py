"""Storage helper for device tools integration."""

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .models import PersistentModificationData

STORAGE_VERSION = 1
STORAGE_KEY = "device_tools_data"
_LOGGER = logging.getLogger(__name__)


class Storage:
    """Class to manage storage of persistent data."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize storage."""
        self._hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, PersistentModificationData] = {}

    async def async_load(self) -> None:
        """Load data."""
        self._data = await self._store.async_load() or {}

    async def async_save(self) -> None:
        """Save data."""
        await self._store.async_save(self._data)

    def has_entry_data(self, entry_id: str) -> bool:
        """Check if data exists for a specific config entry."""
        return entry_id in self._data

    def get_entry_data(self, entry_id: str) -> PersistentModificationData:
        """Get data for a specific config entry."""
        return self._data.get(entry_id, PersistentModificationData(original_data={}))

    def init_entry_data(self, entry_id: str, data: PersistentModificationData) -> None:
        """Initialize data for a specific config entry."""
        if self.has_entry_data(entry_id):
            return
        self.set_entry_data(entry_id, data)

    def set_entry_data(self, entry_id: str, data: PersistentModificationData) -> None:
        """Set data for a specific config entry."""
        _LOGGER.debug("Setting data for entry %s: %s", entry_id, data)
        self._data[entry_id] = data
        self._hass.loop.create_task(self.async_save())

    def remove_entry_data(self, entry_id: str) -> None:
        """Remove data for a specific config entry."""
        self._data.pop(entry_id, None)
        self._hass.loop.create_task(self.async_save())
