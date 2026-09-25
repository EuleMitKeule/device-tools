"""Migration of config entries created by previous versions of Device Tools."""

from __future__ import annotations

import logging
from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    CONF_ASSIGNED_ENTITIES,
    CONF_DEVICE_ID,
    CONF_ENTITIES,
    CONF_HW_VERSION,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_ENTRY_NAME,
    CONF_MODIFICATION_IS_CUSTOM_ENTRY,
    CONF_MODIFICATION_ORIGINAL_DATA,
    CONF_MODIFICATION_TYPE,
    CONF_SERIAL_NUMBER,
    CONF_SW_VERSION,
    CONF_VIA_DEVICE_ID,
    DOMAIN,
    MODIFIABLE_ATTRIBUTES,
    ModificationType,
)
from .data import DATA_KEY
from .original_data_store import KIND_DEVICES, KIND_ENTITIES, OriginalDataStore
from .utils import (
    async_get_device,
    async_resolve_device_id,
    get_default_config_entry_title,
    name_for_device,
)

_LOGGER = logging.getLogger(__name__)

VERSION = 2
MINOR_VERSION = 1

V1_ATTRIBUTES = [
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_SW_VERSION,
    CONF_HW_VERSION,
    CONF_SERIAL_NUMBER,
    CONF_VIA_DEVICE_ID,
]


async def async_migrate_entry(
    hass: HomeAssistant, config_entry: ConfigEntry[Any]
) -> bool:
    """Migrate a config entry created by a previous version."""
    if config_entry.version > VERSION:
        _LOGGER.error(
            "Modification %s was created by a newer version of Device Tools",
            config_entry.title,
        )
        return False

    if config_entry.version == 1:
        if not await _async_migrate_v1(hass, config_entry):
            return False
    elif config_entry.minor_version < 1:
        _migrate_v2_0(hass, config_entry)

    _LOGGER.info(
        "Migrated modification %s to version %s.%s",
        config_entry.title,
        VERSION,
        MINOR_VERSION,
    )
    return True


async def _async_migrate_v1(
    hass: HomeAssistant, config_entry: ConfigEntry[Any]
) -> bool:
    """Migrate a 1.x config entry in place.

    A 1.x config entry combined attribute changes, entity assignments and merges for
    a single device. The entry keeps its id and becomes a device modification, so
    devices created by it keep their id as well. Merges are moved to a separate
    merge modification.
    """
    if not (device_modification := config_entry.data.get("device_modification")):
        _LOGGER.error(
            "Modification %s has no data and cannot be migrated, please remove it",
            config_entry.title,
        )
        return False

    device = _get_v1_device(hass, config_entry, device_modification)
    modification_data = _get_v1_modification_data(hass, device_modification)
    merge_device_ids = _get_v1_merge_device_ids(hass, device_modification, device)

    if device is None or (DOMAIN, config_entry.entry_id) in device.identifiers:
        _migrate_v1_device(
            hass,
            config_entry,
            config_entry.entry_id if device is None else device.id,
            device_modification.get("device_name") or config_entry.title,
            modification_data,
            is_custom_entry=True,
        )
    elif modification_data or not merge_device_ids:
        _migrate_v1_device(
            hass,
            config_entry,
            device.id,
            name_for_device(device),
            modification_data,
            is_custom_entry=False,
        )
    else:
        fields = _merge_entry_fields(
            device.id, name_for_device(device), merge_device_ids
        )
        del fields["title"]
        hass.config_entries.async_update_entry(
            config_entry, **fields, version=VERSION, minor_version=MINOR_VERSION
        )
        return True

    if device is not None and merge_device_ids:
        await _async_add_merge_entry(hass, config_entry, device, merge_device_ids)
    return True


def _get_v1_device(
    hass: HomeAssistant,
    config_entry: ConfigEntry[Any],
    device_modification: dict[str, Any],
) -> dr.AnyDeviceEntry | None:
    """Return the device of a 1.x modification or None if it does not exist."""
    if (device_id := device_modification.get("device_id")) is None:
        return None
    if (resolved := async_resolve_device_id(hass, device_id)) is not None and (
        device := async_get_device(hass, resolved)
    ) is not None:
        return device
    _LOGGER.warning(
        "Device %s of modification %s no longer exists, it will be recreated",
        device_id,
        config_entry.title,
    )
    return None


