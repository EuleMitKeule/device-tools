import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components.mqtt.const import CONF_SW_VERSION
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceEntry, DeviceRegistry
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from homeassistant.helpers.entity_registry import (
    EntityRegistry,
    async_entries_for_device,
)
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.selector import (
    ConstantSelector,
    ConstantSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

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
from .models import (
    AttributeModification,
    DeviceModification,
    DeviceToolsConfigEntryData,
    EntityModification,
)

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
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(
                            {
                                "value": entity.id,
                                "label": entity.name
                                if entity.name is not None
                                else entity.entity_id,
                            }
                        )
                        for entity in er.entities.values()
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
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
        self._device_modification: DeviceModification | None = None
        self._device: DeviceEntry | None = None

    @property
    def device_registry(self) -> DeviceRegistry:
        """Return the device registry."""

        return async_get_device_registry(self.hass)

    @property
    def entity_registry(self) -> EntityRegistry:
        """Return the entity registry."""

        return async_get_entity_registry(self.hass)

    @property
    def device(self) -> DeviceEntry:
        """Return the device."""

        if TYPE_CHECKING:
            assert self._device is not None

        return self._device

    @device.setter
    def device(self, value: DeviceEntry) -> None:
        """Set the device."""

        if TYPE_CHECKING:
            assert value is not None

        self._device = value

    @property
    def device_modification(self) -> DeviceModification:
        """Return the device modification."""

        if TYPE_CHECKING:
            assert self._device_modification is not None

        return self._device_modification

    @device_modification.setter
    def device_modification(self, value: DeviceModification) -> None:
        """Set the device modification."""

        self._device_modification = value

    @property
    def user_input_user(self) -> dict[str, Any]:
        """Return the user input user."""

        if TYPE_CHECKING:
            assert self._user_input_user is not None

        return self._user_input_user

    @user_input_user.setter
    def user_input_user(self, value: dict[str, Any]) -> None:
        """Set the user input user."""

        self._user_input_user = value

    @property
    def user_input_main(self) -> dict[str, Any]:
        """Return the user input main."""

        if TYPE_CHECKING:
            assert self._user_input_main is not None

        return self._user_input_main

    @user_input_main.setter
    def user_input_main(self, value: dict[str, Any]) -> None:
        """Set the user input main."""

        self._user_input_main = value

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
                        vol.Required(CONF_DEVICE_ID): SelectSelector(
                            SelectSelectorConfig(
                                options=[
                                    SelectOptionDict(
                                        {
                                            "value": device.id,
                                            "label": device.name_by_user
                                            or device.name
                                            or device.id,
                                        }
                                    )
                                    for device in self.device_registry.devices.values()
                                ],
                                mode=SelectSelectorMode.DROPDOWN,
                            )
                        ),
                    }
                ),
            )

        self._user_input_user = user_input

        modification_type: ModificationType = user_input[CONF_MODIFICATION_TYPE]
        modification_name: str = user_input[CONF_MODIFICATION_NAME]
        device = self.device_registry.async_get(user_input[CONF_DEVICE_ID])

        if device is None:
            return self.async_abort(reason="device_not_found")

        if device.disabled_by is not None:
            return self.async_abort(reason="device_disabled")

        self.device = device
        self.device_modification = DeviceModification(
            {
                "modification_name": modification_name,
                "device_id": user_input[CONF_DEVICE_ID],
                "device_name": self.device.name_by_user
                or self.device.name
                or self.device.id,
                "attribute_modification": None,
                "entity_modification": None,
            }
        )

        await self.async_set_unique_id(user_input[CONF_DEVICE_ID])
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

        if self.device_modification["attribute_modification"] is None:
            self.device_modification["attribute_modification"] = AttributeModification(
                {
                    "manufacturer": self.device.manufacturer or "",
                    "model": self.device.model or "",
                    "sw_version": self.device.sw_version or "",
                    "hw_version": self.device.hw_version or "",
                    "serial_number": self.device.serial_number or "",
                    "via_device_id": self.device.via_device_id or "",
                }
            )

        if TYPE_CHECKING:
            assert self.device_modification["attribute_modification"] is not None

        if user_input is None:
            return self.async_show_form(
                step_id="attributes",
                data_schema=_schema_attributes(
                    self.device_modification["attribute_modification"]
                ),
            )

        self.device_modification["attribute_modification"]["manufacturer"] = user_input[
            CONF_MANUFACTURER
        ]
        self.device_modification["attribute_modification"]["model"] = user_input[
            CONF_MODEL
        ]
        self.device_modification["attribute_modification"]["sw_version"] = user_input[
            CONF_SW_VERSION
        ]
        self.device_modification["attribute_modification"]["hw_version"] = user_input[
            CONF_HW_VERSION
        ]
        self.device_modification["attribute_modification"][
            "serial_number"
        ] = user_input[CONF_SERIAL_NUMBER]
        self.device_modification["attribute_modification"][
            "via_device_id"
        ] = user_input[CONF_VIA_DEVICE]

        return self.async_create_entry(
            title=self.device_modification["modification_name"],
            data=DeviceToolsConfigEntryData(
                {
                    "device_modification": self.device_modification,
                }
            ),
        )

    async def async_step_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the entities step."""

        entities = async_entries_for_device(self.entity_registry, self.device.id)
        entity_ids = {entity.id for entity in entities}

        if self.device_modification["entity_modification"] is None:
            self.device_modification["entity_modification"] = EntityModification(
                {
                    "entities": entity_ids,
                }
            )

        if TYPE_CHECKING:
            assert self.device_modification["entity_modification"] is not None

        if user_input is None:
            return self.async_show_form(
                step_id="entities",
                data_schema=_schema_entities(
                    self.hass,
                    entity_modification=self.device_modification["entity_modification"],
                ),
            )

        self.device_modification["entity_modification"]["entities"] = user_input[
            CONF_ENTITIES
        ]

        return self.async_create_entry(
            title=self.device_modification["modification_name"],
            data=DeviceToolsConfigEntryData(
                {
                    "device_modification": self.device_modification,
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
        self.device_modification: DeviceModification = config_entry.data[
            "device_modification"
        ]

    @property
    def device_registry(self) -> DeviceRegistry:
        """Return the device registry."""

        return async_get_device_registry(self.hass)

    @property
    def entity_registry(self) -> EntityRegistry:
        """Return the entity registry."""

        return async_get_entity_registry(self.hass)

    @property
    def device(self) -> DeviceEntry:
        """Return the device."""

        device = self.device_registry.async_get(self.device_modification["device_id"])

        if device is None:
            raise HomeAssistantError("device_not_found")

        return device

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""

        if user_input is None:
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(
                    {
                        vol.Optional(
                            CONF_DEVICE_ID,
                        ): ConstantSelector(
                            ConstantSelectorConfig(
                                label=f"Device: {self.device.name_by_user or self.device.name or self.device.id}",
                                value="",
                            )
                        ),
                        vol.Required(
                            CONF_MODIFICATION_TYPE, default=ModificationType.ATTRIBUTES
                        ): vol.In(
                            [value for value in ModificationType.__members__.values()]
                        ),
                    }
                ),
            )

        modification_type: ModificationType = user_input[CONF_MODIFICATION_TYPE]

        match modification_type:
            case ModificationType.ATTRIBUTES:
                return await self.async_step_attributes()
            case ModificationType.ENTITIES:
                return await self.async_step_entities()

    async def async_step_attributes(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the attributes step."""

        if self.device_modification["attribute_modification"] is None:
            self.device_modification["attribute_modification"] = AttributeModification(
                {
                    "manufacturer": self.device.manufacturer or "",
                    "model": self.device.model or "",
                    "sw_version": self.device.sw_version or "",
                    "hw_version": self.device.hw_version or "",
                    "serial_number": self.device.serial_number or "",
                    "via_device_id": self.device.via_device_id or "",
                }
            )

        if TYPE_CHECKING:
            assert self.device_modification["attribute_modification"] is not None

        if user_input is None:
            return self.async_show_form(
                step_id="attributes",
                data_schema=_schema_attributes(
                    self.device_modification["attribute_modification"]
                ),
            )

        self.device_modification["attribute_modification"] = AttributeModification(
            {
                "manufacturer": user_input[CONF_MANUFACTURER],
                "model": user_input[CONF_MODEL],
                "sw_version": user_input[CONF_SW_VERSION],
                "hw_version": user_input[CONF_HW_VERSION],
                "serial_number": user_input[CONF_SERIAL_NUMBER],
                "via_device_id": user_input[CONF_VIA_DEVICE],
            }
        )

        return self.async_create_entry(
            title="",
            data=DeviceToolsConfigEntryData(
                {
                    "device_modification": self.device_modification,
                }
            ),
        )

    async def async_step_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the entities step."""

        if self.device_modification["entity_modification"] is None:
            entities = async_entries_for_device(self.entity_registry, self.device.id)
            entity_ids = {entity.id for entity in entities}

            self.device_modification["entity_modification"] = EntityModification(
                {
                    "entities": entity_ids,
                }
            )

        if TYPE_CHECKING:
            assert self.device_modification["entity_modification"] is not None

        if user_input is None:
            return self.async_show_form(
                step_id="entities",
                data_schema=_schema_entities(
                    self.hass,
                    entity_modification=self.device_modification["entity_modification"],
                ),
            )

        self.device_modification["entity_modification"] = EntityModification(
            {
                "entities": user_input[CONF_ENTITIES],
            }
        )

        return self.async_create_entry(
            title="",
            data=DeviceToolsConfigEntryData(
                {
                    "device_modification": self.device_modification,
                }
            ),
        )
