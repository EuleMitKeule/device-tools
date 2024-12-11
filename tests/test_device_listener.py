from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.device_tools.device_listener import DeviceListener


@pytest.fixture
def mock_hass():
    return MagicMock(spec=HomeAssistant)


@pytest.fixture
def mock_device_registry():
    return MagicMock(spec=dr.DeviceRegistry)


@pytest.fixture
def mock_device_listener(
    monkeypatch: pytest.MonkeyPatch,
    mock_hass: HomeAssistant,
    mock_device_registry: MagicMock,
):
    mock_hass.bus = MagicMock()
    mock_hass.bus.async_listen = MagicMock()
    monkeypatch.setattr(dr, "async_get", MagicMock(return_value=mock_device_registry))
    return DeviceListener(mock_hass)


@pytest.fixture
def mock_device_entry():
    return MagicMock(spec=dr.DeviceEntry)


@pytest.fixture
def mock_event(mock_device_entry: MagicMock):
    return Event(dr.EVENT_DEVICE_REGISTRY_UPDATED, {"device_id": mock_device_entry.id})


async def test_register_callback(
    mock_device_listener: DeviceListener, mock_device_entry: MagicMock
):
    callback = AsyncMock()
    mock_device_listener.register_callback(mock_device_entry.id, callback)
    assert callback in mock_device_listener._callbacks[mock_device_entry.id]


async def test_unregister_callback(
    mock_device_listener: DeviceListener, mock_device_entry: MagicMock
):
    callback = AsyncMock()
    mock_device_listener.register_callback(mock_device_entry.id, callback)
    mock_device_listener.unregister_callback(mock_device_entry.id, callback)
    assert callback not in mock_device_listener._callbacks[mock_device_entry.id]


async def test_ignore_next_update(
    mock_device_listener: DeviceListener, mock_device_entry: MagicMock
):
    callback = AsyncMock()
    mock_device_listener.ignore_next_update(mock_device_entry.id, callback)
    assert callback in mock_device_listener._ignored_callbacks[mock_device_entry.id]


async def test_async_on_device_registry_updated(
    mock_device_listener: DeviceListener,
    mock_device_registry: MagicMock,
    mock_device_entry: MagicMock,
    mock_event: Event[
        dr._EventDeviceRegistryUpdatedData_CreateRemove
        | dr._EventDeviceRegistryUpdatedData_Update
        | dict[str, Any]
    ],
):
    callback = AsyncMock()
    mock_device_listener.register_callback(mock_device_entry.id, callback)
    mock_device_registry.async_get.return_value = mock_device_entry

    await mock_device_listener._async_on_device_registry_updated(mock_event)
    callback.assert_awaited_once_with(mock_device_entry, mock_event)


async def test_async_on_device_registry_updated_ignored_callback(
    mock_device_listener: DeviceListener,
    mock_device_registry: MagicMock,
    mock_device_entry: MagicMock,
    mock_event: Event[
        dr._EventDeviceRegistryUpdatedData_CreateRemove
        | dr._EventDeviceRegistryUpdatedData_Update
        | dict[str, Any]
    ],
):
    callback = AsyncMock()
    mock_device_listener.register_callback(mock_device_entry.id, callback)
    mock_device_listener.ignore_next_update(mock_device_entry.id, callback)
    assert callback in mock_device_listener._ignored_callbacks[mock_device_entry.id]
    mock_device_registry.async_get.return_value = mock_device_entry

    await mock_device_listener._async_on_device_registry_updated(mock_event)
    callback.assert_not_awaited()
    assert callback not in mock_device_listener._ignored_callbacks[mock_device_entry.id]

    await mock_device_listener._async_on_device_registry_updated(mock_event)
    callback.assert_awaited_once_with(mock_device_entry, mock_event)
