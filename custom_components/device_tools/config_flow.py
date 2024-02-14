import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components.mqtt.const import CONF_SW_VERSION
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from homeassistant.helpers.entity_registry import async_entries_for_device
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from .const import (
    CONF_DEVICE_ID,
    CONF_ENTITIES,
    CONF_HW_VERSION,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_MODIFICATION_NAME,
    CONF_MODIFICATION_TYPE,
    CONF_SERIAL_NUMBER,
    CONF_VIA_DEVICE,
    DOMAIN,
    ModificationType,
)
from .models.attribute_modification import AttributeModification
from .models.config_entry_data import DeviceToolsConfigEntryData
from .models.device_modification import DeviceModification
from .models.entity_modification import EntityModification

_LOGGER = logging.getLogger(__name__)


def _schema_attributes(attribute_modification: AttributeModification) -> vol.Schema:
    """Return the attributes schema."""

    return vol.Schema(
        {
            vol.Optional(
                CONF_MANUFACTURER, default=attribute_modification["manufacturer"]
            ): str,
            vol.Optional(CONF_MODEL, default=attribute_modification["model"]): str,
            vol.Optional(
                CONF_VIA_DEVICE, default=attribute_modification["via_device_id"]
            ): str,
            vol.Optional(
                CONF_SW_VERSION, default=attribute_modification["sw_version"]
            ): str,
            vol.Optional(
                CONF_HW_VERSION, default=attribute_modification["hw_version"]
            ): str,
            vol.Optional(
                CONF_SERIAL_NUMBER, default=attribute_modification["serial_number"]
            ): str,
        }
    )


def _schema_entities(
    hass: HomeAssistant, entity_modification: EntityModification
) -> vol.Schema:
    """Return the entities schema."""

    er = async_get_entity_registry(hass)

    return vol.Schema(
        {
            vol.Optional(
                CONF_ENTITIES, default=entity_modification["entities"]
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {
                            "value": entity.id,
                            "label": entity.name
                            if entity.name is not None
                            else entity.entity_id,
                        }
                        for entity in er.entities.values()
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    multiple=True,
                )
            ),
        }
    )


class DeviceToolsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Device Tools config flow."""

    def __init__(self) -> None:
        """Initialize the config flow."""

        self._user_input_user: dict[str, Any] | None = None
        self._user_input_main: dict[str, Any] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initialized by the user."""

        dr = async_get_device_registry(self.hass)

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_MODIFICATION_NAME): str,
                        vol.Required(
                            CONF_MODIFICATION_TYPE, default=ModificationType.ATTRIBUTES
                        ): vol.In(
                            [value for value in ModificationType.__members__.values()]
                        ),
                        vol.Required(CONF_DEVICE_ID): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=[
                                    {"value": device.id, "label": device.name}
                                    for device in dr.devices.values()
                                ],
                                mode=selector.SelectSelectorMode.DROPDOWN,
                            )
                        ),
                    }
                ),
            )

        self._user_input_user = user_input

        modification_type: ModificationType = user_input[CONF_MODIFICATION_TYPE]
        modification_name: str = user_input[CONF_MODIFICATION_NAME]

        await self.async_set_unique_id(modification_name)
        self._abort_if_unique_id_configured(updates=user_input)

        match modification_type:
            case ModificationType.ATTRIBUTES:
                return await self.async_step_attributes()
            case ModificationType.ENTITIES:
                return await self.async_step_entities()

    async def async_step_attributes(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the attributes step."""

        dr = async_get_device_registry(self.hass)
        device_id = self._user_input_user[CONF_DEVICE_ID]
        device = dr.async_get(device_id)

        if TYPE_CHECKING:
            assert device is not None

        attribute_modification = AttributeModification.from_device(
            self._user_input_user["modification_name"], device
        )

        if user_input is None:
            return self.async_show_form(
                step_id="attributes",
                data_schema=_schema_attributes(attribute_modification),
            )

        attribute_modification.update(user_input)

        return self.async_create_entry(
            title=attribute_modification["modification_name"],
            data=DeviceToolsConfigEntryData(
                {
                    "device_modification": attribute_modification,
                }
            ),
        )

    async def async_step_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the entities step."""

        dr = async_get_device_registry(self.hass)
        device_id = self._user_input_user[CONF_DEVICE_ID]
        device = dr.async_get(device_id)

        er = async_get_entity_registry(self.hass)
        entities = async_entries_for_device(er, device_id)
        entity_ids = {entity.id for entity in entities}

        entity_modification = EntityModification.from_device(
            self._user_input_user["modification_name"], device, entity_ids
        )

        if user_input is None:
            return self.async_show_form(
                step_id="entities",
                data_schema=_schema_entities(
                    self.hass, entity_modification=entity_modification
                ),
            )

        entity_modification.update(user_input)

        return self.async_create_entry(
            title=entity_modification["modification_name"],
            data=DeviceToolsConfigEntryData(
                {
                    "device_modification": entity_modification,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""

        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        config_entry_data: DeviceToolsConfigEntryData = self.config_entry.data
        device_modification: DeviceModification = config_entry_data[
            "device_modification"
        ]

        match device_modification["modification_type"]:
            case ModificationType.ATTRIBUTES:
                return await self.async_step_attributes()
            case ModificationType.ENTITIES:
                return await self.async_step_entities()

    async def async_step_attributes(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the attributes step."""

        attribute_modification: AttributeModification = self.config_entry.data[
            "device_modification"
        ]

        if user_input is None:
            return self.async_show_form(
                step_id="attributes",
                data_schema=_schema_attributes(attribute_modification),
            )

        attribute_modification.update(user_input)

        return self.async_create_entry(
            title="",
            data=DeviceToolsConfigEntryData(
                {
                    "device_modification": attribute_modification,
                }
            ),
        )

    async def async_step_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the entities step."""

        entity_modification: EntityModification = self.config_entry.data[
            "device_modification"
        ]

        if user_input is None:
            return self.async_show_form(
                step_id="entities",
                data_schema=_schema_entities(
                    self.hass, entity_modification=entity_modification
                ),
            )

        entity_modification.update(user_input)

        return self.async_create_entry(
            title="",
            data=DeviceToolsConfigEntryData(
                {
                    "device_modification": entity_modification,
                }
            ),
        )
