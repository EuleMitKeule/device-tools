"""Tests for EntityHandler and DeviceHandler."""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.device_tools.const import (
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
