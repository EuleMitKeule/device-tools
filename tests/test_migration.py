"""Tests for async_migrate_entry (1.x → 2.x config-entry migration)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.device_tools.const import (
    CONF_ASSIGNED_ENTITIES,
    CONF_HW_VERSION,
    CONF_MANUFACTURER,
    CONF_MERGE_DEVICE_IDS,
    CONF_MODEL,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_ENTRY_NAME,
    CONF_MODIFICATION_IS_CUSTOM_ENTRY,
    CONF_MODIFICATION_ORIGINAL_DATA,
    CONF_MODIFICATION_TYPE,
    CONF_SW_VERSION,
    ModificationType,
)

MODULE = "custom_components.device_tools"

# ---------------------------------------------------------------------------
# 1.x config-entry data fixtures
# ---------------------------------------------------------------------------


def _v1_data(device_modification: dict[str, Any]) -> dict[str, Any]:
    """Wrap a device_modification dict in the 1.x top-level structure."""
    return {"device_modification": device_modification}


V1_FULL = _v1_data(
    {
        "modification_name": "Full Modification",
        "device_id": "device_1",
        "device_name": "My Device",
        "attribute_modification": {
            "manufacturer": "Acme",
            "model": "Widget",
            "sw_version": "1.0",
            "hw_version": "2.0",
            "serial_number": "SN123",
            "via_device_id": "via_1",
        },
        "entity_modification": {
            "entities": ["entity_uid_1", "entity_uid_2"],
        },
        "merge_modification": {
            "devices": ["merge_dev_1", "merge_dev_2"],
        },
    }
)

V1_ATTRIBUTE_ONLY = _v1_data(
    {
        "modification_name": "Attr Only",
        "device_id": "device_1",
        "device_name": "My Device",
        "attribute_modification": {
            "manufacturer": "Acme",
            "model": None,
            "sw_version": None,
            "hw_version": None,
            "serial_number": None,
            "via_device_id": None,
        },
        "entity_modification": None,
        "merge_modification": None,
    }
)

V1_ENTITY_ONLY = _v1_data(
    {
        "modification_name": "Entity Only",
        "device_id": "device_1",
        "device_name": "My Device",
        "attribute_modification": None,
        "entity_modification": {
            "entities": ["entity_uid_1", "entity_uid_2"],
        },
        "merge_modification": None,
    }
)

V1_MERGE_ONLY = _v1_data(
    {
        "modification_name": "Merge Only",
        "device_id": "device_1",
        "device_name": "My Device",
        "attribute_modification": None,
        "entity_modification": None,
        "merge_modification": {
            "devices": ["merge_dev_1", "merge_dev_2"],
        },
    }
)

V1_CUSTOM_NO_ATTRS = _v1_data(
    {
        "modification_name": "Custom Entry",
        "device_id": None,
        "device_name": "My Virtual Device",
        "attribute_modification": None,
        "entity_modification": None,
        "merge_modification": None,
    }
)

V1_CUSTOM_WITH_ATTRS = _v1_data(
    {
        "modification_name": "Custom With Attrs",
        "device_id": None,
        "device_name": "Virtual With Attrs",
        "attribute_modification": {
            "manufacturer": "Virtual Corp",
            "model": "V-100",
            "sw_version": None,
            "hw_version": None,
            "serial_number": None,
            "via_device_id": None,
        },
        "entity_modification": None,
        "merge_modification": None,
    }
)

V1_DEVICE_MISSING = _v1_data(
    {
        "modification_name": "Stale Ref",
        "device_id": "deleted_device",
        "device_name": "Gone Device",
        "attribute_modification": {
            "manufacturer": "X",
            "model": None,
            "sw_version": None,
            "hw_version": None,
            "serial_number": None,
            "via_device_id": None,
        },
        "entity_modification": None,
        "merge_modification": None,
    }
)

V1_NO_MODS = _v1_data(
    {
        "modification_name": "No Mods",
        "device_id": "device_1",
        "device_name": "My Device",
        "attribute_modification": None,
        "entity_modification": None,
        "merge_modification": None,
    }
)

V1_ATTR_AND_ENTITY = _v1_data(
    {
        "modification_name": "Attr+Entity",
        "device_id": "device_1",
        "device_name": "My Device",
        "attribute_modification": {
            "manufacturer": "Combined",
            "model": None,
            "sw_version": None,
            "hw_version": None,
            "serial_number": None,
            "via_device_id": None,
        },
        "entity_modification": {
            "entities": ["entity_uid_1"],
        },
        "merge_modification": None,
    }
)

V1_CUSTOM_WITH_ENTITIES = _v1_data(
    {
        "modification_name": "Custom With Entities",
        "device_id": None,
        "device_name": "Virtual With Entities",
        "attribute_modification": None,
        "entity_modification": {
            "entities": ["entity_uid_1"],
        },
        "merge_modification": None,
    }
)

V1_EMPTY_MODIFICATION_NAME = _v1_data(
    {
        "modification_name": "",
        "device_id": "device_1",
        "device_name": "My Device",
        "attribute_modification": {
            "manufacturer": "Acme",
            "model": None,
            "sw_version": None,
            "hw_version": None,
            "serial_number": None,
            "via_device_id": None,
        },
        "entity_modification": None,
        "merge_modification": None,
    }
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_v1_config_entry(
    data: dict[str, Any],
    entry_id: str = "old_entry_1",
) -> MagicMock:
    """Build a mock v1 ConfigEntry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.version = 1
    entry.entry_id = entry_id
    entry.data = data
    entry.options = {}
    entry.title = data.get("device_modification", {}).get(
        "modification_name", "Unknown"
    )
    entry.source = "user"
    entry.created_at = "2025-01-01T00:00:00+00:00"
    entry.disabled_by = None
    entry.discovery_keys = {}
    entry.pref_disable_new_entities = False
    entry.pref_disable_polling = False
    entry.domain = "device_tools"
    return entry


