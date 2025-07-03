"""HASS data definitions for device_tools."""

from dataclasses import dataclass, field

from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN
from .device_listener import DeviceListener
from .entity_listener import EntityListener
from .modification import Modification


@dataclass(slots=True)
class DeviceToolsData:
    """Runtime data."""

    device_listener: DeviceListener
    entity_listener: EntityListener
    modifications: dict[str, Modification] = field(default_factory=dict)


DATA_KEY: HassKey[DeviceToolsData] = HassKey(DOMAIN)
