"""Tests for adding connections to devices."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.setup import async_setup_component
from probatio import to_field_list
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.device_tools.const import (
    CONF_CONNECTION_TYPE,
    CONF_CONNECTION_VALUE,
    CONF_CONNECTIONS,
    CONF_DEVICE_ATTRIBUTES,
    CONF_DEVICE_CONNECTIONS,
    CONF_ENTITY_ASSIGNMENT,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_ENTRY_NAME,
    DOMAIN,
    ModificationType,
)
from custom_components.device_tools.data import DATA_KEY
from custom_components.device_tools.original_data_store import KIND_DEVICES

from .conftest import create_device, modification_entry, setup_entry, update_options

MAC = (dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")
OTHER_MAC = (dr.CONNECTION_NETWORK_MAC, "11:22:33:44:55:66")


def _connections(hass: HomeAssistant, device_id: str) -> set[tuple[str, str]]:
    device = dr.async_get(hass).async_get(device_id)
    assert device is not None
    return set(device.connections)


async def test_connections_added_and_removed(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a", connections={OTHER_MAC})
    config_entry = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_CONNECTIONS: [list(MAC)]}
    )
    await setup_entry(hass, config_entry)

    assert _connections(hass, device.id) == {MAC, OTHER_MAC}
    assert hass.data[DATA_KEY].store.get(KIND_DEVICES, device.id) == {
        CONF_CONNECTIONS: [list(OTHER_MAC)]
    }

    await update_options(hass, config_entry, {})

    assert _connections(hass, device.id) == {OTHER_MAC}
    assert hass.data[DATA_KEY].store.get(KIND_DEVICES, device.id) == {}


async def test_device_with_shared_connection_is_linked(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    """A device tracker creates its device once a device with its MAC exists."""
    router_entry = MockConfigEntry(domain="router")
    router_entry.add_to_hass(hass)
    created = modification_entry(
        ModificationType.DEVICE,
        "placeholder",
        {CONF_CONNECTIONS: [list(MAC)]},
        is_custom_entry=True,
        name="Phone",
    )
    await setup_entry(hass, created)
    created_id = created.data[CONF_MODIFICATION_ENTRY_ID]

    device_registry = dr.async_get(hass)
    assert {
        device.id for device in device_registry.async_get_devices(connections={MAC})
    } == {created_id}

    tracker = device_registry.async_get_or_create(
        config_entry_id=router_entry.entry_id, connections={MAC}
    )
    assert tracker.id != created_id
    assert {
        device.id for device in device_registry.async_get_devices(connections={MAC})
    } == {created_id, tracker.id}


async def test_integration_connection_updates_are_kept(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a")
    config_entry = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_CONNECTIONS: [list(MAC)]}
    )
    await setup_entry(hass, config_entry)
    device_registry = dr.async_get(hass)

    # The integration replaces all connections, dropping the added one.
    device_registry.async_update_device(device.id, new_connections={OTHER_MAC})
    await hass.async_block_till_done()
    assert _connections(hass, device.id) == {MAC, OTHER_MAC}
    assert hass.data[DATA_KEY].store.get(KIND_DEVICES, device.id) == {
        CONF_CONNECTIONS: [list(OTHER_MAC)]
    }

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert _connections(hass, device.id) == {OTHER_MAC}


async def _start_device_flow(hass: HomeAssistant, device_id: str) -> str:
    assert await async_setup_component(hass, DOMAIN, {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "device"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MODIFICATION_ENTRY_ID: device_id}
    )
    assert result["step_id"] == "modify_device"
    return result["flow_id"]


def _form(*connections: tuple[str, str]) -> dict[str, Any]:
    return {
        CONF_DEVICE_ATTRIBUTES: {},
        CONF_ENTITY_ASSIGNMENT: {},
        CONF_DEVICE_CONNECTIONS: {
            CONF_CONNECTIONS: [
                {CONF_CONNECTION_TYPE: connection_type, CONF_CONNECTION_VALUE: value}
                for connection_type, value in connections
            ]
        },
    }


@pytest.mark.parametrize(
    ("entered", "stored"),
    [
        (("mac", "AA-BB-CC-DD-EE-FF"), ["mac", "aa:bb:cc:dd:ee:ff"]),
        (("mac", " aabbccddeeff "), ["mac", "aa:bb:cc:dd:ee:ff"]),
        (("bluetooth", "aa:bb:cc:dd:ee:ff"), ["bluetooth", "AA:BB:CC:DD:EE:FF"]),
        (("zigbee", "00:11:22:33:44:55:66:AA"), ["zigbee", "00:11:22:33:44:55:66:aa"]),
        (("upnp", "uuid:Abc"), ["upnp", "uuid:Abc"]),
    ],
)
async def test_connections_are_normalized(
    hass: HomeAssistant,
    source_entry: MockConfigEntry,
    entered: tuple[str, str],
    stored: list[str],
) -> None:
    device = create_device(hass, source_entry, "a")
    flow_id = await _start_device_flow(hass, device.id)

    result = await hass.config_entries.flow.async_configure(
        flow_id, _form(entered, entered)
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {CONF_MODIFICATION_DATA: {CONF_CONNECTIONS: [stored]}}
    await hass.async_block_till_done()
    assert tuple(stored) in _connections(hass, device.id)


async def test_connection_flow_errors(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a", connections={OTHER_MAC})
    create_device(hass, source_entry, "b", connections={MAC})
    flow_id = await _start_device_flow(hass, device.id)

    for connection, error in (
        (("mac", "aa:bb:cc"), "invalid_connection"),
        (("bluetooth", "not a mac"), "invalid_connection"),
        (MAC, "connection_in_use"),
    ):
        result = await hass.config_entries.flow.async_configure(
            flow_id, _form(connection)
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": error}

    # A connection the device already has is not added.
    result = await hass.config_entries.flow.async_configure(flow_id, _form(OTHER_MAC))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {CONF_MODIFICATION_DATA: {}}


async def test_create_device_flow_with_connections(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    # Devices of other config entries may have the same connection.
    other = create_device(hass, source_entry, "b", connections={MAC})
    assert await async_setup_component(hass, DOMAIN, {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    flow_id = result["flow_id"]
    await hass.config_entries.flow.async_configure(
        flow_id, {"next_step_id": "create_device"}
    )
    await hass.config_entries.flow.async_configure(
        flow_id, {CONF_MODIFICATION_ENTRY_NAME: "Phone"}
    )

    result = await hass.config_entries.flow.async_configure(flow_id, _form(MAC))

    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    created_id = result["result"].data[CONF_MODIFICATION_ENTRY_ID]
    assert _connections(hass, created_id) == {MAC}
    assert _connections(hass, other.id) == {MAC}


async def test_connection_options_flow(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a")
    config_entry = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_CONNECTIONS: [list(MAC)]}
    )
    await setup_entry(hass, config_entry)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    connections_section = next(
        key for key in result["data_schema"].schema if key == CONF_DEVICE_CONNECTIONS
    )
    inner = next(iter(result["data_schema"].schema[connections_section].schema.schema))
    # The connection added by the modification is not an original connection.
    assert inner.description == {
        "suggested_value": [
            {CONF_CONNECTION_TYPE: MAC[0], CONF_CONNECTION_VALUE: MAC[1]}
        ]
    }

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _form(MAC, OTHER_MAC)
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert _connections(hass, device.id) == {MAC, OTHER_MAC}

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _form()
    )
    await hass.async_block_till_done()
    assert config_entry.options[CONF_MODIFICATION_DATA] == {}
    assert _connections(hass, device.id) == set()


async def test_created_device_is_created_with_connections(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    """Device trackers enable their entity when a device with their MAC is created."""
    created_events: list[dict[str, Any]] = []

    def _on_device_event(event: Any) -> None:
        if event.data["action"] == "create":
            device = dr.async_get(hass).async_get(event.data["device_id"])
            assert device is not None
            created_events.append({"connections": set(device.connections)})

    hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, _on_device_event)
    created = modification_entry(
        ModificationType.DEVICE,
        "placeholder",
        {CONF_CONNECTIONS: [list(MAC)]},
        is_custom_entry=True,
        name="Phone",
    )
    await setup_entry(hass, created)

    assert created_events == [{"connections": {MAC}}]
    created_id = created.data[CONF_MODIFICATION_ENTRY_ID]
    assert hass.data[DATA_KEY].store.get(KIND_DEVICES, created_id) == {
        CONF_CONNECTIONS: []
    }

    await update_options(hass, created, {})
    assert _connections(hass, created_id) == set()

    # Reloading does not add the removed connection again.
    assert await hass.config_entries.async_reload(created.entry_id)
    await hass.async_block_till_done()
    assert _connections(hass, created_id) == set()


def _selector_translation_keys(value: Any) -> set[str]:
    """Return all translation keys of selectors in a serialized form schema."""
    keys: set[str] = set()
    if isinstance(value, dict):
        if isinstance(key := value.get("translation_key"), str):
            keys.add(key)
        for item in value.values():
            keys |= _selector_translation_keys(item)
    elif isinstance(value, list):
        for item in value:
            keys |= _selector_translation_keys(item)
    return keys


async def test_selector_translation_keys_exist(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:

    device = create_device(hass, source_entry, "a")
    flow_id = await _start_device_flow(hass, device.id)
    result = await hass.config_entries.flow.async_configure(flow_id, _form(("mac", "")))
    keys = _selector_translation_keys(
        to_field_list(result["data_schema"], custom_serializer=cv.custom_serializer)
    )
    assert "connection" in keys

    translations = (
        Path(__file__).parents[1] / "custom_components" / DOMAIN / "translations"
    )
    for language in ("en", "de"):
        selectors = json.loads((translations / f"{language}.json").read_text())[
            "selector"
        ]
        assert keys <= set(selectors), language
