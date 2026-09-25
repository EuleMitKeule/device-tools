"""Tests for merge modifications."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.device_tools.const import (
    CONF_MODIFICATION_ORIGINAL_DATA,
    ModificationType,
)

from .conftest import create_device, create_entity, modification_entry, setup_entry


async def test_merge(hass: HomeAssistant, source_entry: MockConfigEntry) -> None:
    target = create_device(hass, source_entry, "target")
    source = create_device(hass, source_entry, "source")
    entity = create_entity(hass, source_entry, "1", source)
    disabled_entity = create_entity(
        hass, source_entry, "2", source, disabled_by=er.RegistryEntryDisabler.USER
    )
    config_entry = modification_entry(
        ModificationType.MERGE,
        target.id,
        original_data={source.id: {"entities": {}}},
    )
    await setup_entry(hass, config_entry)

    entity_registry = er.async_get(hass)
    assert entity_registry.async_get(entity.entity_id).device_id == target.id
    assert entity_registry.async_get(disabled_entity.entity_id).device_id == target.id
    assert set(
        config_entry.data[CONF_MODIFICATION_ORIGINAL_DATA][source.id]["entities"]
    ) == {entity.entity_id, disabled_entity.entity_id}

    new_entity = create_entity(hass, source_entry, "3", source)
    await hass.async_block_till_done()
    assert entity_registry.async_get(new_entity.entity_id).device_id == target.id

    create_entity(hass, source_entry, "1", source)
    await hass.async_block_till_done()
    assert entity_registry.async_get(entity.entity_id).device_id == target.id

    assert dr.async_get(hass).async_get(source.id) is not None

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    for entity_id in (
        entity.entity_id,
        disabled_entity.entity_id,
        new_entity.entity_id,
    ):
        assert entity_registry.async_get(entity_id).device_id == source.id


async def test_removed_source_device(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    target = create_device(hass, source_entry, "target")
    source = create_device(hass, source_entry, "source")
    other_source = create_device(hass, source_entry, "other_source")
    config_entry = modification_entry(
        ModificationType.MERGE,
        target.id,
        original_data={source.id: {"entities": {}}, other_source.id: {"entities": {}}},
    )
    await setup_entry(hass, config_entry)

    dr.async_get(hass).async_remove_device(source.id)
    await hass.async_block_till_done()

    assert list(config_entry.data[CONF_MODIFICATION_ORIGINAL_DATA]) == [other_source.id]


async def test_removed_merged_entity(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    target = create_device(hass, source_entry, "target")
    source = create_device(hass, source_entry, "source")
    entity = create_entity(hass, source_entry, "1", source)
    config_entry = modification_entry(
        ModificationType.MERGE,
        target.id,
        original_data={source.id: {"entities": {}}},
    )
    await setup_entry(hass, config_entry)

    er.async_get(hass).async_remove(entity.entity_id)
    await hass.async_block_till_done()

    assert config_entry.data[CONF_MODIFICATION_ORIGINAL_DATA] == {
        source.id: {"entities": {}}
    }
