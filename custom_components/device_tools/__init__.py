"""Device tools for Home Assistant."""

from __future__ import annotations

import logging
from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.typing import ConfigType

from .config_flow import DeviceToolsConfigFlow
from .const import (
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
from .data import DATA_KEY, DeviceToolsData
from .device_listener import DeviceListener
from .device_modification import DeviceModification
from .entity_listener import EntityListener
from .entity_modification import EntityModification
from .merge_modification import MergeModification

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
_LOGGER = logging.getLogger(__name__)


def setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Set up the device tools component."""
    _LOGGER.debug("Setting up Device Tools")

    hass.data[DATA_KEY] = DeviceToolsData(
        device_listener=DeviceListener(hass),
        entity_listener=EntityListener(hass),
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry[Any]
) -> bool:
    """Set up the config entry."""
    if config_entry.version < 2:
        return False

    if config_entry.unique_id is None:
        _LOGGER.error(
            "Config entry %s is missing a unique_id, cannot set up modification",
            config_entry.entry_id,
        )
        return False

    _LOGGER.debug("Setting up Device Tools config entry %s", config_entry.entry_id)
    _LOGGER.debug("Config entry data: %s", config_entry.data)
    _LOGGER.debug("Config entry options: %s", config_entry.options)

    device_tools_data: DeviceToolsData = hass.data[DATA_KEY]

    modification_type: ModificationType = config_entry.data[CONF_MODIFICATION_TYPE]
    modification_entry_name: str = config_entry.data[CONF_MODIFICATION_ENTRY_NAME]
    modification_is_custom_entry: bool = config_entry.data[
        CONF_MODIFICATION_IS_CUSTOM_ENTRY
    ]

    if modification_is_custom_entry:
        _LOGGER.debug(
            "Creating device for modification entry %s",
            config_entry.entry_id,
        )
        device = dr.async_get(hass).async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=modification_entry_name,
        )
        hass.config_entries.async_update_entry(
            config_entry,
            unique_id=f"{modification_type}_{device.id}",
            data={
                **config_entry.data,
                CONF_MODIFICATION_ENTRY_ID: device.id,
            },
        )

    modification: DeviceModification | EntityModification | MergeModification
    match modification_type:
        case ModificationType.DEVICE:
            modification = DeviceModification(
                hass,
                config_entry,
                device_tools_data.device_listener,
            )
        case ModificationType.ENTITY:
            modification = EntityModification(
                hass,
                config_entry,
                device_tools_data.entity_listener,
            )
        case ModificationType.MERGE:
            modification = MergeModification(
                hass,
                config_entry,
                device_tools_data.device_listener,
                device_tools_data.entity_listener,
            )

    device_tools_data.modifications[config_entry.unique_id] = modification

    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))

    await modification.apply()
    return True


async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry[Any]) -> None:
    """Handle options update."""
    _LOGGER.debug("Updating Device Tools config entry %s", config_entry.entry_id)

    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, config_entry: ConfigEntry[Any]
) -> bool:
    """Handle config entry unload."""
    if config_entry.unique_id is None:
        _LOGGER.error(
            "Config entry %s is missing a unique_id, cannot unload modification",
            config_entry.entry_id,
        )
        return False

    _LOGGER.debug("Unloading Device Tools config entry %s", config_entry.entry_id)

    device_tools_data: DeviceToolsData = hass.data[DATA_KEY]

    modification_entry_id: str = config_entry.data[CONF_MODIFICATION_ENTRY_ID]
    modification_is_custom_entry: bool = config_entry.data[
        CONF_MODIFICATION_IS_CUSTOM_ENTRY
    ]
    modification = device_tools_data.modifications.pop(config_entry.unique_id)

    if modification:
        await modification.revert()

    if modification_is_custom_entry:
        _LOGGER.debug(
            "Removing device for modification entry %s",
            config_entry.entry_id,
        )
        dr.async_get(hass).async_remove_device(modification_entry_id)

    return True


async def _async_add_entry(
    hass: HomeAssistant,
    modification_entry_id: str,
    modification_entry_name: str,
    modification_type: ModificationType,
    modification_data: dict[str, Any],
    modification_original_data: dict[str, Any],
    modification_is_custom_entry: bool,
    config_entry: ConfigEntry[Any],
) -> None:
    """Add a new config entry."""
    new_config_entry: ConfigEntry[Any] = ConfigEntry(
        created_at=config_entry.created_at,
        data={
            CONF_MODIFICATION_ENTRY_ID: modification_entry_id,
            CONF_MODIFICATION_ENTRY_NAME: modification_entry_name,
            CONF_MODIFICATION_IS_CUSTOM_ENTRY: modification_is_custom_entry,
            CONF_MODIFICATION_ORIGINAL_DATA: modification_original_data,
            CONF_MODIFICATION_TYPE: modification_type,
        },
        disabled_by=config_entry.disabled_by,
        discovery_keys=config_entry.discovery_keys,
        domain=DOMAIN,
        minor_version=DeviceToolsConfigFlow.MINOR_VERSION,
        options={
            CONF_MODIFICATION_DATA: modification_data,
        },
        pref_disable_new_entities=config_entry.pref_disable_new_entities,
        pref_disable_polling=config_entry.pref_disable_polling,
        source=config_entry.source,
        subentries_data=MappingProxyType({}),
        title=modification_entry_name,
        unique_id=f"{modification_type.value}_{modification_entry_id}",
        version=DeviceToolsConfigFlow.VERSION,
    )
    await hass.config_entries.async_add(new_config_entry)


async def _async_migrate_creation_modification(
    hass: HomeAssistant,
    config_entry: ConfigEntry[Any],
    device_id: str,
    device_name: str,
    attribute_modification: dict[str, Any] | None,
) -> None:
    """Migrate creation modification to new format."""
    modification_data: dict[str, Any] = {}

    if attribute_modification:
        modification_data = {
            new_key: old_value
            for old_key, new_key in {
                "manufacturer": CONF_MANUFACTURER,
                "model": CONF_MODEL,
                "sw_version": CONF_SW_VERSION,
                "hw_version": CONF_HW_VERSION,
                "serial_number": CONF_SERIAL_NUMBER,
                "via_device_id": CONF_VIA_DEVICE_ID,
            }.items()
            if old_key in attribute_modification
            and (old_value := attribute_modification[old_key])
        }

    await _async_add_entry(
        hass=hass,
        modification_entry_id=device_id,
        modification_entry_name=device_name,
        modification_type=ModificationType.DEVICE,
        modification_data=modification_data,
        modification_is_custom_entry=True,
        modification_original_data={},
        config_entry=config_entry,
    )


async def _async_migrate_attribute_modification(
    hass: HomeAssistant,
    config_entry: ConfigEntry[Any],
    device_id: str,
    device: dr.DeviceEntry,
    modification_name: str,
    attribute_modification: dict[str, Any],
) -> None:
    """Migrate attribute modification to new format."""
    modification_original_data = {
        k: v
        for k, v in device.dict_repr.items()
        if k in MODIFIABLE_ATTRIBUTES[ModificationType.DEVICE]
    }

    modification_data: dict[str, Any] = {
        new_key: old_value
        for old_key, new_key in {
            "manufacturer": CONF_MANUFACTURER,
            "model": CONF_MODEL,
            "sw_version": CONF_SW_VERSION,
            "hw_version": CONF_HW_VERSION,
            "serial_number": CONF_SERIAL_NUMBER,
            "via_device_id": CONF_VIA_DEVICE_ID,
        }.items()
        if old_key in attribute_modification
        and (old_value := attribute_modification[old_key])
    }

    await _async_add_entry(
        hass=hass,
        modification_entry_id=device_id,
        modification_entry_name=modification_name,
        modification_type=ModificationType.DEVICE,
        modification_data=modification_data,
        modification_is_custom_entry=False,
        modification_original_data=modification_original_data,
        config_entry=config_entry,
    )


async def _async_migrate_entity_modification(
    hass: HomeAssistant,
    config_entry: ConfigEntry[Any],
    device_id: str,
    modification_name: str,
    entity_modification: dict[str, Any],
) -> None:
    """Migrate entity modification to new format."""
    entity_registry = er.async_get(hass)
    entities = entity_modification.get("entities", [])

    for modification_entry_id in entities:
        if not (entity := entity_registry.async_get(modification_entry_id)):
            _LOGGER.warning(
                "Entity %s not found during entity modification migration",
                modification_entry_id,
            )
            continue

        if entity.device_id == device_id:
            continue

        modification_original_data: dict[str, Any] = {
            k: v
            for k, v in entity.extended_dict.items()
            if k in MODIFIABLE_ATTRIBUTES[ModificationType.ENTITY]
        }

        modification_data: dict[str, Any] = {
            CONF_DEVICE_ID: device_id,
        }

        await _async_add_entry(
            hass=hass,
            modification_entry_id=modification_entry_id,
            modification_entry_name=modification_name,
            modification_type=ModificationType.ENTITY,
            modification_data=modification_data,
            modification_is_custom_entry=False,
            modification_original_data=modification_original_data,
            config_entry=config_entry,
        )


async def _async_migrate_merge_modification(
    hass: HomeAssistant,
    config_entry: ConfigEntry[Any],
    device_id: str,
    modification_name: str,
    merge_modification: dict[str, Any],
) -> None:
    """Migrate merge modification to new format."""
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    devices = merge_modification.get("devices", [])

    modification_original_data: dict[str, Any] = {}

    for merge_device_entry_id in devices:
        if not device_registry.async_get(merge_device_entry_id):
            _LOGGER.warning(
                "Device %s not found during merge modification migration",
                merge_device_entry_id,
            )
            continue

        merge_device_entities = er.async_entries_for_device(
            entity_registry,
            merge_device_entry_id,
            include_disabled_entities=True,
        )

        entities_data: dict[str, dict[str, Any]] = {}
        for merge_entity_entry in merge_device_entities:
            entities_data[merge_entity_entry.entity_id] = {
                k: v
                for k, v in merge_entity_entry.extended_dict.items()
                if k in MODIFIABLE_ATTRIBUTES[ModificationType.ENTITY]
            }

        modification_original_data[merge_device_entry_id] = {
            CONF_ENTITIES: entities_data,
        }

    await _async_add_entry(
        hass=hass,
        modification_entry_id=device_id,
        modification_entry_name=modification_name,
        modification_type=ModificationType.MERGE,
        modification_data={},
        modification_is_custom_entry=False,
        modification_original_data=modification_original_data,
        config_entry=config_entry,
    )


async def async_migrate_entry(
    hass: HomeAssistant, config_entry: ConfigEntry[Any]
) -> bool:
    """Migrate old entry."""
    if config_entry.version >= 2:
        return True

    if not (device_modification := config_entry.data.get("device_modification")):
        return False

    device_registry = dr.async_get(hass)
    device_id = device_modification.get("device_id")
    device_name = device_modification.get("device_name", "Unknown Device")
    if not (device := device_registry.async_get(device_id)):
        return False

    modification_name = device_modification.get("modification_name", "")
    modification_is_custom_entry = (
        len(device.config_entries) == 1
        and config_entry.entry_id in device.config_entries
    )

    if modification_is_custom_entry:
        await _async_migrate_creation_modification(
            hass,
            config_entry,
            device_id,
            device_name,
            device_modification.get("attribute_modification"),
        )

    if not modification_is_custom_entry and (
        attribute_modification := device_modification.get("attribute_modification")
    ):
        await _async_migrate_attribute_modification(
            hass,
            config_entry,
            device_id,
            device,
            modification_name,
            attribute_modification,
        )

    if entity_modification := device_modification.get("entity_modification"):
        await _async_migrate_entity_modification(
            hass,
            config_entry,
            device_id,
            modification_name,
            entity_modification,
        )

    if merge_modification := device_modification.get("merge_modification"):
        await _async_migrate_merge_modification(
            hass,
            config_entry,
            device_id,
            modification_name,
            merge_modification,
        )

    hass.create_task(hass.config_entries.async_remove(config_entry.entry_id))

    _LOGGER.info(
        "Successfully migrated Device Tools config entry %s to v%s.%s",
        config_entry.entry_id,
        DeviceToolsConfigFlow.VERSION,
        DeviceToolsConfigFlow.MINOR_VERSION,
    )

    return True
