"""ModificationEngine — single orchestrator for all Device Tools modifications."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    CONF_ASSIGNED_ENTITIES,
    CONF_ENTITIES,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_ORIGINAL_DATA,
    CONF_MODIFICATION_TYPE,
    MODIFIABLE_ATTRIBUTES,
    ModificationType,
)
from .entry_handler import DeviceHandler, EntityHandler
from .original_data_store import OriginalDataStore

_LOGGER = logging.getLogger(__name__)

_PRIORITY = {
    ModificationType.MERGE: 0,
    ModificationType.DEVICE: 1,
    ModificationType.ENTITY: 2,
}


class ModificationEngine:
    """Single orchestrator that holds all handler instances and reacts to config entry lifecycle."""

    def __init__(self, hass: HomeAssistant, store: OriginalDataStore) -> None:
        """Initialize the engine."""
        self._hass = hass
        self._store = store

        # Tracked config entries keyed by entry_id
        self._tracked_entries: dict[str, ConfigEntry[Any]] = {}

        # Handler instances keyed by entity_id / device_id
        self._entity_handlers: dict[str, EntityHandler] = {}
        self._device_handlers: dict[str, DeviceHandler] = {}

    async def async_start(self) -> None:
        """Load store. For each existing config entry: call async_on_entry_loaded."""
        await self._store.async_load()

    async def async_stop(self) -> None:
        """Revert all handlers, stop all listeners, clear state."""
        for handler in list(self._entity_handlers.values()):
            try:
                await handler.async_revert()
            except Exception:
                _LOGGER.exception("Error reverting entity handler %s", handler.entry_id)
            await handler.async_stop_listening()

        for handler in list(self._device_handlers.values()):
            try:
                await handler.async_revert()
            except Exception:
                _LOGGER.exception("Error reverting device handler %s", handler.entry_id)
            await handler.async_stop_listening()

        self._entity_handlers.clear()
        self._device_handlers.clear()
        self._tracked_entries.clear()

    async def async_on_entry_loaded(self, config_entry: ConfigEntry[Any]) -> None:
        """Handle a config entry being set up.

        1. Determine affected entity_ids and device_ids
        2. For each: if handler doesn't exist yet, create it
        3. For each: if original_data not in store, read current registry state and store it
        4. For each: call handler.async_apply(all entries for this entity/device)
        5. Start listening if not already
        """
        self._tracked_entries[config_entry.entry_id] = config_entry

        affected_entity_ids = self._get_affected_entity_ids(config_entry)
        affected_device_ids = self._get_affected_device_ids(config_entry)

        entity_registry = er.async_get(self._hass)
        device_registry = dr.async_get(self._hass)

        # Ensure entity handlers and original data
        for entity_id in affected_entity_ids:
            if entity_id not in self._entity_handlers:
                self._entity_handlers[entity_id] = EntityHandler(
                    self._hass,
                    entity_id,
                    self._store,
                    get_active_entries=lambda eid=entity_id: self.get_entries_for_entity(eid),
                )

            if self._store.get_entity(entity_id) is None:
                entity = entity_registry.async_get(entity_id)
                if entity is not None:
                    original = {
                        k: v
                        for k, v in entity.extended_dict.items()
                        if k in MODIFIABLE_ATTRIBUTES[ModificationType.ENTITY]
                        or k == "device_id"
                    }
                    await self._store.async_set_entity(entity_id, original)

        # Ensure device handlers and original data
        for device_id in affected_device_ids:
            if device_id not in self._device_handlers:
                self._device_handlers[device_id] = DeviceHandler(
                    self._hass,
                    device_id,
                    self._store,
                    get_active_entries=lambda did=device_id: self.get_entries_for_device(did),
                )

            if self._store.get_device(device_id) is None:
                device = device_registry.async_get(device_id)
                if device is not None:
                    original = {
                        k: v
                        for k, v in device.dict_repr.items()
                        if k in MODIFIABLE_ATTRIBUTES[ModificationType.DEVICE]
                    }
                    await self._store.async_set_device(device_id, original)

        # Apply all relevant entries and start listening
        for entity_id in affected_entity_ids:
            handler = self._entity_handlers[entity_id]
            entries = self.get_entries_for_entity(entity_id)
            await handler.async_apply(entries)
            await handler.async_start_listening()

        for device_id in affected_device_ids:
            handler = self._device_handlers[device_id]
            entries = self.get_entries_for_device(device_id)
            await handler.async_apply(entries)
            await handler.async_start_listening()

    async def async_on_entry_unloaded(self, config_entry: ConfigEntry[Any]) -> None:
        """Handle config entry unload.

        1. For affected handlers: revert and stop listening
        2. Remove config entry from engine's tracking
        3. For each affected entity/device: if no more config entries reference it,
           remove handler and remove original_data from store
        """
        affected_entity_ids = self._get_affected_entity_ids(config_entry)
        affected_device_ids = self._get_affected_device_ids(config_entry)

        # Revert affected handlers
        for entity_id in affected_entity_ids:
            handler = self._entity_handlers.get(entity_id)
            if handler:
                await handler.async_revert()
                await handler.async_stop_listening()

        for device_id in affected_device_ids:
            handler = self._device_handlers.get(device_id)
            if handler:
                await handler.async_revert()
                await handler.async_stop_listening()

        # Remove from tracking
        self._tracked_entries.pop(config_entry.entry_id, None)

        # Clean up handlers that are no longer needed
        for entity_id in affected_entity_ids:
            remaining = self.get_entries_for_entity(entity_id)
            if not remaining:
                self._entity_handlers.pop(entity_id, None)
                await self._store.async_remove_entity(entity_id)
            else:
                # Re-apply remaining entries
                handler = self._entity_handlers.get(entity_id)
                if handler:
                    await handler.async_apply(remaining)
                    await handler.async_start_listening()

        for device_id in affected_device_ids:
            remaining = self.get_entries_for_device(device_id)
            if not remaining:
                self._device_handlers.pop(device_id, None)
                await self._store.async_remove_device(device_id)
            else:
                handler = self._device_handlers.get(device_id)
                if handler:
                    await handler.async_apply(remaining)
                    await handler.async_start_listening()

    async def async_on_entry_updated(self, config_entry: ConfigEntry[Any]) -> None:
        """Handle options/data change for a config entry.

        1. Revert all affected handlers
        2. Update engine's tracking
        3. Re-apply all affected handlers
        """
        # Collect old affected ids before updating tracking
        old_entry = self._tracked_entries.get(config_entry.entry_id)
        old_entity_ids: set[str] = set()
        old_device_ids: set[str] = set()
        if old_entry is not None:
            old_entity_ids = set(self._get_affected_entity_ids(old_entry))
            old_device_ids = set(self._get_affected_device_ids(old_entry))

        new_entity_ids = set(self._get_affected_entity_ids(config_entry))
        new_device_ids = set(self._get_affected_device_ids(config_entry))

        all_entity_ids = old_entity_ids | new_entity_ids
        all_device_ids = old_device_ids | new_device_ids

        # Revert affected handlers
        for entity_id in all_entity_ids:
            handler = self._entity_handlers.get(entity_id)
            if handler:
                await handler.async_revert()
                await handler.async_stop_listening()

        for device_id in all_device_ids:
            handler = self._device_handlers.get(device_id)
            if handler:
                await handler.async_revert()
                await handler.async_stop_listening()

        # Update tracking
        self._tracked_entries[config_entry.entry_id] = config_entry

        # Re-apply
        for entity_id in all_entity_ids:
            entries = self.get_entries_for_entity(entity_id)
            if not entries:
                self._entity_handlers.pop(entity_id, None)
                await self._store.async_remove_entity(entity_id)
                continue
            handler = self._entity_handlers.get(entity_id)
            if handler:
                await handler.async_apply(entries)
                await handler.async_start_listening()

        for device_id in all_device_ids:
            entries = self.get_entries_for_device(device_id)
            if not entries:
                self._device_handlers.pop(device_id, None)
                await self._store.async_remove_device(device_id)
                continue
            handler = self._device_handlers.get(device_id)
            if handler:
                await handler.async_apply(entries)
                await handler.async_start_listening()

    def _get_affected_entity_ids(self, config_entry: ConfigEntry[Any]) -> list[str]:
        """Return entity_ids affected by this config entry.

        ENTITY -> [modification_entry_id]
        DEVICE -> CONF_ASSIGNED_ENTITIES (may be empty list)
        MERGE  -> all entity_ids across all merged devices (from CONF_MODIFICATION_ORIGINAL_DATA)
        """
        mod_type = ModificationType(config_entry.data[CONF_MODIFICATION_TYPE])
        mod_data: dict[str, Any] = config_entry.options.get(CONF_MODIFICATION_DATA, {})

        if mod_type == ModificationType.ENTITY:
            return [config_entry.data[CONF_MODIFICATION_ENTRY_ID]]
        elif mod_type == ModificationType.DEVICE:
            return list(mod_data.get(CONF_ASSIGNED_ENTITIES, []))
        elif mod_type == ModificationType.MERGE:
            original_data = config_entry.data.get(CONF_MODIFICATION_ORIGINAL_DATA, {})
            entity_ids: list[str] = []
            for device_data in original_data.values():
                entities = device_data.get(CONF_ENTITIES, {})
                entity_ids.extend(entities.keys())
            return entity_ids
        return []

    def _get_affected_device_ids(self, config_entry: ConfigEntry[Any]) -> list[str]:
        """Return device_ids affected by this config entry.

        DEVICE -> [modification_entry_id]
        MERGE  -> [modification_entry_id] + list of merged device_ids
        ENTITY -> []
        """
        mod_type = ModificationType(config_entry.data[CONF_MODIFICATION_TYPE])

        if mod_type == ModificationType.DEVICE:
            return [config_entry.data[CONF_MODIFICATION_ENTRY_ID]]
        elif mod_type == ModificationType.MERGE:
            original_data = config_entry.data.get(CONF_MODIFICATION_ORIGINAL_DATA, {})
            device_ids = [config_entry.data[CONF_MODIFICATION_ENTRY_ID]]
            device_ids.extend(original_data.keys())
            return device_ids
        return []

    def get_entries_for_entity(self, entity_id: str) -> list[ConfigEntry[Any]]:
        """Return all tracked config entries affecting this entity_id, in priority order.

        MERGE first, then DEVICE, then ENTITY.
        """
        result: list[ConfigEntry[Any]] = []
        for entry in self._tracked_entries.values():
            affected = self._get_affected_entity_ids(entry)
            if entity_id in affected:
                result.append(entry)

        result.sort(
            key=lambda e: _PRIORITY.get(
                ModificationType(e.data[CONF_MODIFICATION_TYPE]), 99
            )
        )
        return result

    def get_entries_for_device(self, device_id: str) -> list[ConfigEntry[Any]]:
        """Return all tracked config entries affecting this device_id, in priority order.

        MERGE first, then DEVICE.
        """
        result: list[ConfigEntry[Any]] = []
        for entry in self._tracked_entries.values():
            affected = self._get_affected_device_ids(entry)
            if device_id in affected:
                result.append(entry)

        result.sort(
            key=lambda e: _PRIORITY.get(
                ModificationType(e.data[CONF_MODIFICATION_TYPE]), 99
            )
        )
        return result
