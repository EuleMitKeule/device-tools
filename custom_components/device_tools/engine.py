"""ModificationEngine — single orchestrator for all Device Tools modifications."""

from __future__ import annotations

import functools
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryDisabler
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    CONF_ASSIGNED_ENTITIES,
    CONF_DEVICE_ID,
    CONF_ENTITIES,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_IS_CUSTOM_ENTRY,
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

        # Snapshots of affected IDs at load time, keyed by entry_id.
        # Used in async_on_entry_updated to detect removals even though
        # HA mutates ConfigEntry objects in-place.
        self._tracked_entity_ids: dict[str, set[str]] = {}
        self._tracked_device_ids: dict[str, set[str]] = {}

        # Handler instances keyed by entity_id / device_id
        self._entity_handlers: dict[str, EntityHandler] = {}
        self._device_handlers: dict[str, DeviceHandler] = {}

        # Track already-warned (entry_id + "_" + missing_id) to log only once
        self._warned_missing: set[str] = set()

        # Unsubscribe callbacks for engine-level registry deletion listeners
        self._unsub_entity_removed: CALLBACK_TYPE | None = None
        self._unsub_device_removed: CALLBACK_TYPE | None = None

    async def async_start(self) -> None:
        """Load store. For each existing config entry: call async_on_entry_loaded."""
        await self._store.async_load()
        self._unsub_entity_removed = self._hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED,
            self._async_on_entity_registry_updated,
        )
        self._unsub_device_removed = self._hass.bus.async_listen(
            dr.EVENT_DEVICE_REGISTRY_UPDATED,
            self._async_on_device_registry_updated,
        )

    async def async_stop(self) -> None:
        """Revert all handlers, stop all listeners, clear state."""
        for entity_handler in list(self._entity_handlers.values()):
            try:
                await entity_handler.async_revert()
            except Exception:
                _LOGGER.exception("Error reverting entity handler %s", entity_handler.entry_id)
            await entity_handler.async_stop_listening()

        for device_handler in list(self._device_handlers.values()):
            try:
                await device_handler.async_revert()
            except Exception:
                _LOGGER.exception("Error reverting device handler %s", device_handler.entry_id)
            await device_handler.async_stop_listening()

        self._entity_handlers.clear()
        self._device_handlers.clear()
        self._tracked_entries.clear()
        self._tracked_entity_ids.clear()
        self._tracked_device_ids.clear()

        if self._unsub_entity_removed is not None:
            self._unsub_entity_removed()
            self._unsub_entity_removed = None
        if self._unsub_device_removed is not None:
            self._unsub_device_removed()
            self._unsub_device_removed = None

    async def async_on_entry_loaded(self, config_entry: ConfigEntry[Any]) -> None:
        """Handle a config entry being set up.

        1. Determine affected entity_ids and device_ids
        2. For each: if handler doesn't exist yet, create it
        3. For each: if original_data not in store, read current registry state and store it
        4. For each: call handler.async_apply(all entries for this entity/device)
        5. Start listening if not already
        """
        self._tracked_entries[config_entry.entry_id] = config_entry

        mod_type = ModificationType(config_entry.data[CONF_MODIFICATION_TYPE])
        modification_entry_id: str | None = config_entry.data.get(CONF_MODIFICATION_ENTRY_ID)
        modification_is_custom_entry: bool = config_entry.data.get(
            CONF_MODIFICATION_IS_CUSTOM_ENTRY, False
        )
        title: str = config_entry.title

        entity_registry = er.async_get(self._hass)
        device_registry = dr.async_get(self._hass)

        # --- Graceful handling of deleted targets / sources ---

        # ENTITY modification: check that the referenced entity still exists
        if mod_type == ModificationType.ENTITY and modification_entry_id:
            if entity_registry.async_get(modification_entry_id) is None:
                warn_key = f"{config_entry.entry_id}_{modification_entry_id}"
                if warn_key not in self._warned_missing:
                    self._warned_missing.add(warn_key)
                    _LOGGER.warning(
                        "Entity %s referenced by modification '%s' no longer exists. "
                        "Disabling modification.",
                        modification_entry_id,
                        title,
                    )
                await self._hass.config_entries.async_set_disabled_by(
                    config_entry.entry_id,
                    ConfigEntryDisabler.USER,
                )
                return

        # DEVICE modification (non-creation): check that the referenced device still exists
        if (
            mod_type == ModificationType.DEVICE
            and not modification_is_custom_entry
            and modification_entry_id
        ):
            if device_registry.async_get(modification_entry_id) is None:
                warn_key = f"{config_entry.entry_id}_{modification_entry_id}"
                if warn_key not in self._warned_missing:
                    self._warned_missing.add(warn_key)
                    _LOGGER.warning(
                        "Device %s referenced by modification '%s' no longer exists. "
                        "Disabling modification.",
                        modification_entry_id,
                        title,
                    )
                await self._hass.config_entries.async_set_disabled_by(
                    config_entry.entry_id,
                    ConfigEntryDisabler.USER,
                )
                return

        # MERGE modification: remove any source devices that no longer exist
        if mod_type == ModificationType.MERGE:
            original_data: dict[str, Any] = config_entry.data.get(
                CONF_MODIFICATION_ORIGINAL_DATA, {}
            )
            missing_sources = [
                device_id
                for device_id in original_data
                if device_registry.async_get(device_id) is None
            ]
            if missing_sources:
                new_original_data = {
                    k: v for k, v in original_data.items() if k not in missing_sources
                }
                for missing_id in missing_sources:
                    warn_key = f"{config_entry.entry_id}_{missing_id}"
                    if warn_key not in self._warned_missing:
                        self._warned_missing.add(warn_key)
                        _LOGGER.warning(
                            "Device %s referenced by merge modification '%s' no longer "
                            "exists. Removing from merge sources.",
                            missing_id,
                            title,
                        )
                self._hass.config_entries.async_update_entry(
                    config_entry,
                    data={
                        **config_entry.data,
                        CONF_MODIFICATION_ORIGINAL_DATA: new_original_data,
                    },
                )
                # config_entry is mutated in-place by HA; re-read data from it
                config_entry = self._hass.config_entries.async_get_entry(
                    config_entry.entry_id
                ) or config_entry

        # DEVICE modification: remove assigned entities that no longer exist
        if mod_type == ModificationType.DEVICE:
            mod_data: dict[str, Any] = config_entry.options.get(CONF_MODIFICATION_DATA, {})
            assigned: list[str] = mod_data.get(CONF_ASSIGNED_ENTITIES, [])
            missing_entities = [
                eid for eid in assigned if entity_registry.async_get(eid) is None
            ]
            if missing_entities:
                new_assigned = [eid for eid in assigned if eid not in missing_entities]
                for missing_id in missing_entities:
                    warn_key = f"{config_entry.entry_id}_{missing_id}"
                    if warn_key not in self._warned_missing:
                        self._warned_missing.add(warn_key)
                        _LOGGER.warning(
                            "Entity %s assigned to device modification '%s' no longer "
                            "exists. Removing from assigned entities.",
                            missing_id,
                            title,
                        )
                new_mod_data = {**mod_data, CONF_ASSIGNED_ENTITIES: new_assigned}
                new_options = {
                    **config_entry.options,
                    CONF_MODIFICATION_DATA: new_mod_data,
                }
                self._hass.config_entries.async_update_entry(
                    config_entry,
                    options=new_options,
                )
                config_entry = self._hass.config_entries.async_get_entry(
                    config_entry.entry_id
                ) or config_entry

        # Update the tracked entry reference after potential mutations
        self._tracked_entries[config_entry.entry_id] = config_entry

        affected_entity_ids = self._get_affected_entity_ids(config_entry)
        affected_device_ids = self._get_affected_device_ids(config_entry)

        # Store snapshots of affected IDs so async_on_entry_updated can detect
        # removals even when HA mutates ConfigEntry objects in-place.
        self._tracked_entity_ids[config_entry.entry_id] = set(affected_entity_ids)
        self._tracked_device_ids[config_entry.entry_id] = set(affected_device_ids)

        # Ensure entity handlers and original data
        for entity_id in affected_entity_ids:
            if entity_id not in self._entity_handlers:
                self._entity_handlers[entity_id] = EntityHandler(
                    self._hass,
                    entity_id,
                    self._store,
                    get_active_entries=functools.partial(
                        self.get_entries_for_entity, entity_id
                    ),
                )

            if self._store.get_entity(entity_id) is None:
                entity = entity_registry.async_get(entity_id)
                if entity is not None:
                    original = {
                        k: v
                        for k, v in entity.extended_dict.items()
                        if k in MODIFIABLE_ATTRIBUTES[ModificationType.ENTITY]
                    }
                    await self._store.async_set_entity(entity_id, original)

        # Ensure device handlers and original data
        for device_id in affected_device_ids:
            if device_registry.async_get(device_id) is None:
                _LOGGER.debug(
                    "Device %s not found in registry, skipping handler creation",
                    device_id,
                )
                continue

            if device_id not in self._device_handlers:
                self._device_handlers[device_id] = DeviceHandler(
                    self._hass,
                    device_id,
                    self._store,
                    get_active_entries=functools.partial(
                        self.get_entries_for_device, device_id
                    ),
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

        entity_handler: EntityHandler
        device_handler: DeviceHandler | None
        # Apply all relevant entries and start listening
        for entity_id in affected_entity_ids:
            entity_handler = self._entity_handlers[entity_id]
            entries = self.get_entries_for_entity(entity_id)
            await entity_handler.async_apply(entries)
            await entity_handler.async_start_listening()

        for device_id in affected_device_ids:
            device_handler = self._device_handlers.get(device_id)
            if device_handler is None:
                continue
            entries = self.get_entries_for_device(device_id)
            await device_handler.async_apply(entries)
            await device_handler.async_start_listening()

    async def async_on_entry_unloaded(self, config_entry: ConfigEntry[Any]) -> None:
        """Handle config entry unload.

        1. If this is a creation-modification (modification_is_custom_entry=True),
           cascade-update dependent entries (strip stale device_id, remove device
           from MERGE original_data) BEFORE reverting handlers.
        2. For affected handlers: revert and stop listening
        3. Remove config entry from engine's tracking
        4. For each affected entity/device: if no more config entries reference it,
           remove handler and remove original_data from store
        """
        modification_is_custom_entry: bool = config_entry.data.get(
            CONF_MODIFICATION_IS_CUSTOM_ENTRY, False
        )
        mod_type = ModificationType(config_entry.data[CONF_MODIFICATION_TYPE])

        # Collect additional entity IDs affected by cascade when a
        # creation-modification device is deleted.
        cascade_entity_ids: set[str] = set()

        if (
            modification_is_custom_entry
            and mod_type == ModificationType.DEVICE
        ):
            creation_device_id: str = config_entry.data[CONF_MODIFICATION_ENTRY_ID]

            # --- Cascade: dependent ENTITY / DEVICE mods ---
            dependent_ids = self._find_dependent_entry_ids(
                creation_device_id, exclude_entry_id=config_entry.entry_id
            )
            if dependent_ids:
                dependent_titles = [
                    self._tracked_entries[eid].title
                    for eid in dependent_ids
                    if eid in self._tracked_entries
                ]
                _LOGGER.warning(
                    "Removing creation-modification device %s while %d dependent "
                    "modification(s) still reference it: %s. "
                    "These modifications will be re-applied without the deleted device.",
                    creation_device_id,
                    len(dependent_ids),
                    dependent_titles,
                )

            for dep_entry_id in dependent_ids:
                dep_entry = self._tracked_entries.get(dep_entry_id)
                if dep_entry is None:
                    continue

                mod_data = dict(
                    dep_entry.options.get(CONF_MODIFICATION_DATA, {})
                )
                if mod_data.get(CONF_DEVICE_ID) == creation_device_id:
                    mod_data.pop(CONF_DEVICE_ID)
                    new_options = {
                        **dep_entry.options,
                        CONF_MODIFICATION_DATA: mod_data,
                    }
                    self._hass.config_entries.async_update_entry(
                        dep_entry, options=new_options
                    )
                    _LOGGER.info(
                        "Removed stale device_id %s from dependent modification %s",
                        creation_device_id,
                        dep_entry.title,
                    )

                cascade_entity_ids.update(
                    self._get_affected_entity_ids(dep_entry)
                )

            # --- Cascade: MERGE mods referencing the deleted device as source ---
            for entry_id, entry in list(self._tracked_entries.items()):
                if entry_id == config_entry.entry_id:
                    continue
                entry_mod_type = ModificationType(
                    entry.data[CONF_MODIFICATION_TYPE]
                )
                if entry_mod_type != ModificationType.MERGE:
                    continue

                orig_data = entry.data.get(
                    CONF_MODIFICATION_ORIGINAL_DATA, {}
                )
                if creation_device_id not in orig_data:
                    continue

                # Collect entity IDs from the deleted device's portion
                removed_data = orig_data.get(creation_device_id, {})
                cascade_entity_ids.update(
                    removed_data.get(CONF_ENTITIES, {}).keys()
                )

                # Strip the deleted device from the merge's persisted data
                new_orig_data = {
                    k: v
                    for k, v in orig_data.items()
                    if k != creation_device_id
                }
                self._hass.config_entries.async_update_entry(
                    entry,
                    data={
                        **entry.data,
                        CONF_MODIFICATION_ORIGINAL_DATA: new_orig_data,
                    },
                )

                # Update tracked IDs synchronously so any async listener
                # that fires later sees consistent state.
                self._tracked_entity_ids[entry_id] = set(
                    self._get_affected_entity_ids(entry)
                )
                self._tracked_device_ids[entry_id] = set(
                    self._get_affected_device_ids(entry)
                )

                _LOGGER.info(
                    "Removed deleted device %s from merge modification %s",
                    creation_device_id,
                    entry.title,
                )

        # Combine directly-affected IDs with cascade-affected IDs
        affected_entity_ids = (
            set(self._get_affected_entity_ids(config_entry))
            | cascade_entity_ids
        )
        affected_device_ids = set(self._get_affected_device_ids(config_entry))

        entity_handler: EntityHandler | None
        device_handler: DeviceHandler | None

        # Revert affected handlers
        for entity_id in affected_entity_ids:
            entity_handler = self._entity_handlers.get(entity_id)
            if entity_handler:
                await entity_handler.async_revert()
                await entity_handler.async_stop_listening()

        for device_id in affected_device_ids:
            device_handler = self._device_handlers.get(device_id)
            if device_handler:
                await device_handler.async_revert()
                await device_handler.async_stop_listening()

        # Remove from tracking
        self._tracked_entries.pop(config_entry.entry_id, None)
        self._tracked_entity_ids.pop(config_entry.entry_id, None)
        self._tracked_device_ids.pop(config_entry.entry_id, None)

        # Clean up handlers that are no longer needed
        for entity_id in affected_entity_ids:
            remaining = self.get_entries_for_entity(entity_id)
            if not remaining:
                self._entity_handlers.pop(entity_id, None)
                await self._store.async_remove_entity(entity_id)
            else:
                # Re-apply remaining entries
                entity_handler = self._entity_handlers.get(entity_id)
                if entity_handler:
                    await entity_handler.async_apply(remaining)
                    await entity_handler.async_start_listening()

        for device_id in affected_device_ids:
            remaining = self.get_entries_for_device(device_id)
            if not remaining:
                self._device_handlers.pop(device_id, None)
                await self._store.async_remove_device(device_id)
            else:
                device_handler = self._device_handlers.get(device_id)
                if device_handler:
                    await device_handler.async_apply(remaining)
                    await device_handler.async_start_listening()

    async def async_on_entry_updated(self, config_entry: ConfigEntry[Any]) -> None:
        """Handle options/data change for a config entry.

        1. Revert all affected handlers
        2. Update engine's tracking
        3. Re-apply all affected handlers
        """
        # Use stored ID snapshots rather than re-computing from the old entry object,
        # because HA mutates ConfigEntry objects in-place — the stored reference would
        # already reflect the new state before we get here.
        old_entity_ids: set[str] = self._tracked_entity_ids.get(
            config_entry.entry_id, set()
        )
        old_device_ids: set[str] = self._tracked_device_ids.get(
            config_entry.entry_id, set()
        )

        new_entity_ids = set(self._get_affected_entity_ids(config_entry))
        new_device_ids = set(self._get_affected_device_ids(config_entry))

        all_entity_ids = old_entity_ids | new_entity_ids
        all_device_ids = old_device_ids | new_device_ids

        entity_handler: EntityHandler | None
        device_handler: DeviceHandler | None

        # Revert affected handlers
        for entity_id in all_entity_ids:
            entity_handler = self._entity_handlers.get(entity_id)
            if entity_handler:
                await entity_handler.async_revert()
                await entity_handler.async_stop_listening()

        for device_id in all_device_ids:
            device_handler = self._device_handlers.get(device_id)
            if device_handler:
                await device_handler.async_revert()
                await device_handler.async_stop_listening()

        # Update tracking with the new entry and updated snapshots
        self._tracked_entries[config_entry.entry_id] = config_entry
        self._tracked_entity_ids[config_entry.entry_id] = new_entity_ids
        self._tracked_device_ids[config_entry.entry_id] = new_device_ids

        # Re-apply
        for entity_id in all_entity_ids:
            entries = self.get_entries_for_entity(entity_id)
            if not entries:
                self._entity_handlers.pop(entity_id, None)
                await self._store.async_remove_entity(entity_id)
                continue
            entity_handler = self._entity_handlers.get(entity_id)
            if entity_handler:
                await entity_handler.async_apply(entries)
                await entity_handler.async_start_listening()

        for device_id in all_device_ids:
            entries = self.get_entries_for_device(device_id)
            if not entries:
                self._device_handlers.pop(device_id, None)
                await self._store.async_remove_device(device_id)
                continue
            device_handler = self._device_handlers.get(device_id)
            if device_handler:
                await device_handler.async_apply(entries)
                await device_handler.async_start_listening()

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
        if mod_type == ModificationType.DEVICE:
            return list(mod_data.get(CONF_ASSIGNED_ENTITIES, []))
        if mod_type == ModificationType.MERGE:
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
        if mod_type == ModificationType.MERGE:
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

    def _find_dependent_entry_ids(
        self, device_id: str, exclude_entry_id: str | None = None
    ) -> list[str]:
        """Return entry_ids of tracked modifications that reference device_id.

        This finds:
        - ENTITY modifications whose CONF_DEVICE_ID in modification_data equals device_id
        - DEVICE modifications with CONF_ASSIGNED_ENTITIES that are assigned to device_id
          (i.e. the modification's own entry_id is device_id)

        Args:
            device_id: The device ID to search for as a reference target.
            exclude_entry_id: An entry_id to exclude from the results (typically the
                creation-modification entry being unloaded).

        Returns:
            A list of config entry_ids that depend on the given device_id.

        """
        dependent: list[str] = []
        for entry_id, entry in self._tracked_entries.items():
            if entry_id == exclude_entry_id:
                continue
            mod_type = ModificationType(entry.data[CONF_MODIFICATION_TYPE])
            mod_data: dict[str, Any] = entry.options.get(CONF_MODIFICATION_DATA, {})
            if mod_type == ModificationType.ENTITY:
                if mod_data.get(CONF_DEVICE_ID) == device_id:
                    dependent.append(entry_id)
            elif mod_type == ModificationType.DEVICE:
                if entry.data.get(CONF_MODIFICATION_ENTRY_ID) == device_id:
                    dependent.append(entry_id)
        return dependent

    async def _async_on_entity_registry_updated(
        self,
        event: Event[er.EventEntityRegistryUpdatedData],
    ) -> None:
        """React to entity-registry events at the engine level.

        Handles ``action == "remove"``: an entity that was the *target* of an
        ENTITY modification is disabled; an entity that was *assigned* to a
        DEVICE modification is removed from its ``CONF_ASSIGNED_ENTITIES`` list.
        All other actions are ignored here (individual entity handlers react to
        "update" actions themselves).
        """
        if event.data["action"] != "remove":
            return
        removed_entity_id: str = event.data["entity_id"]

        for entry in list(self._tracked_entries.values()):
            mod_type = ModificationType(entry.data[CONF_MODIFICATION_TYPE])
            entry_target_id: str | None = entry.data.get(CONF_MODIFICATION_ENTRY_ID)

            if mod_type == ModificationType.ENTITY and entry_target_id == removed_entity_id:
                warn_key = f"{entry.entry_id}_{removed_entity_id}"
                if warn_key not in self._warned_missing:
                    self._warned_missing.add(warn_key)
                    _LOGGER.warning(
                        "Entity %s referenced by modification '%s' no longer exists. "
                        "Disabling modification.",
                        removed_entity_id,
                        entry.title,
                    )
                await self._hass.config_entries.async_set_disabled_by(
                    entry.entry_id,
                    ConfigEntryDisabler.USER,
                )

            elif mod_type == ModificationType.DEVICE:
                mod_data: dict[str, Any] = entry.options.get(CONF_MODIFICATION_DATA, {})
                assigned: list[str] = mod_data.get(CONF_ASSIGNED_ENTITIES, [])
                if removed_entity_id in assigned:
                    new_assigned = [eid for eid in assigned if eid != removed_entity_id]
                    warn_key = f"{entry.entry_id}_{removed_entity_id}"
                    if warn_key not in self._warned_missing:
                        self._warned_missing.add(warn_key)
                        _LOGGER.warning(
                            "Entity %s assigned to device modification '%s' no longer "
                            "exists. Removing from assigned entities.",
                            removed_entity_id,
                            entry.title,
                        )
                    new_mod_data = {**mod_data, CONF_ASSIGNED_ENTITIES: new_assigned}
                    self._hass.config_entries.async_update_entry(
                        entry,
                        options={**entry.options, CONF_MODIFICATION_DATA: new_mod_data},
                    )

    async def _async_on_device_registry_updated(
        self,
        event: Event[dr.EventDeviceRegistryUpdatedData],
    ) -> None:
        """React to device-registry events at the engine level.

        Handles ``action == "remove"``: a device that was the *target* of a
        non-creation DEVICE modification is disabled; a device that was a
        *source* in a MERGE modification is removed from
        ``CONF_MODIFICATION_ORIGINAL_DATA``.
        All other actions are ignored here (individual device handlers react
        to "update" actions themselves).
        """
        if event.data["action"] != "remove":
            return
        removed_device_id: str = event.data["device_id"]

        for entry in list(self._tracked_entries.values()):
            mod_type = ModificationType(entry.data[CONF_MODIFICATION_TYPE])
            entry_target_id: str | None = entry.data.get(CONF_MODIFICATION_ENTRY_ID)
            modification_is_custom_entry: bool = entry.data.get(
                CONF_MODIFICATION_IS_CUSTOM_ENTRY, False
            )

            if (
                mod_type == ModificationType.DEVICE
                and not modification_is_custom_entry
                and entry_target_id == removed_device_id
            ):
                warn_key = f"{entry.entry_id}_{removed_device_id}"
                if warn_key not in self._warned_missing:
                    self._warned_missing.add(warn_key)
                    _LOGGER.warning(
                        "Device %s referenced by modification '%s' no longer exists. "
                        "Disabling modification.",
                        removed_device_id,
                        entry.title,
                    )
                await self._hass.config_entries.async_set_disabled_by(
                    entry.entry_id,
                    ConfigEntryDisabler.USER,
                )

            elif mod_type == ModificationType.MERGE:
                original_data: dict[str, Any] = entry.data.get(
                    CONF_MODIFICATION_ORIGINAL_DATA, {}
                )
                if removed_device_id in original_data:
                    new_original_data = {
                        k: v
                        for k, v in original_data.items()
                        if k != removed_device_id
                    }
                    warn_key = f"{entry.entry_id}_{removed_device_id}"
                    if warn_key not in self._warned_missing:
                        self._warned_missing.add(warn_key)
                        _LOGGER.warning(
                            "Device %s referenced by merge modification '%s' no longer "
                            "exists. Removing from merge sources.",
                            removed_device_id,
                            entry.title,
                        )
                    self._hass.config_entries.async_update_entry(
                        entry,
                        data={
                            **entry.data,
                            CONF_MODIFICATION_ORIGINAL_DATA: new_original_data,
                        },
                    )
