from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Called when an entry is setup."""

    entities_to_add: list[Entity] = [
        DummySensor(
            "Google Home",
            DeviceInfo(
                identifiers={("google_home", "78ae633e-b259-4804-9b43-79b2f086fe27")},
                name="Google Home",
                manufacturer="Google Home",
                model="Nest",
                sw_version="1.52.277106",
            ),
        ),
        DummySensor(
            "Chromecast",
            DeviceInfo(
                identifiers={("cast", "3e7573d80740e683a28bdfa7aa4fcab1")},
                name="Chromecast",
                manufacturer="Google Inc.",
                model="Nest Audio",
                sw_version="1.52.277106",
            ),
        ),
    ]

    async_add_entities(entities_to_add)


class DummySensor(BinarySensorEntity):
    """Dummy Sensor."""

    def __init__(self, name: str, device_info: DeviceInfo) -> None:
        """Initialize the sensor."""
        self._name = name
        self._state = False
        self._attr_device_info = device_info
        self._attr_unique_id = slugify(name)

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name

    @property
    def is_on(self) -> bool:
        """Return the state of the sensor."""
        return self._state
