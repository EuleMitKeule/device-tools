"""Tests for ModificationEngine._find_dependent_entry_ids."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.device_tools.const import (
    CONF_ASSIGNED_ENTITIES,
    CONF_DEVICE_ID,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_IS_CUSTOM_ENTRY,
    CONF_MODIFICATION_TYPE,
    ModificationType,
)
from custom_components.device_tools.engine import ModificationEngine
from custom_components.device_tools.original_data_store import OriginalDataStore


def _make_entity_entry(
    entry_id: str,
    entity_id: str,
    device_id: str | None = None,
) -> MagicMock:
    """Create a mock ENTITY config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = entry_id
    entry.title = f"Entity mod {entry_id}"
    mod_data: dict[str, Any] = {}
    if device_id is not None:
        mod_data[CONF_DEVICE_ID] = device_id
    entry.data = {
        CONF_MODIFICATION_TYPE: ModificationType.ENTITY.value,
        CONF_MODIFICATION_ENTRY_ID: entity_id,
        CONF_MODIFICATION_IS_CUSTOM_ENTRY: False,
    }
    entry.options = {CONF_MODIFICATION_DATA: mod_data}
    return entry


def _make_device_entry(
    entry_id: str,
    device_id: str,
    assigned_entities: list[str] | None = None,
    is_custom: bool = False,
) -> MagicMock:
    """Create a mock DEVICE config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = entry_id
    entry.title = f"Device mod {entry_id}"
    mod_data: dict[str, Any] = {}
    if assigned_entities is not None:
        mod_data[CONF_ASSIGNED_ENTITIES] = assigned_entities
    entry.data = {
        CONF_MODIFICATION_TYPE: ModificationType.DEVICE.value,
        CONF_MODIFICATION_ENTRY_ID: device_id,
        CONF_MODIFICATION_IS_CUSTOM_ENTRY: is_custom,
    }
    entry.options = {CONF_MODIFICATION_DATA: mod_data}
    return entry


@pytest.fixture
def mock_hass():
    hass = MagicMock(spec=HomeAssistant)
    hass.bus = MagicMock()
    hass.bus.async_listen = MagicMock(return_value=MagicMock())
    return hass


@pytest.fixture
def mock_store():
    store = MagicMock(spec=OriginalDataStore)
    store.async_load = AsyncMock()
    store.get_entity = MagicMock(return_value=None)
    store.get_device = MagicMock(return_value=None)
    store.async_remove_entity = AsyncMock()
    store.async_remove_device = AsyncMock()
    return store


class TestFindDependentEntryIds:
    """Tests for ModificationEngine._find_dependent_entry_ids."""

    @pytest.fixture
    def engine(self, mock_hass, mock_store):
        return ModificationEngine(mock_hass, mock_store)

    def test_finds_entity_entry_with_matching_device_id(self, engine):
        """Should find ENTITY entries whose modification_data.device_id matches."""
        creation_device_id = "custom_device_123"
        entity_entry = _make_entity_entry(
            "entity_entry_1", "sensor.test", device_id=creation_device_id
        )
        creation_entry = _make_device_entry(
            "creation_entry_1", creation_device_id, is_custom=True
        )

        engine._tracked_entries["entity_entry_1"] = entity_entry
        engine._tracked_entries["creation_entry_1"] = creation_entry

        result = engine._find_dependent_entry_ids(creation_device_id)
        assert "entity_entry_1" in result

    def test_excludes_creation_entry_itself(self, engine):
        """Should not return the creation entry's own entry_id."""
        creation_device_id = "custom_device_123"
        entity_entry = _make_entity_entry(
            "entity_entry_1", "sensor.test", device_id=creation_device_id
        )
        creation_entry = _make_device_entry(
            "creation_entry_1", creation_device_id, is_custom=True
        )

        engine._tracked_entries["entity_entry_1"] = entity_entry
        engine._tracked_entries["creation_entry_1"] = creation_entry

        result = engine._find_dependent_entry_ids(
            creation_device_id, exclude_entry_id="creation_entry_1"
        )
        assert "creation_entry_1" not in result
        assert "entity_entry_1" in result

    def test_returns_empty_when_no_dependents(self, engine):
        """Should return empty list when nothing references the device."""
        creation_device_id = "custom_device_123"
        other_entity_entry = _make_entity_entry(
            "entity_entry_1", "sensor.test", device_id="other_device"
        )
        engine._tracked_entries["entity_entry_1"] = other_entity_entry

        result = engine._find_dependent_entry_ids(creation_device_id)
        assert result == []

    def test_finds_device_entry_targeting_same_device_id(self, engine):
        """DEVICE entries whose CONF_MODIFICATION_ENTRY_ID matches should be included."""
        creation_device_id = "custom_device_123"
        device_entry = _make_device_entry(
            "device_mod_1",
            creation_device_id,
            assigned_entities=["sensor.test"],
        )
        engine._tracked_entries["device_mod_1"] = device_entry

        result = engine._find_dependent_entry_ids(creation_device_id)
        assert "device_mod_1" in result

    def test_entity_entry_without_device_id_not_included(self, engine):
        """ENTITY entries with no device_id in modification_data should be excluded."""
        entity_entry = _make_entity_entry(
            "entity_entry_1", "sensor.test", device_id=None
        )
        engine._tracked_entries["entity_entry_1"] = entity_entry

        result = engine._find_dependent_entry_ids("custom_device_123")
        assert result == []
