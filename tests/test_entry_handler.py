"""Tests for EntityHandler and DeviceHandler."""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.device_tools.const import (
    CONF_ASSIGNED_ENTITIES,
    CONF_DEVICE_ID,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_TYPE,
    ModificationType,
)
from custom_components.device_tools.entry_handler import DeviceHandler, EntityHandler
from custom_components.device_tools.original_data_store import OriginalDataStore


# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------


def _make_config_entry(mod_type: ModificationType, entry_id: str = "entry_1") -> MagicMock:
    entry = MagicMock(spec=ConfigEntry)
    entry.data = {
        CONF_MODIFICATION_TYPE: mod_type.value,
        CONF_MODIFICATION_ENTRY_ID: entry_id,
    }
    entry.options = {CONF_MODIFICATION_DATA: {}}
    entry.entry_id = "config_entry_1"
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
    store.get_entity = MagicMock(return_value={"name": "Original Name"})
    store.get_device = MagicMock(return_value={"name_by_user": "Original Device"})
    store.async_update_entity = AsyncMock()
    store.async_update_device = AsyncMock()
    return store


@pytest.fixture
def mock_get_active_entries() -> Callable[[], list[ConfigEntry[Any]]]:
    return MagicMock(return_value=[])


# ---------------------------------------------------------------------------
# EntityHandler tests
# ---------------------------------------------------------------------------


class TestEntityHandlerListening:
    """Tests for EntityHandler start/stop listening."""

    @pytest.fixture
    def entity_handler(self, mock_hass, mock_store, mock_get_active_entries):
        return EntityHandler(
            mock_hass,
            "sensor.test",
            mock_store,
            get_active_entries=mock_get_active_entries,
        )

    async def test_start_listening_registers_listener(self, entity_handler, mock_hass):
        """start_listening should subscribe to entity registry events."""
        await entity_handler.async_start_listening()
        mock_hass.bus.async_listen.assert_called_once_with(
            er.EVENT_ENTITY_REGISTRY_UPDATED,
            entity_handler._async_on_entity_registry_updated,
        )

    async def test_start_listening_is_idempotent(self, entity_handler, mock_hass):
        """Calling start_listening twice should only register one listener."""
        await entity_handler.async_start_listening()
        await entity_handler.async_start_listening()
        mock_hass.bus.async_listen.assert_called_once()

    async def test_stop_listening_unregisters_listener(self, entity_handler, mock_hass):
        """stop_listening should call the unsubscribe callback."""
        unsub = MagicMock()
        mock_hass.bus.async_listen.return_value = unsub
        await entity_handler.async_start_listening()
        await entity_handler.async_stop_listening()
        unsub.assert_called_once()

    async def test_stop_listening_without_start_is_safe(self, entity_handler):
        """stop_listening before start_listening should not raise."""
        await entity_handler.async_stop_listening()


class TestEntityHandlerRegistryUpdate:
    """Tests for EntityHandler._async_on_entity_registry_updated."""

    @pytest.fixture
    def entity_handler(self, mock_hass, mock_store, mock_get_active_entries):
        return EntityHandler(
            mock_hass,
            "sensor.test",
            mock_store,
            get_active_entries=mock_get_active_entries,
        )

    def _make_update_event(self, entity_id: str, changes: dict) -> MagicMock:
        event = MagicMock(spec=Event)
        event.data = {
            "action": "update",
            "entity_id": entity_id,
            "changes": changes,
        }
        return event

    async def test_ignores_non_update_actions(self, entity_handler, mock_store):
        """Events with action != 'update' should be ignored."""
        event = MagicMock(spec=Event)
        event.data = {"action": "create", "entity_id": "sensor.test"}
        with patch(
            "custom_components.device_tools.entry_handler.er.async_get"
        ) as mock_registry:
            await entity_handler._async_on_entity_registry_updated(event)
            mock_registry.assert_not_called()

    async def test_ignores_other_entity_ids(self, entity_handler, mock_store):
        """Events for a different entity_id should be ignored."""
        event = self._make_update_event("sensor.other", {"name": "foo"})
        with patch(
            "custom_components.device_tools.entry_handler.er.async_get"
        ) as mock_registry:
            await entity_handler._async_on_entity_registry_updated(event)
            mock_registry.assert_not_called()

    async def test_stores_external_changes(self, entity_handler, mock_store):
        """External changes (keys in 'changes') should be persisted to the store."""
        mock_entity = MagicMock()
        mock_entity.extended_dict = {"name": "New Name", "icon": "mdi:home"}
        mock_registry = MagicMock()
        mock_registry.async_get.return_value = mock_entity

        event = self._make_update_event("sensor.test", {"name": "Old Name"})

        with (
            patch(
                "custom_components.device_tools.entry_handler.er.async_get",
                return_value=mock_registry,
            ),
            patch.object(entity_handler, "async_apply", new=AsyncMock()),
        ):
            await entity_handler._async_on_entity_registry_updated(event)
            mock_store.async_update_entity.assert_awaited_once_with(
                "sensor.test", {"name": "New Name"}
            )


