"""Tests for the device_tools module."""

from collections.abc import Awaitable
from types import MappingProxyType
from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockEntity


async def test_device_simple(
    hass: HomeAssistant,
    mock_device_info_maker: Callable[[], dr.DeviceInfo],
    mock_entity_maker: Callable[
        [ConfigEntry | None, dr.DeviceInfo | None], Awaitable[MockEntity]
    ],
    device_registry: dr.DeviceRegistry,
):
    device_info = mock_device_info_maker()
    original_model = device_info.get("model")
    original_sw_version = device_info.get("sw_version")
    entity: MockEntity = await mock_entity_maker(None, device_info)
    device_entry = device_registry.async_get_device(
        device_info.get("identifiers"), device_info.get("connections")
    )

    assert device_entry is not None
    assert device_entry.model != "New Model"
    assert device_entry.sw_version != "New Software Version"

    # create a config entry for device_tools
    config_entry = ConfigEntry(
        version=1,
        domain="device_tools",
        entry_id="test_entry",
        title="Test Entry",
        data={
            "modification_type": "device",
            "modification_entry_id": device_entry.id,
        },
        discovery_keys=MappingProxyType({}),
        minor_version=0,
        options={
            "modification_data": {
                "model": "New Model",
                "sw_version": "New Software Version",
            },
        },
        source="",
        unique_id=None,
    )
    await hass.config_entries.async_add(config_entry)

    device_entry = device_registry.async_get_device(
        device_info.get("identifiers"), device_info.get("connections")
    )
    assert device_entry is not None
    assert device_entry.model == "New Model"
    assert device_entry.sw_version == "New Software Version"

    await hass.config_entries.async_remove(config_entry.entry_id)

    device_entry = device_registry.async_get_device(
        device_info.get("identifiers"), device_info.get("connections")
    )
    assert device_entry is not None
    assert device_entry.model == original_model
    assert device_entry.sw_version == original_sw_version


async def test_device_advanced(
    hass: HomeAssistant,
    mock_device_info_maker: Callable[[], dr.DeviceInfo],
    mock_entity_maker: Callable[
        [ConfigEntry | None, dr.DeviceInfo | None], Awaitable[MockEntity]
    ],
    device_registry: dr.DeviceRegistry,
):
    device_info = mock_device_info_maker()
    original_model = device_info.get("model")
    original_sw_version = device_info.get("sw_version")
    entity: MockEntity = await mock_entity_maker(None, device_info)
    device_entry = device_registry.async_get_device(
        device_info.get("identifiers"), device_info.get("connections")
    )

    assert device_entry is not None
    assert device_entry.model != "New Model"
    assert device_entry.sw_version != "New Software Version"

    # create a config entry for device_tools
    config_entry = ConfigEntry(
        version=1,
        domain="device_tools",
        entry_id="test_entry",
        title="Test Entry",
        data={
            "modification_type": "device",
            "modification_entry_id": device_entry.id,
        },
        discovery_keys=MappingProxyType({}),
        minor_version=0,
        options={
            "modification_data": {
                "model": "New Model",
                "sw_version": "New Software Version",
            },
        },
        source="",
        unique_id=None,
    )
    await hass.config_entries.async_add(config_entry)

    device_entry = device_registry.async_get_device(
        device_info.get("identifiers"), device_info.get("connections")
    )
    assert device_entry is not None
    assert device_entry.model == "New Model"
    assert device_entry.sw_version == "New Software Version"

    device_registry.async_update_device(
        device_entry.id, model="Other model", sw_version="Other version"
    )

    device_entry = device_registry.async_get_device(
        device_info.get("identifiers"), device_info.get("connections")
    )
    assert device_entry is not None
    assert device_entry.model == "New Model"
    assert device_entry.sw_version == "New Software Version"

    await hass.config_entries.async_remove(config_entry.entry_id)

    device_entry = device_registry.async_get_device(
        device_info.get("identifiers"), device_info.get("connections")
    )
    assert device_entry is not None
    assert device_entry.model == "Other model"
    assert device_entry.sw_version == "Other version"


# async def test_attributes(
#     hass: HomeAssistant,
#     mock_device_info_maker: Callable[[], dr.DeviceInfo],
#     mock_entity_maker: Callable[
#         [ConfigEntry | None, dr.DeviceInfo | None], Awaitable[MockEntity]
#     ],
#     device_modification_registry: DeviceModificationRegistry,
#     mock_device_tools: DeviceTools,
#     device_registry: dr.DeviceRegistry,
# ) -> None:
#     device_info = mock_device_info_maker()
#     entity: MockEntity = await mock_entity_maker(
#         config_entry=None, device_info=device_info
#     )
#     device_entry = device_registry.async_get_device(
#         device_info["identifiers"], device_info["connections"]
#     )

#     attribute_modification = AttributeModification(
#         hw_version="New Hardware Version",
#         sw_version="New Software Version",
#     )
#     device_modification = DeviceModification(
#         attribute_modification=attribute_modification,
#         device_id=device_entry.id,
#         device_name=device_entry.name,
#         entity_modification=None,
#         merge_modification=None,
#         modification_name="Test Modification",
#     )

