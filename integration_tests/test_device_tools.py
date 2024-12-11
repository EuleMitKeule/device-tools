"""Tests for the device_tools module."""

from typing import Awaitable, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockEntity

from custom_components.device_tools import DeviceTools
from custom_components.device_tools.device_modification_registry import (
    DeviceModificationRegistry,
)
from custom_components.device_tools.models import (
    AttributeModification,
    DeviceModification,
)


async def test_attributes(
    hass: HomeAssistant,
    mock_device_info_maker: Callable[[], dr.DeviceInfo],
    mock_entity_maker: Callable[
        [ConfigEntry | None, dr.DeviceInfo | None], Awaitable[MockEntity]
    ],
    device_modification_registry: DeviceModificationRegistry,
    mock_device_tools: DeviceTools,
    device_registry: dr.DeviceRegistry,
) -> None:
    device_info = mock_device_info_maker()
    entity: MockEntity = await mock_entity_maker(
        config_entry=None, device_info=device_info
    )
    device_entry = device_registry.async_get_device(
        device_info["identifiers"], device_info["connections"]
    )

    attribute_modification = AttributeModification(
        hw_version="New Hardware Version",
        sw_version="New Software Version",
    )
    device_modification = DeviceModification(
        attribute_modification=attribute_modification,
        device_id=device_entry.id,
        device_name=device_entry.name,
        entity_modification=None,
        merge_modification=None,
        modification_name="Test Modification",
    )

    assert device_entry.sw_version != "New Software Version"

    await device_modification_registry.add_entry("test_entry", device_modification)

    device_entry = device_registry.async_get_device(
        device_info["identifiers"], device_info["connections"]
    )
    assert device_entry.sw_version == "New Software Version"

    await device_modification_registry.remove_entry("test_entry")

    device_entry = device_registry.async_get_device(
        device_info["identifiers"], device_info["connections"]
    )
    assert device_entry.sw_version != "New Software Version"

    await device_modification_registry.add_entry("test_entry", device_modification)

    device_entry = device_registry.async_get_device(
        device_info["identifiers"], device_info["connections"]
    )
    assert device_entry.sw_version == "New Software Version"

    device_registry.async_update_device(
        device_entry.id, sw_version="Other version", model="Other model"
    )

    device_entry = device_registry.async_get_device(
        device_info["identifiers"], device_info["connections"]
    )
    assert device_entry.model == "Other model"
    assert device_entry.sw_version == "New Software Version"


async def test_attributes_revert_after_device_update_when_attribute_was_newly_introduced_by_integration_later(
    hass: HomeAssistant,
    mock_device_info_maker: Callable[[], dr.DeviceInfo],
    mock_entity_maker: Callable[
        [ConfigEntry | None, dr.DeviceInfo | None], Awaitable[MockEntity]
    ],
    device_modification_registry: DeviceModificationRegistry,
    mock_device_tools: DeviceTools,
    device_registry: dr.DeviceRegistry,
) -> None:
    device_info = dr.DeviceInfo(
        identifiers={("test", "test")},
        sw_version="Initial Software Version",
    )
    entity: MockEntity = await mock_entity_maker(
        config_entry=None, device_info=device_info
    )

    device_entry = device_registry.async_get_device(device_info["identifiers"])
    assert device_entry.sw_version == "Initial Software Version"

    attribute_modification = AttributeModification(
        hw_version="New Hardware Version",
        sw_version="New Software Version",
    )
    device_modification = DeviceModification(
        attribute_modification=attribute_modification,
        device_id=device_entry.id,
        device_name=device_entry.name,
        entity_modification=None,
        merge_modification=None,
        modification_name="Test Modification",
    )

    await device_modification_registry.add_entry("test_entry", device_modification)

    device_entry = device_registry.async_get_device(device_info["identifiers"])
    assert device_entry.sw_version == "New Software Version"

    device_registry.async_update_device(
        device_entry.id, sw_version="Other version", model="Other model"
    )

    device_entry = device_registry.async_get_device(device_info["identifiers"])
    assert device_entry.model == "Other model"
    assert device_entry.sw_version == "New Software Version"

    await device_modification_registry.remove_entry("test_entry")

    device_entry = device_registry.async_get_device(device_info["identifiers"])
    assert device_entry.model == "Other model"
    assert device_entry.sw_version == "Other version"
