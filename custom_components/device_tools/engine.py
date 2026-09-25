"""Modification engine orchestrating all Device Tools modifications."""

from __future__ import annotations

from collections.abc import Iterable
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CALLBACK_TYPE, CoreState, Event, HomeAssistant, callback
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)

from .const import (
    CONF_ASSIGNED_ENTITIES,
    CONF_DEVICE_ID,
    CONF_ENTITIES,
    CONF_ENTITY_CATEGORY,
    CONF_ENTRY_TYPE,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_ORIGINAL_DATA,
    CONF_VIA_DEVICE_ID,
    DOMAIN,
    ENTITY_CATEGORY_DEFAULT,
    ENTRY_TYPE_NONE,
    MODIFIABLE_ATTRIBUTES,
    MODIFICATION_PRECEDENCE,
    ModificationType,
)
from .entry_handler import (
    DeviceHandler,
    EntityHandler,
    EntryHandler,
    get_device_data,
    get_entity_data,
)
from .original_data_store import KIND_DEVICES, KIND_ENTITIES, OriginalDataStore
from .utils import (
    assigned_entities,
    async_get_device,
    async_resolve_device_id,
    merge_sources,
    modification_data,
    modification_entry_id,
    modification_is_custom_entry,
    modification_type,
)

_LOGGER = logging.getLogger(__name__)

ISSUE_MISSING_REFERENCES = "missing_references"


