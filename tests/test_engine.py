"""Tests for ModificationEngine."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.device_tools.const import (
    CONF_ASSIGNED_ENTITIES,
    CONF_DEVICE_ID,
    CONF_ENTITIES,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_IS_CUSTOM_ENTRY,
    CONF_MODIFICATION_ORIGINAL_DATA,
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


def _make_merge_entry(
    entry_id: str,
    target_device_id: str,
    original_data: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock MERGE config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = entry_id
    entry.title = f"Merge mod {entry_id}"
    entry.data = {
        CONF_MODIFICATION_TYPE: ModificationType.MERGE.value,
        CONF_MODIFICATION_ENTRY_ID: target_device_id,
        CONF_MODIFICATION_IS_CUSTOM_ENTRY: False,
        CONF_MODIFICATION_ORIGINAL_DATA: original_data or {},
    }
    entry.options = {CONF_MODIFICATION_DATA: {}}
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


class TestAsyncOnEntryUnloadedStripsStalDeviceId:
    """Tests that async_on_entry_unloaded strips stale device_id from dependent entries."""

    @pytest.fixture
    def engine(self, mock_hass, mock_store):
        """Create a ModificationEngine instance."""
        return ModificationEngine(mock_hass, mock_store)

    @pytest.mark.asyncio
    async def test_strips_stale_device_id_from_dependent_options(
        self, engine, mock_hass
    ):
        """Deleting a creation-mod should remove device_id from dependent entry options."""
        creation_device_id = "custom_device_123"

        creation_entry = _make_device_entry(
            "creation_entry_1", creation_device_id, is_custom=True
        )
        entity_entry = _make_entity_entry(
            "entity_entry_1", "sensor.test", device_id=creation_device_id
        )

        engine._tracked_entries["creation_entry_1"] = creation_entry
        engine._tracked_entries["entity_entry_1"] = entity_entry
        engine._tracked_entity_ids["creation_entry_1"] = set()
        engine._tracked_device_ids["creation_entry_1"] = {creation_device_id}

        mock_hass.config_entries = MagicMock()

        await engine.async_on_entry_unloaded(creation_entry)

        mock_hass.config_entries.async_update_entry.assert_called_once()
        call_args = mock_hass.config_entries.async_update_entry.call_args
        updated_entry = call_args[0][0]
        new_options = call_args[1]["options"]
        assert updated_entry is entity_entry
        assert CONF_DEVICE_ID not in new_options[CONF_MODIFICATION_DATA]

    @pytest.mark.asyncio
    async def test_does_not_strip_when_device_id_differs(self, engine, mock_hass):
        """Should not update options if the dependent's device_id is not the deleted one."""
        creation_device_id = "custom_device_123"

        creation_entry = _make_device_entry(
            "creation_entry_1", creation_device_id, is_custom=True
        )
        entity_entry = _make_entity_entry(
            "entity_entry_1", "sensor.test", device_id="other_device"
        )

        engine._tracked_entries["creation_entry_1"] = creation_entry
        engine._tracked_entries["entity_entry_1"] = entity_entry
        engine._tracked_entity_ids["creation_entry_1"] = set()
        engine._tracked_device_ids["creation_entry_1"] = {creation_device_id}

        mock_hass.config_entries = MagicMock()

        await engine.async_on_entry_unloaded(creation_entry)

        mock_hass.config_entries.async_update_entry.assert_not_called()


