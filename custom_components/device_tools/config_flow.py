"""Config and options flow for the device-tools integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
import uuid

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import device_registry as dr, entity_registry as er, selector
import voluptuous as vol

from .const import (
    CONF_ASSIGNED_ENTITIES,
    CONF_CONFIGURATION_URL,
    CONF_DEVICE_ATTRIBUTES,
    CONF_DEVICE_ID,
    CONF_ENTITIES,
    CONF_ENTITY_ASSIGNMENT,
    CONF_ENTITY_ATTRIBUTES,
    CONF_ENTITY_CATEGORY,
    CONF_ENTRY_TYPE,
    CONF_HW_VERSION,
    CONF_INFORMATION,
    CONF_MANUFACTURER,
    CONF_MERGE_DEVICE_IDS,
    CONF_MERGE_OPTIONS,
    CONF_MODEL,
    CONF_MODEL_ID,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_ENTRY_NAME,
    CONF_MODIFICATION_IS_CUSTOM_ENTRY,
    CONF_MODIFICATION_ORIGINAL_DATA,
    CONF_MODIFICATION_TYPE,
    CONF_SERIAL_NUMBER,
    CONF_SW_VERSION,
    CONF_VIA_DEVICE_ID,
    DOMAIN,
    ENTITY_CATEGORY_DEFAULT,
    ENTITY_CATEGORY_OPTIONS,
    ENTRY_TYPE_NONE,
    ENTRY_TYPE_OPTIONS,
    MODIFIABLE_ATTRIBUTES,
    ModificationType,
)
from .data import DATA_KEY
from .migration import MINOR_VERSION, VERSION
from .utils import (
    async_get_device,
    get_default_config_entry_title,
    is_valid_configuration_url,
    merge_sources,
    modification_type,
    name_for_device,
    name_for_entity,
)

DEVICE_TEXT_ATTRIBUTES = [
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_MODEL_ID,
    CONF_SW_VERSION,
    CONF_HW_VERSION,
    CONF_SERIAL_NUMBER,
    CONF_CONFIGURATION_URL,
]


def _to_form_value(key: str, value: Any) -> Any:
    """Return the form representation of an attribute value."""
    if value is not None:
        return str(value)
    match key:
        case "entity_category":
            return ENTITY_CATEGORY_DEFAULT
        case "entry_type":
            return ENTRY_TYPE_NONE
    return None


def _suggested(
    key: str, modification_data: dict[str, Any], original_data: dict[str, Any]
) -> dict[str, Any]:
    """Return the description of a form field with its suggested value."""
    return {
        "suggested_value": modification_data.get(
            key, _to_form_value(key, original_data.get(key))
        )
    }


def _get_information_schema(
    modification_type: ModificationType, modification_entry_id: str
) -> dict[vol.Marker, Any]:
    """Return the read-only information section of a modification."""
    entry_selector: selector.Selector[Any] = (
        selector.EntitySelector(selector.EntitySelectorConfig(read_only=True))
        if modification_type == ModificationType.ENTITY
        else selector.DeviceSelector(selector.DeviceSelectorConfig(read_only=True))
    )
    return {
        vol.Optional(CONF_INFORMATION): section(
            vol.Schema(
                {
                    vol.Optional(
                        CONF_MODIFICATION_ENTRY, default=modification_entry_id
                    ): entry_selector,
                    vol.Optional(
                        CONF_MODIFICATION_TYPE, default=modification_type.value
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[mt.value for mt in ModificationType],
                            read_only=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key=CONF_MODIFICATION_TYPE,
                        )
                    ),
                }
            ),
            {"collapsed": True},
        )
    }


def _get_device_schema(
    hass: HomeAssistant,
    modification_entry_id: str | None,
    modification_data: dict[str, Any],
    original_data: dict[str, Any],
) -> vol.Schema:
    """Return the schema of a device modification."""
    assigned_entities: list[str] = modification_data.get(CONF_ASSIGNED_ENTITIES, [])
    native_entities = (
        [
            entity.entity_id
            for entity in er.async_entries_for_device(
                er.async_get(hass),
                modification_entry_id,
                include_disabled_entities=True,
            )
            if entity.entity_id not in assigned_entities
        ]
        if modification_entry_id is not None
        else []
    )
    attributes: dict[vol.Marker, Any] = {
        vol.Optional(
            key, description=_suggested(key, modification_data, original_data)
        ): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
            if key == CONF_CONFIGURATION_URL
            else None
        )
        for key in DEVICE_TEXT_ATTRIBUTES
    }
    attributes[
        vol.Optional(
            CONF_VIA_DEVICE_ID,
            description=_suggested(
                CONF_VIA_DEVICE_ID, modification_data, original_data
            ),
        )
    ] = selector.DeviceSelector()
    attributes[
        vol.Optional(
            CONF_ENTRY_TYPE,
            description=_suggested(CONF_ENTRY_TYPE, modification_data, original_data),
        )
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=ENTRY_TYPE_OPTIONS,
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key=CONF_ENTRY_TYPE,
        )
    )
    return vol.Schema(
        {
            vol.Optional(CONF_DEVICE_ATTRIBUTES): section(vol.Schema(attributes)),
            vol.Optional(CONF_ENTITY_ASSIGNMENT): section(
                vol.Schema(
                    {
                        vol.Optional(
                            CONF_ASSIGNED_ENTITIES,
                            description={"suggested_value": assigned_entities},
                        ): selector.EntitySelector(
                            selector.EntitySelectorConfig(
                                multiple=True, exclude_entities=native_entities
                            )
                        ),
                    }
                )
            ),
        }
    )


def _get_entity_schema(
    modification_data: dict[str, Any], original_data: dict[str, Any]
) -> vol.Schema:
    """Return the schema of an entity modification."""
    return vol.Schema(
        {
            vol.Optional(CONF_ENTITY_ATTRIBUTES): section(
                vol.Schema(
                    {
                        vol.Optional(
                            CONF_DEVICE_ID,
                            description=_suggested(
                                CONF_DEVICE_ID, modification_data, original_data
                            ),
                        ): selector.DeviceSelector(),
                        vol.Optional(
                            CONF_ENTITY_CATEGORY,
                            description=_suggested(
                                CONF_ENTITY_CATEGORY, modification_data, original_data
                            ),
                        ): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=ENTITY_CATEGORY_OPTIONS,
                                mode=selector.SelectSelectorMode.DROPDOWN,
                                translation_key=CONF_ENTITY_CATEGORY,
                            )
                        ),
                    }
                )
            ),
        }
    )


def _get_merge_schema(merge_device_ids: list[str]) -> vol.Schema:
    """Return the schema of a merge modification."""
    return vol.Schema(
        {
            vol.Optional(CONF_MERGE_OPTIONS): section(
                vol.Schema(
                    {
                        vol.Required(
                            CONF_MERGE_DEVICE_IDS,
                            description={"suggested_value": merge_device_ids},
                        ): selector.DeviceSelector(
                            selector.DeviceSelectorConfig(multiple=True)
                        ),
                    }
                )
            )
        }
    )


def _get_modification_schema(
    hass: HomeAssistant,
    mod_type: ModificationType,
    modification_entry_id: str | None,
    modification_data: dict[str, Any],
    original_data: dict[str, Any],
    *,
    information: bool,
) -> vol.Schema:
    """Return the schema to edit a modification."""
    match mod_type:
        case ModificationType.DEVICE:
            schema = _get_device_schema(
                hass, modification_entry_id, modification_data, original_data
            )
        case ModificationType.ENTITY:
            schema = _get_entity_schema(modification_data, original_data)
        case ModificationType.MERGE:
            schema = _get_merge_schema(modification_data.get(CONF_MERGE_DEVICE_IDS, []))
    if not information or modification_entry_id is None:
        return schema
    return schema.extend(_get_information_schema(mod_type, modification_entry_id))


def _user_input_to_modification_data(
    mod_type: ModificationType,
    user_input: dict[str, Any],
    original_data: dict[str, Any],
) -> dict[str, Any]:
    """Return the modification data of a submitted form.

    Only attributes that differ from their original value are modified, so
    attributes reset to their original value are no longer controlled.
    """
    match mod_type:
        case ModificationType.DEVICE:
            attributes: dict[str, Any] = user_input.get(CONF_DEVICE_ATTRIBUTES, {})
        case ModificationType.ENTITY:
            attributes = user_input.get(CONF_ENTITY_ATTRIBUTES, {})
        case ModificationType.MERGE:
            return {}

    modification_data = {
        key: value
        for key in MODIFIABLE_ATTRIBUTES[mod_type]
        if (value := attributes.get(key)) not in (None, "")
        and value != _to_form_value(key, original_data.get(key))
    }

    if mod_type == ModificationType.DEVICE and (
        assigned_entities := user_input.get(CONF_ENTITY_ASSIGNMENT, {}).get(
            CONF_ASSIGNED_ENTITIES
        )
    ):
        modification_data[CONF_ASSIGNED_ENTITIES] = list(
            dict.fromkeys(assigned_entities)
        )

    return modification_data


def _validate_modification_data(
    hass: HomeAssistant,
    modification_entry_id: str | None,
    modification_data: dict[str, Any],
) -> dict[str, str]:
    """Return form errors of modification data."""
    errors: dict[str, str] = {}
    if (
        configuration_url := modification_data.get(CONF_CONFIGURATION_URL)
    ) is not None and not is_valid_configuration_url(configuration_url):
        errors["base"] = "invalid_configuration_url"
    if (via_device_id := modification_data.get(CONF_VIA_DEVICE_ID)) is not None and (
        via_device_id == modification_entry_id
    ):
        errors["base"] = "via_device_is_device"
    if (device_id := modification_data.get(CONF_DEVICE_ID)) is not None and (
        async_get_device(hass, device_id) is None
    ):
        errors["base"] = "entry_not_found"
    return errors


def _validate_merge_device_ids(
    hass: HomeAssistant,
    modification_entry_id: str,
    merge_device_ids: list[str],
    exclude_entry_id: str | None = None,
) -> dict[str, str]:
    """Return form errors of the devices to merge."""
    if not merge_device_ids:
        return {"base": "no_devices_to_merge"}
    if modification_entry_id in merge_device_ids:
        return {"base": "cannot_merge_into_itself"}
    for config_entry in hass.config_entries.async_entries(DOMAIN):
        if (
            config_entry.entry_id == exclude_entry_id
            or modification_type(config_entry) != ModificationType.MERGE
        ):
            continue
        other_merge_device_ids = merge_sources(config_entry)
        if any(device_id in other_merge_device_ids for device_id in merge_device_ids):
            return {"base": "device_already_merged"}
        if config_entry.data[CONF_MODIFICATION_ENTRY_ID] in merge_device_ids or (
            modification_entry_id in other_merge_device_ids
        ):
            return {"base": "merge_chain"}
    return {}


def _original_data(
    hass: HomeAssistant, mod_type: ModificationType, modification_entry_id: str | None
) -> dict[str, Any]:
    """Return the values the modified entity or device has without modifications."""
    if modification_entry_id is None:
        return {}
    engine = hass.data[DATA_KEY].engine
    match mod_type:
        case ModificationType.DEVICE:
            return engine.get_original_device_data(modification_entry_id)
        case ModificationType.ENTITY:
            return engine.get_original_entity_data(modification_entry_id)
        case ModificationType.MERGE:
            return {}


class DeviceToolsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Device Tools config flow."""

    VERSION = VERSION
    MINOR_VERSION = MINOR_VERSION

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._modification_type = ModificationType.DEVICE
        self._modification_entry_id: str | None = None
        self._modification_entry_name = ""
        self._modification_is_custom_entry = False
        self._modification_original_data: dict[str, Any] = {}
        self._modification_data: dict[str, Any] = {}

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> ConfigFlowResult:
        """Choose the type of the modification."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["device", "create_device", "entity", "merge"],
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select the device to modify."""
        self._modification_type = ModificationType.DEVICE
        return await self._async_step_select_device("device", user_input)

    async def async_step_merge(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select the device to merge other devices into."""
        self._modification_type = ModificationType.MERGE
        return await self._async_step_select_device("merge", user_input)

    async def _async_step_select_device(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Select a device."""
        errors: dict[str, str] = {}
        if user_input is not None:
            device_id: str = user_input[CONF_MODIFICATION_ENTRY_ID]
            device = async_get_device(self.hass, device_id)
            if device is None:
                errors["base"] = "entry_not_found"
            elif not isinstance(device, dr.DeviceEntry):
                errors["base"] = "child_device"
            else:
                await self.async_set_unique_id(f"{self._modification_type}_{device_id}")
                self._abort_if_unique_id_configured()
                self._modification_entry_id = device_id
                self._modification_entry_name = name_for_device(device)
                if self._modification_type == ModificationType.MERGE:
                    return await self.async_step_merge_devices()
                return await self.async_step_modify_device()

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {vol.Required(CONF_MODIFICATION_ENTRY_ID): selector.DeviceSelector()}
            ),
            errors=errors,
        )

    async def async_step_create_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter the name of a new device."""
        if user_input is None:
            return self.async_show_form(
                step_id="create_device",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_MODIFICATION_ENTRY_NAME
                        ): selector.TextSelector()
                    }
                ),
            )

        self._modification_type = ModificationType.DEVICE
        self._modification_entry_name = user_input[CONF_MODIFICATION_ENTRY_NAME]
        self._modification_is_custom_entry = True
        await self.async_set_unique_id(f"{ModificationType.DEVICE}_{uuid.uuid4().hex}")
        return await self.async_step_modify_device()

    async def async_step_entity(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select the entity to modify."""
        self._modification_type = ModificationType.ENTITY
        errors: dict[str, str] = {}
        if user_input is not None:
            entity_id: str = user_input[CONF_MODIFICATION_ENTRY_ID]
            if (entity := er.async_get(self.hass).async_get(entity_id)) is None:
                errors["base"] = "entry_not_found"
            else:
                await self.async_set_unique_id(f"{ModificationType.ENTITY}_{entity_id}")
                self._abort_if_unique_id_configured()
                self._modification_entry_id = entity_id
                self._modification_entry_name = name_for_entity(entity)
                return await self.async_step_modify_entity()

        return self.async_show_form(
            step_id="entity",
            data_schema=vol.Schema(
                {vol.Required(CONF_MODIFICATION_ENTRY_ID): selector.EntitySelector()}
            ),
            errors=errors,
        )

    async def async_step_modify_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Modify the device."""
        return await self._async_step_modify("modify_device", user_input)

    async def async_step_modify_entity(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Modify the entity."""
        return await self._async_step_modify("modify_entity", user_input)

    async def _async_step_modify(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Modify the device or entity."""
        original_data = _original_data(
            self.hass, self._modification_type, self._modification_entry_id
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            self._modification_data = _user_input_to_modification_data(
                self._modification_type, user_input, original_data
            )
            if not (
                errors := _validate_modification_data(
                    self.hass, self._modification_entry_id, self._modification_data
                )
            ):
                return self._async_create_modification()

        return self.async_show_form(
            step_id=step_id,
            data_schema=_get_modification_schema(
                self.hass,
                self._modification_type,
                self._modification_entry_id,
                self._modification_data,
                original_data,
                information=False,
            ),
            description_placeholders={"name": self._modification_entry_name},
            errors=errors,
        )

    async def async_step_merge_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select the devices to merge."""
        if TYPE_CHECKING:
            assert self._modification_entry_id is not None

        merge_device_ids: list[str] = []
        errors: dict[str, str] = {}
        if user_input is not None:
            merge_device_ids = user_input.get(CONF_MERGE_OPTIONS, {}).get(
                CONF_MERGE_DEVICE_IDS, []
            )
            if not (
                errors := _validate_merge_device_ids(
                    self.hass, self._modification_entry_id, merge_device_ids
                )
            ):
                self._modification_original_data = {
                    merge_device_id: {CONF_ENTITIES: {}}
                    for merge_device_id in merge_device_ids
                }
                return self._async_create_modification()

        return self.async_show_form(
            step_id="merge_devices",
            data_schema=_get_merge_schema(merge_device_ids),
            description_placeholders={"name": self._modification_entry_name},
            errors=errors,
        )

    @callback
    def _async_create_modification(self) -> ConfigFlowResult:
        """Create the config entry of the modification."""
        return self.async_create_entry(
            title=get_default_config_entry_title(
                self._modification_type, self._modification_entry_name
            ),
            data={
                CONF_MODIFICATION_TYPE: self._modification_type,
                CONF_MODIFICATION_ENTRY_ID: self._modification_entry_id
                or str(self.unique_id).removeprefix(f"{ModificationType.DEVICE}_"),
                CONF_MODIFICATION_ENTRY_NAME: self._modification_entry_name,
                CONF_MODIFICATION_IS_CUSTOM_ENTRY: self._modification_is_custom_entry,
                CONF_MODIFICATION_ORIGINAL_DATA: self._modification_original_data,
            },
            options={CONF_MODIFICATION_DATA: self._modification_data},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry[Any]) -> OptionsFlow:  # noqa: ARG004
        """Create the options flow."""
        return OptionsFlowHandler()


class OptionsFlowHandler(OptionsFlow):
    """Options flow for the device-tools integration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the modification."""
        mod_type = modification_type(self.config_entry)
        modification_entry_id: str = self.config_entry.data[CONF_MODIFICATION_ENTRY_ID]
        modification_data: dict[str, Any] = dict(
            self.config_entry.options.get(CONF_MODIFICATION_DATA, {})
        )
        original_data = _original_data(self.hass, mod_type, modification_entry_id)
        if mod_type == ModificationType.MERGE:
            modification_data[CONF_MERGE_DEVICE_IDS] = list(
                merge_sources(self.config_entry)
            )

        errors: dict[str, str] = {}
        if user_input is not None:
            if mod_type == ModificationType.MERGE:
                merge_device_ids: list[str] = user_input.get(
                    CONF_MERGE_OPTIONS, {}
                ).get(CONF_MERGE_DEVICE_IDS, [])
                if not (
                    errors := _validate_merge_device_ids(
                        self.hass,
                        modification_entry_id,
                        merge_device_ids,
                        self.config_entry.entry_id,
                    )
                ):
                    self._async_update_merge_device_ids(merge_device_ids)
                    return self.async_create_entry(data={CONF_MODIFICATION_DATA: {}})
                modification_data[CONF_MERGE_DEVICE_IDS] = merge_device_ids
            else:
                modification_data = _user_input_to_modification_data(
                    mod_type, user_input, original_data
                )
                if not (
                    errors := _validate_modification_data(
                        self.hass, modification_entry_id, modification_data
                    )
                ):
                    return self.async_create_entry(
                        data={CONF_MODIFICATION_DATA: modification_data}
                    )

        return self.async_show_form(
            step_id="init",
            data_schema=_get_modification_schema(
                self.hass,
                mod_type,
                modification_entry_id,
                modification_data,
                original_data,
                information=True,
            ),
            errors=errors,
        )

    @callback
    def _async_update_merge_device_ids(self, merge_device_ids: list[str]) -> None:
        """Store the devices to merge, keeping the entities found on them so far."""
        sources: dict[str, Any] = self.config_entry.data[
            CONF_MODIFICATION_ORIGINAL_DATA
        ]
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={
                **self.config_entry.data,
                CONF_MODIFICATION_ORIGINAL_DATA: {
                    merge_device_id: sources.get(merge_device_id, {CONF_ENTITIES: {}})
                    for merge_device_id in merge_device_ids
                },
            },
        )