class ModificationEngine:
    """Single orchestrator for all modifications.

    Every loaded config entry contributes to the desired state of the entities and
    devices it targets. Whenever a config entry or a targeted registry entry changes,
    the affected entities and devices are reconciled with their desired state.
    """

    def __init__(self, hass: HomeAssistant, store: OriginalDataStore) -> None:
        """Initialize the engine."""
        self._hass = hass
        self._store = store
        self._config_entries: dict[str, ConfigEntry[Any]] = {}
        self._targets: dict[str, tuple[set[str], set[str]]] = {}
        self._entity_handlers: dict[str, EntityHandler] = {}
        self._device_handlers: dict[str, DeviceHandler] = {}
        self._unsub: list[CALLBACK_TYPE] = []
        self._stale_original_data_forgotten = False

    @property
    def store(self) -> OriginalDataStore:
        """Return the original data store."""
        return self._store

    async def async_start(self) -> None:
        """Load persisted data and start listening for registry updates."""
        await self._store.async_load()
        self._unsub = [
            self._hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED,
                self._async_on_entity_registry_updated,
            ),
            self._hass.bus.async_listen(
                dr.EVENT_DEVICE_REGISTRY_UPDATED,
                self._async_on_device_registry_updated,
            ),
        ]
        if self._hass.state is not CoreState.running:
            self._hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, self._async_on_started
            )

    @callback
    def async_stop(self) -> None:
        """Stop listening for registry updates."""
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()

    @callback
    def _async_on_started(self, _event: Event) -> None:
        """Handle Home Assistant being started."""
        self._async_forget_stale_original_data()

    @callback
    def _async_forget_stale_original_data(self) -> None:
        """Forget original values of attributes that no modification controls.

        This only happens if a modification could not be unloaded properly, e.g.
        because it failed to set up. The registry is left untouched in that case,
        as it is unknown whether the stored values are still accurate. It is done
        once after all modifications were loaded, or after Home Assistant started.
        """
        if self._stale_original_data_forgotten:
            return
        self._stale_original_data_forgotten = True
        for kind, desired_data in (
            (KIND_ENTITIES, self.get_desired_entity_data),
            (KIND_DEVICES, self.get_desired_device_data),
        ):
            for target_id in self._store.target_ids(kind):
                desired = desired_data(target_id)
                for key in self._store.get(kind, target_id):
                    if key not in desired:
                        _LOGGER.debug(
                            "Forgetting stale original value of %s of %s %s",
                            key,
                            kind,
                            target_id,
                        )
                        self._store.async_remove(kind, target_id, key)

    @callback
    def async_on_entry_loaded(self, config_entry: ConfigEntry[Any]) -> None:
        """Start applying a modification."""
        self._async_discover_merge_entities(config_entry)
        self._config_entries[config_entry.entry_id] = config_entry
        self._targets[config_entry.entry_id] = self.get_targets(config_entry)
        self._async_reconcile_targets(
            *self._targets[config_entry.entry_id], release=False
        )
        self._async_update_issue(config_entry)
        if all(
            entry.entry_id in self._config_entries
            for entry in self._hass.config_entries.async_entries(
                DOMAIN, include_ignore=False, include_disabled=False
            )
        ):
            self._async_forget_stale_original_data()

    @callback
    def async_on_entry_updated(self, config_entry: ConfigEntry[Any]) -> None:
        """Re-apply a modification after its data or options changed."""
        if config_entry.entry_id not in self._config_entries:
            return
        self._async_discover_merge_entities(config_entry)
        old_entity_ids, old_device_ids = self._targets[config_entry.entry_id]
        entity_ids, device_ids = self._targets[config_entry.entry_id] = (
            self.get_targets(config_entry)
        )
        self._async_reconcile_targets(
            old_entity_ids | entity_ids, old_device_ids | device_ids, release=True
        )
        self._async_update_issue(config_entry)

    @callback
    def async_on_entry_unloaded(self, config_entry: ConfigEntry[Any]) -> None:
        """Stop applying a modification and restore the original values."""
        if config_entry.entry_id not in self._config_entries:
            return
        del self._config_entries[config_entry.entry_id]
        entity_ids, device_ids = self._targets.pop(config_entry.entry_id)
        self._async_reconcile_targets(entity_ids, device_ids, release=True)

    @callback
    def async_on_entry_removed(self, config_entry: ConfigEntry[Any]) -> None:
        """Clean up after a modification was removed."""
        ir.async_delete_issue(
            self._hass, DOMAIN, f"{ISSUE_MISSING_REFERENCES}_{config_entry.entry_id}"
        )
        if not modification_is_custom_entry(config_entry):
            return
        self._async_remove_device_references(modification_entry_id(config_entry))

    @callback
    def _async_remove_device_references(self, device_id: str) -> None:
        """Remove references to a device that was removed with its modification."""
        for config_entry in list(self._config_entries.values()):
            data = dict(config_entry.data)
            options = modification_data(config_entry)
            match modification_type(config_entry):
                case ModificationType.ENTITY:
                    if options.get(CONF_DEVICE_ID) != device_id:
                        continue
                    del options[CONF_DEVICE_ID]
                case ModificationType.DEVICE:
                    if options.get(CONF_VIA_DEVICE_ID) != device_id:
                        continue
                    del options[CONF_VIA_DEVICE_ID]
                case ModificationType.MERGE:
                    sources = dict(data.get(CONF_MODIFICATION_ORIGINAL_DATA, {}))
                    if sources.pop(device_id, None) is None:
                        continue
                    data[CONF_MODIFICATION_ORIGINAL_DATA] = sources
            _LOGGER.info(
                "Removing reference to removed device %s from modification %s",
                device_id,
                config_entry.title,
            )
            self._hass.config_entries.async_update_entry(
                config_entry,
                data=data,
                options={**config_entry.options, CONF_MODIFICATION_DATA: options},
            )

    def get_config_entries(self) -> list[ConfigEntry[Any]]:
        """Return all loaded modifications."""
        return list(self._config_entries.values())

    def get_desired_entity_data(self, entity_id: str) -> dict[str, Any]:
        """Return the attribute values all modifications want an entity to have."""
        desired_data: dict[str, Any] = {}
        for config_entry in self._sorted_config_entries():
            match modification_type(config_entry):
                case ModificationType.DEVICE:
                    if entity_id in assigned_entities(config_entry):
                        desired_data[CONF_DEVICE_ID] = modification_entry_id(
                            config_entry
                        )
                case ModificationType.MERGE:
                    if any(
                        entity_id in entity_ids
                        for entity_ids in merge_sources(config_entry).values()
                    ):
                        desired_data[CONF_DEVICE_ID] = modification_entry_id(
                            config_entry
                        )
                case ModificationType.ENTITY:
                    if modification_entry_id(config_entry) == entity_id:
                        desired_data.update(
                            _filter_data(
                                ModificationType.ENTITY, modification_data(config_entry)
                            )
                        )

        if (device_id := desired_data.get(CONF_DEVICE_ID)) is not None and (
            async_get_device(self._hass, device_id) is None
        ):
            del desired_data[CONF_DEVICE_ID]
        return desired_data

    def get_desired_device_data(self, device_id: str) -> dict[str, Any]:
        """Return the attribute values all modifications want a device to have."""
        desired_data: dict[str, Any] = {}
        for config_entry in self._sorted_config_entries():
            if (
                modification_type(config_entry) == ModificationType.DEVICE
                and modification_entry_id(config_entry) == device_id
            ):
                desired_data.update(
                    _filter_data(
                        ModificationType.DEVICE, modification_data(config_entry)
                    )
                )

        if (via_device_id := desired_data.get(CONF_VIA_DEVICE_ID)) is not None and (
            via_device_id == device_id
            or async_get_device(self._hass, via_device_id) is None
        ):
            del desired_data[CONF_VIA_DEVICE_ID]
        return desired_data

    def get_original_entity_data(self, entity_id: str) -> dict[str, Any]:
        """Return the attribute values an entity would have without modifications."""
        return {
            **(get_entity_data(self._hass, entity_id) or {}),
            **self._store.get(KIND_ENTITIES, entity_id),
        }

    def get_original_device_data(self, device_id: str) -> dict[str, Any]:
        """Return the attribute values a device would have without modifications."""
        return {
            **(get_device_data(self._hass, device_id) or {}),
            **self._store.get(KIND_DEVICES, device_id),
        }

    def _sorted_config_entries(self) -> list[ConfigEntry[Any]]:
        """Return all loaded modifications in ascending order of precedence."""
        return sorted(
            self._config_entries.values(),
            key=lambda config_entry: MODIFICATION_PRECEDENCE[
                modification_type(config_entry)
            ],
        )

    def get_targets(self, config_entry: ConfigEntry[Any]) -> tuple[set[str], set[str]]:
        """Return the entity ids and device ids a modification targets."""
        match modification_type(config_entry):
            case ModificationType.ENTITY:
                return {modification_entry_id(config_entry)}, set()
            case ModificationType.DEVICE:
                return set(assigned_entities(config_entry)), {
                    modification_entry_id(config_entry)
                }
            case ModificationType.MERGE:
                return {
                    entity_id
                    for entity_ids in merge_sources(config_entry).values()
                    for entity_id in entity_ids
                }, set()

    @callback
    def _async_reconcile_targets(
        self, entity_ids: Iterable[str], device_ids: Iterable[str], *, release: bool
    ) -> None:
        """Reconcile entities and devices with their desired state."""
        for device_id in device_ids:
            self._async_reconcile(
                self._device_handlers,
                DeviceHandler,
                device_id,
                self.get_desired_device_data(device_id),
                release=release,
            )
        for entity_id in entity_ids:
            self._async_reconcile(
                self._entity_handlers,
                EntityHandler,
                entity_id,
                self.get_desired_entity_data(entity_id),
                release=release,
            )

    @callback
    def _async_reconcile[HandlerT: EntryHandler](
        self,
        handlers: dict[str, HandlerT],
        handler_type: type[HandlerT],
        target_id: str,
        desired_data: dict[str, Any],
        *,
        release: bool,
    ) -> None:
        """Reconcile a single entity or device with its desired state."""
        if (handler := handlers.get(target_id)) is None:
            handler = handlers[target_id] = handler_type(
                self._hass, target_id, self._store
            )
        handler.async_reconcile(desired_data, release=release)
        if not desired_data and not handler.original_data:
            del handlers[target_id]

    @callback
    def _async_on_entity_registry_updated(
        self, event: Event[er.EventEntityRegistryUpdatedData]
    ) -> None:
        """Handle an entity registry update."""
        entity_id = event.data["entity_id"]
        match event.data:
            case {"action": "update", "old_entity_id": old_entity_id} if (
                old_entity_id != entity_id
            ):
                self._async_on_entity_renamed(old_entity_id, entity_id)
            case {"action": "update", "changes": changes}:
                if CONF_DEVICE_ID in changes:
                    self._async_discover_merge_entity(entity_id)
                if (handler := self._entity_handlers.get(entity_id)) is not None:
                    handler.async_on_registry_updated(
                        self.get_desired_entity_data(entity_id), changes
                    )
            case {"action": "create"}:
                self._async_discover_merge_entity(entity_id)
                self._async_on_reference_changed(entity_id=entity_id)
            case {"action": "remove"}:
                self._async_on_entity_removed(entity_id)

    @callback
    def _async_on_device_registry_updated(
        self, event: Event[dr.EventDeviceRegistryUpdatedData]
    ) -> None:
        """Handle a device registry update."""
        device_id = event.data["device_id"]
        match event.data:
            case {"action": "update", "changes": changes}:
                if (handler := self._device_handlers.get(device_id)) is not None:
                    handler.async_on_registry_updated(
                        self.get_desired_device_data(device_id), changes
                    )
            case {"action": "create"}:
                self._async_on_reference_changed(device_id=device_id)
            case {"action": "remove"}:
                self._async_on_device_removed(device_id)

    @callback
    def _async_on_entity_renamed(self, old_entity_id: str, entity_id: str) -> None:
        """Follow an entity id change in all modifications."""
        if (handler := self._entity_handlers.pop(old_entity_id, None)) is not None:
            handler.async_rename(entity_id)
            self._entity_handlers[entity_id] = handler
        else:
            self._store.async_rename(KIND_ENTITIES, old_entity_id, entity_id)

        for config_entry_id, (entity_ids, device_ids) in self._targets.items():
            if old_entity_id in entity_ids:
                self._targets[config_entry_id] = (
                    (entity_ids - {old_entity_id}) | {entity_id},
                    device_ids,
                )

        for config_entry in self._hass.config_entries.async_entries(DOMAIN):
            if (data := _rename_entity(config_entry, old_entity_id, entity_id)) is None:
                continue
            _LOGGER.info(
                "Entity %s was renamed to %s, updating modification %s",
                old_entity_id,
                entity_id,
                config_entry.title,
            )
            self._hass.config_entries.async_update_entry(config_entry, **data)

    @callback
    def _async_on_entity_removed(self, entity_id: str) -> None:
        """Forget an entity that was removed from the registry."""
        self._entity_handlers.pop(entity_id, None)
        self._store.async_remove(KIND_ENTITIES, entity_id)

        for config_entry in list(self._config_entries.values()):
            if modification_type(config_entry) != ModificationType.MERGE:
                continue
            sources = config_entry.data.get(CONF_MODIFICATION_ORIGINAL_DATA, {})
            if not any(
                entity_id in entity_ids
                for entity_ids in merge_sources(config_entry).values()
            ):
                continue
            self._hass.config_entries.async_update_entry(
                config_entry,
                data={
                    **config_entry.data,
                    CONF_MODIFICATION_ORIGINAL_DATA: {
                        device_id: {
                            **device_data,
                            CONF_ENTITIES: {
                                key: value
                                for key, value in device_data.get(
                                    CONF_ENTITIES, {}
                                ).items()
                                if key != entity_id
                            },
                        }
                        for device_id, device_data in sources.items()
                    },
                },
            )

        self._async_on_reference_changed(entity_id=entity_id)

    @callback
    def _async_on_device_removed(self, device_id: str) -> None:
        """Forget a device that was removed from the registry."""
        self._device_handlers.pop(device_id, None)
        self._store.async_remove(KIND_DEVICES, device_id)

        for config_entry in list(self._config_entries.values()):
            if modification_type(config_entry) != ModificationType.MERGE:
                continue
            sources = dict(config_entry.data.get(CONF_MODIFICATION_ORIGINAL_DATA, {}))
            if sources.pop(device_id, None) is None:
                continue
            _LOGGER.info(
                "Device %s was removed, removing it from merge modification %s",
                device_id,
                config_entry.title,
            )
            self._hass.config_entries.async_update_entry(
                config_entry,
                data={**config_entry.data, CONF_MODIFICATION_ORIGINAL_DATA: sources},
            )

        self._async_on_reference_changed(device_id=device_id)

    @callback
    def _async_on_reference_changed(
        self, *, entity_id: str | None = None, device_id: str | None = None
    ) -> None:
        """Re-apply modifications referencing an entity or device that appeared or vanished."""
        for config_entry in list(self._config_entries.values()):
            if not _references(config_entry, entity_id=entity_id, device_id=device_id):
                continue
            self._async_reconcile_targets(
                *self._targets[config_entry.entry_id], release=True
            )
            self._async_update_issue(config_entry)

    @callback
    def _async_discover_merge_entities(self, config_entry: ConfigEntry[Any]) -> None:
        """Add entities that were added to merged devices to a merge modification."""
        if modification_type(config_entry) != ModificationType.MERGE:
            return
        sources: dict[str, Any] = config_entry.data.get(
            CONF_MODIFICATION_ORIGINAL_DATA, {}
        )
        new_sources = {
            device_id: {
                **device_data,
                CONF_ENTITIES: {
                    **device_data.get(CONF_ENTITIES, {}),
                    **{
                        entity_id: {}
                        for entity_id in self._get_merge_candidates(
                            modification_entry_id(config_entry), device_id
                        )
                        if entity_id not in device_data.get(CONF_ENTITIES, {})
                    },
                },
            }
            for device_id, device_data in sources.items()
        }
        if new_sources == sources:
            return
        _LOGGER.debug(
            "Discovered new entities for merge modification %s", config_entry.title
        )
        self._hass.config_entries.async_update_entry(
            config_entry,
            data={**config_entry.data, CONF_MODIFICATION_ORIGINAL_DATA: new_sources},
        )

    def _get_merge_candidates(self, target_id: str, device_id: str) -> list[str]:
        """Return the entities a merge takes from a merged device.

        These are the entities of the device, including ones moved away by
        modifications. Previous versions added the config entries of merged devices
        to the target device, so Home Assistant 2026.8 split the target device and
        moved the merged entities to one of the splits. Those are included as well.
        """
        entity_registry = er.async_get(self._hass)
        candidates = [
            entity.entity_id
            for entity in er.async_entries_for_device(
                entity_registry, device_id, include_disabled_entities=True
            )
        ] + [
            entity_id
            for entity_id in self._store.target_ids(KIND_ENTITIES)
            if self._store.get(KIND_ENTITIES, entity_id).get(CONF_DEVICE_ID)
            == device_id
        ]

        device_registry = dr.async_get(self._hass)
        target = async_get_device(self._hass, target_id)
        device = async_get_device(self._hass, device_id)
        if (
            not isinstance(target, dr.DeviceEntry)
            or not isinstance(device, dr.DeviceEntry)
            or target.composite_device_id is None
        ):
            return candidates
        for split in device_registry.async_get_devices_for_composite_device_id(
            target.composite_device_id
        ):
            if split.id == target_id or split.config_entry_id != device.config_entry_id:
                continue
            candidates.extend(
                entity.entity_id
                for entity in er.async_entries_for_device(
                    entity_registry, split.id, include_disabled_entities=True
                )
                if entity.config_entry_id == device.config_entry_id
            )
        return candidates

    @callback
    def _async_discover_merge_entity(self, entity_id: str) -> None:
        """Add an entity to a merge modification if it belongs to a merged device."""
        entity_registry = er.async_get(self._hass)
        if (
            entity := entity_registry.async_get(entity_id)
        ) is None or entity.device_id is None:
            return
        for config_entry in list(self._config_entries.values()):
            if modification_type(config_entry) != ModificationType.MERGE:
                continue
            sources = merge_sources(config_entry)
            if (
                entity.device_id not in sources
                or entity_id in sources[entity.device_id]
            ):
                continue
            self._async_discover_merge_entities(config_entry)

    @callback
    def _async_update_issue(self, config_entry: ConfigEntry[Any]) -> None:
        """Create or delete the repair issue about missing references of a modification."""
        issue_id = f"{ISSUE_MISSING_REFERENCES}_{config_entry.entry_id}"
        if not (missing := self._get_missing_references(config_entry)):
            ir.async_delete_issue(self._hass, DOMAIN, issue_id)
            return
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_MISSING_REFERENCES,
            translation_placeholders={
                "title": config_entry.title,
                "references": ", ".join(sorted(missing)),
            },
        )

    def _get_missing_references(self, config_entry: ConfigEntry[Any]) -> set[str]:
        """Return the entity ids and device ids a modification references but which do not exist."""
        entity_registry = er.async_get(self._hass)
        entity_ids, device_ids = _referenced_ids(config_entry)
        return {
            entity_id
            for entity_id in entity_ids
            if entity_registry.async_get(entity_id) is None
        } | {
            device_id
            for device_id in device_ids
            if async_get_device(self._hass, device_id) is None
        }


