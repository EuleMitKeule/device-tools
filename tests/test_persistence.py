"""Tests for persisting original values and diagnostics."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.device_tools.const import (
    CONF_DEVICE_ID,
    CONF_MANUFACTURER,
    ModificationType,
)
from custom_components.device_tools.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.device_tools.original_data_store import STORAGE_KEY

from .conftest import create_device, create_entity, modification_entry, setup_entry


async def test_original_values_survive_restart(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    source_entry: MockConfigEntry,
) -> None:
    device = create_device(hass, source_entry, "a", manufacturer="Changed")
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "key": STORAGE_KEY,
        "data": {
            "entities": {},
            "devices": {device.id: {CONF_MANUFACTURER: "Acme"}},
        },
    }
    config_entry = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_MANUFACTURER: "Changed"}
    )
    await setup_entry(hass, config_entry)

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert dr.async_get(hass).async_get(device.id).manufacturer == "Acme"


async def test_original_values_are_saved(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    source_entry: MockConfigEntry,
) -> None:
    device = create_device(hass, source_entry, "a", manufacturer="Acme")
    await setup_entry(
        hass,
        modification_entry(
            ModificationType.DEVICE, device.id, {CONF_MANUFACTURER: "Changed"}
        ),
    )
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done()

    assert hass_storage[STORAGE_KEY]["data"] == {
        "entities": {},
        "devices": {device.id: {CONF_MANUFACTURER: "Acme"}},
    }


async def test_stale_original_values_are_forgotten(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    source_entry: MockConfigEntry,
) -> None:
    device = create_device(hass, source_entry, "a", manufacturer="Current")
    entity = create_entity(hass, source_entry, "1")
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "key": STORAGE_KEY,
        "data": {
            "entities": {entity.entity_id: {CONF_DEVICE_ID: None}},
            "devices": {device.id: {CONF_MANUFACTURER: "Stale"}},
        },
    }
    config_entry = modification_entry(
        ModificationType.ENTITY, entity.entity_id, {CONF_DEVICE_ID: device.id}
    )
    await setup_entry(hass, config_entry)

    store = hass.data["device_tools"].store
    assert store.get("devices", device.id) == {}
    assert store.get("entities", entity.entity_id) == {CONF_DEVICE_ID: None}
    assert dr.async_get(hass).async_get(device.id).manufacturer == "Current"


async def test_diagnostics(hass: HomeAssistant, source_entry: MockConfigEntry) -> None:
    device = create_device(hass, source_entry, "a", manufacturer="Acme")
    config_entry = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_MANUFACTURER: "Changed"}
    )
    await setup_entry(hass, config_entry)

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)
    assert diagnostics["loaded"] is True
    assert diagnostics["entities"] == {}
    assert diagnostics["devices"][device.id]["original"] == {CONF_MANUFACTURER: "Acme"}
    assert diagnostics["devices"][device.id]["desired"] == {
        CONF_MANUFACTURER: "Changed"
    }
    assert diagnostics["devices"][device.id]["current"][CONF_MANUFACTURER] == "Changed"
