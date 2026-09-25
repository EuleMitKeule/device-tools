"""Persistent storage for original (pre-Device-Tools) registry data."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

STORAGE_KEY = "device_tools.original_data"
STORAGE_VERSION = 1
SAVE_DELAY = 2.0

KIND_DEVICES = "devices"
KIND_ENTITIES = "entities"


class OriginalDataStore:
    """Persistent store holding the original value of every modified attribute.

    Only attributes currently controlled by a modification are stored. The data is
    keyed by kind (entities or devices), then by entity or device id, then by
    attribute name. Values are stored in their JSON representation.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the store."""
        self._store: Store[dict[str, dict[str, dict[str, Any]]]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY
        )
        self._data: dict[str, dict[str, dict[str, Any]]] = {
            KIND_ENTITIES: {},
            KIND_DEVICES: {},
        }

    async def async_load(self) -> None:
        """Load persisted data from disk."""
        if (data := await self._store.async_load()) is None:
            return
        for kind in (KIND_ENTITIES, KIND_DEVICES):
            self._data[kind] = {
                target_id: dict(values)
                for target_id, values in data.get(kind, {}).items()
                if values
            }

    @callback
    def _async_schedule_save(self) -> None:
        """Schedule a debounced save."""
        self._store.async_delay_save(lambda: self._data, SAVE_DELAY)

    def get(self, kind: str, target_id: str) -> dict[str, Any]:
        """Return the stored original values of an entity or device."""
        return dict(self._data[kind].get(target_id, {}))

    def target_ids(self, kind: str) -> set[str]:
        """Return the ids of all entities or devices with stored original values."""
        return set(self._data[kind])

    @callback
    def async_set(self, kind: str, target_id: str, key: str, value: Any) -> None:
        """Store the original value of an attribute."""
        values = self._data[kind].setdefault(target_id, {})
        if key in values and values[key] == value:
            return
        values[key] = value
        self._async_schedule_save()

    @callback
    def async_remove(self, kind: str, target_id: str, key: str | None = None) -> None:
        """Remove the original value of an attribute, or of all attributes."""
        if (values := self._data[kind].get(target_id)) is None:
            return
        if key is not None:
            if key not in values:
                return
            del values[key]
            if values:
                self._async_schedule_save()
                return
        del self._data[kind][target_id]
        self._async_schedule_save()

    @callback
    def async_rename(self, kind: str, old_target_id: str, new_target_id: str) -> None:
        """Move the original values of a renamed entity."""
        if (values := self._data[kind].pop(old_target_id, None)) is None:
            return
        self._data[kind][new_target_id] = values
        self._async_schedule_save()