#     assert device_entry.sw_version != "New Software Version"

#     await device_modification_registry.add_entry("test_entry", device_modification)

#     device_entry = device_registry.async_get_device(
#         device_info["identifiers"], device_info["connections"]
#     )
#     assert device_entry.sw_version == "New Software Version"

#     await device_modification_registry.remove_entry("test_entry")

#     device_entry = device_registry.async_get_device(
#         device_info["identifiers"], device_info["connections"]
#     )
#     assert device_entry.sw_version != "New Software Version"

#     await device_modification_registry.add_entry("test_entry", device_modification)

#     device_entry = device_registry.async_get_device(
#         device_info["identifiers"], device_info["connections"]
#     )
#     assert device_entry.sw_version == "New Software Version"

#     device_registry.async_update_device(
#         device_entry.id, sw_version="Other version", model="Other model"
#     )

#     device_entry = device_registry.async_get_device(
#         device_info["identifiers"], device_info["connections"]
#     )
#     assert device_entry.model == "Other model"
#     assert device_entry.sw_version == "New Software Version"


# async def test_attributes_revert_after_device_update_when_attribute_was_newly_introduced_by_integration_later(
#     hass: HomeAssistant,
#     mock_device_info_maker: Callable[[], dr.DeviceInfo],
#     mock_entity_maker: Callable[
#         [ConfigEntry | None, dr.DeviceInfo | None], Awaitable[MockEntity]
#     ],
#     device_modification_registry: DeviceModificationRegistry,
#     mock_device_tools: DeviceTools,
#     device_registry: dr.DeviceRegistry,
# ) -> None:
#     device_info = dr.DeviceInfo(
#         identifiers={("test", "test")},
#         sw_version="Initial Software Version",
#     )
#     entity: MockEntity = await mock_entity_maker(
#         config_entry=None, device_info=device_info
#     )

#     device_entry = device_registry.async_get_device(device_info["identifiers"])
#     assert device_entry.sw_version == "Initial Software Version"

#     attribute_modification = AttributeModification(
#         hw_version="New Hardware Version",
#         sw_version="New Software Version",
#     )
#     device_modification = DeviceModification(
#         attribute_modification=attribute_modification,
#         device_id=device_entry.id,
#         device_name=device_entry.name,
#         entity_modification=None,
#         merge_modification=None,
#         modification_name="Test Modification",
#     )

#     await device_modification_registry.add_entry("test_entry", device_modification)

#     device_entry = device_registry.async_get_device(device_info["identifiers"])
#     assert device_entry.sw_version == "New Software Version"

#     device_registry.async_update_device(
#         device_entry.id, sw_version="Other version", model="Other model"
#     )

#     device_entry = device_registry.async_get_device(device_info["identifiers"])
#     assert device_entry.model == "Other model"
#     assert device_entry.sw_version == "New Software Version"

#     await device_modification_registry.remove_entry("test_entry")

#     device_entry = device_registry.async_get_device(device_info["identifiers"])
#     assert device_entry.model == "Other model"
#     assert device_entry.sw_version == "Other version"


# async def test_entity_modification(
#     hass: HomeAssistant,
#     mock_device_info_maker: Callable[[], dr.DeviceInfo],
#     mock_entity_maker: Callable[
#         [ConfigEntry | None, dr.DeviceInfo | None], Awaitable[MockEntity]
#     ],
#     device_modification_registry: DeviceModificationRegistry,
#     mock_device_tools: DeviceTools,
#     device_registry: dr.DeviceRegistry,
#     entity_registry: er.EntityRegistry,
# ) -> None:
#     device_info = mock_device_info_maker()
#     entity: MockEntity = await mock_entity_maker(
#         config_entry=None, device_info=device_info
#     )
#     other_entity: MockEntity = await mock_entity_maker(
#         config_entry=None, device_info=device_info
#     )
#     device_entry = device_registry.async_get_device(
#         device_info["identifiers"], device_info["connections"]
#     )
#     entity_entry = entity_registry.async_get(entity.entity_id)

#     entity_modification = AttributeModification(
#         name="New Name",
#         unique_id="New Unique ID",
#     )
#     device_modification = DeviceModification(
#         attribute_modification=None,
#         device_id=device_entry.id,
#         device_name=device_entry.name,
#         entity_modification=entity_modification,
#         merge_modification=None,
#         modification_name="Test Modification",
#     )

#     assert entity_entry.unique_id != "New Unique ID"

#     await device_modification_registry.add_entry("test_entry", device_modification)

#     entity_entry = entity_registry.async_get(entity.entity_id)
#     assert entity_entry.unique_id == "New Unique ID"

#     await device_modification_registry.remove_entry("test_entry")

#     entity_entry = entity_registry.async_get(entity.entity_id)
#     assert entity_entry.unique_id != "New Unique ID"

#     await device_modification_registry.add_entry("test_entry", device_modification)

#     entity_entry = entity_registry.async_get(entity.entity_id)
#     assert entity_entry.unique_id == "New Unique ID"

#     entity_registry.async_update_entity(entity.entity_id, name="Other name")

#     entity_entry = entity_registry.async_get(entity.entity_id)
#     assert entity_entry.name == "Other name"
