"""Constants for the Device Tools integration."""

from enum import StrEnum

DOMAIN = "device_tools"

CONF_MODIFICATION_TYPE = "modification_type"
CONF_MODIFICATION_ENTRY_ID = "modification_entry_id"
CONF_MODIFICATION_DATA = "modification_data"
CONF_MODIFICATION_ORIGINAL_DATA = "modification_original_data"
CONF_MANUFACTURER = "manufacturer"
CONF_MODEL = "model"
CONF_SW_VERSION = "sw_version"
CONF_HW_VERSION = "hw_version"
CONF_SERIAL_NUMBER = "serial_number"
CONF_VIA_DEVICE_ID = "via_device_id"
CONF_DEVICE_ID = "device_id"


class ModificationType(StrEnum):
    """Modification type enum."""

    DEVICE = "device"
    ENTITY = "entity"


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