def _get_v1_modification_data(
    hass: HomeAssistant, device_modification: dict[str, Any]
) -> dict[str, Any]:
    """Return the modification data of the device of a 1.x modification."""
    attribute_modification = device_modification.get("attribute_modification") or {}
    modification_data: dict[str, Any] = {
        key: value
        for key in V1_ATTRIBUTES
        if (value := attribute_modification.get(key))
    }
    if CONF_VIA_DEVICE_ID in modification_data:
        via_device_id = async_resolve_device_id(
            hass, modification_data.pop(CONF_VIA_DEVICE_ID)
        )
        if via_device_id is not None:
            modification_data[CONF_VIA_DEVICE_ID] = via_device_id
    entity_modification = device_modification.get("entity_modification") or {}
    if assigned_entities := _resolve_v1_entities(
        hass, entity_modification.get(CONF_ENTITIES, [])
    ):
        modification_data[CONF_ASSIGNED_ENTITIES] = assigned_entities
    return modification_data


def _get_v1_merge_device_ids(
    hass: HomeAssistant,
    device_modification: dict[str, Any],
    device: dr.AnyDeviceEntry | None,
) -> list[str]:
    """Return the ids of the devices merged by a 1.x modification."""
    merge_modification = device_modification.get("merge_modification") or {}
    return [
        merge_device_id
        for device_id in merge_modification.get("devices", [])
        if (merge_device_id := async_resolve_device_id(hass, device_id)) is not None
        and (device is None or merge_device_id != device.id)
    ]


def _migrate_v1_device(
    hass: HomeAssistant,
    config_entry: ConfigEntry[Any],
    device_id: str,
    device_name: str,
    modification_data: dict[str, Any],
    *,
    is_custom_entry: bool,
) -> None:
    """Turn a 1.x modification into a device modification."""
    hass.config_entries.async_update_entry(
        config_entry,
        data={
            CONF_MODIFICATION_TYPE: ModificationType.DEVICE,
            CONF_MODIFICATION_ENTRY_ID: device_id,
            CONF_MODIFICATION_ENTRY_NAME: device_name,
            CONF_MODIFICATION_IS_CUSTOM_ENTRY: is_custom_entry,
            CONF_MODIFICATION_ORIGINAL_DATA: {},
        },
        options={CONF_MODIFICATION_DATA: modification_data},
        unique_id=f"{ModificationType.DEVICE}_{device_id}",
        version=VERSION,
        minor_version=MINOR_VERSION,
    )


async def _async_add_merge_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry[Any],
    device: dr.AnyDeviceEntry,
    merge_device_ids: list[str],
) -> None:
    """Add a merge modification for the merges of a 1.x modification."""
    fields = _merge_entry_fields(device.id, name_for_device(device), merge_device_ids)
    if hass.config_entries.async_entry_for_domain_unique_id(
        DOMAIN, fields["unique_id"]
    ):
        return
    await hass.config_entries.async_add(
        ConfigEntry(
            data=fields["data"],
            discovery_keys=MappingProxyType({}),
            domain=DOMAIN,
            minor_version=MINOR_VERSION,
            options=fields["options"],
            source=config_entry.source,
            subentries_data=None,
            title=fields["title"],
            unique_id=fields["unique_id"],
            version=VERSION,
            disabled_by=config_entry.disabled_by,
        )
    )


def _merge_entry_fields(
    device_id: str, device_name: str, merge_device_ids: list[str]
) -> dict[str, Any]:
    """Return the config entry fields of a merge modification."""
    return {
        "data": {
            CONF_MODIFICATION_TYPE: ModificationType.MERGE,
            CONF_MODIFICATION_ENTRY_ID: device_id,
            CONF_MODIFICATION_ENTRY_NAME: device_name,
            CONF_MODIFICATION_IS_CUSTOM_ENTRY: False,
            CONF_MODIFICATION_ORIGINAL_DATA: {
                merge_device_id: {CONF_ENTITIES: {}}
                for merge_device_id in dict.fromkeys(merge_device_ids)
            },
        },
        "options": {CONF_MODIFICATION_DATA: {}},
        "title": get_default_config_entry_title(ModificationType.MERGE, device_name),
        "unique_id": f"{ModificationType.MERGE}_{device_id}",
    }