class TestAsyncOnEntryUnloadedMergeCascade:
    """Tests that unloading a creation-mod removes deleted device from MERGE entries."""

    @pytest.fixture
    def engine(self, mock_hass, mock_store):
        """Create a ModificationEngine instance."""
        return ModificationEngine(mock_hass, mock_store)

    @pytest.mark.asyncio
    async def test_removes_device_from_merge_original_data(self, engine, mock_hass):
        """Deleting a creation-mod should strip the device from MERGE original_data."""
        creation_device_id = "virtual_device_1"
        merge_target_id = "real_device_1"

        creation_entry = _make_device_entry(
            "creation_entry_1", creation_device_id, is_custom=True
        )
        merge_entry = _make_merge_entry(
            "merge_entry_1",
            merge_target_id,
            original_data={
                creation_device_id: {
                    CONF_ENTITIES: {
                        "sensor.test": {CONF_DEVICE_ID: creation_device_id},
                    }
                }
            },
        )

        engine._tracked_entries["creation_entry_1"] = creation_entry
        engine._tracked_entries["merge_entry_1"] = merge_entry
        engine._tracked_entity_ids["creation_entry_1"] = set()
        engine._tracked_device_ids["creation_entry_1"] = {creation_device_id}
        engine._tracked_entity_ids["merge_entry_1"] = {"sensor.test"}
        engine._tracked_device_ids["merge_entry_1"] = {
            merge_target_id,
            creation_device_id,
        }

        mock_hass.config_entries = MagicMock()

        await engine.async_on_entry_unloaded(creation_entry)

        # async_update_entry should have been called to update the merge entry's data
        mock_hass.config_entries.async_update_entry.assert_called_once()
        call_args = mock_hass.config_entries.async_update_entry.call_args
        updated_entry = call_args[0][0]
        new_data = call_args[1]["data"]
        assert updated_entry is merge_entry
        assert creation_device_id not in new_data[CONF_MODIFICATION_ORIGINAL_DATA]

    @pytest.mark.asyncio
    async def test_updates_merge_tracked_ids_after_cascade(self, engine, mock_hass):
        """After removing a device from merge, tracked IDs should be updated."""
        creation_device_id = "virtual_device_1"
        merge_target_id = "real_device_1"

        creation_entry = _make_device_entry(
            "creation_entry_1", creation_device_id, is_custom=True
        )
        merge_entry = _make_merge_entry(
            "merge_entry_1",
            merge_target_id,
            original_data={
                creation_device_id: {
                    CONF_ENTITIES: {
                        "sensor.test": {CONF_DEVICE_ID: creation_device_id},
                    }
                }
            },
        )

        engine._tracked_entries["creation_entry_1"] = creation_entry
        engine._tracked_entries["merge_entry_1"] = merge_entry
        engine._tracked_entity_ids["creation_entry_1"] = set()
        engine._tracked_device_ids["creation_entry_1"] = {creation_device_id}
        engine._tracked_entity_ids["merge_entry_1"] = {"sensor.test"}
        engine._tracked_device_ids["merge_entry_1"] = {
            merge_target_id,
            creation_device_id,
        }

        mock_hass.config_entries = MagicMock()

        def _fake_update_entry(entry, **kwargs):
            if "data" in kwargs:
                entry.data = kwargs["data"]
            if "options" in kwargs:
                entry.options = kwargs["options"]

        mock_hass.config_entries.async_update_entry.side_effect = _fake_update_entry

        await engine.async_on_entry_unloaded(creation_entry)

        # After cascade, the merge entry's tracked entity IDs should not include
        # entities from the deleted device.
        assert "sensor.test" not in engine._tracked_entity_ids.get(
            "merge_entry_1", set()
        )
        # The merge entry's tracked device IDs should not include the deleted device.
        assert creation_device_id not in engine._tracked_device_ids.get(
            "merge_entry_1", set()
        )

    @pytest.mark.asyncio
    async def test_entity_handler_cleaned_up_when_no_remaining(
        self, engine, mock_hass, mock_store
    ):
        """Entity handler should be removed if no entries reference it after cascade."""
        creation_device_id = "virtual_device_1"
        merge_target_id = "real_device_1"

        creation_entry = _make_device_entry(
            "creation_entry_1",
            creation_device_id,
            assigned_entities=["sensor.test"],
            is_custom=True,
        )
        merge_entry = _make_merge_entry(
            "merge_entry_1",
            merge_target_id,
            original_data={
                creation_device_id: {
                    CONF_ENTITIES: {
                        "sensor.test": {CONF_DEVICE_ID: creation_device_id},
                    }
                }
            },
        )

        engine._tracked_entries["creation_entry_1"] = creation_entry
        engine._tracked_entries["merge_entry_1"] = merge_entry
        engine._tracked_entity_ids["creation_entry_1"] = {"sensor.test"}
        engine._tracked_device_ids["creation_entry_1"] = {creation_device_id}
        engine._tracked_entity_ids["merge_entry_1"] = {"sensor.test"}
        engine._tracked_device_ids["merge_entry_1"] = {
            merge_target_id,
            creation_device_id,
        }

        mock_hass.config_entries = MagicMock()

        def _fake_update_entry(entry, **kwargs):
            if "data" in kwargs:
                entry.data = kwargs["data"]
            if "options" in kwargs:
                entry.options = kwargs["options"]

        mock_hass.config_entries.async_update_entry.side_effect = _fake_update_entry

        await engine.async_on_entry_unloaded(creation_entry)

        # sensor.test should have been removed from entity handlers
        assert "sensor.test" not in engine._entity_handlers
        # And from the store
        mock_store.async_remove_entity.assert_any_call("sensor.test")

    @pytest.mark.asyncio
    async def test_does_not_touch_merge_without_deleted_device(
        self, engine, mock_hass
    ):
        """MERGE entries not referencing the deleted device should be untouched."""
        creation_device_id = "virtual_device_1"
        merge_target_id = "real_device_1"
        other_device_id = "other_device"

        creation_entry = _make_device_entry(
            "creation_entry_1", creation_device_id, is_custom=True
        )
        merge_entry = _make_merge_entry(
            "merge_entry_1",
            merge_target_id,
            original_data={
                other_device_id: {
                    CONF_ENTITIES: {
                        "sensor.other": {CONF_DEVICE_ID: other_device_id},
                    }
                }
            },
        )

        engine._tracked_entries["creation_entry_1"] = creation_entry
        engine._tracked_entries["merge_entry_1"] = merge_entry
        engine._tracked_entity_ids["creation_entry_1"] = set()
        engine._tracked_device_ids["creation_entry_1"] = {creation_device_id}
        engine._tracked_entity_ids["merge_entry_1"] = {"sensor.other"}
        engine._tracked_device_ids["merge_entry_1"] = {
            merge_target_id,
            other_device_id,
        }

        mock_hass.config_entries = MagicMock()

        await engine.async_on_entry_unloaded(creation_entry)

        # The merge entry should not have been updated
        mock_hass.config_entries.async_update_entry.assert_not_called()
