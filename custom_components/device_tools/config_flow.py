from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import (
    DeviceEntry,
    DeviceRegistry,
)
from homeassistant.helpers.device_registry import (
    async_get as async_get_device_registry,
)
from homeassistant.helpers.entity_registry import (
    EntityRegistry,
    async_entries_for_device,
)
from homeassistant.helpers.entity_registry import (
    async_get as async_get_entity_registry,
)
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
    CONF_DEVICE_NAME,
    CONF_DEVICES,
    CONF_ENTITIES,
    CONF_HW_VERSION,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_MODIFICATION_NAME,
    CONF_MODIFICATION_TYPE,
    CONF_SERIAL_NUMBER,
    CONF_SW_VERSION,
    CONF_VIA_DEVICE,
    DOMAIN,
    ModificationType,
)
from .models import (
    AttributeModification,
    DeviceModification,
    DeviceToolsConfigEntryData,
    EntityModification,
    MergeModification,
)

_LOGGER = logging.getLogger(__name__)


def _schema_attributes(
    hass: HomeAssistant, attribute_modification: AttributeModification
) -> vol.Schema:
    """Return the attributes schema."""

    dr = async_get_device_registry(hass)

    config_entries = hass.config_entries.async_entries(DOMAIN)
    device_ids: set[str] = {
        entry.data["device_modification"]["device_id"] for entry in config_entries
    }

    return vol.Schema(
        {
            vol.Optional(
                CONF_MANUFACTURER,
                description={"suggested_value": attribute_modification["manufacturer"]},
            ): str,
            vol.Optional(
                CONF_MODEL,
                description={"suggested_value": attribute_modification["model"]},
            ): str,
            vol.Optional(
                CONF_VIA_DEVICE,
                description={
                    "suggested_value": attribute_modification["via_device_id"]
                },
            ): SelectSelector(
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
                        for device in dr.devices.values()
                        if device.id not in device_ids and device.disabled_by is None
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_SW_VERSION,
                description={"suggested_value": attribute_modification["sw_version"]},
            ): str,
            vol.Optional(
                CONF_HW_VERSION,
                description={"suggested_value": attribute_modification["hw_version"]},
            ): str,
            vol.Optional(
                CONF_SERIAL_NUMBER,
                description={
                    "suggested_value": attribute_modification["serial_number"]
                },
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
                CONF_ENTITIES,
                description={"suggested_value": entity_modification["entities"]},
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(
                            {
                                "value": entity.id,
                                "label": entity.name or entity.entity_id,
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


def _schema_merge(
    hass: HomeAssistant, device_id: str, merge_modification: MergeModification
) -> vol.Schema:
    """Return the merge schema."""

    dr = async_get_device_registry(hass)

    return vol.Schema(
        {
            vol.Optional(
                CONF_DEVICES,
                description={"suggested_value": merge_modification["devices"]},
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(
                            {
                                "value": other_device.id,
                                "label": other_device.name_by_user
                                or other_device.name
                                or other_device.id,
                            }
                        )
                        for other_device in dr.devices.values()
                        if other_device.id != device_id
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
        self._user_input_device: dict[str, Any] | None = None

    @property
    def device_registry(self) -> DeviceRegistry:
        """Return the device registry."""

        return async_get_device_registry(self.hass)

    @property
    def entity_registry(self) -> EntityRegistry:
        """Return the entity registry."""

        return async_get_entity_registry(self.hass)

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
    def user_input_device(self) -> dict[str, Any]:
        """Return the  input device."""

        if TYPE_CHECKING:
            assert self._user_input_device is not None

        return self._user_input_device

    @user_input_device.setter
    def user_input_device(self, value: dict[str, Any]) -> None:
        """Set the user input device."""

        self._user_input_device = value

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

        other_entries = self._async_current_entries()
        other_device_ids: set[str] = {
            entry.data["device_modification"]["device_id"] for entry in other_entries
        }

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_MODIFICATION_NAME): str,
                        vol.Optional(CONF_DEVICE_ID): SelectSelector(
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
                                    for device in sorted(list(self.device_registry.devices.values()),key=lambda x: x.name_by_user or x.name or x.id)
                                    if device.id not in other_device_ids
                                    and device.disabled_by is None
                                ],
                                mode=SelectSelectorMode.DROPDOWN,
                            )
                        ),
                    }
                ),
            )

        self._user_input_user = user_input

        await self.async_set_unique_id(user_input[CONF_MODIFICATION_NAME])
        self._abort_if_unique_id_configured(updates=user_input)

        return await self.async_step_device()

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the device step."""

        device_id: str | None = self.user_input_user.get(CONF_DEVICE_ID)
        modification_name: str = self.user_input_user[CONF_MODIFICATION_NAME]

        if user_input is None and device_id is None:
            return self.async_show_form(
                step_id="device",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_DEVICE_NAME): str,
                    }
                ),
            )
        elif device_id is not None:
            other_entries: list[ConfigEntry] = self._async_current_entries()
            entry_with_same_device: ConfigEntry | None = next(
                (
                    entry
                    for entry in other_entries
                    if entry.data["device_modification"]["device_id"] == device_id
                    and device_id is not None
                ),
                None,
            )

            if entry_with_same_device is not None:
                return self.async_abort(reason="already_configured")

            device = self.device_registry.async_get(device_id)

            if device is None:
                return self.async_abort(reason="device_not_found")

            if device.disabled_by is not None:
                return self.async_abort(reason="device_disabled")

            device_modification = DeviceModification(
                {
                    "modification_name": modification_name,
                    "device_id": device.id,
                    "device_name": device.name_by_user or device.name or device.id,
                    "attribute_modification": None,
                    "entity_modification": None,
                    "merge_modification": None,
                }
            )
        elif user_input is not None:
            device_modification = DeviceModification(
                {
                    "modification_name": modification_name,
                    "device_id": None,
                    "device_name": user_input[CONF_DEVICE_NAME],
                    "attribute_modification": None,
                    "entity_modification": None,
                    "merge_modification": None,
                }
            )

        return self.async_create_entry(
            title=device_modification["modification_name"],
            data=DeviceToolsConfigEntryData(
                {
                    "device_modification": device_modification,
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

        device_id: str | None = self.device_modification["device_id"]

        if device_id is None:
            raise HomeAssistantError("device_not_found")

        device = self.device_registry.async_get(device_id)

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
            case ModificationType.MERGE:
                return await self.async_step_merge()

    async def async_step_attributes(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the attributes step."""

        if self.device_modification["attribute_modification"] is None:
            self.device_modification["attribute_modification"] = AttributeModification(
                {
                    "manufacturer": self.device.manufacturer,
                    "model": self.device.model,
                    "sw_version": self.device.sw_version,
                    "hw_version": self.device.hw_version,
                    "serial_number": self.device.serial_number,
                    "via_device_id": self.device.via_device_id,
                }
            )

        if TYPE_CHECKING:
            assert self.device_modification["attribute_modification"] is not None

        if user_input is None:
            return self.async_show_form(
                step_id="attributes",
                data_schema=_schema_attributes(
                    self.hass, self.device_modification["attribute_modification"]
                ),
            )

        self.device_modification["attribute_modification"] = AttributeModification(
            {
                "manufacturer": user_input.get(CONF_MANUFACTURER),
                "model": user_input.get(CONF_MODEL),
                "sw_version": user_input.get(CONF_SW_VERSION),
                "hw_version": user_input.get(CONF_HW_VERSION),
                "serial_number": user_input.get(CONF_SERIAL_NUMBER),
                "via_device_id": user_input.get(CONF_VIA_DEVICE),
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

        config_entries: list[ConfigEntry] = self.hass.config_entries.async_entries(
            DOMAIN
        )
        for config_entry in config_entries:
            if config_entry.entry_id == self.config_entry.entry_id:
                continue

            other_device_modification: DeviceModification = config_entry.data[
                "device_modification"
            ]

            other_entity_modification: EntityModification | None = (
                other_device_modification.get("entity_modification")
            )

            if other_entity_modification is None:
                continue

            other_entities = set(other_entity_modification["entities"])
            own_entities = set(user_input[CONF_ENTITIES])
            duplicate_entities = other_entities & own_entities

            if len(duplicate_entities) == 0:
                continue

            new_entities = other_entities - duplicate_entities

            other_device_modification["entity_modification"] = EntityModification(
                {
                    "entities": new_entities,
                }
            )

            self.hass.config_entries.async_update_entry(
                config_entry,
                data=DeviceToolsConfigEntryData(
                    {
                        "device_modification": other_device_modification,
                    }
                ),
            )

        return self.async_create_entry(
            title="",
            data=DeviceToolsConfigEntryData(
                {
                    "device_modification": self.device_modification,
                }
            ),
        )

    async def async_step_merge(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the merge step."""

        if self.device_modification["merge_modification"] is None:
            self.device_modification["merge_modification"] = MergeModification(
                {
                    "devices": set(),
                }
            )

        if TYPE_CHECKING:
            assert self.device_modification["merge_modification"] is not None

        if self.device_modification["device_id"] is None:
            return self.async_abort(reason="device_not_found")

        if user_input is None:
            return self.async_show_form(
                step_id="merge",
                data_schema=_schema_merge(
                    self.hass,
                    self.device_modification["device_id"],
                    self.device_modification["merge_modification"],
                ),
            )

        config_entries: list[ConfigEntry] = self.hass.config_entries.async_entries(
            DOMAIN
        )

        for config_entry in config_entries:
            if config_entry.entry_id == self.config_entry.entry_id:
                continue

            own_devices = set(user_input[CONF_DEVICES])

            other_device_modification: DeviceModification = config_entry.data[
                "device_modification"
            ]

            if other_device_modification["device_id"] in own_devices:
                return self.async_abort(reason="device_in_use")

            other_merge_modification: MergeModification | None = (
                other_device_modification.get("merge_modification")
            )

            if other_merge_modification is None:
                continue

            other_devices = set(other_merge_modification["devices"])
            duplicate_devices = other_devices & own_devices

            if len(duplicate_devices) > 0:
                return self.async_abort(reason="device_already_merged")

        self.device_modification["merge_modification"] = MergeModification(
            {
                "devices": user_input[CONF_DEVICES],
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