# ---------------------------------------------------------------------------
# DeviceHandler tests
# ---------------------------------------------------------------------------


class TestDeviceHandlerListening:
    """Tests for DeviceHandler start/stop listening."""

    @pytest.fixture
    def device_handler(self, mock_hass, mock_store, mock_get_active_entries):
        return DeviceHandler(
            mock_hass,
            "device_id_1",
            mock_store,
            get_active_entries=mock_get_active_entries,
        )

    async def test_start_listening_registers_listener(self, device_handler, mock_hass):
        """start_listening should subscribe to device registry events."""
        await device_handler.async_start_listening()
        mock_hass.bus.async_listen.assert_called_once_with(
            dr.EVENT_DEVICE_REGISTRY_UPDATED,
            device_handler._async_on_device_registry_updated,
        )

    async def test_start_listening_is_idempotent(self, device_handler, mock_hass):
        """Calling start_listening twice should only register one listener."""
        await device_handler.async_start_listening()
        await device_handler.async_start_listening()
        mock_hass.bus.async_listen.assert_called_once()

    async def test_stop_listening_unregisters_listener(self, device_handler, mock_hass):
        """stop_listening should call the unsubscribe callback."""
        unsub = MagicMock()
        mock_hass.bus.async_listen.return_value = unsub
        await device_handler.async_start_listening()
        await device_handler.async_stop_listening()
        unsub.assert_called_once()

    async def test_stop_listening_without_start_is_safe(self, device_handler):
        """stop_listening before start_listening should not raise."""
        await device_handler.async_stop_listening()


class TestDeviceHandlerRegistryUpdate:
    """Tests for DeviceHandler._async_on_device_registry_updated."""

    @pytest.fixture
    def device_handler(self, mock_hass, mock_store, mock_get_active_entries):
        return DeviceHandler(
            mock_hass,
            "device_id_1",
            mock_store,
            get_active_entries=mock_get_active_entries,
        )

    def _make_update_event(self, device_id: str, changes: dict) -> MagicMock:
        event = MagicMock(spec=Event)
        event.data = {
            "action": "update",
            "device_id": device_id,
            "changes": changes,
        }
        return event

    async def test_ignores_non_update_actions(self, device_handler, mock_store):
        """Events with action != 'update' should be ignored."""
        event = MagicMock(spec=Event)
        event.data = {"action": "create", "device_id": "device_id_1"}
        with patch(
            "custom_components.device_tools.entry_handler.dr.async_get"
        ) as mock_registry:
            await device_handler._async_on_device_registry_updated(event)
            mock_registry.assert_not_called()

    async def test_ignores_other_device_ids(self, device_handler, mock_store):
        """Events for a different device_id should be ignored."""
        event = self._make_update_event("device_id_other", {"name_by_user": "foo"})
        with patch(
            "custom_components.device_tools.entry_handler.dr.async_get"
        ) as mock_registry:
            await device_handler._async_on_device_registry_updated(event)
            mock_registry.assert_not_called()

    async def test_stores_external_changes(self, device_handler, mock_store):
        """External changes (keys in 'changes') should be persisted to the store."""
        mock_device = MagicMock()
        mock_device.dict_repr = {"name_by_user": "New Name", "area_id": "living_room"}
        mock_registry = MagicMock()
        mock_registry.async_get.return_value = mock_device

        event = self._make_update_event("device_id_1", {"name_by_user": "Old Name"})

        with (
            patch(
                "custom_components.device_tools.entry_handler.dr.async_get",
                return_value=mock_registry,
            ),
            patch.object(device_handler, "async_apply", new=AsyncMock()),
        ):
            await device_handler._async_on_device_registry_updated(event)
            mock_store.async_update_device.assert_awaited_once_with(
                "device_id_1", {"name_by_user": "New Name"}
            )


