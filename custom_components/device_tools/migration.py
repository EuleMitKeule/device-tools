"""Migration of config entries created by previous versions of Device Tools."""

from __future__ import annotations

import logging
from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

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
from .original_data_store import KIND_DEVICES, KIND_ENTITIES
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

    device_name: str = device_modification.get("device_name") or config_entry.title
    device_id = async_resolve_device_id(hass, device_modification.get("device_id"))
    device = async_get_device(hass, device_id) if device_id is not None else None
    is_custom_entry = (
        device is None or (DOMAIN, config_entry.entry_id) in device.identifiers
    )
    if device is None and device_modification.get("device_id") is not None:
        _LOGGER.warning(
            "Device %s of modification %s no longer exists, it will be recreated",
            device_modification["device_id"],
            config_entry.title,
        )

    modification_data: dict[str, Any] = {
        key: value
        for key in V1_ATTRIBUTES
        if (value := (device_modification.get("attribute_modification") or {}).get(key))
    }
    if (via_device_id := modification_data.get(CONF_VIA_DEVICE_ID)) is not None:
        if (resolved := async_resolve_device_id(hass, via_device_id)) is None:
            del modification_data[CONF_VIA_DEVICE_ID]
        else:
            modification_data[CONF_VIA_DEVICE_ID] = resolved
    if assigned_entities := _resolve_v1_entities(
        hass,
        (device_modification.get("entity_modification") or {}).get(CONF_ENTITIES, []),
    ):
        modification_data[CONF_ASSIGNED_ENTITIES] = assigned_entities

    merge_device_ids = [
        merge_device_id
        for source_id in (device_modification.get("merge_modification") or {}).get(
            "devices", []
        )
        if (merge_device_id := async_resolve_device_id(hass, source_id)) is not None
        and merge_device_id != device_id
    ]

    if (
        device is not None
        and not is_custom_entry
        and not modification_data
        and merge_device_ids
    ):
        fields = _merge_entry_fields(
            device.id, name_for_device(device), merge_device_ids
        )
        del fields["title"]
        hass.config_entries.async_update_entry(
            config_entry,
            **fields,
            version=VERSION,
            minor_version=MINOR_VERSION,
        )
        return True

    target_id = (
        config_entry.entry_id if device_id is None or device is None else device_id
    )
    hass.config_entries.async_update_entry(
        config_entry,
        data={
            CONF_MODIFICATION_TYPE: ModificationType.DEVICE,
            CONF_MODIFICATION_ENTRY_ID: target_id,
            CONF_MODIFICATION_ENTRY_NAME: device_name
            if is_custom_entry or device is None
            else name_for_device(device),
            CONF_MODIFICATION_IS_CUSTOM_ENTRY: is_custom_entry,
            CONF_MODIFICATION_ORIGINAL_DATA: {},
        },
        options={CONF_MODIFICATION_DATA: modification_data},
        unique_id=f"{ModificationType.DEVICE}_{target_id}",
        version=VERSION,
        minor_version=MINOR_VERSION,
    )

    if merge_device_ids and device is not None:
        fields = _merge_entry_fields(
            device.id, name_for_device(device), merge_device_ids
        )
        if hass.config_entries.async_entry_for_domain_unique_id(
            DOMAIN, fields["unique_id"]
        ):
            return True
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
    return True


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
        case ModificationType.DEVICE | ModificationType.ENTITY:
            kind = (
                KIND_DEVICES
                if modification_type == ModificationType.DEVICE
                else KIND_ENTITIES
            )
            stored = store.get(kind, target_id)
            for key in modification_data:
                if key in original_data and key not in stored:
                    store.async_set(
                        kind, target_id, key, _json_value(original_data[key])
                    )
            original_data = {}
        case ModificationType.MERGE:
            for device_data in original_data.values():
                for entity_id, entity_data in device_data.get(
                    CONF_ENTITIES, {}
                ).items():
                    if (
                        CONF_DEVICE_ID in entity_data
                        and CONF_DEVICE_ID not in store.get(KIND_ENTITIES, entity_id)
                    ):
                        store.async_set(
                            KIND_ENTITIES,
                            entity_id,
                            CONF_DEVICE_ID,
                            entity_data[CONF_DEVICE_ID],
                        )
            original_data = {
                device_id: {
                    CONF_ENTITIES: {
                        entity_id: {}
                        for entity_id in device_data.get(CONF_ENTITIES, {})
                    }
                }
                for device_id, device_data in original_data.items()
            }

    hass.config_entries.async_update_entry(
        config_entry,
        data={**config_entry.data, CONF_MODIFICATION_ORIGINAL_DATA: original_data},
        options={**config_entry.options, CONF_MODIFICATION_DATA: modification_data},
        minor_version=MINOR_VERSION,
    )


def _json_value(value: Any) -> Any:
    """Return the JSON representation of a stored original value."""
    if hasattr(value, "value"):
        return value.value
    return value