@callback
def async_resolve_references(
    hass: HomeAssistant, config_entry: ConfigEntry[Any]
) -> dict[str, Any] | None:
    """Return updated config entry data and options with resolved device ids.

    Devices that were split by Home Assistant 2026.8 get new ids, so references to
    the old composite device id are replaced by the id of the matching split device.
    Returns None if nothing needs to be changed.
    """
    data = dict(config_entry.data)
    options = modification_data(config_entry)

    def resolve(device_id: str, owner_config_entry_id: str | None = None) -> str:
        resolved = async_resolve_device_id(hass, device_id, owner_config_entry_id)
        if resolved is not None and resolved != device_id:
            _LOGGER.info(
                "Device %s referenced by modification %s was split by Home Assistant, "
                "using device %s instead",
                device_id,
                config_entry.title,
                resolved,
            )
            return resolved
        return device_id

    if modification_type(config_entry) != ModificationType.ENTITY:
        data[CONF_MODIFICATION_ENTRY_ID] = resolve(
            modification_entry_id(config_entry),
            config_entry.entry_id
            if modification_is_custom_entry(config_entry)
            else None,
        )
    for key in (CONF_DEVICE_ID, CONF_VIA_DEVICE_ID):
        if (device_id := options.get(key)) is not None:
            options[key] = resolve(device_id)
    if modification_type(config_entry) == ModificationType.MERGE:
        sources: dict[str, Any] = {}
        for device_id, device_data in data.get(
            CONF_MODIFICATION_ORIGINAL_DATA, {}
        ).items():
            resolved = resolve(device_id)
            if resolved == data[CONF_MODIFICATION_ENTRY_ID]:
                continue
            sources.setdefault(resolved, {CONF_ENTITIES: {}})[CONF_ENTITIES].update(
                device_data.get(CONF_ENTITIES, {})
            )
        data[CONF_MODIFICATION_ORIGINAL_DATA] = sources

    if data == dict(config_entry.data) and options == modification_data(config_entry):
        return None
    return {
        "data": data,
        "options": {**config_entry.options, CONF_MODIFICATION_DATA: options},
        "unique_id": f"{modification_type(config_entry)}_{data[CONF_MODIFICATION_ENTRY_ID]}",
    }