# ---------------------------------------------------------------------------
# EntityHandler.async_apply — device-existence guard (Bug 2)
# ---------------------------------------------------------------------------


class TestEntityHandlerApplyDeviceGuard:
    """Tests for the device-existence guard in EntityHandler.async_apply."""

    @pytest.fixture
    def entity_handler(self, mock_hass, mock_store, mock_get_active_entries):
        return EntityHandler(
            mock_hass,
            "sensor.test",
            mock_store,
            get_active_entries=mock_get_active_entries,
        )

    async def test_apply_skips_nonexistent_device_id(self, entity_handler, mock_hass):
        """async_apply should skip device_id when the device no longer exists."""
        entry = MagicMock(spec=ConfigEntry)
        entry.data = {
            CONF_MODIFICATION_TYPE: ModificationType.ENTITY.value,
            CONF_MODIFICATION_ENTRY_ID: "sensor.test",
        }
        entry.options = {CONF_MODIFICATION_DATA: {CONF_DEVICE_ID: "deleted_device_id"}}

        mock_entity = MagicMock()
        mock_entity.entity_id = "sensor.test"
        mock_entity_registry = MagicMock()
        mock_entity_registry.async_get.return_value = mock_entity

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = None  # device does not exist

        with (
            patch(
                "custom_components.device_tools.entry_handler.er.async_get",
                return_value=mock_entity_registry,
            ),
            patch(
                "custom_components.device_tools.entry_handler.dr.async_get",
                return_value=mock_device_registry,
            ),
        ):
            await entity_handler.async_apply([entry])
            # async_update_entity should NOT have been called (no valid kwargs remain)
            mock_entity_registry.async_update_entity.assert_not_called()

    async def test_apply_includes_existing_device_id(self, entity_handler, mock_hass):
        """async_apply should include device_id when the device exists."""
        entry = MagicMock(spec=ConfigEntry)
        entry.data = {
            CONF_MODIFICATION_TYPE: ModificationType.ENTITY.value,
            CONF_MODIFICATION_ENTRY_ID: "sensor.test",
        }
        entry.options = {CONF_MODIFICATION_DATA: {CONF_DEVICE_ID: "valid_device_id"}}

        mock_entity = MagicMock()
        mock_entity.entity_id = "sensor.test"
        mock_entity_registry = MagicMock()
        mock_entity_registry.async_get.return_value = mock_entity

        mock_device = MagicMock()
        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = mock_device  # device exists

        with (
            patch(
                "custom_components.device_tools.entry_handler.er.async_get",
                return_value=mock_entity_registry,
            ),
            patch(
                "custom_components.device_tools.entry_handler.dr.async_get",
                return_value=mock_device_registry,
            ),
        ):
            await entity_handler.async_apply([entry])
            mock_entity_registry.async_update_entity.assert_called_once_with(
                "sensor.test", device_id="valid_device_id"
            )

    async def test_apply_device_mod_skips_nonexistent_device_id(
        self, entity_handler, mock_hass
    ):
        """async_apply should skip device_id from a DEVICE mod when device is gone."""
        entry = MagicMock(spec=ConfigEntry)
        entry.data = {
            CONF_MODIFICATION_TYPE: ModificationType.DEVICE.value,
            CONF_MODIFICATION_ENTRY_ID: "deleted_device_id",
        }
        entry.options = {
            CONF_MODIFICATION_DATA: {
                CONF_ASSIGNED_ENTITIES: ["sensor.test"],
            }
        }

        mock_entity = MagicMock()
        mock_entity.entity_id = "sensor.test"
        mock_entity_registry = MagicMock()
        mock_entity_registry.async_get.return_value = mock_entity

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = None  # device does not exist

        with (
            patch(
                "custom_components.device_tools.entry_handler.er.async_get",
                return_value=mock_entity_registry,
            ),
            patch(
                "custom_components.device_tools.entry_handler.dr.async_get",
                return_value=mock_device_registry,
            ),
        ):
            await entity_handler.async_apply([entry])
            mock_entity_registry.async_update_entity.assert_not_called()

    async def test_merge_takes_precedence_over_device_mod(
        self, entity_handler, mock_hass
    ):
        """MERGE should take precedence over DEVICE mod for device_id assignment."""
        merge_entry = MagicMock(spec=ConfigEntry)
        merge_entry.data = {
            CONF_MODIFICATION_TYPE: ModificationType.MERGE.value,
            CONF_MODIFICATION_ENTRY_ID: "merge_target_device",
        }
        merge_entry.options = {CONF_MODIFICATION_DATA: {}}

        device_entry = MagicMock(spec=ConfigEntry)
        device_entry.data = {
            CONF_MODIFICATION_TYPE: ModificationType.DEVICE.value,
            CONF_MODIFICATION_ENTRY_ID: "virtual_device",
        }
        device_entry.options = {
            CONF_MODIFICATION_DATA: {
                CONF_ASSIGNED_ENTITIES: ["sensor.test"],
            }
        }

        mock_entity = MagicMock()
        mock_entity.entity_id = "sensor.test"
        mock_entity_registry = MagicMock()
        mock_entity_registry.async_get.return_value = mock_entity

        mock_device = MagicMock()
        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = mock_device

        # Entries are sorted by priority: MERGE first, DEVICE second
        with (
            patch(
                "custom_components.device_tools.entry_handler.er.async_get",
                return_value=mock_entity_registry,
            ),
            patch(
                "custom_components.device_tools.entry_handler.dr.async_get",
                return_value=mock_device_registry,
            ),
        ):
            await entity_handler.async_apply([merge_entry, device_entry])
            mock_entity_registry.async_update_entity.assert_called_once_with(
                "sensor.test", device_id="merge_target_device"
            )


