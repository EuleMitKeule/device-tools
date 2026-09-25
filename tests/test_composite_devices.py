"""Tests for devices split by Home Assistant 2026.8."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    category_registry as cr,
    device_registry as dr,
    entity_registry as er,
    floor_registry as fr,
    issue_registry as ir,
    label_registry as lr,
)
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.device_tools.const import (
    CONF_ASSIGNED_ENTITIES,
    CONF_DEVICE_ID,
    CONF_MANUFACTURER,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    DOMAIN,
    ModificationType,
)

from .conftest import SOURCE_DOMAIN, modification_entry

pytestmark = [
    pytest.mark.parametrize("load_registries", [False]),
    pytest.mark.parametrize("expected_lingering_timers", [True]),
]

CREATED_AT = "2025-01-01T00:00:00+00:00"


def _device(
    device_id: str,
    config_entries: list[str],
    identifiers: list[list[str]],
    **kwargs: Any,
) -> dict[str, Any]:
    """Return a device as stored before Home Assistant 2026.8."""
    return {
        "area_id": None,
        "config_entries": config_entries,
        "config_entries_subentries": {entry_id: [None] for entry_id in config_entries},
        "configuration_url": None,
        "connections": [],
        "created_at": CREATED_AT,
        "disabled_by": None,
        "entry_type": None,
        "hw_version": None,
        "id": device_id,
        "identifiers": identifiers,
        "labels": [],
        "manufacturer": None,
        "model": None,
        "model_id": None,
        "modified_at": CREATED_AT,
        "name_by_user": None,
        "name": device_id,
        "primary_config_entry": config_entries[0],
        "serial_number": None,
        "sw_version": None,
        "via_device_id": None,
        **kwargs,
    }


def _entity(
    entity_id: str, config_entry_id: str, device_id: str | None
) -> dict[str, Any]:
    """Return an entity as stored by the entity registry."""
    return {
        "aliases": [],
        "area_id": None,
        "categories": {},
        "capabilities": None,
        "config_entry_id": config_entry_id,
        "config_subentry_id": None,
        "created_at": CREATED_AT,
        "device_class": None,
        "device_id": device_id,
        "disabled_by": None,
        "entity_category": None,
        "entity_id": entity_id,
        "hidden_by": None,
        "icon": None,
        "id": f"id_{entity_id}",
        "has_entity_name": False,
        "labels": [],
        "modified_at": CREATED_AT,
        "name": None,
        "options": {},
        "original_device_class": None,
        "original_icon": None,
        "original_name": None,
        "platform": SOURCE_DOMAIN,
        "suggested_object_id": None,
        "supported_features": 0,
        "translation_key": None,
        "unique_id": entity_id,
        "previous_unique_id": None,
        "unit_of_measurement": None,
    }


async def _load_registries(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    devices: list[dict[str, Any]],
    entities: list[dict[str, Any]],
) -> None:
    """Load registries stored before Home Assistant 2026.8."""
    hass_storage[dr.STORAGE_KEY] = {
        "version": 1,
        "minor_version": 12,
        "key": dr.STORAGE_KEY,
        "data": {"devices": devices, "deleted_devices": []},
    }
    hass_storage[er.STORAGE_KEY] = {
        "version": 1,
        "minor_version": 18,
        "key": er.STORAGE_KEY,
        "data": {"entities": entities, "deleted_entities": []},
    }
    dr.async_setup(hass)
    for registry in (ar, cr, dr, er, fr, ir, lr):
        await registry.async_load(hass)


async def test_split_modified_device(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    source_entry = MockConfigEntry(domain=SOURCE_DOMAIN)
    source_entry.add_to_hass(hass)
    config_entry = modification_entry(
        ModificationType.DEVICE,
        "composite",
        {
            CONF_MANUFACTURER: "Changed",
            CONF_ASSIGNED_ENTITIES: ["sensor.assigned"],
        },
    )
    config_entry.add_to_hass(hass)
    await _load_registries(
        hass,
        hass_storage,
        [
            _device(
                "composite",
                [source_entry.entry_id, config_entry.entry_id],
                [[SOURCE_DOMAIN, "a"]],
            ),
            _device("other", [source_entry.entry_id], [[SOURCE_DOMAIN, "b"]]),
        ],
        [
            _entity("sensor.native", source_entry.entry_id, "composite"),
            _entity("sensor.assigned", source_entry.entry_id, "composite"),
        ],
    )

    device_registry = dr.async_get(hass)
    split_ids = {
        device.config_entry_id: device.id
        for device in device_registry.async_get_devices_for_composite_device_id(
            "composite"
        )
    }
    assert set(split_ids) == {source_entry.entry_id, config_entry.entry_id}

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    device_id = split_ids[source_entry.entry_id]
    assert config_entry.data[CONF_MODIFICATION_ENTRY_ID] == device_id
    assert config_entry.unique_id == f"device_{device_id}"
    assert device_registry.async_get(device_id).manufacturer == "Changed"
    assert device_registry.async_get(split_ids[config_entry.entry_id]) is None
    assert not dr.async_entries_for_config_entry(device_registry, config_entry.entry_id)
    entity_registry = er.async_get(hass)
    assert entity_registry.async_get("sensor.assigned").device_id == device_id
    assert entity_registry.async_get("sensor.native").device_id == device_id


async def test_split_custom_device(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    source_entry = MockConfigEntry(domain=SOURCE_DOMAIN)
    source_entry.add_to_hass(hass)
    custom_entry = modification_entry(
        ModificationType.DEVICE, "custom", is_custom_entry=True, name="Virtual"
    )
    custom_entry.add_to_hass(hass)
    entity_entry = modification_entry(
        ModificationType.ENTITY, "sensor.moved", {CONF_DEVICE_ID: "custom"}
    )
    entity_entry.add_to_hass(hass)
    await _load_registries(
        hass,
        hass_storage,
        [
            _device(
                "custom",
                [custom_entry.entry_id, source_entry.entry_id],
                [[DOMAIN, custom_entry.entry_id]],
            ),
            _device("source", [source_entry.entry_id], [[SOURCE_DOMAIN, "a"]]),
        ],
        [_entity("sensor.moved", source_entry.entry_id, "custom")],
    )
    device_registry = dr.async_get(hass)
    split_ids = {
        device.config_entry_id: device.id
        for device in device_registry.async_get_devices_for_composite_device_id(
            "custom"
        )
    }

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    custom_device_id = split_ids[custom_entry.entry_id]
    assert custom_entry.data[CONF_MODIFICATION_ENTRY_ID] == custom_device_id
    assert entity_entry.options[CONF_MODIFICATION_DATA] == {
        CONF_DEVICE_ID: custom_device_id
    }
    assert er.async_get(hass).async_get("sensor.moved").device_id == custom_device_id
