"""Tests for the config and options flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.setup import async_setup_component
from probatio import to_field_list
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.device_tools.const import (
    CONF_ASSIGNED_ENTITIES,
    CONF_CONFIGURATION_URL,
    CONF_DEVICE_ATTRIBUTES,
    CONF_DEVICE_ID,
    CONF_ENTITY_ASSIGNMENT,
    CONF_ENTITY_ATTRIBUTES,
    CONF_ENTITY_CATEGORY,
    CONF_ENTRY_TYPE,
    CONF_MANUFACTURER,
    CONF_MERGE_DEVICE_IDS,
    CONF_MERGE_OPTIONS,
    CONF_MODEL,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_ENTRY_NAME,
    CONF_MODIFICATION_IS_CUSTOM_ENTRY,
    CONF_MODIFICATION_ORIGINAL_DATA,
    CONF_MODIFICATION_TYPE,
    CONF_SW_VERSION,
    CONF_VIA_DEVICE_ID,
    DOMAIN,
    ModificationType,
)

from .conftest import create_device, create_entity, modification_entry, setup_entry


async def _start(hass: HomeAssistant, menu_option: str) -> str:
    """Start a config flow and choose a menu option."""
    assert await async_setup_component(hass, DOMAIN, {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": menu_option}
    )
    return result["flow_id"]


async def test_device_flow(hass: HomeAssistant, source_entry: MockConfigEntry) -> None:
    device = create_device(hass, source_entry, "a", manufacturer="Acme", sw_version="1")
    hub = create_device(hass, source_entry, "hub")
    entity = create_entity(hass, source_entry, "1")
    flow_id = await _start(hass, "device")

    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_MODIFICATION_ENTRY_ID: device.id}
    )
    assert result["step_id"] == "modify_device"

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_DEVICE_ATTRIBUTES: {
                CONF_MANUFACTURER: "Changed",
                CONF_SW_VERSION: "1",
                CONF_CONFIGURATION_URL: "ftp://device",
                CONF_ENTRY_TYPE: "none",
            },
            CONF_ENTITY_ASSIGNMENT: {},
        },
    )
    assert result["errors"] == {"base": "invalid_configuration_url"}

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_DEVICE_ATTRIBUTES: {
                CONF_MANUFACTURER: "Changed",
                CONF_SW_VERSION: "1",
                CONF_VIA_DEVICE_ID: device.id,
                CONF_ENTRY_TYPE: "none",
            },
            CONF_ENTITY_ASSIGNMENT: {},
        },
    )
    assert result["errors"] == {"base": "via_device_is_device"}

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_DEVICE_ATTRIBUTES: {
                CONF_MANUFACTURER: "Changed",
                CONF_SW_VERSION: "1",
                CONF_VIA_DEVICE_ID: hub.id,
                CONF_CONFIGURATION_URL: "http://device.local",
                CONF_ENTRY_TYPE: "none",
            },
            CONF_ENTITY_ASSIGNMENT: {CONF_ASSIGNED_ENTITIES: [entity.entity_id]},
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Device: a"
    assert result["data"] == {
        CONF_MODIFICATION_TYPE: ModificationType.DEVICE,
        CONF_MODIFICATION_ENTRY_ID: device.id,
        CONF_MODIFICATION_ENTRY_NAME: "a",
        CONF_MODIFICATION_IS_CUSTOM_ENTRY: False,
        CONF_MODIFICATION_ORIGINAL_DATA: {},
    }
    assert result["options"] == {
        CONF_MODIFICATION_DATA: {
            CONF_MANUFACTURER: "Changed",
            CONF_VIA_DEVICE_ID: hub.id,
            CONF_CONFIGURATION_URL: "http://device.local",
            CONF_ASSIGNED_ENTITIES: [entity.entity_id],
        }
    }
    modified = dr.async_get(hass).async_get(device.id)
    assert modified.manufacturer == "Changed"
    assert modified.via_device_id == hub.id
    assert er.async_get(hass).async_get(entity.entity_id).device_id == device.id

    flow_id = await _start(hass, "device")
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_MODIFICATION_ENTRY_ID: device.id}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_create_device_flow(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    entity = create_entity(hass, source_entry, "1")
    flow_id = await _start(hass, "create_device")
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_MODIFICATION_ENTRY_NAME: "Virtual"}
    )
    assert result["step_id"] == "modify_device"
    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_DEVICE_ATTRIBUTES: {CONF_MODEL: "V1"},
            CONF_ENTITY_ASSIGNMENT: {CONF_ASSIGNED_ENTITIES: [entity.entity_id]},
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Device: Virtual"

    config_entry = result["result"]
    device_id = config_entry.data[CONF_MODIFICATION_ENTRY_ID]
    device = dr.async_get(hass).async_get(device_id)
    assert device.name == "Virtual"
    assert device.model == "V1"
    assert config_entry.unique_id == f"device_{device_id}"
    assert er.async_get(hass).async_get(entity.entity_id).device_id == device_id


async def test_entity_flow(hass: HomeAssistant, source_entry: MockConfigEntry) -> None:
    device = create_device(hass, source_entry, "a")
    entity = create_entity(hass, source_entry, "1")
    flow_id = await _start(hass, "entity")
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_MODIFICATION_ENTRY_ID: entity.entity_id}
    )
    assert result["step_id"] == "modify_entity"
    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_ENTITY_ATTRIBUTES: {
                CONF_DEVICE_ID: device.id,
                CONF_ENTITY_CATEGORY: "default",
            }
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Entity: sensor.test_1"
    assert result["options"] == {CONF_MODIFICATION_DATA: {CONF_DEVICE_ID: device.id}}
    assert er.async_get(hass).async_get(entity.entity_id).device_id == device.id


async def test_merge_flow(hass: HomeAssistant, source_entry: MockConfigEntry) -> None:
    device = create_device(hass, source_entry, "a")
    merged_device = create_device(hass, source_entry, "merged")
    third_device = create_device(hass, source_entry, "third")
    entity = create_entity(hass, source_entry, "1", merged_device)
    await setup_entry(
        hass,
        modification_entry(
            ModificationType.MERGE,
            third_device.id,
            original_data={create_device(hass, source_entry, "x").id: {"entities": {}}},
        ),
    )

    flow_id = await _start(hass, "merge")
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_MODIFICATION_ENTRY_ID: device.id}
    )
    assert result["step_id"] == "merge_devices"

    for merge_device_ids, error in (
        ([], "no_devices_to_merge"),
        ([device.id], "cannot_merge_into_itself"),
        ([third_device.id], "merge_chain"),
    ):
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_MERGE_OPTIONS: {CONF_MERGE_DEVICE_IDS: merge_device_ids}}
        )
        assert result["errors"] == {"base": error}

    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_MERGE_OPTIONS: {CONF_MERGE_DEVICE_IDS: [merged_device.id]}}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Merge: a"
    assert er.async_get(hass).async_get(entity.entity_id).device_id == device.id


async def test_device_options_flow(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a", manufacturer="Acme", model="M")
    config_entry = modification_entry(
        ModificationType.DEVICE, device.id, {CONF_MANUFACTURER: "Changed"}
    )
    await setup_entry(hass, config_entry)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["step_id"] == "init"
    schema = result["data_schema"].schema
    device_section = schema[CONF_DEVICE_ATTRIBUTES].schema.schema
    suggested = {
        str(key): key.description["suggested_value"]
        for key in device_section
        if key.description
    }
    assert suggested[CONF_MANUFACTURER] == "Changed"
    assert suggested[CONF_MODEL] == "M"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_ATTRIBUTES: {CONF_MANUFACTURER: "Acme", CONF_MODEL: "Other"},
            CONF_ENTITY_ASSIGNMENT: {},
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {CONF_MODIFICATION_DATA: {CONF_MODEL: "Other"}}
    modified = dr.async_get(hass).async_get(device.id)
    assert modified.manufacturer == "Acme"
    assert modified.model == "Other"


async def test_merge_options_flow(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a")
    merged_device = create_device(hass, source_entry, "merged")
    other_device = create_device(hass, source_entry, "other")
    entity = create_entity(hass, source_entry, "1", merged_device)
    other_entity = create_entity(hass, source_entry, "2", other_device)
    config_entry = modification_entry(
        ModificationType.MERGE,
        device.id,
        original_data={merged_device.id: {"entities": {}}},
    )
    await setup_entry(hass, config_entry)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_MERGE_OPTIONS: {CONF_MERGE_DEVICE_IDS: [other_device.id]}},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY

    entity_registry = er.async_get(hass)
    assert entity_registry.async_get(entity.entity_id).device_id == merged_device.id
    assert entity_registry.async_get(other_entity.entity_id).device_id == device.id


async def test_entity_options_flow(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a")
    other_device = create_device(hass, source_entry, "b")
    entity = create_entity(hass, source_entry, "1", device)
    config_entry = modification_entry(
        ModificationType.ENTITY, entity.entity_id, {CONF_DEVICE_ID: other_device.id}
    )
    await setup_entry(hass, config_entry)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_ENTITY_ATTRIBUTES: {
                CONF_DEVICE_ID: device.id,
                CONF_ENTITY_CATEGORY: "diagnostic",
            }
        },
    )
    await hass.async_block_till_done()
    assert config_entry.options == {
        CONF_MODIFICATION_DATA: {CONF_ENTITY_CATEGORY: "diagnostic"}
    }
    modified = er.async_get(hass).async_get(entity.entity_id)
    assert modified.device_id == device.id
    assert modified.entity_category == "diagnostic"


async def test_forms_are_serializable(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a")
    entity = create_entity(hass, source_entry, "1", device)
    forms = []

    for menu_option, user_input in (
        ("device", {CONF_MODIFICATION_ENTRY_ID: device.id}),
        ("create_device", {CONF_MODIFICATION_ENTRY_NAME: "Virtual"}),
        ("entity", {CONF_MODIFICATION_ENTRY_ID: entity.entity_id}),
        ("merge", {CONF_MODIFICATION_ENTRY_ID: device.id}),
    ):
        flow_id = await _start(hass, menu_option)
        forms.append(await hass.config_entries.flow.async_configure(flow_id))
        forms.append(
            await hass.config_entries.flow.async_configure(flow_id, user_input)
        )

    for config_entry in (
        modification_entry(ModificationType.DEVICE, device.id),
        modification_entry(ModificationType.ENTITY, entity.entity_id),
        modification_entry(
            ModificationType.MERGE,
            device.id,
            original_data={create_device(hass, source_entry, "b").id: {"entities": {}}},
        ),
    ):
        await setup_entry(hass, config_entry)
        forms.append(
            await hass.config_entries.options.async_init(config_entry.entry_id)
        )

    for form in forms:
        assert form["type"] is FlowResultType.FORM
        to_field_list(form["data_schema"], custom_serializer=cv.custom_serializer)


async def test_child_device_cannot_be_changed(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    parent = create_device(hass, source_entry, "parent")
    child = dr.async_get(hass).async_get_or_create_child(
        config_entry_id=source_entry.entry_id,
        identifiers={("test", "child")},
        parent_device_id=parent.id,
    )
    flow_id = await _start(hass, "device")
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_MODIFICATION_ENTRY_ID: child.id}
    )
    assert result["errors"] == {"base": "child_device"}

    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_MODIFICATION_ENTRY_ID: "missing"}
    )
    assert result["errors"] == {"base": "entry_not_found"}


async def test_device_already_merged(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    merged_device = create_device(hass, source_entry, "merged")
    await setup_entry(
        hass,
        modification_entry(
            ModificationType.MERGE,
            create_device(hass, source_entry, "a").id,
            original_data={merged_device.id: {"entities": {}}},
        ),
    )
    flow_id = await _start(hass, "merge")
    await hass.config_entries.flow.async_configure(
        flow_id, {CONF_MODIFICATION_ENTRY_ID: create_device(hass, source_entry, "b").id}
    )
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_MERGE_OPTIONS: {CONF_MERGE_DEVICE_IDS: [merged_device.id]}}
    )
    assert result["errors"] == {"base": "device_already_merged"}


async def test_flow_before_setup(
    hass: HomeAssistant, source_entry: MockConfigEntry
) -> None:
    device = create_device(hass, source_entry, "a", manufacturer="Acme")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "device"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MODIFICATION_ENTRY_ID: device.id}
    )
    assert result["step_id"] == "modify_device"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_DEVICE_ATTRIBUTES: {CONF_MANUFACTURER: "Changed"}},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert dr.async_get(hass).async_get(device.id).manufacturer == "Changed"