def _make_device(
    device_id: str,
    config_entries: set[str] | None = None,
    name: str = "Test Device",
    name_by_user: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    sw_version: str | None = None,
    hw_version: str | None = None,
    serial_number: str | None = None,
    via_device_id: str | None = None,
) -> MagicMock:
    """Build a mock DeviceEntry."""
    device = MagicMock()
    device.id = device_id
    device.name = name
    device.name_by_user = name_by_user
    device.manufacturer = manufacturer
    device.model = model
    device.sw_version = sw_version
    device.hw_version = hw_version
    device.serial_number = serial_number
    device.via_device_id = via_device_id
    device.config_entries = config_entries or {device_id}
    device.dict_repr = {
        "manufacturer": manufacturer,
        "model": model,
        "sw_version": sw_version,
        "hw_version": hw_version,
        "serial_number": serial_number,
        "via_device_id": via_device_id,
    }
    return device


def _make_entity(
    entity_id: str,
    name: str | None = None,
    original_name: str | None = None,
    device_id: str | None = "other_device",
) -> MagicMock:
    """Build a mock entity registry entry."""
    entity = MagicMock()
    entity.entity_id = entity_id
    entity.id = entity_id  # registry entry ID (same for simplicity)
    entity.name = name
    entity.original_name = original_name
    entity.device_id = device_id
    entity.extended_dict = {
        "device_id": device_id,
        "entity_category": None,
    }
    return entity


