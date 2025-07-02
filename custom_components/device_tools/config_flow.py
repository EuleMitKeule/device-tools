"""Config and options flow for the device-tools integration."""

from __future__ import annotations

from typing import Any, TypedDict

import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.entity_registry as er
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from custom_components.device_tools.models import PersistentModificationData

from .const import (
    CONF_DEVICE_ID,
    CONF_HW_VERSION,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_TYPE,
    CONF_SERIAL_NUMBER,
    CONF_SW_VERSION,
    CONF_VIA_DEVICE_ID,
    DOMAIN,
    ModificationType,
)
from .data import DATA_KEY, DeviceToolsData


def _get_device_schema(
    hass: HomeAssistant,
    modification_entry_id: str,
    modification_data: dict[str, Any],
    modification_original_data: dict[str, Any],
) -> vol.Schema:
    """Return the schema for a device modification."""
    device_registry = dr.async_get(hass)

    return vol.Schema(
        {
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


def _get_entity_schema(
    hass: HomeAssistant,
    modification_data: dict[str, Any],
    modification_original_data: dict[str, Any],
) -> vol.Schema:
    """Return the schema for an entity modification."""
    device_registry = dr.async_get(hass)

    return vol.Schema(
        {
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


def _name_for_device(device: dr.DeviceEntry) -> str:
    """Return the name for a device."""
    return device.name_by_user or device.name or device.id


def _name_for_entity(entity: er.RegistryEntry) -> str:
    """Return the name for an entity."""
    return entity.name or entity.original_name or entity.entity_id


def _get_schema(
    hass: HomeAssistant,
    modification_type: ModificationType,
    modification_entry_id: str,
    modification_data: dict[str, Any],
    modification_original_data: dict[str, Any],
) -> vol.Schema:
    """Return the schema for a modification."""
    if modification_type == ModificationType.DEVICE:
        return _get_device_schema(
            hass,
            modification_entry_id,
            modification_data,
            modification_original_data,
        )
    return _get_entity_schema(hass, modification_data, modification_original_data)


def _user_input_to_modification_data(
    user_input: dict[str, Any], modification_original_data: dict[str, Any]
) -> dict[str, Any]:
    """Return the modification data from user input."""
    return {
        k: v
        for k, v in user_input.items()
        if v is not None and v != modification_original_data.get(k)
    }


class DeviceToolsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Device Tools config flow."""

    VERSION = 2
    MINOR_VERSION = 0

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._modification_type: ModificationType = ModificationType.DEVICE
        self._modification_entry_id: str | None = None

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
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select the entry to modify."""
        device_registry = dr.async_get(self.hass)
        entity_registry = er.async_get(self.hass)
        existing_entry_ids = {
            entry.data[CONF_MODIFICATION_ENTRY_ID]
            for entry in self._async_current_entries()
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
                    if self._modification_type == ModificationType.DEVICE
                    else entity_registry.entities.values()
                ),
            )
        ]

        if user_input is None:
            return self.async_show_form(
                step_id="select_entry",
                data_schema=vol.Schema(
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
                ),
            )

        self._modification_entry_id = user_input.get(CONF_MODIFICATION_ENTRY_ID)

        if self._modification_entry_id is None:
            return self.async_abort(reason="no_entry_selected")

        return await self.async_step_modify_entry()

    async def async_step_modify_entry(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Modify the entry."""
        device_tools_data: DeviceToolsData = self.hass.data[DATA_KEY]

        modification_original_data: PersistentModificationData

        if self._modification_entry_id is None:
            return self.async_abort(reason="no_entry_selected")

        match self._modification_type:
            case ModificationType.DEVICE:
                device_registry = dr.async_get(self.hass)
                modification_entry = device_registry.async_get(
                    self._modification_entry_id
                )
                if modification_entry is None:
                    return self.async_abort(reason="entry_not_found")
                modification_entry_name = _name_for_device(modification_entry)
                modification_original_data = (
                    device_tools_data.storage.get_entry_data(
                        self._modification_entry_id
                    )
                    or modification_entry.dict_repr
                )
            case ModificationType.ENTITY:
                entity_registry = er.async_get(self.hass)
                modification_entry = entity_registry.async_get(
                    self._modification_entry_id
                )
                if modification_entry is None:
                    return self.async_abort(reason="entry_not_found")
                modification_entry_name = _name_for_entity(modification_entry)
                modification_original_data = (
                    device_tools_data.storage.get_entry_data(
                        self._modification_entry_id
                    )
                    or modification_entry.extended_dict()
                )

        schema = _get_schema(
            self.hass,
            self._modification_type,
            self._modification_entry_id,
            {},
            modification_original_data["original_data"],
        )

        if user_input is None:
            return self.async_show_form(
                step_id="modify_entry",
                data_schema=schema,
            )

        await self.async_set_unique_id(self._modification_entry_id)
        self._abort_if_unique_id_configured(updates=user_input)

        modification_data = _user_input_to_modification_data(
            user_input, modification_original_data["original_data"]
        )

        return self.async_create_entry(
            title=modification_entry_name,
            data={
                CONF_MODIFICATION_TYPE: self._modification_type,
                CONF_MODIFICATION_ENTRY_ID: self._modification_entry_id,
            },
            options={
                CONF_MODIFICATION_DATA: modification_data,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        _config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler()


class OptionsFlowHandler(OptionsFlow):
    """Options flow for the device-tools integration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        storage = self.hass.data[DATA_KEY].storage

        modification_type = self.config_entry.data[CONF_MODIFICATION_TYPE]
        modification_entry_id = self.config_entry.data[CONF_MODIFICATION_ENTRY_ID]
        modification_data = self.config_entry.options[CONF_MODIFICATION_DATA]
        modification_original_data = storage.get_entry_data(modification_entry_id)

        match modification_type:
            case ModificationType.DEVICE:
                device_registry = dr.async_get(self.hass)
                modification_entry = device_registry.async_get(modification_entry_id)
                if modification_entry is None:
                    return self.async_abort(reason="entry_not_found")
                modification_entry_name = _name_for_device(modification_entry)
            case ModificationType.ENTITY:
                entity_registry = er.async_get(self.hass)
                modification_entry = entity_registry.async_get(modification_entry_id)
                if modification_entry is None:
                    return self.async_abort(reason="entry_not_found")
                modification_entry_name = _name_for_entity(modification_entry)

        schema = _get_schema(
            self.hass,
            modification_type,
            modification_entry_id,
            modification_data,
            modification_original_data,
        )

        if user_input is None:
            return self.async_show_form(
                step_id="init",
                data_schema=schema,
            )

        modification_data = _user_input_to_modification_data(
            user_input, modification_original_data
        )

        return self.async_create_entry(
            title=modification_entry_name,
            data={
                CONF_MODIFICATION_DATA: modification_data,
            },
        )
