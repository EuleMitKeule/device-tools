"""Config and options flow for the device-tools integration."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryBaseFlow,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
    CONF_DEVICE_ID,
    CONF_DISABLE_MERGED_DEVICES,
    CONF_DISABLED_BY,
    CONF_ENTITIES,
    CONF_HW_VERSION,
    CONF_MANUFACTURER,
    CONF_MERGE_DEVICE_IDS,
    CONF_MODEL,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_ENTRY_NAME,
    CONF_MODIFICATION_ORIGINAL_DATA,
    CONF_MODIFICATION_TYPE,
    CONF_SERIAL_NUMBER,
    CONF_SW_VERSION,
    CONF_VIA_DEVICE_ID,
    DOMAIN,
    MODIFIABLE_ATTRIBUTES,
    ModificationType,
)

_LOGGER = logging.getLogger(__name__)


def _get_device_options_schema(
    hass: HomeAssistant,
    modification_entry_id: str,
    modification_entry_name: str,
    modification_data: dict[str, Any],
    modification_original_data: dict[str, Any],
) -> vol.Schema:
    """Return the schema for a device modification."""
    device_registry = dr.async_get(hass)

    return vol.Schema(
        {
            vol.Optional(
                CONF_MODIFICATION_ENTRY_ID,
                description={
                    "suggested_value": modification_entry_id,
                },
            ): TextSelector(TextSelectorConfig(read_only=True)),
            vol.Optional(
                CONF_MODIFICATION_ENTRY_NAME,
                description={
                    "suggested_value": modification_entry_name,
                },
            ): TextSelector(TextSelectorConfig(read_only=True)),
            vol.Optional(
                CONF_MANUFACTURER,
                description={
                    "suggested_value": modification_data.get(
                        CONF_MANUFACTURER,
                        modification_original_data.get(CONF_MANUFACTURER),
                    ),
                },
            ): str,
            vol.Optional(
                CONF_MODEL,
                description={
                    "suggested_value": modification_data.get(
                        CONF_MODEL, modification_original_data.get(CONF_MODEL)
                    )
                },
            ): str,
            vol.Optional(
                CONF_SW_VERSION,
                description={
                    "suggested_value": modification_data.get(
                        CONF_SW_VERSION, modification_original_data.get(CONF_SW_VERSION)
                    )
                },
            ): str,
            vol.Optional(
                CONF_HW_VERSION,
                description={
                    "suggested_value": modification_data.get(
                        CONF_HW_VERSION, modification_original_data.get(CONF_HW_VERSION)
                    )
                },
            ): str,
            vol.Optional(
                CONF_SERIAL_NUMBER,
                description={
                    "suggested_value": modification_data.get(
                        CONF_SERIAL_NUMBER,
                        modification_original_data.get(CONF_SERIAL_NUMBER),
                    )
                },
            ): str,
            vol.Optional(
                CONF_VIA_DEVICE_ID,
                description={
                    "suggested_value": modification_data.get(
                        CONF_VIA_DEVICE_ID,
                        modification_original_data.get(CONF_VIA_DEVICE_ID),
                    )
                },
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(
                            {
                                "value": device.id,
                                "label": _name_for_device(device),
                            }
                        )
                        for device in device_registry.devices.values()
                        if device.id != modification_entry_id
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


def _get_entity_options_schema(
    hass: HomeAssistant,
    modification_entry_id: str,
    modification_entry_name: str,
    modification_data: dict[str, Any],
    modification_original_data: dict[str, Any],
) -> vol.Schema:
    """Return the schema for an entity modification."""
    device_registry = dr.async_get(hass)

    return vol.Schema(
        {
            vol.Optional(
                CONF_MODIFICATION_ENTRY_ID,
                description={
                    "suggested_value": modification_entry_id,
                },
            ): TextSelector(TextSelectorConfig(read_only=True)),
            vol.Optional(
                CONF_MODIFICATION_ENTRY_NAME,
                description={
                    "suggested_value": modification_entry_name,
                },
            ): TextSelector(TextSelectorConfig(read_only=True)),
            vol.Optional(
                CONF_DEVICE_ID,
                description={
                    "suggested_value": modification_data.get(
                        CONF_DEVICE_ID, modification_original_data.get(CONF_DEVICE_ID)
                    )
                },
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(
                            {
                                "value": device.id,
                                "label": _name_for_device(device),
                            }
                        )
                        for device in device_registry.devices.values()
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


def _get_merge_options_schema(
    hass: HomeAssistant,
    modification_entry_id: str,
    modification_entry_name: str,
    modification_original_data: dict[str, Any],
    modification_data: dict[str, Any],
) -> vol.Schema:
    """Return the schema for a merge modification."""
    device_registry = dr.async_get(hass)

    return vol.Schema(
        {
            vol.Optional(
                CONF_MODIFICATION_ENTRY_ID,
                description={
                    "suggested_value": modification_entry_id,
                },
            ): TextSelector(TextSelectorConfig(read_only=True)),
            vol.Optional(
                CONF_MODIFICATION_ENTRY_NAME,
                description={
                    "suggested_value": modification_entry_name,
                },
            ): TextSelector(TextSelectorConfig(read_only=True)),
            vol.Optional(
                CONF_MERGE_DEVICE_IDS,
                description={
                    "suggested_value": list(modification_original_data.keys()),
                },
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(
                            {
                                "value": device.id,
                                "label": _name_for_device(device),
                            }
                        )
                        for device in device_registry.devices.values()
                        if device.id != modification_entry_id
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                    multiple=True,
                    read_only=True,
                )
            ),
            vol.Required(
                CONF_DISABLE_MERGED_DEVICES,
                description={
                    "suggested_value": modification_data.get(
                        CONF_DISABLE_MERGED_DEVICES, True
                    ),
                },
            ): bool,
        }
    )


def _get_options_schema(
    hass: HomeAssistant,
    modification_type: ModificationType,
    modification_entry_id: str,
    modification_entry_name: str,
    modification_original_data: dict[str, Any] | None,
    modification_data: dict[str, Any],
) -> vol.Schema:
    """Return the schema for a modification."""
    match modification_type:
        case ModificationType.DEVICE:
            return _get_device_options_schema(
                hass,
                modification_entry_id,
                modification_entry_name,
                modification_original_data or {},
                modification_data,
            )
        case ModificationType.ENTITY:
            return _get_entity_options_schema(
                hass,
                modification_entry_id,
                modification_entry_name,
                modification_original_data or {},
                modification_data,
            )
        case ModificationType.MERGE:
            return _get_merge_options_schema(
                hass,
                modification_entry_id,
                modification_entry_name,
                modification_original_data or {},
                modification_data,
            )


def _get_merge_schema(
    hass: HomeAssistant,
    modification_entry_id: str,
) -> vol.Schema:
    """Return the schema for merging entries."""
    device_registry = dr.async_get(hass)

    return vol.Schema(
        {
            vol.Required(CONF_MERGE_DEVICE_IDS, default=[]): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(
                            {
                                "value": device.id,
                                "label": _name_for_device(device),
                            }
                        )
                        for device in device_registry.devices.values()
                        if device.id != modification_entry_id
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                    multiple=True,
                )
            ),
        }
    )


def _get_data_schema(
    hass: HomeAssistant,
    current_entries: list[ConfigEntry[Any]],
    modification_type: ModificationType,
) -> vol.Schema:
    """Return the data schema for a modification."""
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    existing_entry_ids = {
        entry.data[CONF_MODIFICATION_ENTRY_ID]
        for entry in current_entries
        if entry.data[CONF_MODIFICATION_TYPE] == modification_type
        and modification_type != ModificationType.MERGE
    }

    class ModificationEntry(TypedDict):
        """Entry class."""

        id: str
        name: str

    entries = [
        ModificationEntry(
            {
                "id": entry.id,
                "name": _name_for_device(entry)
                if isinstance(entry, dr.DeviceEntry)
                else _name_for_entity(entry),
            }
        )
        for entry in filter(
            lambda entry: entry.id not in existing_entry_ids
            and entry.disabled_by is None,
            (
                device_registry.devices.values()
                if modification_type
                in [ModificationType.DEVICE, ModificationType.MERGE]
                else entity_registry.entities.values()
            ),
        )
    ]

    match modification_type:
        case ModificationType.DEVICE:
            return vol.Schema(
                {
                    vol.Optional(CONF_MODIFICATION_ENTRY_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(
                                    {
                                        "value": entry["id"],
                                        "label": entry["name"],
                                    }
                                )
                                for entry in entries
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            )
        case ModificationType.ENTITY | ModificationType.MERGE:
            return vol.Schema(
                {
                    vol.Required(CONF_MODIFICATION_ENTRY_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(
                                    {
                                        "value": entry["id"],
                                        "label": entry["name"],
                                    }
                                )
                                for entry in entries
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            )


def _name_for_device(device: dr.DeviceEntry) -> str:
    """Return the name for a device."""
    return device.name_by_user or device.name or device.id


def _name_for_entity(entity: er.RegistryEntry) -> str:
    """Return the name for an entity."""
    return entity.name or entity.original_name or entity.entity_id


def _name_for_entry(
    flow: ConfigEntryBaseFlow,
    modification_type: ModificationType,
    modification_entry_id: str,
) -> str:
    """Return the name for a config entry."""
    match modification_type:
        case ModificationType.DEVICE | ModificationType.MERGE:
            device_registry = dr.async_get(flow.hass)
            device = device_registry.async_get(modification_entry_id)
            if device is None:
                flow.async_abort(reason="entry_not_found")
            return _name_for_device(device)
        case ModificationType.ENTITY:
            entity_registry = er.async_get(flow.hass)
            entity = entity_registry.async_get(modification_entry_id)
            if entity is None:
                flow.async_abort(reason="entry_not_found")
            return _name_for_entity(entity)


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
        self._modification_original_data: dict[str, Any] = {}
        self._modification_data: dict[str, Any] = {}

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
                        ): vol.In(list(ModificationType)),
                    }
                ),
            )

        self._modification_type = user_input[CONF_MODIFICATION_TYPE]

        return await self.async_step_select_entry()

    async def async_step_select_entry(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select the entry to modify."""

        schema = _get_data_schema(
            self.hass, self._async_current_entries(), self._modification_type
        )

        if user_input is None:
            match self._modification_type:
                case ModificationType.DEVICE:
                    return self.async_show_form(
                        step_id="select_entry", data_schema=schema
                    )
                case ModificationType.ENTITY | ModificationType.MERGE:
                    return self.async_show_form(
                        step_id="select_entry", data_schema=schema
                    )

        self._modification_entry_id = user_input.get(CONF_MODIFICATION_ENTRY_ID)

        if self._modification_entry_id is None:
            return await self.async_step_create_entry()

        self._modification_entry_name = _name_for_entry(
            self, self._modification_type, self._modification_entry_id
        )

        if self._modification_type == ModificationType.MERGE:
            return await self.async_step_merge_entry()

        return await self.async_step_modify_entry()

    async def async_step_create_entry(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a new entry."""
        if user_input is None:
            return self.async_show_form(
                step_id="create_entry",
                data_schema=vol.Schema(
                    {vol.Required(CONF_MODIFICATION_ENTRY_NAME): str}
                ),
            )

        self._modification_entry_name = user_input[CONF_MODIFICATION_ENTRY_NAME]

        return await self.async_step_modify_entry()

    async def async_step_merge_entry(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Merge entries."""
        if user_input is None:
            return self.async_show_form(
                step_id="merge_entry",
                data_schema=_get_merge_schema(
                    self.hass,
                    self._modification_entry_id,
                ),
            )

        self._modification_original_data = {
            merge_device_id: {
                CONF_ENTITIES: [
                    merge_entity_entry.id
                    for merge_entity_entry in er.async_entries_for_device(
                        er.async_get(self.hass),
                        merge_device_id,
                        include_disabled_entities=True,
                    )
                ],
                CONF_DISABLED_BY: dr.async_get(self.hass)
                .async_get(merge_device_id)
                .disabled_by,
            }
            for merge_device_id in user_input.get(CONF_MERGE_DEVICE_IDS, [])
        }

        return await self.async_step_merge_entry_options()

    async def async_step_merge_entry_options(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Merge entries."""
        if user_input is None:
            return self.async_show_form(
                step_id="merge_entry_options",
                data_schema=_get_options_schema(
                    self.hass,
                    self._modification_type,
                    self._modification_entry_id,
                    self._modification_entry_name,
                    {},
                    {},
                ),
            )

        self._modification_data[CONF_DISABLE_MERGED_DEVICES] = user_input.get(
            CONF_DISABLE_MERGED_DEVICES, True
        )

        return await self.async_step_finish()

    async def async_step_modify_entry(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Modify the entry."""
        modification_original_data: dict[str, Any]
        match self._modification_type:
            case ModificationType.DEVICE:
                device_registry = dr.async_get(self.hass)
                device = device_registry.async_get(self._modification_entry_id)

                if device is None:
                    return self.async_abort(reason="entry_not_found")

                modification_original_data = device.dict_repr
            case ModificationType.ENTITY:
                entity_registry = er.async_get(self.hass)
                entity = entity_registry.async_get(self._modification_entry_id)

                if entity is None:
                    return self.async_abort(reason="entry_not_found")

                modification_original_data = entity.extended_dict

        self._modification_original_data = {
            k: v
            for k, v in modification_original_data.items()
            if k in MODIFIABLE_ATTRIBUTES[self._modification_type]
        }

        if user_input is None:
            return self.async_show_form(
                step_id="modify_entry",
                data_schema=_get_options_schema(
                    self.hass,
                    self._modification_type,
                    self._modification_entry_id,
                    self._modification_entry_name,
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

        await self.async_set_unique_id(self._modification_entry_id)
        self._abort_if_unique_id_configured(updates=user_input)

        return self.async_create_entry(
            title=f"Merge into {self._modification_entry_name}"
            if self._modification_type == ModificationType.MERGE
            else self._modification_entry_name,
            data={
                CONF_MODIFICATION_TYPE: self._modification_type,
                CONF_MODIFICATION_ENTRY_ID: self._modification_entry_id,
                CONF_MODIFICATION_ENTRY_NAME: self._modification_entry_name,
                CONF_MODIFICATION_ORIGINAL_DATA: self._modification_original_data,
            },
            options={
                CONF_MODIFICATION_DATA: self._modification_data,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(_config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler()


class OptionsFlowHandler(OptionsFlow):
    """Options flow for the device-tools integration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        modification_type: ModificationType = self.config_entry.data[
            CONF_MODIFICATION_TYPE
        ]
        modification_entry_id: str = self.config_entry.data[CONF_MODIFICATION_ENTRY_ID]
        modification_entry_name: str = self.config_entry.data[
            CONF_MODIFICATION_ENTRY_NAME
        ]
        modification_original_data: dict[str, Any] = self.config_entry.data[
            CONF_MODIFICATION_ORIGINAL_DATA
        ]
        modification_data: dict[str, Any] = self.config_entry.options[
            CONF_MODIFICATION_DATA
        ]

        schema = _get_options_schema(
            self.hass,
            modification_type,
            modification_entry_id,
            modification_entry_name,
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

        return self.async_create_entry(
            data={CONF_MODIFICATION_DATA: modification_data},
        )
