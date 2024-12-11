from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from custom_components.device_tools.device_listener import DeviceListener
from custom_components.device_tools.device_modification_registry import (
    DeviceModificationRegistry,
)
from custom_components.device_tools.device_tools import DeviceTools
from custom_components.device_tools.models import DeviceToolsHistoryData


@pytest.fixture
def mock_hass():
    return MagicMock(spec=HomeAssistant)


@pytest.fixture
def mock_device_modification_registry():
    return MagicMock(spec=DeviceModificationRegistry)


@pytest.fixture
def mock_device_tools_history_data():
    return MagicMock(spec=DeviceToolsHistoryData)


@pytest.fixture
def mock_device_listener():
    return MagicMock(spec=DeviceListener)


@pytest.fixture
def mock_device_registry():
    return MagicMock()


@pytest.fixture
def mock_entity_registry():
    return MagicMock()


@pytest.fixture
def mock_device_tools(
    monkeypatch: pytest.MonkeyPatch,
    mock_hass: MagicMock,
    mock_device_modification_registry: MagicMock,
    mock_device_tools_history_data: MagicMock,
    mock_device_listener: MagicMock,
    mock_device_registry: MagicMock,
    mock_entity_registry: MagicMock,
):
    monkeypatch.setattr(
        "custom_components.device_tools.device_tools.dr.async_get",
        MagicMock(return_value=mock_device_registry),
    )
    monkeypatch.setattr(
        "custom_components.device_tools.device_tools.er.async_get",
        MagicMock(return_value=mock_entity_registry),
    )
    return DeviceTools(
        mock_hass,
        mock_device_modification_registry,
        mock_device_tools_history_data,
        mock_device_listener,
    )


@pytest.fixture
def mock_device_entry():
    return MagicMock(spec=DeviceEntry)


@pytest.fixture
def mock_device_modification():
    return {
        "device_id": "device_1",
        "device_name": "Test Device",
        "attribute_modification": {
            "manufacturer": "Test Manufacturer",
            "model": "Test Model",
            "sw_version": "1.0",
            "hw_version": "1.0",
            "serial_number": "123456",
            "via_device_id": "via_device_1",
        },
    }


async def test_async_on_modification_added(
    mock_device_tools: DeviceTools, mock_device_modification: dict[str, Any]
):
    mock_device_tools._async_apply = AsyncMock()
    await mock_device_tools._async_on_modification_added(mock_device_modification)
    mock_device_tools._async_apply.assert_called_once_with(mock_device_modification)


async def test_async_on_modification_removed(
    mock_device_tools: DeviceTools, mock_device_modification: dict[str, Any]
):
    mock_device_tools._async_revert = AsyncMock()
    await mock_device_tools._async_on_modification_removed(mock_device_modification)
    mock_device_tools._async_revert.assert_called_once_with(mock_device_modification)


async def test_async_on_device_updated(
    mock_device_tools: DeviceTools, mock_device_entry: MagicMock
):
    mock_device_tools._device_modification_registry.get_modification_for_device = (
        MagicMock(return_value=MagicMock())
    )
    mock_device_tools._async_apply = AsyncMock()
    await mock_device_tools._async_on_device_updated(mock_device_entry, MagicMock())
    mock_device_tools._async_apply.assert_called()


async def test_async_apply(
    mock_device_tools: DeviceTools,
    mock_device_modification: dict[str, Any],
    mock_device_entry: MagicMock,
):
    mock_device_tools._device_registry.async_get = MagicMock(
        return_value=mock_device_entry
    )
    mock_device_tools._async_apply_attribute_modification = AsyncMock()
    mock_device_tools._device_listener.register_callback = MagicMock()
    mock_device_tools._device_listener.unregister_callback = MagicMock()

    await mock_device_tools._async_apply(mock_device_modification)

    mock_device_tools._async_apply_attribute_modification.assert_called_once_with(
        mock_device_entry, mock_device_modification["attribute_modification"]
    )
    mock_device_tools._device_listener.register_callback.assert_called_once()
    mock_device_tools._device_listener.unregister_callback.assert_called_once()


async def test_async_revert(
    mock_device_tools: DeviceTools,
    mock_device_modification: dict[str, Any],
    mock_device_entry: MagicMock,
):
    mock_device_tools._device_registry.async_get = MagicMock(
        return_value=mock_device_entry
    )
    mock_device_tools._async_revert_attribute_modification = AsyncMock()
    mock_device_tools._device_listener.unregister_callback = MagicMock()

    await mock_device_tools._async_revert(mock_device_modification)

    mock_device_tools._async_revert_attribute_modification.assert_called_once_with(
        mock_device_entry
    )
    mock_device_tools._device_listener.unregister_callback.assert_called_once()


