import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components.mqtt.const import CONF_SW_VERSION
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from .const import (
    CONF_CONNECTION_BLUETOOTH_MAC,
    CONF_CONNECTION_NETWORK_MAC,
    CONF_CONNECTION_UPNP,
    CONF_CONNECTION_ZIGBEE,
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

        if user_input is None:
            return self.async_show_form(
                step_id="attributes",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_DEVICE_ID): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=[
                                    {"value": device.id, "label": device.name}
                                    for device in dr.devices.values()
                                ],
                                mode=selector.SelectSelectorMode.DROPDOWN,
                            )
                        ),
                        vol.Optional(CONF_MANUFACTURER): str,
                        vol.Optional(CONF_MODEL): str,
                        vol.Optional(CONF_VIA_DEVICE): str,
                        vol.Optional(CONF_SW_VERSION): str,
                        vol.Optional(CONF_HW_VERSION): str,
                        vol.Optional(CONF_SERIAL_NUMBER): str,
                        vol.Optional(CONF_CONNECTION_NETWORK_MAC): str,
                        vol.Optional(CONF_CONNECTION_BLUETOOTH_MAC): str,
                        vol.Optional(CONF_CONNECTION_UPNP): str,
                        vol.Optional(CONF_CONNECTION_ZIGBEE): str,
                    }
                ),
            )

        self._user_input_main = user_input

        return await self.async_step_finish()

    async def async_step_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the entities step."""

        dr = async_get_device_registry(self.hass)
        er = async_get_entity_registry(self.hass)

        if user_input is None:
            return self.async_show_form(
                step_id="entities",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_DEVICE_ID): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=[
                                    {"value": device.id, "label": device.name}
                                    for device in dr.devices.values()
                                ],
                                mode=selector.SelectSelectorMode.DROPDOWN,
                            )
                        ),
                        vol.Required(CONF_ENTITIES): selector.SelectSelector(
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
                ),
            )

        self._user_input_main = user_input

        return await self.async_step_finish()

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Finish the flow."""

        if TYPE_CHECKING:
            assert self._user_input_main is not None

        modification_type: ModificationType = self._user_input_user[
            CONF_MODIFICATION_TYPE
        ]
        modification_name: str = self._user_input_user[CONF_MODIFICATION_NAME]
        device_modification: DeviceModification

        dr = async_get_device_registry(self.hass)
        device_id = self._user_input_main[CONF_DEVICE_ID]
        device = dr.async_get(device_id)

        if TYPE_CHECKING:
            assert device is not None

        device_name = device.name

        match modification_type:
            case ModificationType.ATTRIBUTES:
                device_modification = AttributeModification(
                    modification_name=modification_name,
                    modification_type=modification_type,
                    device_id=device_id,
                    device_name=device_name,
                    manufacturer=self._user_input_main.get(CONF_MANUFACTURER),
                    model=self._user_input_main.get(CONF_MODEL),
                    sw_version=self._user_input_main.get(CONF_SW_VERSION),
                    hw_version=self._user_input_main.get(CONF_HW_VERSION),
                    serial_number=self._user_input_main.get(CONF_SERIAL_NUMBER),
                    via_device=self._user_input_main.get(CONF_VIA_DEVICE),
                    connections={
                        (connection_type, self._user_input_main[connection_type])
                        for connection_type in (
                            CONF_CONNECTION_NETWORK_MAC,
                            CONF_CONNECTION_BLUETOOTH_MAC,
                            CONF_CONNECTION_UPNP,
                            CONF_CONNECTION_ZIGBEE,
                        )
                        if self._user_input_main.get(connection_type)
                    },
                )
            case ModificationType.ENTITIES:
                device_modification = EntityModification(
                    modification_name=modification_name,
                    modification_type=modification_type,
                    device_id=device_id,
                    device_name=device_name,
                    entities=self._user_input_main.get(CONF_ENTITIES),
                )

        return self.async_create_entry(
            title=modification_name,
            data=DeviceToolsConfigEntryData(
                {
                    "device_modification": device_modification,
                }
            ),
        )

    # @staticmethod
    # @callback
    # def async_get_options_flow(
    #     config_entry: ConfigEntry,
    # ) -> OptionsFlow:
    #     """Create the options flow."""
    #     return OptionsFlowHandler(config_entry)


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

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "show_things",
                        default=self.config_entry.options.get("show_things"),
                    ): bool
                }
            ),
        )
