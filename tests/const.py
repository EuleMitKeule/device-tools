from typing import Any

CONFIG_ENTRY_TITLE_V1 = "Some Modification"
CONFIG_ENTRY_DATA_V1: dict[str, Any] = {
    "modification_name": "Some Modification",
    "device_id": "some_device_id",
    "device_name": "Some Device",
    "attribute_modification": {
        "manufacturer": "Some Manufacturer",
        "model": "Some Model",
        "sw_version": "Some Software Version",
        "hw_version": "Some Hardware Version",
        "serial_number": "Some Serial Number",
        "via_device_id": "some_via_device_id",
    },
    "entity_modification": {
        "entities": [
            "light.some_light",
            "switch.some_switch",
            "sensor.some_sensor",
        ]
    },
    "merge_modification": {
        "devices": [
            "merge_device_id_1",
            "merge_device_id_2",
            "merge_device_id_3",
        ]
    },
}
