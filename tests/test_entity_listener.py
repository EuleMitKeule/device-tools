from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_registry import EventEntityRegistryUpdatedData
from homeassistant.util.event_type import EventType

from custom_components.device_tools.entity_listener import EntityListener


@pytest.fixture
def mock_hass():
    return MagicMock(spec=HomeAssistant)


@pytest.fixture
def mock_entity_registry():
    return MagicMock(spec=er.EntityRegistry)


@pytest.fixture
def mock_entity_listener(
    monkeypatch: pytest.MonkeyPatch,
    mock_hass: HomeAssistant,
    mock_entity_registry: MagicMock,
):
    mock_hass.bus = MagicMock()
    mock_hass.bus.async_listen = MagicMock()
    monkeypatch.setattr(er, "async_get", MagicMock(return_value=mock_entity_registry))
    return EntityListener(mock_hass)


@pytest.fixture
def mock_entity_entry():
    return MagicMock(spec=er.RegistryEntry)


@pytest.fixture
def mock_event(mock_entity_entry: MagicMock):
    return Event(
        cast(
            EventType[EventEntityRegistryUpdatedData | dict[str, Any]],
            er.EVENT_ENTITY_REGISTRY_UPDATED,
        ),
        {"entity_id": mock_entity_entry.entity_id},
    )


async def test_register_callback(
    mock_entity_listener: EntityListener, mock_entity_entry: MagicMock
):
    callback = AsyncMock()
    mock_entity_listener.register_callback(mock_entity_entry.entity_id, callback)
    assert callback in mock_entity_listener._callbacks[mock_entity_entry.entity_id]


async def test_unregister_callback(
    mock_entity_listener: EntityListener, mock_entity_entry: MagicMock
):
    callback = AsyncMock()
    mock_entity_listener.register_callback(mock_entity_entry.entity_id, callback)
    mock_entity_listener.unregister_callback(mock_entity_entry.entity_id, callback)
    assert callback not in mock_entity_listener._callbacks[mock_entity_entry.entity_id]


async def test_async_on_entity_registry_updated(
    mock_entity_listener: EntityListener,
    mock_entity_registry: MagicMock,
    mock_entity_entry: MagicMock,
    mock_event: MagicMock,
):
    callback = AsyncMock()
    mock_entity_listener.register_callback(mock_entity_entry.entity_id, callback)
    mock_entity_registry.async_get.return_value = mock_entity_entry

    await mock_entity_listener._async_on_entity_registry_updated(mock_event)
    callback.assert_called_once_with(mock_entity_entry, mock_event)
