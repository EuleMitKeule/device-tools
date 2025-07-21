"""Device tools for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import (
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_ENTRY_NAME,
    CONF_MODIFICATION_IS_CUSTOM_ENTRY,
    CONF_MODIFICATION_TYPE,
    DOMAIN,
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


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Set up the device tools component."""
    _LOGGER.debug("Setting up Device Tools")

    hass.data[DATA_KEY] = DeviceToolsData(
        device_listener=DeviceListener(hass),
        entity_listener=EntityListener(hass),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up the config entry."""
    _LOGGER.debug("Setting up Device Tools config entry %s", config_entry.entry_id)
    _LOGGER.debug("Config entry data: %s", config_entry.data)
    _LOGGER.debug("Config entry options: %s", config_entry.options)

    device_tools_data: DeviceToolsData = hass.data[DATA_KEY]

    modification_type: ModificationType = config_entry.data[CONF_MODIFICATION_TYPE]
    modification_entry_id: str = config_entry.data[CONF_MODIFICATION_ENTRY_ID]
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
        modification_entry_id = device.id
        hass.config_entries.async_update_entry(
            config_entry,
            data={
                **config_entry.data,
                CONF_MODIFICATION_ENTRY_ID: device.id,
            },
        )

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

    device_tools_data.modifications[modification_entry_id] = modification

    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))

    await modification.apply()
    return True


async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.debug("Updating Device Tools config entry %s", config_entry.entry_id)

    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Handle config entry unload."""
    _LOGGER.debug("Unloading Device Tools config entry %s", config_entry.entry_id)

    device_tools_data: DeviceToolsData = hass.data[DATA_KEY]

    modification_entry_id: str = config_entry.data[CONF_MODIFICATION_ENTRY_ID]
    modification_is_custom_entry: bool = config_entry.data[
        CONF_MODIFICATION_IS_CUSTOM_ENTRY
    ]
    modification = device_tools_data.modifications.pop(modification_entry_id)

    if modification:
        await modification.revert()

    if modification_is_custom_entry:
        _LOGGER.debug(
            "Removing device for modification entry %s",
            config_entry.entry_id,
        )
        dr.async_get(hass).async_remove_device(modification_entry_id)

    return True


# async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
#     """Migrate old entry."""
#     _LOGGER.debug(
#         "Migrating Device Tools config entry %s from %s",
#         config_entry.entry_id,
#         f"v{config_entry.version}.{config_entry.minor_version}",
#     )

#     device_registry = dr.async_get(hass)
#     entity_registry = er.async_get(hass)

#     if config_entry.version == 1:
#         device = device_registry.async_get(config_entry.data["device_id"])

#         if not device:
#             _LOGGER.debug(
#                 "Device with ID %s not found, skipping migration of Device Tools config entry %s",
#                 device.id,
#                 config_entry.entry_id,
#             )
#             return False

#         new_data = {
#             CONF_MODIFICATION_TYPE: ModificationType.DEVICE,
#             CONF_MODIFICATION_ENTRY_ID: device.id,
#         }
#         new_options: dict[str, Any] = {}

#         if "attribute_modification" in config_entry.data:
#             for old_key, new_key in [
#                 ("manufacturer", CONF_MANUFACTURER),
#                 ("model", CONF_MODEL),
#                 ("sw_version", CONF_SW_VERSION),
#                 ("hw_version", CONF_HW_VERSION),
#                 ("serial_number", CONF_SERIAL_NUMBER),
#                 ("via_device_id", CONF_VIA_DEVICE_ID),
#             ]:
#                 if old_key not in config_entry.data["attribute_modification"]:
#                     continue

#                 new_options[new_key] = config_entry.data["attribute_modification"][
#                     old_key
#                 ]

#             new_options[CONF_MODIFICATION_DATA] = {
#                 CONF_MANUFACTURER: config_entry.data["attribute_modification"][
#                     "manufacturer"
#                 ],
#             }

#         new_title = device.name_by_user or device.name or device.id

#         hass.config_entries.async_update_entry(
#             config_entry,
#             data=new_data,
#             options=new_options,
#             title=new_title,
#             unique_id=device.id,
#             version=2,
#             minor_version=0,
#         )

#     if "entity_modification" in config_entry.data:
#         for entity_id in config_entry.data["entity_modification"]["entities"]:
#             entity = entity_registry.async_get(entity_id)

#             if not entity:
#                 _LOGGER.debug(
#                     "Entity with ID %s not found, skipping migration of entity modification of Device Tools config entry %s",
#                     entity_id,
#                     config_entry.entry_id,
#                 )
#                 continue

#             new_data = {
#                 CONF_MODIFICATION_TYPE: ModificationType.ENTITY,
#                 CONF_MODIFICATION_ENTRY_ID: entity.id,
#             }
#             new_options: dict[str, Any] = {
#                 CONF_MODIFICATION_DATA: {
#                     CONF_DEVICE_ID: device.id,
#                 }
#             }

#             new_title = entity.name or entity.original_name or entity.entity_id

#             await hass.config_entries.async_add(
#                 ConfigEntry(
#                     config_entry,
#                     data=new_data,
#                     domain=DOMAIN,
#                     entry_id=f"{config_entry.entry_id}-{entity.id}",
#                     options=new_options,
#                     title=new_title,
#                     version=2,
#                     minor_version=0,
#                     unique_id=entity.id,
#                     source=SOURCE_USER,
#                 )
#             )

#     if "merge_modification" in config_entry.data:
#         # TODO: Implement migration of merge modification
#         pass

#     _LOGGER.debug(
#         "Successfully migrated Device Tools config entry %s to latest version",
#         config_entry.entry_id,
#     )

#     return True
