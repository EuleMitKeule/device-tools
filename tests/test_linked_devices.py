"""Tests for linking devices of different integrations."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.device_tools.const import (
    CONF_DEVICE_ATTRIBUTES,
    CONF_DEVICE_LINKING,
    CONF_ENTITY_ASSIGNMENT,
    CONF_IDENTIFIERS,
    CONF_LINKED_DEVICE_IDS,
    CONF_MANUFACTURER,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_ENTRY_NAME,
    DOMAIN,
    ModificationType,
)
from custom_components.device_tools.data import DATA_KEY
from custom_components.device_tools.original_data_store import KIND_DEVICES

from .conftest import (
    SOURCE_DOMAIN,
    create_device,
    modification_entry,
    setup_entry,
    update_options,
)

OTHER_DOMAIN = "other"


def _source(hass: HomeAssistant, domain: str, title: str) -> MockConfigEntry:
    config_entry = MockConfigEntry(domain=domain, title=title)
    config_entry.add_to_hass(hass)
    return config_entry


def _link(config_entry: MockConfigEntry, device_id: str) -> tuple[str, str]:
    return (DOMAIN, f"link_{config_entry.entry_id}_{device_id}")


def _identifiers(hass: HomeAssistant, device_id: str) -> set[tuple[str, str]]:
    device = dr.async_get(hass).async_get(device_id)
    assert device is not None
    return set(device.identifiers)


async def _linked_devices(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, device_id: str
) -> set[str]:
    """Return the linked devices as shown on the device page."""
    assert await async_setup_component(hass, "config", {})
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": "config/device_registry/list_linked_devices", "device_id": device_id}
    )
    response = await client.receive_json()
    assert response["success"], response
    return set(response["result"]["linked_devices"])


async def test_devices_are_linked_and_unlinked(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    source_entry: MockConfigEntry,
) -> None:
    other_entry = _source(hass, OTHER_DOMAIN, "Other")
    device = create_device(hass, source_entry, "a")
    other = create_device(hass, other_entry, "b")
    config_entry = modification_entry(
        ModificationType.DEVICE,
        device.id,
        {CONF_MANUFACTURER: "Changed", CONF_LINKED_DEVICE_IDS: [other.id]},
    )
    await setup_entry(hass, config_entry)

    link = _link(config_entry, other.id)
    assert _identifiers(hass, device.id) == {(SOURCE_DOMAIN, "a"), link}
    assert _identifiers(hass, other.id) == {(SOURCE_DOMAIN, "b"), link}
    assert await _linked_devices(hass, hass_ws_client, device.id) == {other.id}
    assert await _linked_devices(hass, hass_ws_client, other.id) == {device.id}
    store = hass.data[DATA_KEY].store
    assert store.get(KIND_DEVICES, other.id) == {
        CONF_IDENTIFIERS: [[SOURCE_DOMAIN, "b"]]
    }

    await update_options(hass, config_entry, {CONF_MANUFACTURER: "Changed"})

    assert _identifiers(hass, device.id) == {(SOURCE_DOMAIN, "a")}
    assert _identifiers(hass, other.id) == {(SOURCE_DOMAIN, "b")}
    assert await _linked_devices(hass, hass_ws_client, device.id) == set()
    assert store.get(KIND_DEVICES, other.id) == {}
    modified = dr.async_get(hass).async_get(device.id)
    assert modified is not None
    assert modified.manufacturer == "Changed"


async def test_unload_unlinks_devices(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    other_entry = _source(hass, OTHER_DOMAIN, "Other")
    device = create_device(hass, source_entry, "a")
    other = create_device(hass, other_entry, "b")
    config_entry = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_LINKED_DEVICE_IDS: [other.id]}
    )
    await setup_entry(hass, config_entry)
    assert _link(config_entry, other.id) in _identifiers(hass, other.id)

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert _identifiers(hass, device.id) == {(SOURCE_DOMAIN, "a")}
    assert _identifiers(hass, other.id) == {(SOURCE_DOMAIN, "b")}
    store = hass.data[DATA_KEY].store
    assert store.get(KIND_DEVICES, device.id) == {}
    assert store.get(KIND_DEVICES, other.id) == {}


async def test_several_devices_are_linked(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    source_entry: MockConfigEntry,
) -> None:
    device = create_device(hass, source_entry, "a")
    second = create_device(hass, _source(hass, OTHER_DOMAIN, "Second"), "b")
    third = create_device(hass, _source(hass, "third", "Third"), "c")
    config_entry = modification_entry(
        ModificationType.DEVICE,
        device.id,
        {CONF_LINKED_DEVICE_IDS: [second.id, third.id]},
    )
    await setup_entry(hass, config_entry)

    assert await _linked_devices(hass, hass_ws_client, device.id) == {
        second.id,
        third.id,
    }
    # The linked devices are only linked to the device, not to each other.
    assert await _linked_devices(hass, hass_ws_client, second.id) == {device.id}
    assert await _linked_devices(hass, hass_ws_client, third.id) == {device.id}


async def test_devices_of_one_integration_are_linked(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    source_entry: MockConfigEntry,
) -> None:
    lights = [create_device(hass, source_entry, f"light_{index}") for index in range(3)]
    group = modification_entry(
        ModificationType.DEVICE,
        "placeholder",
        {CONF_LINKED_DEVICE_IDS: [light.id for light in lights]},
        is_custom_entry=True,
        name="Light group",
    )
    await setup_entry(hass, group)
    group_id = group.data[CONF_MODIFICATION_ENTRY_ID]

    assert await _linked_devices(hass, hass_ws_client, group_id) == {
        light.id for light in lights
    }
    for light in lights:
        assert await _linked_devices(hass, hass_ws_client, light.id) == {group_id}

    assert await hass.config_entries.async_remove(group.entry_id)
    await hass.async_block_till_done()
    for index, light in enumerate(lights):
        assert _identifiers(hass, light.id) == {(SOURCE_DOMAIN, f"light_{index}")}


async def test_device_linked_by_two_modifications(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    hub_entry = _source(hass, OTHER_DOMAIN, "Hub")
    device = create_device(hass, source_entry, "a")
    second = create_device(hass, source_entry, "b")
    hub = create_device(hass, hub_entry, "hub")
    first_link = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_LINKED_DEVICE_IDS: [hub.id]}
    )
    second_link = modification_entry(
        ModificationType.DEVICE, second.id, {CONF_LINKED_DEVICE_IDS: [hub.id]}
    )
    await setup_entry(hass, first_link)
    await setup_entry(hass, second_link)

    assert _identifiers(hass, hub.id) == {
        (SOURCE_DOMAIN, "hub"),
        _link(first_link, hub.id),
        _link(second_link, hub.id),
    }

    assert await hass.config_entries.async_remove(first_link.entry_id)
    await hass.async_block_till_done()

    assert _identifiers(hass, hub.id) == {
        (SOURCE_DOMAIN, "hub"),
        _link(second_link, hub.id),
    }
    assert _identifiers(hass, device.id) == {(SOURCE_DOMAIN, "a")}

    assert await hass.config_entries.async_remove(second_link.entry_id)
    await hass.async_block_till_done()

    assert _identifiers(hass, hub.id) == {(SOURCE_DOMAIN, "hub")}


async def test_integration_identifier_updates_are_kept(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    other_entry = _source(hass, OTHER_DOMAIN, "Other")
    device = create_device(hass, source_entry, "a")
    other = create_device(hass, other_entry, "b")
    config_entry = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_LINKED_DEVICE_IDS: [other.id]}
    )
    await setup_entry(hass, config_entry)
    device_registry = dr.async_get(hass)

    # The integration adds an identifier, keeping the existing ones.
    dr.async_get(hass).async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={(SOURCE_DOMAIN, "b"), (SOURCE_DOMAIN, "serial")},
    )
    await hass.async_block_till_done()
    assert _identifiers(hass, other.id) == {
        (SOURCE_DOMAIN, "b"),
        (SOURCE_DOMAIN, "serial"),
        _link(config_entry, other.id),
    }

    # The integration replaces all identifiers, dropping the link.
    device_registry.async_update_device(
        other.id, new_identifiers={(SOURCE_DOMAIN, "new")}
    )
    await hass.async_block_till_done()
    assert _identifiers(hass, other.id) == {
        (SOURCE_DOMAIN, "new"),
        _link(config_entry, other.id),
    }
    assert hass.data[DATA_KEY].store.get(KIND_DEVICES, other.id) == {
        CONF_IDENTIFIERS: [[SOURCE_DOMAIN, "new"]]
    }

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert _identifiers(hass, other.id) == {(SOURCE_DOMAIN, "new")}


async def test_linked_device_removed_and_readded(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    other_entry = _source(hass, OTHER_DOMAIN, "Other")
    device = create_device(hass, source_entry, "a")
    other = create_device(hass, other_entry, "b")
    config_entry = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_LINKED_DEVICE_IDS: [other.id]}
    )
    await setup_entry(hass, config_entry)

    dr.async_get(hass).async_remove_device(other.id)
    await hass.async_block_till_done()

    assert _identifiers(hass, device.id) == {(SOURCE_DOMAIN, "a")}
    assert hass.data[DATA_KEY].store.get(KIND_DEVICES, other.id) == {}

    # Restoring a deleted device keeps its id.
    restored = create_device(hass, other_entry, "b")
    await hass.async_block_till_done()
    assert restored.id == other.id
    link = _link(config_entry, other.id)
    assert _identifiers(hass, device.id) == {(SOURCE_DOMAIN, "a"), link}
    assert _identifiers(hass, other.id) == {(SOURCE_DOMAIN, "b"), link}


async def test_stale_link_identifiers_are_not_restored(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    other_entry = _source(hass, OTHER_DOMAIN, "Other")
    device = create_device(hass, source_entry, "a")
    other = create_device(hass, other_entry, "b")
    # Left over by a modification which could not be unloaded.
    dr.async_get(hass).async_update_device(
        other.id, new_identifiers={(SOURCE_DOMAIN, "b"), (DOMAIN, "link_stale")}
    )
    config_entry = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_LINKED_DEVICE_IDS: [other.id]}
    )
    await setup_entry(hass, config_entry)

    assert _identifiers(hass, other.id) == {
        (SOURCE_DOMAIN, "b"),
        _link(config_entry, other.id),
    }

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert _identifiers(hass, other.id) == {(SOURCE_DOMAIN, "b")}


async def test_created_device_is_linked(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    source_entry: MockConfigEntry,
) -> None:
    other = create_device(hass, source_entry, "b")
    config_entry = modification_entry(
        ModificationType.DEVICE,
        "placeholder",
        {CONF_LINKED_DEVICE_IDS: [other.id]},
        is_custom_entry=True,
    )
    await setup_entry(hass, config_entry)
    device_id = config_entry.data[CONF_MODIFICATION_ENTRY_ID]

    assert _identifiers(hass, device_id) == {
        (DOMAIN, config_entry.entry_id),
        _link(config_entry, other.id),
    }
    assert await _linked_devices(hass, hass_ws_client, other.id) == {device_id}

    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()

    assert _identifiers(hass, other.id) == {(SOURCE_DOMAIN, "b")}


async def test_removed_created_device_is_removed_from_links(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    other = create_device(hass, _source(hass, OTHER_DOMAIN, "Other"), "b")
    created = modification_entry(
        ModificationType.DEVICE, "placeholder", is_custom_entry=True, name="New"
    )
    await setup_entry(hass, created)
    created_id = created.data[CONF_MODIFICATION_ENTRY_ID]
    device = create_device(hass, source_entry, "a")
    config_entry = modification_entry(
        ModificationType.DEVICE,
        device.id,
        {CONF_LINKED_DEVICE_IDS: [created_id, other.id]},
    )
    await setup_entry(hass, config_entry)

    assert await hass.config_entries.async_remove(created.entry_id)
    await hass.async_block_till_done()

    assert config_entry.options[CONF_MODIFICATION_DATA] == {
        CONF_LINKED_DEVICE_IDS: [other.id]
    }
    assert _link(config_entry, other.id) in _identifiers(hass, other.id)
    assert _link(config_entry, created_id) not in _identifiers(hass, device.id)


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


def _form(linked_device_ids: list[str]) -> dict[str, Any]:
    return {
        CONF_DEVICE_ATTRIBUTES: {},
        CONF_ENTITY_ASSIGNMENT: {},
        CONF_DEVICE_LINKING: {CONF_LINKED_DEVICE_IDS: linked_device_ids},
    }


async def test_link_flow(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    source_entry: MockConfigEntry,
) -> None:
    other_entry = _source(hass, OTHER_DOMAIN, "Other")
    device = create_device(hass, source_entry, "a")
    sibling = create_device(hass, source_entry, "sibling")
    other = create_device(hass, other_entry, "b")
    child = dr.async_get(hass).async_get_or_create_child(
        config_entry_id=other_entry.entry_id,
        parent_device_id=other.id,
        identifiers={(SOURCE_DOMAIN, "child")},
    )
    flow_id = await _start_device_flow(hass, device.id)

    for linked, error in (
        ([device.id], "cannot_link_to_itself"),
        ([sibling.id], "linked_devices_same_config_entry"),
        ([other.id, "missing"], "entry_not_found"),
        ([child.id], "child_device"),
    ):
        result = await hass.config_entries.flow.async_configure(flow_id, _form(linked))
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": error}

    result = await hass.config_entries.flow.async_configure(
        flow_id, _form([other.id, other.id])
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {
        CONF_MODIFICATION_DATA: {CONF_LINKED_DEVICE_IDS: [other.id]}
    }
    await hass.async_block_till_done()
    assert await _linked_devices(hass, hass_ws_client, device.id) == {other.id}


async def test_create_device_flow_with_links(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    first = create_device(hass, source_entry, "a")
    second = create_device(hass, source_entry, "b")
    assert await async_setup_component(hass, DOMAIN, {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    flow_id = result["flow_id"]
    await hass.config_entries.flow.async_configure(
        flow_id, {"next_step_id": "create_device"}
    )
    await hass.config_entries.flow.async_configure(
        flow_id, {CONF_MODIFICATION_ENTRY_NAME: "New"}
    )

    result = await hass.config_entries.flow.async_configure(
        flow_id, _form([first.id, second.id])
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    config_entry = result["result"]
    assert _link(config_entry, first.id) in _identifiers(hass, first.id)
    assert _link(config_entry, second.id) in _identifiers(hass, second.id)


async def test_link_options_flow(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    other = create_device(hass, _source(hass, OTHER_DOMAIN, "Other"), "b")
    device = create_device(hass, source_entry, "a")
    config_entry = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_LINKED_DEVICE_IDS: [other.id]}
    )
    await setup_entry(hass, config_entry)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    linking = next(
        key for key in result["data_schema"].schema if key == CONF_DEVICE_LINKING
    )
    inner = next(iter(result["data_schema"].schema[linking].schema.schema))
    assert inner.description == {"suggested_value": [other.id]}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _form([])
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert config_entry.options[CONF_MODIFICATION_DATA] == {}
    assert _identifiers(hass, other.id) == {(SOURCE_DOMAIN, "b")}


async def test_device_with_connections_only(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    other_entry = _source(hass, OTHER_DOMAIN, "Other")
    device_registry = dr.async_get(hass)
    other = device_registry.async_get_or_create(
        config_entry_id=other_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")},
    )
    device = create_device(hass, source_entry, "a")
    config_entry = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_LINKED_DEVICE_IDS: [other.id]}
    )
    await setup_entry(hass, config_entry)
    assert _identifiers(hass, other.id) == {_link(config_entry, other.id)}

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert _identifiers(hass, other.id) == set()
    restored = device_registry.async_get(other.id)
    assert restored is not None
    assert restored.connections == {(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")}


async def test_stale_link_identifiers_are_removed_on_start(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a")
    other = create_device(hass, _source(hass, OTHER_DOMAIN, "Other"), "b")
    # Left over e.g. by an older version of Device Tools after a downgrade.
    device_registry = dr.async_get(hass)
    device_registry.async_update_device(
        other.id,
        new_identifiers={(SOURCE_DOMAIN, "b"), (DOMAIN, "link_stale")},
    )
    config_entry = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_LINKED_DEVICE_IDS: [other.id]}
    )
    config_entry.add_to_hass(hass)
    # The identifier of the modification is kept, since it is still wanted. The
    # one of the previous test version, shared by all linked devices, is removed.
    device_registry.async_update_device(
        device.id,
        new_identifiers={
            (SOURCE_DOMAIN, "a"),
            _link(config_entry, other.id),
            (DOMAIN, f"link_{config_entry.entry_id}"),
        },
    )
    unrelated = create_device(hass, source_entry, "c")
    device_registry.async_update_device(
        unrelated.id,
        new_identifiers={(SOURCE_DOMAIN, "c"), (DOMAIN, "link_stale")},
    )

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    link = _link(config_entry, other.id)
    assert _identifiers(hass, device.id) == {(SOURCE_DOMAIN, "a"), link}
    assert _identifiers(hass, other.id) == {(SOURCE_DOMAIN, "b"), link}
    assert _identifiers(hass, unrelated.id) == {(SOURCE_DOMAIN, "c")}

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert _identifiers(hass, device.id) == {(SOURCE_DOMAIN, "a")}
    assert _identifiers(hass, other.id) == {(SOURCE_DOMAIN, "b")}


async def test_removing_modification_that_is_not_loaded(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a")
    other = create_device(hass, _source(hass, OTHER_DOMAIN, "Other"), "b")
    loaded = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_MANUFACTURER: "Changed"}
    )
    await setup_entry(hass, loaded)
    not_loaded = modification_entry(
        ModificationType.DEVICE, other.id, {CONF_LINKED_DEVICE_IDS: [device.id]}
    )
    not_loaded.add_to_hass(hass)
    # Links applied before the modification failed to unload.
    device_registry = dr.async_get(hass)
    for linked in (device, other):
        current = device_registry.async_get(linked.id)
        assert current is not None
        device_registry.async_update_device(
            linked.id,
            new_identifiers=current.identifiers | {_link(not_loaded, device.id)},
        )
    await hass.async_block_till_done()

    assert await hass.config_entries.async_remove(not_loaded.entry_id)
    await hass.async_block_till_done()

    assert _identifiers(hass, device.id) == {(SOURCE_DOMAIN, "a")}
    assert _identifiers(hass, other.id) == {(SOURCE_DOMAIN, "b")}
