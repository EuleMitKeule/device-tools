"""HASS data definitions for device_tools."""

from dataclasses import dataclass, field

from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN
from .engine import ModificationEngine
from .original_data_store import OriginalDataStore


@dataclass(slots=True)
class DeviceToolsData:
    """Runtime data."""

    engine: ModificationEngine
    store: OriginalDataStore


DATA_KEY: HassKey[DeviceToolsData] = HassKey(DOMAIN)
