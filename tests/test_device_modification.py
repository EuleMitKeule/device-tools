"""Tests for device modifications."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.device_tools.const import (
    CONF_ASSIGNED_ENTITIES,
    CONF_ENTRY_TYPE,
    CONF_MANUFACTURER,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_SW_VERSION,
    CONF_VIA_DEVICE_ID,
    ModificationType,
)
from custom_components.device_tools.data import DATA_KEY
from custom_components.device_tools.original_data_store import KIND_DEVICES

from .conftest import (
    create_device,
    create_entity,
    modification_entry,
    setup_entry,
    update_options,
)


async def test_attributes_applied_and_restored(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(
        hass, source_entry, "a", manufacturer="Acme", sw_version="1.0"
    )
    config_entry = modification_entry(
        ModificationType.DEVICE,
        device.id,
        {CONF_MANUFACTURER: "Changed", CONF_ENTRY_TYPE: "service"},
    )
    await setup_entry(hass, config_entry)

    device_registry = dr.async_get(hass)
    modified = device_registry.async_get(device.id)
    assert modified is not None
    assert modified.manufacturer == "Changed"
    assert modified.entry_type is dr.DeviceEntryType.SERVICE
    assert modified.sw_version == "1.0"
    assert hass.data[DATA_KEY].store.get(KIND_DEVICES, device.id) == {
        CONF_MANUFACTURER: "Acme",
        CONF_ENTRY_TYPE: None,
    }

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    restored = device_registry.async_get(device.id)
    assert restored is not None
    assert restored.manufacturer == "Acme"
    assert restored.entry_type is None
    assert hass.data[DATA_KEY].store.get(KIND_DEVICES, device.id) == {}


async def test_integration_updates_are_tracked(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(
        hass, source_entry, "a", manufacturer="Acme", sw_version="1.0"
    )
    config_entry = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_MANUFACTURER: "Changed"}
    )
    await setup_entry(hass, config_entry)

    create_device(hass, source_entry, "a", manufacturer="Acme 2", sw_version="2.0")
    await hass.async_block_till_done()

    device_registry = dr.async_get(hass)
    modified = device_registry.async_get(device.id)
    assert modified is not None
    assert modified.manufacturer == "Changed"
    assert modified.sw_version == "2.0"

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    restored = device_registry.async_get(device.id)
    assert restored is not None
    assert restored.manufacturer == "Acme 2"
    assert restored.sw_version == "2.0"


async def test_resetting_attribute_restores_it(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(
        hass, source_entry, "a", manufacturer="Acme", sw_version="1.0"
    )
    config_entry = modification_entry(
        ModificationType.DEVICE,
        device.id,
        {CONF_MANUFACTURER: "Changed", CONF_SW_VERSION: "9.9"},
    )
    await setup_entry(hass, config_entry)

    await update_options(hass, config_entry, {CONF_MANUFACTURER: "Changed"})

    modified = dr.async_get(hass).async_get(device.id)
    assert modified is not None
    assert modified.manufacturer == "Changed"
    assert modified.sw_version == "1.0"


async def test_no_config_entry_added_to_device(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a")
    config_entry = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_MANUFACTURER: "Changed"}
    )
    await setup_entry(hass, config_entry)

    modified = dr.async_get(hass).async_get(device.id)
    assert modified is not None
    assert modified.config_entry_id == source_entry.entry_id
    assert not dr.async_entries_for_config_entry(
        dr.async_get(hass), config_entry.entry_id
    )


async def test_assigned_entities(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a")
    other_device = create_device(hass, source_entry, "b")
    entity = create_entity(hass, source_entry, "1", other_device)
    lonely_entity = create_entity(hass, source_entry, "2")
    config_entry = modification_entry(
        ModificationType.DEVICE,
        device.id,
        {CONF_ASSIGNED_ENTITIES: [entity.entity_id, lonely_entity.entity_id]},
    )
    await setup_entry(hass, config_entry)

    entity_registry = er.async_get(hass)
    assert entity_registry.async_get(entity.entity_id).device_id == device.id
    assert entity_registry.async_get(lonely_entity.entity_id).device_id == device.id

    await update_options(
        hass, config_entry, {CONF_ASSIGNED_ENTITIES: [lonely_entity.entity_id]}
    )

    assert entity_registry.async_get(entity.entity_id).device_id == other_device.id
    assert entity_registry.async_get(lonely_entity.entity_id).device_id == device.id

    create_entity(hass, source_entry, "2", other_device)
    await hass.async_block_till_done()
    assert entity_registry.async_get(lonely_entity.entity_id).device_id == device.id

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert (
        entity_registry.async_get(lonely_entity.entity_id).device_id == other_device.id
    )


async def test_via_device(hass: HomeAssistant, source_entry: MockConfigEntry) -> None:
    device = create_device(hass, source_entry, "a")
    hub = create_device(hass, source_entry, "hub")
    config_entry = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_VIA_DEVICE_ID: hub.id}
    )
    await setup_entry(hass, config_entry)

    device_registry = dr.async_get(hass)
    assert device_registry.async_get(device.id).via_device_id == hub.id

    device_registry.async_remove_device(hub.id)
    await hass.async_block_till_done()

    assert device_registry.async_get(device.id).via_device_id is None


async def test_custom_device_is_stable(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    entity = create_entity(hass, source_entry, "1")
    config_entry = modification_entry(
        ModificationType.DEVICE,
        "placeholder",
        {CONF_ASSIGNED_ENTITIES: [entity.entity_id], CONF_MANUFACTURER: "Me"},
        is_custom_entry=True,
        name="Virtual",
    )
    await setup_entry(hass, config_entry)

    device_id = config_entry.data[CONF_MODIFICATION_ENTRY_ID]
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)
    assert device is not None
    assert device.name == "Virtual"
    assert device.manufacturer == "Me"
    assert config_entry.unique_id == f"device_{device_id}"
    entity_registry = er.async_get(hass)
    assert entity_registry.async_get(entity.entity_id).device_id == device_id

    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.data[CONF_MODIFICATION_ENTRY_ID] == device_id
    assert device_registry.async_get(device_id) is not None
    assert entity_registry.async_get(entity.entity_id).device_id == device_id

    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()

    assert device_registry.async_get(device_id) is None
    assert entity_registry.async_get(entity.entity_id).device_id is None


async def test_invalid_value_does_not_block_others(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a")
    config_entry = modification_entry(
        ModificationType.DEVICE,
        device.id,
        {CONF_MANUFACTURER: "Changed", "configuration_url": "ftp://invalid"},
    )
    await setup_entry(hass, config_entry)

    modified = dr.async_get(hass).async_get(device.id)
    assert modified.manufacturer == "Changed"
    assert modified.configuration_url is None


async def test_removing_custom_device_updates_merge_and_via_device(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a")
    custom_entry = modification_entry(
        ModificationType.DEVICE, "placeholder", is_custom_entry=True, name="Virtual"
    )
    await setup_entry(hass, custom_entry)
    custom_device_id = custom_entry.data[CONF_MODIFICATION_ENTRY_ID]
    device_entry = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_VIA_DEVICE_ID: custom_device_id}
    )
    merge_entry = modification_entry(
        ModificationType.MERGE,
        create_device(hass, source_entry, "target").id,
        original_data={custom_device_id: {"entities": {}}, device.id: {"entities": {}}},
    )
    await setup_entry(hass, device_entry)
    await setup_entry(hass, merge_entry)
    assert dr.async_get(hass).async_get(device.id).via_device_id == custom_device_id

    assert await hass.config_entries.async_remove(custom_entry.entry_id)
    await hass.async_block_till_done()

    assert device_entry.options == {"modification_data": {}}
    assert list(merge_entry.data["modification_original_data"]) == [device.id]
    assert dr.async_get(hass).async_get(device.id).via_device_id is None