@pytest.fixture
def mock_hass():
    """Create a mock HomeAssistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.config_entries = MagicMock()
    hass.config_entries.async_remove = AsyncMock()
    hass.config_entries.async_add = AsyncMock()
    hass.create_task = MagicMock()
    return hass


class _AddedEntryCollector:
    """Collect ConfigEntry objects passed to hass.config_entries.async_add."""

    def __init__(self) -> None:
        self.entries: list[ConfigEntry[Any]] = []

    async def __call__(self, entry: ConfigEntry[Any]) -> None:
        self.entries.append(entry)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMigrateEntryAlreadyV2:
    """Migration should be a no-op for entries already at version ≥ 2."""

    @pytest.mark.asyncio
    async def test_returns_true_for_v2(self, mock_hass):
        entry = MagicMock(spec=ConfigEntry)
        entry.version = 2
        from custom_components.device_tools import async_migrate_entry

        result = await async_migrate_entry(mock_hass, entry)
        assert result is True


class TestMigrateEntryMissingDeviceModification:
    """Migration should fail when device_modification is absent."""

    @pytest.mark.asyncio
    async def test_returns_false_without_device_modification(self, mock_hass):
        entry = MagicMock(spec=ConfigEntry)
        entry.version = 1
        entry.data = {}
        from custom_components.device_tools import async_migrate_entry

        result = await async_migrate_entry(mock_hass, entry)
        assert result is False


class TestMigrateCustomDeviceNone:
    """Migration of entries with device_id=None (virtual/custom device)."""

    @pytest.mark.asyncio
    async def test_custom_entry_no_attrs(self, mock_hass):
        """Pure creation entry without attribute_modification succeeds."""
        entry = _make_v1_config_entry(V1_CUSTOM_NO_ATTRS, entry_id="custom_1")
        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        with patch(f"{MODULE}.dr.async_get") as mock_dr:
            mock_dr.return_value = MagicMock()
            from custom_components.device_tools import async_migrate_entry

            result = await async_migrate_entry(mock_hass, entry)

        assert result is True
        assert len(collector.entries) == 1
        new = collector.entries[0]
        assert new.data[CONF_MODIFICATION_TYPE] == ModificationType.DEVICE
        assert new.data[CONF_MODIFICATION_IS_CUSTOM_ENTRY] is True
        assert new.data[CONF_MODIFICATION_ENTRY_NAME] == "My Virtual Device"
        # Temporary entry_id used as placeholder
        assert new.data[CONF_MODIFICATION_ENTRY_ID] == "custom_1"
        assert new.options[CONF_MODIFICATION_DATA] == {}
        mock_hass.create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_custom_entry_with_attrs(self, mock_hass):
        """Creation entry with attribute_modification carries attrs over."""
        entry = _make_v1_config_entry(V1_CUSTOM_WITH_ATTRS, entry_id="custom_2")
        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        with patch(f"{MODULE}.dr.async_get") as mock_dr:
            mock_dr.return_value = MagicMock()
            from custom_components.device_tools import async_migrate_entry

            result = await async_migrate_entry(mock_hass, entry)

        assert result is True
        assert len(collector.entries) == 1
        new = collector.entries[0]
        mod_data = new.options[CONF_MODIFICATION_DATA]
        assert mod_data[CONF_MANUFACTURER] == "Virtual Corp"
        assert mod_data[CONF_MODEL] == "V-100"
        # None values should be excluded
        assert CONF_SW_VERSION not in mod_data
        assert CONF_HW_VERSION not in mod_data

    @pytest.mark.asyncio
    async def test_unique_id_uses_old_entry_id(self, mock_hass):
        """unique_id should use the old entry_id, not 'None'."""
        entry = _make_v1_config_entry(V1_CUSTOM_NO_ATTRS, entry_id="old_abc")
        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        with patch(f"{MODULE}.dr.async_get") as mock_dr:
            mock_dr.return_value = MagicMock()
            from custom_components.device_tools import async_migrate_entry

            await async_migrate_entry(mock_hass, entry)

        new = collector.entries[0]
        assert new.unique_id == "device_old_abc"
        assert "None" not in new.unique_id

    @pytest.mark.asyncio
    async def test_two_custom_entries_no_collision(self, mock_hass):
        """Two custom entries with device_id=None must get different unique_ids."""
        entry_a = _make_v1_config_entry(V1_CUSTOM_NO_ATTRS, entry_id="entry_a")
        entry_b = _make_v1_config_entry(V1_CUSTOM_NO_ATTRS, entry_id="entry_b")
        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        with patch(f"{MODULE}.dr.async_get") as mock_dr:
            mock_dr.return_value = MagicMock()
            from custom_components.device_tools import async_migrate_entry

            await async_migrate_entry(mock_hass, entry_a)
            await async_migrate_entry(mock_hass, entry_b)

        assert len(collector.entries) == 2
        assert collector.entries[0].unique_id != collector.entries[1].unique_id

    @pytest.mark.asyncio
    async def test_custom_entry_with_entities(self, mock_hass):
        """Custom device with entity_modification folds entities into the DEVICE entry."""
        entry = _make_v1_config_entry(V1_CUSTOM_WITH_ENTITIES, entry_id="custom_3")
        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        entity = _make_entity("sensor.one", device_id="other_dev")
        mock_er = MagicMock()
        mock_er.async_get.side_effect = lambda uid: (
            entity if uid == "entity_uid_1" else None
        )

        with (
            patch(f"{MODULE}.dr.async_get") as mock_dr,
            patch(f"{MODULE}.er.async_get", return_value=mock_er),
        ):
            mock_dr.return_value = MagicMock()
            from custom_components.device_tools import async_migrate_entry

            result = await async_migrate_entry(mock_hass, entry)

        assert result is True
        assert len(collector.entries) == 1
        new = collector.entries[0]
        assert new.data[CONF_MODIFICATION_TYPE] == ModificationType.DEVICE
        assert new.data[CONF_MODIFICATION_IS_CUSTOM_ENTRY] is True
        assert new.options[CONF_MODIFICATION_DATA][CONF_ASSIGNED_ENTITIES] == [
            "sensor.one"
        ]


class TestMigrateDeviceNotInRegistry:
    """Migration when the referenced device no longer exists."""

    @pytest.mark.asyncio
    async def test_returns_true_and_removes_entry(self, mock_hass):
        """Migration succeeds and schedules removal of the stale entry."""
        entry = _make_v1_config_entry(V1_DEVICE_MISSING, entry_id="stale_1")
        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = None  # device gone

        with patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry):
            from custom_components.device_tools import async_migrate_entry

            result = await async_migrate_entry(mock_hass, entry)

        assert result is True
        # No new entries should be created
        assert len(collector.entries) == 0
        # Removal should be scheduled
        mock_hass.create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_entries_created_for_missing_device(self, mock_hass):
        """No new 2.x entries are created when the device is gone."""
        entry = _make_v1_config_entry(V1_FULL, entry_id="stale_2")
        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = None

        mock_entity_registry = MagicMock()
        mock_entity_registry.async_get.return_value = None

        with (
            patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry),
            patch(f"{MODULE}.er.async_get", return_value=mock_entity_registry),
        ):
            from custom_components.device_tools import async_migrate_entry

            await async_migrate_entry(mock_hass, entry)

        assert len(collector.entries) == 0


class TestMigrateAttributeOnly:
    """Migration of entries with only attribute_modification."""

    @pytest.mark.asyncio
    async def test_creates_device_modification(self, mock_hass):
        """A single DEVICE modification entry should be created."""
        entry = _make_v1_config_entry(V1_ATTRIBUTE_ONLY)
        device = _make_device(
            "device_1",
            config_entries={"other_integration", entry.entry_id},
            name="My Device",
            manufacturer="OldMfg",
        )
        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = device

        with patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry):
            from custom_components.device_tools import async_migrate_entry

            result = await async_migrate_entry(mock_hass, entry)

        assert result is True
        assert len(collector.entries) == 1
        new = collector.entries[0]
        assert new.data[CONF_MODIFICATION_TYPE] == ModificationType.DEVICE
        assert new.data[CONF_MODIFICATION_IS_CUSTOM_ENTRY] is False
        assert new.data[CONF_MODIFICATION_ENTRY_ID] == "device_1"
        # manufacturer "Acme" from v1 data
        assert new.options[CONF_MODIFICATION_DATA][CONF_MANUFACTURER] == "Acme"
        # None values should be excluded
        assert CONF_MODEL not in new.options[CONF_MODIFICATION_DATA]
        # Original data should be captured from the device
        assert CONF_MODIFICATION_ORIGINAL_DATA in new.data

    @pytest.mark.asyncio
    async def test_custom_device_with_attrs(self, mock_hass):
        """A custom device (only config entry) goes through creation path."""
        entry = _make_v1_config_entry(V1_ATTRIBUTE_ONLY)
        device = _make_device(
            "device_1",
            config_entries={entry.entry_id},
            name="My Device",
        )
        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = device

        with patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry):
            from custom_components.device_tools import async_migrate_entry

            result = await async_migrate_entry(mock_hass, entry)

        assert result is True
        assert len(collector.entries) == 1
        new = collector.entries[0]
        assert new.data[CONF_MODIFICATION_IS_CUSTOM_ENTRY] is True
        assert new.options[CONF_MODIFICATION_DATA][CONF_MANUFACTURER] == "Acme"


class TestMigrateEntityOnly:
    """Migration of entries with only entity_modification.

    In 2.x, entity assignments are stored as CONF_ASSIGNED_ENTITIES inside
    a DEVICE modification entry, not as individual ENTITY entries.
    """

    @pytest.mark.asyncio
    async def test_creates_single_device_entry_with_assigned_entities(self, mock_hass):
        """One DEVICE entry with CONF_ASSIGNED_ENTITIES storing entity_ids."""
        entry = _make_v1_config_entry(V1_ENTITY_ONLY)
        device = _make_device(
            "device_1",
            config_entries={"other_integration", entry.entry_id},
        )

        entities = {
            "entity_uid_1": _make_entity("sensor.one", device_id="other_dev"),
            "entity_uid_2": _make_entity("switch.two", device_id="other_dev"),
        }

        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = device

        mock_entity_registry = MagicMock()
        mock_entity_registry.async_get.side_effect = lambda uid: entities.get(uid)

        with (
            patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry),
            patch(f"{MODULE}.er.async_get", return_value=mock_entity_registry),
        ):
            from custom_components.device_tools import async_migrate_entry

            result = await async_migrate_entry(mock_hass, entry)

        assert result is True
        assert len(collector.entries) == 1
        new = collector.entries[0]
        assert new.data[CONF_MODIFICATION_TYPE] == ModificationType.DEVICE
        assert new.data[CONF_MODIFICATION_IS_CUSTOM_ENTRY] is False
        assigned = new.options[CONF_MODIFICATION_DATA][CONF_ASSIGNED_ENTITIES]
        assert set(assigned) == {"sensor.one", "switch.two"}

    @pytest.mark.asyncio
    async def test_converts_uids_to_entity_ids(self, mock_hass):
        """1.x stores registry UIDs; 2.x needs entity_id strings."""
        entry = _make_v1_config_entry(V1_ENTITY_ONLY)
        device = _make_device(
            "device_1",
            config_entries={"other_integration", entry.entry_id},
        )

        # UID differs from entity_id
        entity = MagicMock()
        entity.id = "registry-uuid-abc"
        entity.entity_id = "sensor.temperature"
        entity.device_id = "other_dev"

        mock_entity_registry = MagicMock()
        mock_entity_registry.async_get.side_effect = (
            lambda uid: entity if uid == "entity_uid_1" else None
        )

        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = device

        with (
            patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry),
            patch(f"{MODULE}.er.async_get", return_value=mock_entity_registry),
        ):
            from custom_components.device_tools import async_migrate_entry

            await async_migrate_entry(mock_hass, entry)

        new = collector.entries[0]
        assigned = new.options[CONF_MODIFICATION_DATA][CONF_ASSIGNED_ENTITIES]
        assert "sensor.temperature" in assigned
        # The UID should NOT appear in the data
        assert "registry-uuid-abc" not in assigned

    @pytest.mark.asyncio
    async def test_skips_entity_already_on_target_device(self, mock_hass):
        """Entities already assigned to the target device are filtered out."""
        entry = _make_v1_config_entry(V1_ENTITY_ONLY)
        device = _make_device(
            "device_1",
            config_entries={"other_integration", entry.entry_id},
        )

        entities = {
            "entity_uid_1": _make_entity("sensor.one", device_id="device_1"),
            "entity_uid_2": _make_entity("switch.two", device_id="other_dev"),
        }

        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = device

        mock_entity_registry = MagicMock()
        mock_entity_registry.async_get.side_effect = lambda uid: entities.get(uid)

        with (
            patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry),
            patch(f"{MODULE}.er.async_get", return_value=mock_entity_registry),
        ):
            from custom_components.device_tools import async_migrate_entry

            result = await async_migrate_entry(mock_hass, entry)

        assert result is True
        assert len(collector.entries) == 1
        assigned = collector.entries[0].options[CONF_MODIFICATION_DATA][
            CONF_ASSIGNED_ENTITIES
        ]
        assert assigned == ["switch.two"]

    @pytest.mark.asyncio
    async def test_skips_missing_entities(self, mock_hass):
        """Entities no longer in the registry are skipped."""
        entry = _make_v1_config_entry(V1_ENTITY_ONLY)
        device = _make_device(
            "device_1",
            config_entries={"other_integration", entry.entry_id},
        )

        entities = {
            "entity_uid_1": _make_entity("sensor.one", device_id="other_dev"),
            # entity_uid_2 is missing
        }

        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = device

        mock_entity_registry = MagicMock()
        mock_entity_registry.async_get.side_effect = lambda uid: entities.get(uid)

        with (
            patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry),
            patch(f"{MODULE}.er.async_get", return_value=mock_entity_registry),
        ):
            from custom_components.device_tools import async_migrate_entry

            result = await async_migrate_entry(mock_hass, entry)

        assert result is True
        assert len(collector.entries) == 1
        assigned = collector.entries[0].options[CONF_MODIFICATION_DATA][
            CONF_ASSIGNED_ENTITIES
        ]
        assert assigned == ["sensor.one"]

    @pytest.mark.asyncio
    async def test_all_entities_missing_creates_no_device_entry(self, mock_hass):
        """If every entity is gone, no DEVICE entry is created."""
        entry = _make_v1_config_entry(V1_ENTITY_ONLY)
        device = _make_device(
            "device_1",
            config_entries={"other_integration", entry.entry_id},
        )

        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = device

        mock_entity_registry = MagicMock()
        mock_entity_registry.async_get.return_value = None

        with (
            patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry),
            patch(f"{MODULE}.er.async_get", return_value=mock_entity_registry),
        ):
            from custom_components.device_tools import async_migrate_entry

            result = await async_migrate_entry(mock_hass, entry)

        assert result is True
        assert len(collector.entries) == 0

    @pytest.mark.asyncio
    async def test_all_entities_on_target_device_creates_no_device_entry(
        self, mock_hass
    ):
        """If every entity is already on the target device, no entry is created."""
        entry = _make_v1_config_entry(V1_ENTITY_ONLY)
        device = _make_device(
            "device_1",
            config_entries={"other_integration", entry.entry_id},
        )

        entities = {
            "entity_uid_1": _make_entity("sensor.one", device_id="device_1"),
            "entity_uid_2": _make_entity("switch.two", device_id="device_1"),
        }

        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = device

        mock_entity_registry = MagicMock()
        mock_entity_registry.async_get.side_effect = lambda uid: entities.get(uid)

        with (
            patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry),
            patch(f"{MODULE}.er.async_get", return_value=mock_entity_registry),
        ):
            from custom_components.device_tools import async_migrate_entry

            result = await async_migrate_entry(mock_hass, entry)

        assert result is True
        assert len(collector.entries) == 0


# ---------------------------------------------------------------------------
# Tests — combined attribute + entity
# ---------------------------------------------------------------------------


class TestMigrateAttributeAndEntity:
    """Migration of entries with both attribute_modification and entity_modification."""

    @pytest.mark.asyncio
    async def test_creates_single_device_entry(self, mock_hass):
        """Both attrs and assigned_entities land in ONE DEVICE entry."""
        entry = _make_v1_config_entry(V1_ATTR_AND_ENTITY)
        device = _make_device(
            "device_1",
            config_entries={"other_integration", entry.entry_id},
        )

        entities = {
            "entity_uid_1": _make_entity("sensor.one", device_id="other_dev"),
        }

        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = device

        mock_entity_registry = MagicMock()
        mock_entity_registry.async_get.side_effect = lambda uid: entities.get(uid)

        with (
            patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry),
            patch(f"{MODULE}.er.async_get", return_value=mock_entity_registry),
        ):
            from custom_components.device_tools import async_migrate_entry

            result = await async_migrate_entry(mock_hass, entry)

        assert result is True
        # Only ONE entry — no separate ENTITY entries
        assert len(collector.entries) == 1
        new = collector.entries[0]
        assert new.data[CONF_MODIFICATION_TYPE] == ModificationType.DEVICE
        mod_data = new.options[CONF_MODIFICATION_DATA]
        assert mod_data[CONF_MANUFACTURER] == "Combined"
        assert mod_data[CONF_ASSIGNED_ENTITIES] == ["sensor.one"]

    # ---------------------------------------------------------------------------
    # Tests — merge only
    # ---------------------------------------------------------------------------
    """Migration of entries with only merge_modification."""

    @pytest.mark.asyncio
    async def test_creates_merge_entry_with_device_ids(self, mock_hass):
        """A single MERGE entry is created with CONF_MERGE_DEVICE_IDS in modification_data."""
        entry = _make_v1_config_entry(V1_MERGE_ONLY)
        device = _make_device(
            "device_1",
            config_entries={"other_integration", entry.entry_id},
        )
        merge_dev_1 = _make_device("merge_dev_1", name="Merge 1")
        merge_dev_2 = _make_device("merge_dev_2", name="Merge 2")

        def registry_get(did):
            return {
                "device_1": device,
                "merge_dev_1": merge_dev_1,
                "merge_dev_2": merge_dev_2,
            }.get(did)

        merge_entity = _make_entity("sensor.merged", device_id="merge_dev_1")

        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.side_effect = registry_get

        mock_entity_registry = MagicMock()

        with (
            patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry),
            patch(f"{MODULE}.er.async_get", return_value=mock_entity_registry),
            patch(
                f"{MODULE}.er.async_entries_for_device",
                return_value=[merge_entity],
            ),
        ):
            from custom_components.device_tools import async_migrate_entry

            result = await async_migrate_entry(mock_hass, entry)

        assert result is True
        assert len(collector.entries) == 1
        new = collector.entries[0]
        assert new.data[CONF_MODIFICATION_TYPE] == ModificationType.MERGE
        assert new.data[CONF_MODIFICATION_IS_CUSTOM_ENTRY] is False
        assert new.data[CONF_MODIFICATION_ENTRY_ID] == "device_1"
        # CONF_MERGE_DEVICE_IDS must be present in modification_data
        mod_data = new.options[CONF_MODIFICATION_DATA]
        assert CONF_MERGE_DEVICE_IDS in mod_data
        assert set(mod_data[CONF_MERGE_DEVICE_IDS]) == {"merge_dev_1", "merge_dev_2"}
        # original_data should contain per-device entity data
        orig = new.data[CONF_MODIFICATION_ORIGINAL_DATA]
        assert "merge_dev_1" in orig
        assert "merge_dev_2" in orig

    @pytest.mark.asyncio
    async def test_skips_missing_merge_devices(self, mock_hass):
        """Missing merge source devices are skipped; remaining are kept."""
        entry = _make_v1_config_entry(V1_MERGE_ONLY)
        device = _make_device(
            "device_1",
            config_entries={"other_integration", entry.entry_id},
        )
        merge_dev_1 = _make_device("merge_dev_1", name="Merge 1")

        def registry_get(did):
            return {
                "device_1": device,
                "merge_dev_1": merge_dev_1,
                # merge_dev_2 is missing
            }.get(did)

        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.side_effect = registry_get

        mock_entity_registry = MagicMock()

        with (
            patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry),
            patch(f"{MODULE}.er.async_get", return_value=mock_entity_registry),
            patch(f"{MODULE}.er.async_entries_for_device", return_value=[]),
        ):
            from custom_components.device_tools import async_migrate_entry

            result = await async_migrate_entry(mock_hass, entry)

        assert result is True
        new = collector.entries[0]
        mod_data = new.options[CONF_MODIFICATION_DATA]
        assert mod_data[CONF_MERGE_DEVICE_IDS] == ["merge_dev_1"]
        assert "merge_dev_2" not in new.data[CONF_MODIFICATION_ORIGINAL_DATA]

    @pytest.mark.asyncio
    async def test_all_merge_devices_missing(self, mock_hass):
        """All merge devices gone → entry is still created with empty lists."""
        entry = _make_v1_config_entry(V1_MERGE_ONLY)
        device = _make_device(
            "device_1",
            config_entries={"other_integration", entry.entry_id},
        )

        def registry_get(did):
            return {"device_1": device}.get(did)

        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.side_effect = registry_get

        with (
            patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry),
            patch(f"{MODULE}.er.async_get", return_value=MagicMock()),
        ):
            from custom_components.device_tools import async_migrate_entry

            result = await async_migrate_entry(mock_hass, entry)

        assert result is True
        new = collector.entries[0]
        assert new.options[CONF_MODIFICATION_DATA][CONF_MERGE_DEVICE_IDS] == []


class TestMigrateFullEntry:
    """Migration of a complete 1.x entry with all three modification types."""

    @pytest.mark.asyncio
    async def test_creates_device_and_merge_entries(self, mock_hass):
        """attrs + entities fold into ONE DEVICE entry; merge is separate → 2 entries."""
        entry = _make_v1_config_entry(V1_FULL)
        device = _make_device(
            "device_1",
            config_entries={"other_integration", entry.entry_id},
            name="My Device",
            manufacturer="OldMfg",
        )
        merge_dev_1 = _make_device("merge_dev_1")
        merge_dev_2 = _make_device("merge_dev_2")

        def registry_get(did):
            return {
                "device_1": device,
                "merge_dev_1": merge_dev_1,
                "merge_dev_2": merge_dev_2,
            }.get(did)

        entities = {
            "entity_uid_1": _make_entity("sensor.one", device_id="other_dev"),
            "entity_uid_2": _make_entity("switch.two", device_id="other_dev"),
        }

        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.side_effect = registry_get

        mock_entity_registry = MagicMock()
        mock_entity_registry.async_get.side_effect = lambda uid: entities.get(uid)

        merge_entity = _make_entity("sensor.merged", device_id="merge_dev_1")

        with (
            patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry),
            patch(f"{MODULE}.er.async_get", return_value=mock_entity_registry),
            patch(
                f"{MODULE}.er.async_entries_for_device",
                return_value=[merge_entity],
            ),
        ):
            from custom_components.device_tools import async_migrate_entry

            result = await async_migrate_entry(mock_hass, entry)

        assert result is True
        # 1 DEVICE (attrs + assigned_entities) + 1 MERGE = 2 entries
        assert len(collector.entries) == 2

        types = [e.data[CONF_MODIFICATION_TYPE] for e in collector.entries]
        assert types.count(ModificationType.DEVICE) == 1
        assert types.count(ModificationType.MERGE) == 1

        # DEVICE entry should contain both attrs and assigned entities
        device_entry = next(
            e
            for e in collector.entries
            if e.data[CONF_MODIFICATION_TYPE] == ModificationType.DEVICE
        )
        mod_data = device_entry.options[CONF_MODIFICATION_DATA]
        assert mod_data[CONF_MANUFACTURER] == "Acme"
        assert set(mod_data[CONF_ASSIGNED_ENTITIES]) == {"sensor.one", "switch.two"}


class TestMigrateCreationEntry:
    """Migration of a creation entry (custom device that exists in registry)."""

    @pytest.mark.asyncio
    async def test_custom_device_in_registry(self, mock_hass):
        """A device owned solely by the old entry is treated as a creation entry."""
        entry = _make_v1_config_entry(V1_ATTRIBUTE_ONLY, entry_id="sole_owner")
        device = _make_device(
            "device_1",
            config_entries={"sole_owner"},
            name="Custom Device",
        )

        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = device

        with patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry):
            from custom_components.device_tools import async_migrate_entry

            result = await async_migrate_entry(mock_hass, entry)

        assert result is True
        assert len(collector.entries) == 1
        new = collector.entries[0]
        assert new.data[CONF_MODIFICATION_IS_CUSTOM_ENTRY] is True
        assert new.data[CONF_MODIFICATION_ENTRY_ID] == "device_1"

    @pytest.mark.asyncio
    async def test_creation_entry_no_attribute_modification(self, mock_hass):
        """Custom device without attribute_modification gets empty modification_data."""
        entry = _make_v1_config_entry(V1_NO_MODS, entry_id="sole_owner")
        device = _make_device(
            "device_1",
            config_entries={"sole_owner"},
            name="Bare Device",
        )

        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = device

        with patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry):
            from custom_components.device_tools import async_migrate_entry

            result = await async_migrate_entry(mock_hass, entry)

        assert result is True
        # With the sole-owner check, this IS a custom entry even though
        # attribute_modification is None → creation path, not attribute path
        assert len(collector.entries) == 1
        new = collector.entries[0]
        assert new.data[CONF_MODIFICATION_IS_CUSTOM_ENTRY] is True
        assert new.options[CONF_MODIFICATION_DATA] == {}


class TestMigrateEntryTitleAndNaming:
    """Ensure migrated entries have correct title and CONF_MODIFICATION_ENTRY_NAME."""

    @pytest.mark.asyncio
    async def test_title_uses_modification_name(self, mock_hass):
        """Title should use the 1.x modification_name for user recognition."""
        entry = _make_v1_config_entry(V1_ATTRIBUTE_ONLY)
        device = _make_device(
            "device_1",
            config_entries={"other_integration", entry.entry_id},
            name="HW Device Name",
            name_by_user="User Name",
        )

        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = device

        with patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry):
            from custom_components.device_tools import async_migrate_entry

            await async_migrate_entry(mock_hass, entry)

        new = collector.entries[0]
        # Title uses modification_name ("Attr Only"), not the device name
        assert new.title == "Device: Attr Only"
        assert new.unique_id == "device_device_1"

    @pytest.mark.asyncio
    async def test_entry_name_uses_device_name(self, mock_hass):
        """CONF_MODIFICATION_ENTRY_NAME should be the actual device name."""
        entry = _make_v1_config_entry(V1_ATTRIBUTE_ONLY)
        device = _make_device(
            "device_1",
            config_entries={"other_integration", entry.entry_id},
            name="HW Device Name",
            name_by_user="User Device Name",
        )

        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = device

        with patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry):
            from custom_components.device_tools import async_migrate_entry

            await async_migrate_entry(mock_hass, entry)

        new = collector.entries[0]
        # CONF_MODIFICATION_ENTRY_NAME = name_for_device (config-flow convention)
        assert new.data[CONF_MODIFICATION_ENTRY_NAME] == "User Device Name"

    @pytest.mark.asyncio
    async def test_empty_modification_name_falls_back_to_device_name(self, mock_hass):
        """When modification_name is empty, title falls back to device name."""
        entry = _make_v1_config_entry(V1_EMPTY_MODIFICATION_NAME)
        device = _make_device(
            "device_1",
            config_entries={"other_integration", entry.entry_id},
            name="Fallback Name",
        )

        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = device

        with patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry):
            from custom_components.device_tools import async_migrate_entry

            await async_migrate_entry(mock_hass, entry)

        new = collector.entries[0]
        assert new.title == "Device: Fallback Name"

    @pytest.mark.asyncio
    async def test_creation_title_uses_modification_name(self, mock_hass):
        """Custom device title should prefer modification_name."""
        entry = _make_v1_config_entry(V1_CUSTOM_WITH_ATTRS, entry_id="custom_t")
        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        with patch(f"{MODULE}.dr.async_get") as mock_dr:
            mock_dr.return_value = MagicMock()
            from custom_components.device_tools import async_migrate_entry

            await async_migrate_entry(mock_hass, entry)

        new = collector.entries[0]
        # modification_name = "Custom With Attrs"
        assert new.title == "Device: Custom With Attrs"
        # CONF_MODIFICATION_ENTRY_NAME = device_name for custom entries
        assert new.data[CONF_MODIFICATION_ENTRY_NAME] == "Virtual With Attrs"

    @pytest.mark.asyncio
    async def test_merge_title_uses_modification_name(self, mock_hass):
        """Merge entries should also use modification_name in the title."""
        entry = _make_v1_config_entry(V1_MERGE_ONLY)
        device = _make_device(
            "device_1",
            config_entries={"other_integration", entry.entry_id},
            name="Target Device",
            name_by_user="User Target",
        )
        merge_dev = _make_device("merge_dev_1")

        def registry_get(did):
            return {"device_1": device, "merge_dev_1": merge_dev}.get(did)

        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.side_effect = registry_get

        mock_entity_registry = MagicMock()

        with (
            patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry),
            patch(f"{MODULE}.er.async_get", return_value=mock_entity_registry),
            patch(f"{MODULE}.er.async_entries_for_device", return_value=[]),
        ):
            from custom_components.device_tools import async_migrate_entry

            await async_migrate_entry(mock_hass, entry)

        new = collector.entries[0]
        # modification_name = "Merge Only"
        assert new.title == "Merge: Merge Only"
        # CONF_MODIFICATION_ENTRY_NAME = name_for_device
        assert new.data[CONF_MODIFICATION_ENTRY_NAME] == "User Target"


class TestMigrateOldEntryRemoval:
    """The old v1 config entry should be scheduled for removal."""

    @pytest.mark.asyncio
    async def test_removal_scheduled(self, mock_hass):
        entry = _make_v1_config_entry(V1_ATTRIBUTE_ONLY)
        device = _make_device(
            "device_1",
            config_entries={"other_integration", entry.entry_id},
        )
        mock_hass.config_entries.async_add = AsyncMock()

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = device

        with patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry):
            from custom_components.device_tools import async_migrate_entry

            await async_migrate_entry(mock_hass, entry)

        mock_hass.create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_removal_scheduled_for_device_not_found(self, mock_hass):
        entry = _make_v1_config_entry(V1_DEVICE_MISSING)
        mock_hass.config_entries.async_add = AsyncMock()

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = None

        with patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry):
            from custom_components.device_tools import async_migrate_entry

            await async_migrate_entry(mock_hass, entry)

        mock_hass.create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_removal_scheduled_for_custom_device(self, mock_hass):
        entry = _make_v1_config_entry(V1_CUSTOM_NO_ATTRS)
        mock_hass.config_entries.async_add = AsyncMock()

        with patch(f"{MODULE}.dr.async_get") as mock_dr:
            mock_dr.return_value = MagicMock()
            from custom_components.device_tools import async_migrate_entry

            await async_migrate_entry(mock_hass, entry)

        mock_hass.create_task.assert_called_once()


class TestMigrateNewEntryStructure:
    """Verify that new entries have the complete 2.x data structure."""

    @pytest.mark.asyncio
    async def test_v2_data_keys_present(self, mock_hass):
        """All required 2.x data keys must be present."""
        entry = _make_v1_config_entry(V1_ATTRIBUTE_ONLY)
        device = _make_device(
            "device_1",
            config_entries={"other_integration", entry.entry_id},
        )

        collector = _AddedEntryCollector()
        mock_hass.config_entries.async_add = collector

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = device

        with patch(f"{MODULE}.dr.async_get", return_value=mock_device_registry):
            from custom_components.device_tools import async_migrate_entry

            await async_migrate_entry(mock_hass, entry)

        new = collector.entries[0]
        required_data_keys = {
            CONF_MODIFICATION_ENTRY_ID,
            CONF_MODIFICATION_ENTRY_NAME,
            CONF_MODIFICATION_IS_CUSTOM_ENTRY,
            CONF_MODIFICATION_ORIGINAL_DATA,
            CONF_MODIFICATION_TYPE,
        }
        assert required_data_keys.issubset(new.data.keys())
        assert CONF_MODIFICATION_DATA in new.options
        assert new.version == 2
        assert new.domain == "device_tools"