async def test_async_apply_attribute_modification(
    mock_device_tools: DeviceTools, mock_device_entry: MagicMock
):
    attribute_modification = {
        "manufacturer": "New Manufacturer",
        "model": "New Model",
        "sw_version": "2.0",
        "hw_version": "2.0",
        "serial_number": "654321",
        "via_device_id": "via_device_2",
    }
    await mock_device_tools._async_apply_attribute_modification(
        mock_device_entry, attribute_modification
    )
    mock_device_tools._device_registry.async_update_device.assert_called_once_with(
        mock_device_entry.id,
        manufacturer="New Manufacturer",
        model="New Model",
        sw_version="2.0",
        hw_version="2.0",
        serial_number="654321",
        via_device_id="via_device_2",
    )


async def test_async_revert_attribute_modification(
    mock_device_tools: DeviceTools, mock_device_entry: MagicMock
):
    mock_device_tools._device_tools_history_data.device_attribute_history = {
        mock_device_entry.id: {
            "manufacturer": "Original Manufacturer",
            "model": "Original Model",
            "sw_version": "1.0",
            "hw_version": "1.0",
            "serial_number": "123456",
            "via_device_id": "via_device_1",
        }
    }
    await mock_device_tools._async_revert_attribute_modification(mock_device_entry)
    mock_device_tools._device_registry.async_update_device.assert_called_once_with(
        mock_device_entry.id,
        manufacturer="Original Manufacturer",
        model="Original Model",
        sw_version="1.0",
        hw_version="1.0",
        serial_number="123456",
        via_device_id="via_device_1",
    )


async def test_async_on_device_updated_no_modifications(
    mock_device_tools: DeviceTools, mock_device_entry: MagicMock
):
    mock_device_tools._device_modification_registry.get_modification_for_device = (
        MagicMock(return_value=[])
    )
    mock_device_tools._async_apply = AsyncMock()

    await mock_device_tools._async_on_device_updated(mock_device_entry, MagicMock())

    mock_device_tools._async_apply.assert_not_called()


async def test_async_on_device_updated_with_modifications(
    mock_device_tools: DeviceTools, mock_device_entry: MagicMock
):
    mock_modification = MagicMock()
    mock_device_tools._device_modification_registry.get_modification_for_device = (
        MagicMock(return_value=mock_modification)
    )
    mock_device_tools._async_apply = AsyncMock()

    await mock_device_tools._async_on_device_updated(mock_device_entry, MagicMock())

    mock_device_tools._async_apply.assert_called_once_with(mock_modification)


async def test_async_apply_device_not_found(
    mock_device_tools: DeviceTools, mock_device_modification: dict[str, Any]
):
    mock_device_tools._device_registry.async_get = MagicMock(return_value=None)
    mock_device_tools._async_save_original_device_config = AsyncMock()
    mock_device_tools._async_apply_attribute_modification = AsyncMock()
    mock_device_tools._device_listener.register_callback = MagicMock()
    mock_device_tools._device_listener.unregister_callback = MagicMock()

    await mock_device_tools._async_apply(mock_device_modification)

    mock_device_tools._async_save_original_device_config.assert_not_called()
    mock_device_tools._async_apply_attribute_modification.assert_not_called()
    mock_device_tools._device_listener.register_callback.assert_not_called()
    mock_device_tools._device_listener.unregister_callback.assert_not_called()
    mock_device_tools._device_registry.async_get.assert_called_once_with(
        mock_device_modification["device_id"]
    )


async def test_async_revert_device_not_found(
    mock_device_tools: DeviceTools, mock_device_modification: dict[str, Any]
):
    mock_device_tools._device_registry.async_get = MagicMock(return_value=None)
    mock_device_tools._async_revert_attribute_modification = AsyncMock()
    mock_device_tools._device_listener.unregister_callback = MagicMock()

    await mock_device_tools._async_revert(mock_device_modification)

    mock_device_tools._async_revert_attribute_modification.assert_not_called()
    mock_device_tools._device_listener.unregister_callback.assert_not_called()
    mock_device_tools._device_registry.async_get.assert_called_once_with(
        mock_device_modification["device_id"]
    )


async def test_async_on_device_updated_no_relevant_modification(
    mock_device_tools: DeviceTools, mock_device_entry: MagicMock
):
    mock_device_tools._device_modification_registry.get_modification_for_device = (
        MagicMock(return_value=None)
    )
    mock_device_tools._async_apply = AsyncMock()
    mock_device_tools._device_tools_history_data.update_attribute_history = MagicMock()

    await mock_device_tools._async_on_device_updated(mock_device_entry, MagicMock())

    mock_device_tools._async_apply.assert_not_called()
    mock_device_tools._device_tools_history_data.update_attribute_history.assert_called_once()


async def test_async_revert_attribute_modification_no_history(
    mock_device_tools: DeviceTools, mock_device_entry: MagicMock
):
    mock_device_tools._device_tools_history_data.device_attribute_history = {}
    await mock_device_tools._async_revert_attribute_modification(mock_device_entry)
    mock_device_tools._device_registry.async_update_device.assert_not_called()