def _filter_data(mod_type: ModificationType, data: dict[str, Any]) -> dict[str, Any]:
    """Return the modifiable attributes of modification data in their JSON form."""
    return {
        key: None
        if (key, value)
        in (
            (CONF_ENTITY_CATEGORY, ENTITY_CATEGORY_DEFAULT),
            (CONF_ENTRY_TYPE, ENTRY_TYPE_NONE),
        )
        else value
        for key, value in data.items()
        if key in MODIFIABLE_ATTRIBUTES[mod_type]
    }


def _referenced_ids(config_entry: ConfigEntry[Any]) -> tuple[set[str], set[str]]:
    """Return the entity ids and device ids a modification references."""
    options = modification_data(config_entry)
    device_ids = {
        device_id
        for key in (CONF_DEVICE_ID, CONF_VIA_DEVICE_ID)
        if (device_id := options.get(key)) is not None
    }
    match modification_type(config_entry):
        case ModificationType.ENTITY:
            return {modification_entry_id(config_entry)}, device_ids
        case ModificationType.DEVICE:
            return set(assigned_entities(config_entry)), device_ids | {
                modification_entry_id(config_entry)
            }
        case ModificationType.MERGE:
            return set(), device_ids | {modification_entry_id(config_entry)}


def _references(
    config_entry: ConfigEntry[Any],
    *,
    entity_id: str | None = None,
    device_id: str | None = None,
) -> bool:
    """Return whether a modification references an entity or device."""
    entity_ids, device_ids = _referenced_ids(config_entry)
    return entity_id in entity_ids or device_id in device_ids


