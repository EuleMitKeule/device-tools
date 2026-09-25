"""Diagnostics support for Device Tools."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .data import DATA_KEY
from .entry_handler import DeviceHandler, EntityHandler
from .original_data_store import KIND_DEVICES, KIND_ENTITIES


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry[Any]
) -> dict[str, Any]:
    """Return diagnostics for a modification."""
    engine = hass.data[DATA_KEY].engine
    store = hass.data[DATA_KEY].store

    entity_ids, device_ids = engine.get_targets(config_entry)

    return {
        "data": dict(config_entry.data),
        "options": dict(config_entry.options),
        "loaded": config_entry in engine.get_config_entries(),
        "entities": {
            entity_id: {
                "current": EntityHandler(hass, entity_id, store).current_data,
                "desired": engine.get_desired_entity_data(entity_id),
                "original": store.get(KIND_ENTITIES, entity_id),
            }
            for entity_id in sorted(entity_ids)
        },
        "devices": {
            device_id: {
                "current": DeviceHandler(hass, device_id, store).current_data,
                "desired": engine.get_desired_device_data(device_id),
                "original": store.get(KIND_DEVICES, device_id),
            }
            for device_id in sorted(device_ids)
        },
    }
