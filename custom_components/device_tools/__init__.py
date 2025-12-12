"""Device tools for Home Assistant."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import SOURCE_USER, ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_DEVICE_ID,
    CONF_HW_VERSION,
    CONF_MANUFACTURER,
    CONF_MERGE_DEVICE_IDS,
    CONF_MODEL,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_ENTRY_NAME,
    CONF_MODIFICATION_IS_CUSTOM_ENTRY,
    CONF_MODIFICATION_TYPE,
    CONF_SERIAL_NUMBER,
    CONF_SW_VERSION,
    CONF_VIA_DEVICE_ID,
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


def setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Set up the device tools component."""
    _LOGGER.debug("Setting up Device Tools")

    hass.data[DATA_KEY] = DeviceToolsData(
        device_listener=DeviceListener(hass),
        entity_listener=EntityListener(hass),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up the config entry."""
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


async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.debug("Updating Device Tools config entry %s", config_entry.entry_id)

    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
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


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug(
        "Migrating Device Tools config entry %s from v%s.%s",
        config_entry.entry_id,
        config_entry.version,
        config_entry.minor_version,
    )

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    if config_entry.version == 1:
        # Handle device attribute modifications
        if "device_id" in config_entry.data:
            device = device_registry.async_get(config_entry.data["device_id"])

            if not device:
                _LOGGER.warning(
                    "Device with ID %s not found, removing Device Tools config entry %s",
                    config_entry.data["device_id"],
                    config_entry.entry_id,
                )
                hass.async_create_task(
                    hass.config_entries.async_remove(config_entry.entry_id)
                )
                return False

            new_data = {
                CONF_MODIFICATION_TYPE: ModificationType.DEVICE,
                CONF_MODIFICATION_ENTRY_ID: device.id,
                CONF_MODIFICATION_ENTRY_NAME: device.name_by_user
                or device.name
                or device.id,
                CONF_MODIFICATION_IS_CUSTOM_ENTRY: False,
            }
            new_options: dict[str, Any] = {}

            # Migrate attribute modifications to new format
            if "attribute_modification" in config_entry.data:
                modification_data = {}
                for old_key, new_key in [
                    ("manufacturer", CONF_MANUFACTURER),
                    ("model", CONF_MODEL),
                    ("sw_version", CONF_SW_VERSION),
                    ("hw_version", CONF_HW_VERSION),
                    ("serial_number", CONF_SERIAL_NUMBER),
                    ("via_device_id", CONF_VIA_DEVICE_ID),
                ]:
                    if old_key in config_entry.data["attribute_modification"]:
                        modification_data[new_key] = config_entry.data[
                            "attribute_modification"
                        ][old_key]

                if modification_data:
                    new_options[CONF_MODIFICATION_DATA] = modification_data

            new_title = (
                device.name_by_user or device.name or device.id or "Unknown Device"
            )

            hass.config_entries.async_update_entry(
                config_entry,
                data=new_data,
                options=new_options,
                title=new_title,
                unique_id=device.id,
                version=2,
                minor_version=1,
            )

        # Handle entity modifications - create separate config entries
        if "entity_modification" in config_entry.data:
            entities_data = config_entry.data["entity_modification"]
            target_device_id = entities_data.get("device_id")

            for entity_id in entities_data.get("entities", []):
                entity = entity_registry.async_get(entity_id)

                if not entity:
                    _LOGGER.warning(
                        "Entity %s not found, skipping migration of entity modification in config entry %s",
                        entity_id,
                        config_entry.entry_id,
                    )
                    continue

                new_data = {
                    CONF_MODIFICATION_TYPE: ModificationType.ENTITY,
                    CONF_MODIFICATION_ENTRY_ID: entity.id,
                    CONF_MODIFICATION_ENTRY_NAME: (
                        entity.name or entity.original_name or entity.entity_id
                    ),
                    CONF_MODIFICATION_IS_CUSTOM_ENTRY: False,
                }
                new_options: dict[str, Any] = {}

                # Add device assignment if specified
                if target_device_id:
                    new_options[CONF_MODIFICATION_DATA] = {
                        CONF_DEVICE_ID: target_device_id,
                    }

                new_title = (
                    entity.name
                    or entity.original_name
                    or entity.entity_id
                    or "Unknown Entity"
                )

                # Create new config entry for this entity modification
                result = await hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": SOURCE_USER},
                    data=new_data,
                )

                if result.get("type") == "create_entry":
                    _LOGGER.debug(
                        "Created new config entry for entity %s during migration",
                        entity_id,
                    )
                    # Update the new entry with options
                    if new_options and (result_entry := result.get("result")):
                        new_entry = hass.config_entries.async_get_entry(
                            result_entry.entry_id
                        )
                        if new_entry:
                            hass.config_entries.async_update_entry(
                                new_entry,
                                options=new_options,
                                title=new_title,
                                unique_id=entity.id,
                                version=2,
                                minor_version=1,
                            )

            # Remove the original config entry if it was only for entity modifications
            if "device_id" not in config_entry.data:
                _LOGGER.debug(
                    "Removing original entity-only config entry %s after migration",
                    config_entry.entry_id,
                )
                hass.async_create_task(
                    hass.config_entries.async_remove(config_entry.entry_id)
                )
                return True

        # Handle merge modifications
        if "merge_modification" in config_entry.data:
            merge_data = config_entry.data["merge_modification"]
            device_ids = merge_data.get("device_ids", [])

            # Verify all devices exist
            valid_devices = []
            for device_id in device_ids:
                device = device_registry.async_get(device_id)
                if device:
                    valid_devices.append(device_id)
                else:
                    _LOGGER.warning(
                        "Device %s not found during merge modification migration",
                        device_id,
                    )

            if len(valid_devices) < 2:
                _LOGGER.warning(
                    "Not enough valid devices for merge modification in config entry %s, removing",
                    config_entry.entry_id,
                )
                hass.async_create_task(
                    hass.config_entries.async_remove(config_entry.entry_id)
                )
                return False

            # Get a name for the merged device
            primary_device = device_registry.async_get(valid_devices[0])
            if primary_device and primary_device.name_by_user:
                merge_name = primary_device.name_by_user
            elif primary_device and primary_device.name:
                merge_name = primary_device.name
            else:
                merge_name = f"Merged Device {valid_devices[0][:8]}"

            new_data = {
                CONF_MODIFICATION_TYPE: ModificationType.MERGE,
                CONF_MODIFICATION_ENTRY_ID: valid_devices[0],  # Primary device
                CONF_MODIFICATION_ENTRY_NAME: merge_name,
                CONF_MODIFICATION_IS_CUSTOM_ENTRY: True,  # Creates a new device
            }
            new_options = {
                CONF_MODIFICATION_DATA: {
                    CONF_MERGE_DEVICE_IDS: valid_devices,
                }
            }

            hass.config_entries.async_update_entry(
                config_entry,
                data=new_data,
                options=new_options,
                title=merge_name,
                unique_id=f"merge_{'_'.join(valid_devices)}",
                version=2,
                minor_version=1,
            )

    _LOGGER.info(
        "Successfully migrated Device Tools config entry %s to v2.1",
        config_entry.entry_id,
    )

    return True