def _rename_entity(
    config_entry: ConfigEntry[Any], old_entity_id: str, entity_id: str
) -> dict[str, Any] | None:
    """Return updated config entry fields after an entity id changed."""
    match modification_type(config_entry):
        case ModificationType.ENTITY if (
            modification_entry_id(config_entry) == old_entity_id
        ):
            return {
                "data": {**config_entry.data, CONF_MODIFICATION_ENTRY_ID: entity_id},
                "unique_id": f"{ModificationType.ENTITY}_{entity_id}",
            }
        case ModificationType.DEVICE if old_entity_id in assigned_entities(
            config_entry
        ):
            options = modification_data(config_entry)
            options[CONF_ASSIGNED_ENTITIES] = [
                entity_id if assigned == old_entity_id else assigned
                for assigned in options[CONF_ASSIGNED_ENTITIES]
            ]
            return {
                "options": {**config_entry.options, CONF_MODIFICATION_DATA: options}
            }
        case ModificationType.MERGE if any(
            old_entity_id in entity_ids
            for entity_ids in merge_sources(config_entry).values()
        ):
            sources: dict[str, Any] = config_entry.data[CONF_MODIFICATION_ORIGINAL_DATA]
            return {
                "data": {
                    **config_entry.data,
                    CONF_MODIFICATION_ORIGINAL_DATA: {
                        device_id: {
                            **device_data,
                            CONF_ENTITIES: {
                                entity_id if key == old_entity_id else key: value
                                for key, value in device_data.get(
                                    CONF_ENTITIES, {}
                                ).items()
                            },
                        }
                        for device_id, device_data in sources.items()
                    },
                }
            }
    return None
