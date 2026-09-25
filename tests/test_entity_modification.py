"""Tests for entity modifications and interactions between modifications."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.helpers.entity import EntityCategory
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.device_tools.const import (
    CONF_ASSIGNED_ENTITIES,
    CONF_DEVICE_ID,
    CONF_ENTITY_CATEGORY,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    DOMAIN,
    ModificationType,
)
from custom_components.device_tools.data import DATA_KEY
from custom_components.device_tools.original_data_store import KIND_ENTITIES

from .conftest import (
    create_device,
    create_entity,
    modification_entry,
    setup_entry,
    update_options,
)


async def test_entity_attributes(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a")
    other_device = create_device(hass, source_entry, "b")
    entity = create_entity(
        hass, source_entry, "1", device, entity_category=EntityCategory.DIAGNOSTIC
    )
    config_entry = modification_entry(
        ModificationType.ENTITY,
        entity.entity_id,
        {CONF_DEVICE_ID: other_device.id, CONF_ENTITY_CATEGORY: "default"},
    )
    await setup_entry(hass, config_entry)

    entity_registry = er.async_get(hass)
    modified = entity_registry.async_get(entity.entity_id)
    assert modified.device_id == other_device.id
    assert modified.entity_category is None

    create_entity(
        hass, source_entry, "1", device, entity_category=EntityCategory.CONFIG
    )
    await hass.async_block_till_done()
    modified = entity_registry.async_get(entity.entity_id)
    assert modified.device_id == other_device.id
    assert modified.entity_category is None

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    restored = entity_registry.async_get(entity.entity_id)
    assert restored.device_id == device.id
    assert restored.entity_category is EntityCategory.CONFIG


async def test_precedence(hass: HomeAssistant, source_entry: MockConfigEntry) -> None:
    source = create_device(hass, source_entry, "source")
    merge_target = create_device(hass, source_entry, "merge")
    device_target = create_device(hass, source_entry, "device")
    entity_target = create_device(hass, source_entry, "entity")
    entity = create_entity(hass, source_entry, "1", source)

    device_entry = modification_entry(
        ModificationType.DEVICE,
        device_target.id,
        {CONF_ASSIGNED_ENTITIES: [entity.entity_id]},
    )
    merge_entry = modification_entry(
        ModificationType.MERGE,
        merge_target.id,
        original_data={source.id: {"entities": {}}},
    )
    entity_entry = modification_entry(
        ModificationType.ENTITY, entity.entity_id, {CONF_DEVICE_ID: entity_target.id}
    )
    entity_registry = er.async_get(hass)

    await setup_entry(hass, device_entry)
    assert entity_registry.async_get(entity.entity_id).device_id == device_target.id
    await setup_entry(hass, merge_entry)
    assert entity_registry.async_get(entity.entity_id).device_id == merge_target.id
    await setup_entry(hass, entity_entry)
    assert entity_registry.async_get(entity.entity_id).device_id == entity_target.id

    assert await hass.config_entries.async_unload(entity_entry.entry_id)
    await hass.async_block_till_done()
    assert entity_registry.async_get(entity.entity_id).device_id == merge_target.id
    assert await hass.config_entries.async_unload(merge_entry.entry_id)
    await hass.async_block_till_done()
    assert entity_registry.async_get(entity.entity_id).device_id == device_target.id
    assert await hass.config_entries.async_unload(device_entry.entry_id)
    await hass.async_block_till_done()
    assert entity_registry.async_get(entity.entity_id).device_id == source.id
    assert hass.data[DATA_KEY].store.get(KIND_ENTITIES, entity.entity_id) == {}


async def test_entity_rename(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    source = create_device(hass, source_entry, "source")
    target = create_device(hass, source_entry, "target")
    merge_source = create_device(hass, source_entry, "merge_source")
    entity = create_entity(hass, source_entry, "1", source)
    merged_entity = create_entity(hass, source_entry, "2", merge_source)

    entity_entry = modification_entry(
        ModificationType.ENTITY, entity.entity_id, {CONF_DEVICE_ID: target.id}
    )
    device_entry = modification_entry(
        ModificationType.DEVICE, target.id, {CONF_ASSIGNED_ENTITIES: [entity.entity_id]}
    )
    merge_entry = modification_entry(
        ModificationType.MERGE,
        target.id,
        original_data={merge_source.id: {"entities": {}}},
    )
    for config_entry in (entity_entry, device_entry, merge_entry):
        await setup_entry(hass, config_entry)

    entity_registry = er.async_get(hass)
    entity_registry.async_update_entity(
        entity.entity_id, new_entity_id="sensor.renamed"
    )
    entity_registry.async_update_entity(
        merged_entity.entity_id, new_entity_id="sensor.merged_renamed"
    )
    await hass.async_block_till_done()

    assert entity_entry.data[CONF_MODIFICATION_ENTRY_ID] == "sensor.renamed"
    assert entity_entry.unique_id == "entity_sensor.renamed"
    assert device_entry.options[CONF_MODIFICATION_DATA][CONF_ASSIGNED_ENTITIES] == [
        "sensor.renamed"
    ]
    assert list(
        merge_entry.data["modification_original_data"][merge_source.id]["entities"]
    ) == ["sensor.merged_renamed"]
    assert hass.data[DATA_KEY].store.get(KIND_ENTITIES, "sensor.renamed") == {
        CONF_DEVICE_ID: source.id
    }

    for config_entry in (entity_entry, device_entry, merge_entry):
        assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert entity_registry.async_get("sensor.renamed").device_id == source.id
    assert (
        entity_registry.async_get("sensor.merged_renamed").device_id == merge_source.id
    )


async def test_missing_entity_issue(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a")
    config_entry = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_ASSIGNED_ENTITIES: ["sensor.test_1"]}
    )
    await setup_entry(hass, config_entry)

    issue_id = f"missing_references_{config_entry.entry_id}"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_placeholders == {
        "title": config_entry.title,
        "references": "sensor.test_1",
    }

    entity = create_entity(hass, source_entry, "1")
    await hass.async_block_till_done()
    assert entity.entity_id == "sensor.test_1"
    assert er.async_get(hass).async_get(entity.entity_id).device_id == device.id
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None

    er.async_get(hass).async_remove(entity.entity_id)
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None
    assert config_entry.options[CONF_MODIFICATION_DATA][CONF_ASSIGNED_ENTITIES] == [
        "sensor.test_1"
    ]

    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_removing_custom_device_removes_references(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a")
    entity = create_entity(hass, source_entry, "1", device)
    custom_entry = modification_entry(
        ModificationType.DEVICE, "placeholder", is_custom_entry=True, name="Virtual"
    )
    await setup_entry(hass, custom_entry)
    custom_device_id = custom_entry.data[CONF_MODIFICATION_ENTRY_ID]
    entity_entry = modification_entry(
        ModificationType.ENTITY, entity.entity_id, {CONF_DEVICE_ID: custom_device_id}
    )
    await setup_entry(hass, entity_entry)
    entity_registry = er.async_get(hass)
    assert entity_registry.async_get(entity.entity_id).device_id == custom_device_id

    assert await hass.config_entries.async_remove(custom_entry.entry_id)
    await hass.async_block_till_done()

    assert entity_entry.options[CONF_MODIFICATION_DATA] == {}
    assert entity_registry.async_get(entity.entity_id).device_id == device.id


async def test_update_before_load_is_ignored(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a")
    entity = create_entity(hass, source_entry, "1")
    config_entry = modification_entry(
        ModificationType.ENTITY, entity.entity_id, {CONF_DEVICE_ID: device.id}
    )
    await setup_entry(hass, config_entry)
    await update_options(hass, config_entry, {})
    assert er.async_get(hass).async_get(entity.entity_id).device_id is None
