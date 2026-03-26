"""Persistent storage for original (pre-Device-Tools) registry data."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "device_tools.original_data"
STORAGE_VERSION = 1


class OriginalDataStore:
    """Persistent store that holds the true pre-Device-Tools state for every tracked entity and device."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the store."""
        self._hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._entities: dict[str, dict[str, Any]] = {}
        self._devices: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        """Load persisted data from disk."""
        data = await self._store.async_load()
        if data is not None:
            self._entities = data.get("entities", {})
            self._devices = data.get("devices", {})

    async def async_save(self) -> None:
        """Persist current state to disk."""
        await self._store.async_save(
            {
                "entities": self._entities,
                "devices": self._devices,
            }
        )

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        """Return stored original data for an entity. None if not yet tracked."""
        return self._entities.get(entity_id)

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """Return stored original data for a device. None if not yet tracked."""
        return self._devices.get(device_id)

    async def async_set_entity(self, entity_id: str, data: dict[str, Any]) -> None:
        """Store original entity data. Only call once — never overwrite existing entry."""
        if entity_id in self._entities:
            return
        self._entities[entity_id] = data
        await self.async_save()

    async def async_set_device(self, device_id: str, data: dict[str, Any]) -> None:
        """Store original device data. Only call once — never overwrite existing entry."""
        if device_id in self._devices:
            return
        self._devices[device_id] = data
        await self.async_save()

    async def async_update_entity(self, entity_id: str, changes: dict[str, Any]) -> None:
        """Merge changes into existing original entity data. Persists."""
        if entity_id not in self._entities:
            return
        self._entities[entity_id].update(changes)
        await self.async_save()

    async def async_update_device(self, device_id: str, changes: dict[str, Any]) -> None:
        """Merge changes into existing original device data. Persists."""
        if device_id not in self._devices:
            return
        self._devices[device_id].update(changes)
        await self.async_save()

    async def async_remove_entity(self, entity_id: str) -> None:
        """Delete entity entry and persist."""
        if entity_id in self._entities:
            del self._entities[entity_id]
            await self.async_save()

    async def async_remove_device(self, device_id: str) -> None:
        """Delete device entry and persist."""
        if device_id in self._devices:
            del self._devices[device_id]
            await self.async_save()
