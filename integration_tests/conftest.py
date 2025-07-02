import random
import string
from typing import Awaitable, Callable

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockEntity,
    MockEntityPlatform,
)

from custom_components.device_tools.device_listener import DeviceListener
from custom_components.device_tools.entity_listener import EntityListener
from integration_tests.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None):  # noqa: ARG001
    """Enable custom integrations in Home Assistant."""
    yield


def random_string(length: int) -> str:
    return "".join(random.choices(string.ascii_letters, k=length)).lower()


def random_mac() -> str:
    mac = [random.randint(0x00, 0xFF) for _ in range(6)]
    mac[0] = (mac[0] & 0xFE) | 0x02
    return ":".join(f"{byte:02x}" for byte in mac)


@pytest.fixture
def mock_config_entry_maker(hass: HomeAssistant) -> Callable[[], ConfigEntry]:
    """Return a factory function that creates mock config entries."""

    def create_mock_config_entry() -> ConfigEntry:
        """Create a mock config entry."""
        entry_id = random_string(10)
        unique_id = random_string(10)
        config_entry = MockConfigEntry(entry_id=entry_id, unique_id=unique_id)
        config_entry.add_to_hass(hass)

        return config_entry

    return create_mock_config_entry


@pytest.fixture
def mock_device_info_maker() -> Callable[[], dr.DeviceInfo]:
    """Return a factory function that creates mock device info."""

    def create_mock_device_info() -> dr.DeviceInfo:
        """Create a mock device info."""
        device_info = dr.DeviceInfo(
            connections={(dr.CONNECTION_NETWORK_MAC, random_mac())},
            identifiers={(random_string(10), random_string(10))},
            name=random_string(10),
            manufacturer=random_string(10),
            model=random_string(10),
            sw_version=random_string(10),
        )
        return device_info

    return create_mock_device_info


@pytest.fixture
async def mock_entity_maker(
    hass: HomeAssistant,
    mock_config_entry_maker: Callable[[], ConfigEntry],
    mock_device_info_maker: Callable[[], dr.DeviceInfo],
) -> Callable[[ConfigEntry | None, dr.DeviceInfo | None], Awaitable[MockEntity]]:
    """Return a factory function that creates mock entities."""

    async def create_mock_entity(
        config_entry: ConfigEntry | None = None,
        device_info: dr.DeviceInfo | None = None,
    ) -> MockEntity:
        """Create a MockEntity."""

        config_entry = config_entry or mock_config_entry_maker()
        device_info = device_info or mock_device_info_maker()

        platform = MockEntityPlatform(hass)
        platform.config_entry = config_entry

        entity_id = f"{DOMAIN}.{random_string(10)}"
        unique_id = random_string(10)
        entity = MockEntity(
            unique_id=unique_id, entity_id=entity_id, device_info=device_info
        )

        await platform.async_add_entities([entity])
        return entity

    return create_mock_entity


@pytest.fixture
def device_listener(hass: HomeAssistant) -> DeviceListener:
    """Create a device_listener instance."""

    device_listener = DeviceListener(hass)
    return device_listener


@pytest.fixture
def entity_listener(hass: HomeAssistant) -> EntityListener:
    """Create a entity_listener instance."""

    entity_listener = EntityListener(hass)
    return entity_listener


@pytest.fixture
def mock_device_tools(
    device_listener: DeviceListener,
    entity_listener: EntityListener,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Create a device_tools instance."""

    # device_tools = DeviceTools(
    #     device_tools_history_data=device_tools_history_data,
    #     device_modification_registry=device_modification_registry,
    #     device_listener=device_listener,
    #     entity_listener=entity_listener,
    #     device_registry=device_registry,
    #     entity_registry=entity_registry,
    # )
    # return device_tools
