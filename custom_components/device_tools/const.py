"""Constants for the Device Tools integration."""

from enum import StrEnum

DOMAIN = "device_tools"

CONF_INFORMATION = "information"
CONF_DEVICE_ATTRIBUTES = "device_attributes"
CONF_ENTITY_ATTRIBUTES = "entity_attributes"
CONF_ENTITY_ASSIGNMENT = "entity_assignment"
CONF_MERGE_OPTIONS = "merge_options"
CONF_MODIFICATION_TYPE = "modification_type"
CONF_MODIFICATION_ENTRY = "modification_entry"
CONF_MODIFICATION_ENTRY_ID = "modification_entry_id"
CONF_MODIFICATION_IS_CUSTOM_ENTRY = "modification_is_custom_entry"
CONF_MODIFICATION_ENTRY_NAME = "modification_entry_name"
CONF_MODIFICATION_DATA = "modification_data"
CONF_MODIFICATION_ORIGINAL_DATA = "modification_original_data"
CONF_MANUFACTURER = "manufacturer"
CONF_MODEL = "model"
CONF_MODEL_ID = "model_id"
CONF_SW_VERSION = "sw_version"
CONF_HW_VERSION = "hw_version"
CONF_SERIAL_NUMBER = "serial_number"
CONF_VIA_DEVICE_ID = "via_device_id"
CONF_CONFIGURATION_URL = "configuration_url"
CONF_ENTRY_TYPE = "entry_type"
CONF_CONNECTIONS = "connections"
CONF_IDENTIFIERS = "identifiers"

CONF_DEVICE_ID = "device_id"
CONF_ENTITY_CATEGORY = "entity_category"
ENTITY_CATEGORY_OPTIONS = ["default", "config", "diagnostic"]

CONF_ASSIGNED_ENTITIES = "assigned_entities"

CONF_MERGE_DEVICE_IDS = "merge_device_ids"
CONF_ENTITIES = "entities"
CONF_ORIGINAL_DATA = "original_data"


class ModificationType(StrEnum):
    """Modification type enum."""

    DEVICE = "device"
    ENTITY = "entity"
    MERGE = "merge"

    @property
    def friendly_name(self) -> str:
        """Get the friendly name for the modification type."""
        return self.value.capitalize()


MODIFIABLE_ATTRIBUTES = {
    ModificationType.DEVICE: [
        CONF_MANUFACTURER,
        CONF_MODEL,
        CONF_MODEL_ID,
        CONF_SW_VERSION,
        CONF_HW_VERSION,
        CONF_SERIAL_NUMBER,
        CONF_VIA_DEVICE_ID,
        CONF_CONFIGURATION_URL,
        # NOTE: CONF_ENTRY_TYPE, CONF_CONNECTIONS, and CONF_IDENTIFIERS use
        # non-JSON-serializable native HA types (DeviceEntryType, set/frozenset
        # of tuples). They are normalized to JSON-safe forms by
        # _normalize_device_value() in config_flow.py before being stored in
        # config entry data.
        CONF_ENTRY_TYPE,
        CONF_CONNECTIONS,
        CONF_IDENTIFIERS,
    ],
    ModificationType.ENTITY: [
        CONF_DEVICE_ID,
        CONF_ENTITY_CATEGORY,
    ],
    ModificationType.MERGE: [],
}

IGNORED_ATTRIBUTES = [
    "config_entries",
    "created_at",
    "id",
    "modified_at",
    "primary_config_entry",
]
