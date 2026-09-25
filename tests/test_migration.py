"""Tests for the migration of config entries created by previous versions."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.device_tools.const import (
    CONF_ASSIGNED_ENTITIES,
    CONF_DEVICE_ID,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_ENTRY_NAME,
    CONF_MODIFICATION_IS_CUSTOM_ENTRY,
    CONF_MODIFICATION_ORIGINAL_DATA,
    CONF_MODIFICATION_TYPE,
    DOMAIN,
    ModificationType,
)
from custom_components.device_tools.data import DATA_KEY
from custom_components.device_tools.original_data_store import (
    KIND_DEVICES,
    KIND_ENTITIES,
)

from .conftest import create_device, create_entity


def v1_entry(**device_modification: Any) -> MockConfigEntry:
    """Return a config entry created by 1.x."""
    return MockConfigEntry(
        domain=DOMAIN,
        version=1,
        title="My modification",
        unique_id="My modification",
        data={
            "device_modification": {
                "modification_name": "My modification",
                "device_id": None,
                "device_name": "My device",
                "attribute_modification": None,
                "entity_modification": None,
                "merge_modification": None,
                **device_modification,
            }
        },
    )


async def setup_migrated(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Add, migrate and set up a config entry."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def test_v1_device(hass: HomeAssistant, source_entry: MockConfigEntry) -> None:
    device = create_device(hass, source_entry, "a", manufacturer="Acme", model="M")
    other_device = create_device(hass, source_entry, "b")
    merged_device = create_device(hass, source_entry, "merged")
    moved_entity = create_entity(hass, source_entry, "1", device)
    other_entity = create_entity(hass, source_entry, "2", other_device)
    merged_entity = create_entity(hass, source_entry, "3", merged_device)
    config_entry = v1_entry(
        device_id=device.id,
        attribute_modification={
            "manufacturer": "Changed",
            "model": None,
            "sw_version": "",
            "hw_version": None,
            "serial_number": None,
            "via_device_id": None,
        },
        entity_modification={
            "entities": [moved_entity.id, other_entity.entity_id, "missing"]
        },
        merge_modification={"devices": [merged_device.id, "missing", device.id]},
    )
    await setup_migrated(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert (config_entry.version, config_entry.minor_version) == (2, 1)
    assert config_entry.title == "My modification"
    assert config_entry.unique_id == f"device_{device.id}"
    assert config_entry.data == {
        CONF_MODIFICATION_TYPE: ModificationType.DEVICE,
        CONF_MODIFICATION_ENTRY_ID: device.id,
        CONF_MODIFICATION_ENTRY_NAME: "a",
        CONF_MODIFICATION_IS_CUSTOM_ENTRY: False,
        CONF_MODIFICATION_ORIGINAL_DATA: {},
    }
    assert config_entry.options == {
        CONF_MODIFICATION_DATA: {
            CONF_MANUFACTURER: "Changed",
            CONF_ASSIGNED_ENTITIES: [moved_entity.entity_id, other_entity.entity_id],
        }
    }

    merge_entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.data[CONF_MODIFICATION_TYPE] == ModificationType.MERGE
    ]
    assert len(merge_entries) == 1
    merge_entry = merge_entries[0]
    assert merge_entry.state is ConfigEntryState.LOADED
    assert merge_entry.title == "Merge: a"
    assert merge_entry.unique_id == f"merge_{device.id}"
    assert list(merge_entry.data[CONF_MODIFICATION_ORIGINAL_DATA]) == [merged_device.id]

    assert dr.async_get(hass).async_get(device.id).manufacturer == "Changed"
    entity_registry = er.async_get(hass)
    for entity in (moved_entity, other_entity, merged_entity):
        assert entity_registry.async_get(entity.entity_id).device_id == device.id


async def test_v1_custom_device_without_id(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    entity = create_entity(hass, source_entry, "1")
    config_entry = v1_entry(
        attribute_modification={"manufacturer": "Me"},
        entity_modification={"entities": [entity.entity_id]},
    )
    await setup_migrated(hass, config_entry)

    device_id = config_entry.data[CONF_MODIFICATION_ENTRY_ID]
    device = dr.async_get(hass).async_get(device_id)
    assert device is not None
    assert device.name == "My device"
    assert device.manufacturer == "Me"
    assert device.identifiers == {(DOMAIN, config_entry.entry_id)}
    assert config_entry.data[CONF_MODIFICATION_IS_CUSTOM_ENTRY] is True
    assert config_entry.unique_id == f"device_{device_id}"
    assert er.async_get(hass).async_get(entity.entity_id).device_id == device_id


async def test_v1_custom_device_keeps_id(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    config_entry = v1_entry()
    config_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, config_entry.entry_id)},
        name="My device",
    )
    dr.async_get(hass).async_update_device(device.id, area_id="kitchen")
    entity = create_entity(hass, source_entry, "1", device)
    hass.config_entries.async_update_entry(
        config_entry,
        data={
            "device_modification": {
                **config_entry.data["device_modification"],
                "device_id": device.id,
                "entity_modification": {"entities": [entity.id]},
            }
        },
    )
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.data[CONF_MODIFICATION_ENTRY_ID] == device.id
    assert config_entry.data[CONF_MODIFICATION_IS_CUSTOM_ENTRY] is True
    migrated = dr.async_get(hass).async_get(device.id)
    assert migrated is not None
    assert migrated.area_id == "kitchen"
    assert er.async_get(hass).async_get(entity.entity_id).device_id == device.id


async def test_v1_merge_only(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a")
    merged_device = create_device(hass, source_entry, "merged")
    entity = create_entity(hass, source_entry, "1", merged_device)
    config_entry = v1_entry(
        device_id=device.id, merge_modification={"devices": [merged_device.id]}
    )
    await setup_migrated(hass, config_entry)

    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert config_entry.data[CONF_MODIFICATION_TYPE] == ModificationType.MERGE
    assert config_entry.unique_id == f"merge_{device.id}"
    assert config_entry.title == "My modification"
    assert er.async_get(hass).async_get(entity.entity_id).device_id == device.id


async def test_v1_missing_device(hass: HomeAssistant) -> None:
    config_entry = v1_entry(
        device_id="missing", attribute_modification={"model": "Model"}
    )
    await setup_migrated(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    device_id = config_entry.data[CONF_MODIFICATION_ENTRY_ID]
    assert device_id != "missing"
    device = dr.async_get(hass).async_get(device_id)
    assert device is not None
    assert device.model == "Model"


async def test_v1_without_data(hass: HomeAssistant) -> None:
    config_entry = MockConfigEntry(domain=DOMAIN, version=1, data={})
    await setup_migrated(hass, config_entry)
    assert config_entry.state is ConfigEntryState.MIGRATION_ERROR


async def test_newer_version(hass: HomeAssistant) -> None:
    config_entry = MockConfigEntry(domain=DOMAIN, version=3, data={})
    await setup_migrated(hass, config_entry)
    assert config_entry.state is ConfigEntryState.MIGRATION_ERROR


async def test_v2_0_device(hass: HomeAssistant, source_entry: MockConfigEntry) -> None:
    device = create_device(hass, source_entry, "a", manufacturer="Changed", model="M")
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=0,
        unique_id=f"device_{device.id}",
        data={
            CONF_MODIFICATION_TYPE: ModificationType.DEVICE,
            CONF_MODIFICATION_ENTRY_ID: device.id,
            CONF_MODIFICATION_ENTRY_NAME: "a",
            CONF_MODIFICATION_IS_CUSTOM_ENTRY: False,
            CONF_MODIFICATION_ORIGINAL_DATA: {
                CONF_MANUFACTURER: "Acme",
                CONF_MODEL: "M",
                "connections": [["mac", "aa:bb:cc:dd:ee:ff"]],
            },
        },
        options={
            CONF_MODIFICATION_DATA: {
                CONF_MANUFACTURER: "Changed",
                "connections": [["mac", "11:22:33:44:55:66"]],
                "identifiers": [["x", "y"]],
            }
        },
    )
    await setup_migrated(hass, config_entry)

    assert config_entry.minor_version == 1
    assert config_entry.data[CONF_MODIFICATION_ORIGINAL_DATA] == {}
    assert config_entry.options == {
        CONF_MODIFICATION_DATA: {CONF_MANUFACTURER: "Changed"}
    }
    assert hass.data[DATA_KEY].store.get(KIND_DEVICES, device.id) == {
        CONF_MANUFACTURER: "Acme"
    }

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    restored = dr.async_get(hass).async_get(device.id)
    assert restored.manufacturer == "Acme"
    assert restored.connections == set()


async def test_v2_0_merge(hass: HomeAssistant, source_entry: MockConfigEntry) -> None:
    device = create_device(hass, source_entry, "a")
    merged_device = create_device(hass, source_entry, "merged")
    entity = create_entity(hass, source_entry, "1", device)
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=0,
        unique_id=f"merge_{device.id}",
        data={
            CONF_MODIFICATION_TYPE: ModificationType.MERGE,
            CONF_MODIFICATION_ENTRY_ID: device.id,
            CONF_MODIFICATION_ENTRY_NAME: "a",
            CONF_MODIFICATION_IS_CUSTOM_ENTRY: False,
            CONF_MODIFICATION_ORIGINAL_DATA: {
                merged_device.id: {
                    "entities": {entity.entity_id: {CONF_DEVICE_ID: merged_device.id}}
                }
            },
        },
        options={CONF_MODIFICATION_DATA: {"merge_device_ids": [merged_device.id]}},
    )
    await setup_migrated(hass, config_entry)

    assert config_entry.data[CONF_MODIFICATION_ORIGINAL_DATA] == {
        merged_device.id: {"entities": {entity.entity_id: {}}}
    }
    assert config_entry.options == {CONF_MODIFICATION_DATA: {}}
    assert hass.data[DATA_KEY].store.get(KIND_ENTITIES, entity.entity_id) == {
        CONF_DEVICE_ID: merged_device.id
    }

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert er.async_get(hass).async_get(entity.entity_id).device_id == merged_device.id
