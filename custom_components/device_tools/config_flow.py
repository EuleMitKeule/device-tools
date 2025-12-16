"""Config and options flow for the device-tools integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast
import uuid

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import device_registry as dr, entity_registry as er, selector

from .const import (
    CONF_DEVICE_ATTRIBUTES,
    CONF_DEVICE_ID,
    CONF_ENTITIES,
    CONF_ENTITY_ATTRIBUTES,
    CONF_HW_VERSION,
    CONF_INFORMATION,
    CONF_MANUFACTURER,
    CONF_MERGE_DEVICE_IDS,
    CONF_MERGE_OPTIONS,
    CONF_MODEL,
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
    MODIFIABLE_ATTRIBUTES,
    ModificationType,
)
from .utils import (
    check_merge_conflicts,
    get_default_config_entry_title,
    is_entity_in_merge_modification,
    name_for_device,
    name_for_entity,
)

_LOGGER = logging.getLogger(__name__)


def _get_base_options_schema(
    modification_type: ModificationType,
    modification_entry_id: str | None,
) -> vol.Schema:
    """Return the base options schema for a modification."""
    match modification_type:
        case ModificationType.DEVICE | ModificationType.MERGE:
            schema = vol.Schema(
                {
                    vol.Optional(
                        CONF_MODIFICATION_ENTRY,
                        default=modification_entry_id or "",
                    ): selector.DeviceSelector(
                        selector.DeviceSelectorConfig(
                            read_only=True,
                            multiple=False,
                        )
                    ),
                }
            )
        case ModificationType.ENTITY:
            schema = vol.Schema(
                {
                    vol.Optional(
                        CONF_MODIFICATION_ENTRY,
                        default=modification_entry_id or "",
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            read_only=True,
                            multiple=False,
                        )
                    ),
                }
            )

    schema = schema.extend(
        {
            vol.Optional(
                CONF_MODIFICATION_TYPE,
                default=modification_type,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[mt.value for mt in ModificationType],
                    read_only=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key=CONF_MODIFICATION_TYPE,
                )
            ),
        }
    )

    return vol.Schema({vol.Required(CONF_INFORMATION): section(schema)})


def _get_device_options_schema(
    modification_type: ModificationType,
    modification_entry_id: str | None,
    modification_data: dict[str, Any],
    modification_original_data: dict[str, Any],
) -> vol.Schema:
    """Return the schema for a device modification."""
    return cast(
        vol.Schema,
        _get_base_options_schema(
            modification_type,
            modification_entry_id,
        ).extend(
            required=True,
            schema={
                vol.Required(CONF_DEVICE_ATTRIBUTES): section(
                    vol.Schema(
                        {
                            vol.Optional(
                                CONF_MANUFACTURER,
                                description={
                                    "suggested_value": modification_data.get(
                                        CONF_MANUFACTURER,
                                        modification_original_data.get(
                                            CONF_MANUFACTURER
                                        ),
                                    ),
                                },
                            ): str,
                            vol.Optional(
                                CONF_MODEL,
                                description={
                                    "suggested_value": modification_data.get(
                                        CONF_MODEL,
                                        modification_original_data.get(CONF_MODEL),
                                    )
                                },
                            ): str,
                            vol.Optional(
                                CONF_SW_VERSION,
                                description={
                                    "suggested_value": modification_data.get(
                                        CONF_SW_VERSION,
                                        modification_original_data.get(CONF_SW_VERSION),
                                    )
                                },
                            ): str,
                            vol.Optional(
                                CONF_HW_VERSION,
                                description={
                                    "suggested_value": modification_data.get(
                                        CONF_HW_VERSION,
                                        modification_original_data.get(CONF_HW_VERSION),
                                    )
                                },
                            ): str,
                            vol.Optional(
                                CONF_SERIAL_NUMBER,
                                description={
                                    "suggested_value": modification_data.get(
                                        CONF_SERIAL_NUMBER,
                                        modification_original_data.get(
                                            CONF_SERIAL_NUMBER
                                        ),
                                    )
                                },
                            ): str,
                            vol.Optional(
                                CONF_VIA_DEVICE_ID,
                                description={
                                    "suggested_value": modification_data.get(
                                        CONF_VIA_DEVICE_ID,
                                        modification_original_data.get(
                                            CONF_VIA_DEVICE_ID
                                        ),
                                    )
                                },
                            ): selector.DeviceSelector(
                                selector.DeviceSelectorConfig(
                                    multiple=False,
                                )
                            ),
                        },
                    )
                )
            },
        ),
    )


def _get_entity_options_schema(
    modification_type: ModificationType,
    modification_entry_id: str | None,
    modification_data: dict[str, Any],
    modification_original_data: dict[str, Any],
) -> vol.Schema:
    """Return the schema for an entity modification."""
    return cast(
        vol.Schema,
        _get_base_options_schema(
            modification_type,
            modification_entry_id,
        ).extend(
            required=True,
            schema={
                vol.Required(CONF_ENTITY_ATTRIBUTES): section(
                    vol.Schema(
                        {
                            vol.Optional(
                                CONF_DEVICE_ID,
                                description={
                                    "suggested_value": modification_data.get(
                                        CONF_DEVICE_ID,
                                        modification_original_data.get(CONF_DEVICE_ID),
                                    )
                                },
                            ): selector.DeviceSelector(
                                selector.DeviceSelectorConfig(
                                    multiple=False,
                                )
                            ),
                        }
                    )
                ),
            },
        ),
    )


def _get_merge_options_schema(
    modification_type: ModificationType,
    modification_entry_id: str | None,
    modification_data: dict[str, Any],
    modification_original_data: dict[str, Any],
) -> vol.Schema:
    """Return the schema for a merge modification."""
    return cast(
        vol.Schema,
        _get_base_options_schema(
            modification_type,
            modification_entry_id,
        ).extend(
            required=True,
            schema={
                vol.Required(CONF_MERGE_OPTIONS): section(
                    vol.Schema(
                        {
                            vol.Optional(
                                CONF_MERGE_DEVICE_IDS,
                                description={
                                    "suggested_value": modification_data.get(
                                        CONF_MERGE_DEVICE_IDS,
                                        list(modification_original_data.keys()),
                                    )
                                },
                            ): selector.DeviceSelector(
                                selector.DeviceSelectorConfig(
                                    multiple=True,
                                    read_only=True,
                                )
                            ),
                        }
                    )
                )
            },
        ),
    )


def _get_options_schema(
    modification_type: ModificationType,
    modification_entry_id: str | None,
    modification_original_data: dict[str, Any] | None,
    modification_data: dict[str, Any],
) -> vol.Schema:
    """Return the schema for a modification."""
    match modification_type:
        case ModificationType.DEVICE:
            return _get_device_options_schema(
                modification_type,
                modification_entry_id,
                modification_data,
                modification_original_data or {},
            )
        case ModificationType.ENTITY:
            return _get_entity_options_schema(
                modification_type,
                modification_entry_id,
                modification_data,
                modification_original_data or {},
            )
        case ModificationType.MERGE:
            return _get_merge_options_schema(
                modification_type,
                modification_entry_id,
                modification_data,
                modification_original_data or {},
            )


def _get_merge_schema() -> vol.Schema:
    """Return the schema for merging entries."""
    return vol.Schema(
        {
            vol.Required(CONF_MERGE_DEVICE_IDS, default=[]): selector.DeviceSelector(
                selector.DeviceSelectorConfig(
                    multiple=True,
                )
            ),
        }
    )


def _get_select_schema(
    modification_type: ModificationType,
) -> vol.Schema:
    """Return the data schema for a modification."""
    match modification_type:
        case ModificationType.DEVICE:
            return vol.Schema(
                {
                    vol.Optional(CONF_MODIFICATION_ENTRY_ID): selector.DeviceSelector(
                        selector.DeviceSelectorConfig(
                            multiple=False,
                        )
                    ),
                }
            )
        case ModificationType.ENTITY:
            return vol.Schema(
                {
                    vol.Required(CONF_MODIFICATION_ENTRY_ID): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            multiple=False,
                        )
                    ),
                }
            )
        case ModificationType.MERGE:
            return vol.Schema(
                {
                    vol.Required(CONF_MODIFICATION_ENTRY_ID): selector.DeviceSelector(
                        selector.DeviceSelectorConfig(
                            multiple=False,
                        )
                    ),
                }
            )


def _user_input_to_modification_data(
    user_input: dict[str, Any],
    modification_original_data: dict[str, Any] | None,
    modification_type: ModificationType,
) -> dict[str, Any]:
    """Return the modification data from user input."""
    if modification_original_data is None:
        modification_original_data = {}

    return {
        k: v
        for k, v in user_input.items()
        if v is not None
        and v != modification_original_data.get(k)
        and k in MODIFIABLE_ATTRIBUTES[modification_type]
    }


class DeviceToolsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Device Tools config flow."""

    VERSION = 2
    MINOR_VERSION = 0

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._modification_type: ModificationType = ModificationType.DEVICE
        self._modification_entry_id: str | None = None
        self._modification_entry_name: str | None = None
        self._modification_is_custom_entry: bool = False
        self._modification_original_data: dict[str, Any] = {}
        self._modification_data: dict[str, Any] = {}

    @property
    def _device_registry(self) -> dr.DeviceRegistry:
        """Return the device registry."""
        return dr.async_get(self.hass)

    @property
    def _entity_registry(self) -> er.EntityRegistry:
        """Return the entity registry."""
        return er.async_get(self.hass)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_MODIFICATION_TYPE, default=ModificationType.DEVICE
                        ): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=[mt.value for mt in ModificationType],
                                mode=selector.SelectSelectorMode.DROPDOWN,
                                translation_key=CONF_MODIFICATION_TYPE,
                            )
                        ),
                    }
                ),
            )

        self._modification_type = ModificationType(user_input[CONF_MODIFICATION_TYPE])

        match self._modification_type:
            case ModificationType.DEVICE | ModificationType.MERGE:
                return await self.async_step_select_device()
            case ModificationType.ENTITY:
                return await self.async_step_select_entity()

    async def async_step_select_device(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select the device to modify."""
        schema = _get_select_schema(self._modification_type)

        if user_input is None:
            return self.async_show_form(step_id="select_device", data_schema=schema)

        self._modification_entry_id = user_input.get(CONF_MODIFICATION_ENTRY_ID)

        if self._modification_entry_id is None:
            return await self.async_step_create_device()

        device = self._device_registry.async_get(self._modification_entry_id)
        if device is None:
            return self.async_abort(reason="entry_not_found")
        self._modification_entry_name = name_for_device(device)

        match self._modification_type:
            case ModificationType.MERGE:
                return await self.async_step_merge_device()
            case _:
                return await self.async_step_modify_device()

    async def async_step_select_entity(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select the entity to modify or device to merge."""
        schema = _get_select_schema(self._modification_type)

        if user_input is None:
            return self.async_show_form(step_id="select_entity", data_schema=schema)

        self._modification_entry_id = cast(
            str, user_input.get(CONF_MODIFICATION_ENTRY_ID)
        )

        entity = self._entity_registry.async_get(self._modification_entry_id)
        if entity is None:
            return self.async_abort(reason="entry_not_found")
        self._modification_entry_name = name_for_entity(entity)

        return await self.async_step_modify_entity()

    async def async_step_create_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a new entry."""
        if user_input is None:
            return self.async_show_form(
                step_id="create_device",
                data_schema=vol.Schema(
                    {vol.Required(CONF_MODIFICATION_ENTRY_NAME): str}
                ),
            )

        self._modification_entry_name = user_input[CONF_MODIFICATION_ENTRY_NAME]
        self._modification_is_custom_entry = True

        return await self.async_step_modify_device()

    async def async_step_merge_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Merge entries."""
        if user_input is None:
            return self.async_show_form(
                step_id="merge_device",
                data_schema=_get_merge_schema(),
            )

        merge_device_ids: list[str] = user_input.get(CONF_MERGE_DEVICE_IDS, [])

        if self._modification_entry_id in merge_device_ids:
            return self.async_show_form(
                step_id="merge_device",
                data_schema=_get_merge_schema(),
                errors={"base": "cannot_merge_into_itself"},
            )

        if check_merge_conflicts(self.hass, merge_device_ids):
            return self.async_show_form(
                step_id="merge_device",
                data_schema=_get_merge_schema(),
                errors={"base": "entity_has_modification"},
            )

        for merge_device_id in merge_device_ids:
            device = self._device_registry.async_get(merge_device_id)
            if device is None:
                return self.async_abort(reason="entry_not_found")

        self._modification_original_data = {
            merge_device_id: {
                CONF_ENTITIES: {
                    entity.entity_id: {
                        k: v
                        for k, v in entity.extended_dict.items()
                        if k in MODIFIABLE_ATTRIBUTES[ModificationType.ENTITY]
                    }
                    for entity in er.async_entries_for_device(
                        self._entity_registry,
                        merge_device_id,
                        include_disabled_entities=True,
                    )
                }
            }
            for merge_device_id in merge_device_ids
        }

        return await self.async_step_finish()

    async def async_step_modify_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Modify the device."""
        if TYPE_CHECKING:
            assert self._modification_entry_name is not None

        modification_original_data: dict[str, Any] = {}
        if self._modification_entry_id:
            device = self._device_registry.async_get(self._modification_entry_id)
            if device:
                modification_original_data = device.dict_repr
            else:
                modification_original_data = {}

        self._modification_original_data = {
            k: v
            for k, v in modification_original_data.items()
            if k in MODIFIABLE_ATTRIBUTES[self._modification_type]
        }

        if user_input is None:
            return self.async_show_form(
                step_id="modify_device",
                data_schema=_get_options_schema(
                    self._modification_type,
                    self._modification_entry_id,
                    self._modification_original_data,
                    {},
                ),
            )

        self._modification_data = _user_input_to_modification_data(
            user_input, self._modification_original_data, self._modification_type
        )

        return await self.async_step_finish()

    async def async_step_modify_entity(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Modify the entity."""
        if TYPE_CHECKING:
            assert self._modification_entry_name is not None
            assert self._modification_entry_id is not None

        entity = self._entity_registry.async_get(self._modification_entry_id)
        if entity is None:
            return self.async_abort(reason="entry_not_found")

        if is_entity_in_merge_modification(self.hass, self._modification_entry_id):
            return self.async_show_form(
                step_id="modify_entity",
                data_schema=_get_options_schema(
                    self._modification_type,
                    self._modification_entry_id,
                    {},
                    {},
                ),
                errors={"base": "entity_in_merge"},
            )

        modification_original_data = entity.extended_dict

        self._modification_original_data = {
            k: v
            for k, v in modification_original_data.items()
            if k in MODIFIABLE_ATTRIBUTES[self._modification_type]
        }

        if user_input is None:
            return self.async_show_form(
                step_id="modify_entity",
                data_schema=_get_options_schema(
                    self._modification_type,
                    self._modification_entry_id,
                    self._modification_original_data,
                    {},
                ),
            )

        self._modification_data = _user_input_to_modification_data(
            user_input, self._modification_original_data, self._modification_type
        )

        return await self.async_step_finish()

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Finish the configuration flow."""
        if TYPE_CHECKING:
            assert self._modification_entry_id is not None
            assert self._modification_entry_name is not None

        unique_id = f"{self._modification_type}_{self._modification_entry_id or str(uuid.uuid4())}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured(updates=user_input)

        return self.async_create_entry(
            title=get_default_config_entry_title(
                self._modification_type,
                self._modification_entry_name,
            ),
            data={
                CONF_MODIFICATION_TYPE: self._modification_type,
                CONF_MODIFICATION_ENTRY_ID: self._modification_entry_id,
                CONF_MODIFICATION_ENTRY_NAME: self._modification_entry_name,
                CONF_MODIFICATION_ORIGINAL_DATA: self._modification_original_data,
                CONF_MODIFICATION_IS_CUSTOM_ENTRY: self._modification_is_custom_entry,
            },
            options={
                CONF_MODIFICATION_DATA: self._modification_data,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(_config_entry: ConfigEntry[Any]) -> OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler()


class OptionsFlowHandler(OptionsFlow):
    """Options flow for the device-tools integration."""

    @property
    def _device_registry(self) -> dr.DeviceRegistry:
        """Return the device registry."""
        return dr.async_get(self.hass)

    @property
    def _entity_registry(self) -> er.EntityRegistry:
        """Return the entity registry."""
        return er.async_get(self.hass)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        modification_type: ModificationType = self.config_entry.data[
            CONF_MODIFICATION_TYPE
        ]
        modification_entry_id: str | None = self.config_entry.data.get(
            CONF_MODIFICATION_ENTRY_ID
        )
        modification_original_data: dict[str, Any] = self.config_entry.data[
            CONF_MODIFICATION_ORIGINAL_DATA
        ]
        modification_data: dict[str, Any] = self.config_entry.options[
            CONF_MODIFICATION_DATA
        ]

        schema = _get_options_schema(
            modification_type,
            modification_entry_id,
            modification_original_data,
            modification_data,
        )

        if user_input is None:
            return self.async_show_form(
                step_id="init",
                data_schema=schema,
            )

        if modification_type in [ModificationType.DEVICE, ModificationType.ENTITY]:
            modification_data = _user_input_to_modification_data(
                user_input,
                modification_original_data,
                modification_type,
            )
        elif modification_type == ModificationType.MERGE:
            modification_data = {}

        return self.async_create_entry(
            data={CONF_MODIFICATION_DATA: modification_data},
        )
