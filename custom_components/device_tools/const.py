"""Constants for the Device Tools integration."""


from enum import StrEnum

DOMAIN = "device_tools"


SCAN_INTERVAL = 5


CONF_MODIFICATION_TYPE = "modification_type"
CONF_MODIFICATION_NAME = "modification_name"
CONF_DEVICE_ID = "device_id"
CONF_MANUFACTURER = "manufacturer"
CONF_MODEL = "model"
CONF_VIA_DEVICE = "via_device_id"
CONF_SW_VERSION = "sw_version"
CONF_HW_VERSION = "hw_version"
CONF_SERIAL_NUMBER = "serial_number"
CONF_IDENTIFIERS = "identifiers"
CONF_ENTITIES = "entities"
CONF_DEVICE_NAME = "device_name"
CONF_DEVICES = "devices"


class ModificationType(StrEnum):
    """Modification type enum."""

    ATTRIBUTES = "attributes"
    ENTITIES = "entities"
    MERGE = "merge"
