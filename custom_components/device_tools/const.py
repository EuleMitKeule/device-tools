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

CONF_ASSIGNED_ENTITIES = "assigned_entities"

CONF_MERGE_DEVICE_IDS = "merge_device_ids"
CONF_ENTITIES = "entities"

ENTITY_CATEGORY_DEFAULT = "default"
ENTITY_CATEGORY_OPTIONS = [ENTITY_CATEGORY_DEFAULT, "config", "diagnostic"]
ENTRY_TYPE_NONE = "none"
ENTRY_TYPE_OPTIONS = [ENTRY_TYPE_NONE, "service"]

CONFIGURATION_URL_SCHEMES = {"http", "https", "homeassistant"}


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
        CONF_ENTRY_TYPE,
    ],
    ModificationType.ENTITY: [
        CONF_DEVICE_ID,
        CONF_ENTITY_CATEGORY,
    ],
    ModificationType.MERGE: [],
}

# Modifications are applied in ascending order, later ones take precedence.
MODIFICATION_PRECEDENCE = {
    ModificationType.DEVICE: 0,
    ModificationType.MERGE: 1,
    ModificationType.ENTITY: 2,
}
