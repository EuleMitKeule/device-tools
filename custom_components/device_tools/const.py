"""Constants for the Device Tools integration."""


from enum import StrEnum

DOMAIN = "device_tools"


SCAN_INTERVAL = 5


CONF_MODIFICATION_TYPE = "modification_type"
CONF_MODIFICATION_NAME = "modification_name"
CONF_DEVICE_ID = "device_id"
CONF_MANUFACTURER = "manufacturer"
CONF_MODEL = "model"
CONF_VIA_DEVICE = "via_device"
CONF_SW_VERSION = "sw_version"
CONF_HW_VERSION = "hw_version"
CONF_CONNECTION_NETWORK_MAC = "connection_network_mac"
CONF_CONNECTION_BLUETOOTH_MAC = "connection_bluetooth_mac"
CONF_CONNECTION_UPNP = "connection_upnp"
CONF_CONNECTION_ZIGBEE = "connection_zigbee"
CONF_IDENTIFIERS = "identifiers"


class ModificationType(StrEnum):
    """Modification type enum."""

    ATTRIBUTES = "attributes"