# ---------------------------------------------------------------------------
# EntityHandler.async_revert — device-existence guard (Bug 3)
# ---------------------------------------------------------------------------


class TestEntityHandlerRevertDeviceGuard:
    """Tests for the device-existence guard in EntityHandler.async_revert."""

    @pytest.fixture
    def entity_handler(self, mock_hass, mock_get_active_entries):
        store = MagicMock(spec=OriginalDataStore)
        store.get_entity = MagicMock(
            return_value={"device_id": "original_device_id", "entity_category": None}
        )
        return EntityHandler(
            mock_hass,
            "sensor.test",
            store,
            get_active_entries=mock_get_active_entries,
        )

    async def test_revert_skips_nonexistent_original_device_id(
        self, entity_handler, mock_hass
    ):
        """async_revert should skip device_id restore when original device is gone."""
        mock_entity = MagicMock()
        mock_entity.entity_id = "sensor.test"
        mock_entity_registry = MagicMock()
        mock_entity_registry.async_get.return_value = mock_entity

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = None  # original device is gone

        with (
            patch(
                "custom_components.device_tools.entry_handler.er.async_get",
                return_value=mock_entity_registry,
            ),
            patch(
                "custom_components.device_tools.entry_handler.dr.async_get",
                return_value=mock_device_registry,
            ),
        ):
            await entity_handler.async_revert()
            # entity_category=None is also skipped (not in MODIFIABLE_ATTRIBUTES result)
            # The call should omit device_id
            call_kwargs = mock_entity_registry.async_update_entity.call_args
            if call_kwargs is not None:
                assert CONF_DEVICE_ID not in call_kwargs.kwargs

    async def test_revert_restores_existing_original_device_id(
        self, entity_handler, mock_hass
    ):
        """async_revert should restore device_id when original device still exists."""
        mock_entity = MagicMock()
        mock_entity.entity_id = "sensor.test"
        mock_entity_registry = MagicMock()
        mock_entity_registry.async_get.return_value = mock_entity

        mock_device = MagicMock()
        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = mock_device  # device exists

        with (
            patch(
                "custom_components.device_tools.entry_handler.er.async_get",
                return_value=mock_entity_registry,
            ),
            patch(
                "custom_components.device_tools.entry_handler.dr.async_get",
                return_value=mock_device_registry,
            ),
        ):
            await entity_handler.async_revert()
            call_kwargs = mock_entity_registry.async_update_entity.call_args
            assert call_kwargs is not None
            assert call_kwargs.kwargs.get(CONF_DEVICE_ID) == "original_device_id"
