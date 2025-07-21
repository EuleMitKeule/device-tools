"""Constants for the Device Tools integration."""

from enum import StrEnum

DOMAIN = "device_tools"

CONF_MODIFICATION_TYPE = "modification_type"
CONF_MODIFICATION_ENTRY_ID = "modification_entry_id"
CONF_MODIFICATION_IS_CUSTOM_ENTRY = "modification_is_custom_entry"
CONF_MODIFICATION_ENTRY_NAME = "modification_entry_name"
CONF_MODIFICATION_DATA = "modification_data"
CONF_MODIFICATION_ORIGINAL_DATA = "modification_original_data"
CONF_MANUFACTURER = "manufacturer"
CONF_MODEL = "model"
CONF_SW_VERSION = "sw_version"
CONF_HW_VERSION = "hw_version"
CONF_SERIAL_NUMBER = "serial_number"
CONF_VIA_DEVICE_ID = "via_device_id"

CONF_DEVICE_ID = "device_id"

CONF_MERGE_DEVICE_IDS = "merge_device_ids"
CONF_ENTITIES = "entities"
CONF_DISABLED_BY = "disabled_by"
CONF_DISABLE_MERGED_DEVICES = "disable_merged_devices"


class ModificationType(StrEnum):
    """Modification type enum."""

    DEVICE = "device"
    ENTITY = "entity"
    MERGE = "merge"


MODIFIABLE_ATTRIBUTES = {
    ModificationType.DEVICE: [
        CONF_MANUFACTURER,
        CONF_MODEL,
        CONF_SW_VERSION,
        CONF_HW_VERSION,
        CONF_SERIAL_NUMBER,
        CONF_VIA_DEVICE_ID,
    ],
    ModificationType.ENTITY: [
        CONF_DEVICE_ID,
    ],
    ModificationType.MERGE: [
        CONF_MERGE_DEVICE_IDS,
    ],
}

IGNORED_ATTRIBUTES = [
    "config_entries",
    "connections",
    "created_at",
    "id",
    "identifiers",
    "modified_at",
    "primary_config_entry",
]