def _resolve_v1_entities(hass: HomeAssistant, entity_ids: list[str]) -> list[str]:
    """Return the entity ids of entities stored by 1.x.

    1.x stored entity registry ids. Entities already on the device are kept, since
    1.x had moved them there and their integration would move them back otherwise.
    """
    entity_registry = er.async_get(hass)
    resolved: list[str] = []
    for entity_id in entity_ids:
        if (entity := entity_registry.async_get(entity_id)) is None:
            _LOGGER.warning("Entity %s no longer exists, skipping it", entity_id)
            continue
        if entity.entity_id not in resolved:
            resolved.append(entity.entity_id)
    return resolved


def _migrate_v2_0(hass: HomeAssistant, config_entry: ConfigEntry[Any]) -> None:
    """Migrate a 2.0 config entry to 2.1.

    2.0 kept original values in the config entry. They are moved to the original
    data store, and attributes which can no longer be modified are dropped.
    """
    store = hass.data[DATA_KEY].store
    modification_type = ModificationType(config_entry.data[CONF_MODIFICATION_TYPE])
    target_id: str = config_entry.data[CONF_MODIFICATION_ENTRY_ID]
    original_data: dict[str, Any] = config_entry.data.get(
        CONF_MODIFICATION_ORIGINAL_DATA, {}
    )
    modification_data: dict[str, Any] = {
        key: value
        for key, value in config_entry.options.get(CONF_MODIFICATION_DATA, {}).items()
        if key in MODIFIABLE_ATTRIBUTES[modification_type]
        or (
            modification_type == ModificationType.DEVICE
            and key == CONF_ASSIGNED_ENTITIES
        )
    }

    match modification_type:
        case ModificationType.DEVICE:
            _seed_original_data(
                store, KIND_DEVICES, target_id, original_data, modification_data
            )
            original_data = {}
        case ModificationType.ENTITY:
            _seed_original_data(
                store, KIND_ENTITIES, target_id, original_data, modification_data
            )
            original_data = {}
        case ModificationType.MERGE:
            original_data = _migrate_v2_0_merge(store, original_data)

    hass.config_entries.async_update_entry(
        config_entry,
        data={**config_entry.data, CONF_MODIFICATION_ORIGINAL_DATA: original_data},
        options={**config_entry.options, CONF_MODIFICATION_DATA: modification_data},
        minor_version=MINOR_VERSION,
    )


def _seed_original_data(
    store: OriginalDataStore,
    kind: str,
    target_id: str,
    original_data: dict[str, Any],
    modification_data: dict[str, Any],
) -> None:
    """Store the original values of modified attributes kept by 2.0."""
    stored = store.get(kind, target_id)
    for key in modification_data:
        if key in original_data and key not in stored:
            store.async_set(kind, target_id, key, _json_value(original_data[key]))


def _migrate_v2_0_merge(
    store: OriginalDataStore, original_data: dict[str, Any]
) -> dict[str, Any]:
    """Store the original devices of merged entities and return the merged devices."""
    for device_id, device_data in original_data.items():
        for entity_id, entity_data in device_data.get(CONF_ENTITIES, {}).items():
            _seed_original_data(
                store,
                KIND_ENTITIES,
                entity_id,
                {CONF_DEVICE_ID: entity_data.get(CONF_DEVICE_ID, device_id)},
                {CONF_DEVICE_ID: None},
            )
    return {
        device_id: {
            CONF_ENTITIES: {
                entity_id: {} for entity_id in device_data.get(CONF_ENTITIES, {})
            }
        }
        for device_id, device_data in original_data.items()
    }


def _json_value(value: Any) -> Any:
    """Return the JSON representation of a stored original value."""
    if hasattr(value, "value"):
        return value.value
    return value
