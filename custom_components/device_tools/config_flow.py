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
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import device_registry as dr, entity_registry as er, selector

from .const import (
    CONF_ASSIGNED_ENTITIES,
    CONF_CONFIGURATION_URL,
    CONF_CONNECTIONS,
    CONF_DEVICE_ATTRIBUTES,
    CONF_DEVICE_ID,
    CONF_ENTITIES,
    CONF_ENTRY_TYPE,
    CONF_ENTITY_ASSIGNMENT,
    CONF_ENTITY_ATTRIBUTES,
    CONF_ENTITY_CATEGORY,
    CONF_HW_VERSION,
    CONF_IDENTIFIERS,
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
    ENTITY_CATEGORY_OPTIONS,
    MODIFIABLE_ATTRIBUTES,
    ModificationType,
)
from .utils import get_default_config_entry_title, name_for_device, name_for_entity

_LOGGER = logging.getLogger(__name__)


def _check_connections_collision(
    connections: list[Any],
    target_device_id: str | None,
    device_registry: dr.DeviceRegistry,
) -> dr.DeviceEntry | None:
    """Return the first device that already owns one of the given connections.

    Returns ``None`` when no collision is found or all connections are
    claimed by ``target_device_id`` itself.
    Only inspects well-formed [type, value] pairs; malformed entries are skipped.
    """
    for connection in connections:
        if not isinstance(connection, (list, tuple)) or len(connection) != 2:
            continue
        conn_type, conn_val = connection
        existing = device_registry.async_get_device(
            connections={(str(conn_type), str(conn_val))}
        )
        if existing is not None and existing.id != target_device_id:
            return existing
    return None


def _connections_have_invalid_format(connections: list[Any]) -> bool:
    """Return True if any entry in *connections* is not a 2-item list/tuple."""
    return any(
        not isinstance(item, (list, tuple)) or len(item) != 2
        for item in connections
    )


def _normalize_device_value(key: str, value: Any) -> Any:
    """Convert a raw device-registry field value to a JSON-serializable form.

    ``device.dict_repr`` returns:
    - ``connections`` / ``identifiers`` as ``frozenset[tuple[str, str]]``
    - ``entry_type`` as ``DeviceEntryType | None``
    These cannot be stored in config-entry data (JSON) as-is.
    """
    if key in (CONF_CONNECTIONS, CONF_IDENTIFIERS):
        if isinstance(value, (set, frozenset)):
            sorted_pairs = sorted(
                (pair for pair in value if isinstance(pair, (list, tuple)) and len(pair) >= 2),
                key=lambda pair: (str(pair[0]), str(pair[1])),
            )
            return [list(pair) for pair in sorted_pairs]
    if key == CONF_ENTRY_TYPE and isinstance(value, dr.DeviceEntryType):
        return value.value
    return value


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
    hass: HomeAssistant | None = None,
) -> vol.Schema:
    """Return the schema for a device modification."""
    # Entities already natively on the target device should not be selectable —
    # they are already there and don't need bulk assignment.  Entities that the
    # user previously bulk-assigned (present in CONF_ASSIGNED_ENTITIES) are kept
    # selectable so the user can deselect (remove) them.
    already_assigned_by_us: set[str] = set(
        modification_data.get(CONF_ASSIGNED_ENTITIES, [])
    )
    exclude_entities: list[str] = []
    if hass is not None and modification_entry_id:
        exclude_entities = [
            entity.entity_id
            for entity in er.async_entries_for_device(
                er.async_get(hass),
                modification_entry_id,
                include_disabled_entities=True,
            )
            if entity.entity_id not in already_assigned_by_us
        ]

    # entry_type is stored as a DeviceEntryType enum (or None) in original data;
    # convert to string for the selector default value.
    original_entry_type = modification_original_data.get(CONF_ENTRY_TYPE)
    if isinstance(original_entry_type, dr.DeviceEntryType):
        original_entry_type = original_entry_type.value
    suggested_entry_type = (
        modification_data.get(CONF_ENTRY_TYPE, original_entry_type) or "none"
    )

    # connections/identifiers are frozenset[tuple[str, str]] in device.dict_repr;
    # convert to list-of-lists so the ObjectSelector can serialize them to JSON.
    def _set_to_list(value: Any) -> list[list[str]] | None:
        if value is None:
            return None
        if isinstance(value, (set, frozenset)):
            return [list(pair) for pair in value]
        return value  # already list-of-lists from a previous form submission

    suggested_connections = _set_to_list(
        modification_data.get(
            CONF_CONNECTIONS,
            modification_original_data.get(CONF_CONNECTIONS),
        )
    )
    suggested_identifiers = _set_to_list(
        modification_data.get(
            CONF_IDENTIFIERS,
            modification_original_data.get(CONF_IDENTIFIERS),
        )
    )
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
                            vol.Optional(
                                CONF_CONFIGURATION_URL,
                                description={
                                    "suggested_value": modification_data.get(
                                        CONF_CONFIGURATION_URL,
                                        modification_original_data.get(
                                            CONF_CONFIGURATION_URL
                                        ),
                                    )
                                },
                            ): str,
                            vol.Optional(
                                CONF_MODEL_ID,
                                description={
                                    "suggested_value": modification_data.get(
                                        CONF_MODEL_ID,
                                        modification_original_data.get(CONF_MODEL_ID),
                                    )
                                },
                            ): str,
                            vol.Optional(
                                CONF_ENTRY_TYPE,
                                description={
                                    "suggested_value": suggested_entry_type,
                                },
                            ): selector.SelectSelector(
                                selector.SelectSelectorConfig(
                                    options=["none", "service"],
                                    mode=selector.SelectSelectorMode.DROPDOWN,
                                    translation_key=CONF_ENTRY_TYPE,
                                )
                            ),
                            vol.Optional(
                                CONF_CONNECTIONS,
                                description={
                                    "suggested_value": suggested_connections,
                                },
                            ): selector.ObjectSelector(),
                            vol.Optional(
                                CONF_IDENTIFIERS,
                                description={
                                    "suggested_value": suggested_identifiers,
                                },
                            ): selector.ObjectSelector(),
                        },
                    )
                ),
                vol.Required(CONF_ENTITY_ASSIGNMENT): section(
                    vol.Schema(
                        {
                            vol.Optional(
                                CONF_ASSIGNED_ENTITIES,
                                description={
                                    "suggested_value": modification_data.get(
                                        CONF_ASSIGNED_ENTITIES, []
                                    ),
                                },
                            ): selector.EntitySelector(
                                selector.EntitySelectorConfig(
                                    multiple=True,
                                    exclude_entities=exclude_entities,
                                )
                            ),
                        }
                    )
                ),
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
    # entity_category is stored as an EntityCategory enum (or None) in original data;
    # convert to string for the selector default value.
    original_entity_category = modification_original_data.get(CONF_ENTITY_CATEGORY)
    if original_entity_category is not None:
        original_entity_category = original_entity_category.value
    suggested_entity_category = (
        modification_data.get(
            CONF_ENTITY_CATEGORY,
            original_entity_category,
        )
        or "default"
    )
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
                            vol.Optional(
                                CONF_ENTITY_CATEGORY,
                                description={
                                    "suggested_value": suggested_entity_category,
                                },
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
    hass: HomeAssistant | None = None,
) -> vol.Schema:
    """Return the schema for a modification."""
    match modification_type:
        case ModificationType.DEVICE:
            return _get_device_options_schema(
                modification_type,
                modification_entry_id,
                modification_data,
                modification_original_data or {},
                hass,
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

    # Attributes are nested inside a section wrapper in the form schema.
    match modification_type:
        case ModificationType.DEVICE:
            attributes = user_input.get(CONF_DEVICE_ATTRIBUTES, {})
        case ModificationType.ENTITY:
            attributes = user_input.get(CONF_ENTITY_ATTRIBUTES, {})
        case _:
            attributes = {}

    result = {
        k: v
        for k, v in attributes.items()
        if v is not None
        and v != ""
        and v != modification_original_data.get(k)
        and k in MODIFIABLE_ATTRIBUTES[modification_type]
    }

    if modification_type == ModificationType.DEVICE:
        entity_assignment = user_input.get(CONF_ENTITY_ASSIGNMENT, {})
        assigned = entity_assignment.get(CONF_ASSIGNED_ENTITIES) or []
        if assigned:
            result[CONF_ASSIGNED_ENTITIES] = assigned

    return result


def _options_flow_user_input_to_modification_data(
    user_input: dict[str, Any],
    modification_type: ModificationType,
) -> dict[str, Any]:
    """Return the modification data from options flow user input.

    Unlike _user_input_to_modification_data, this does NOT filter out values
    that match the original data. This allows resetting an attribute back to
    its original value via the options flow (fix for issue #45).
    """
    # Attributes are nested inside a section wrapper in the form schema.
    match modification_type:
        case ModificationType.DEVICE:
            attributes = user_input.get(CONF_DEVICE_ATTRIBUTES, {})
        case ModificationType.ENTITY:
            attributes = user_input.get(CONF_ENTITY_ATTRIBUTES, {})
        case _:
            attributes = {}

    result = {
        k: v
        for k, v in attributes.items()
        if v is not None and v != "" and k in MODIFIABLE_ATTRIBUTES[modification_type]
    }

    if modification_type == ModificationType.DEVICE:
        entity_assignment = user_input.get(CONF_ENTITY_ASSIGNMENT, {})
        # Always store CONF_ASSIGNED_ENTITIES (even as []) so the user can
        # clear a previously saved bulk assignment via the options flow.
        result[CONF_ASSIGNED_ENTITIES] = (
            entity_assignment.get(CONF_ASSIGNED_ENTITIES) or []
        )

    return result


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

        # Prevent selecting the target device itself as a merge source
        if self._modification_entry_id:
            merge_device_ids = [
                merge_device_id
                for merge_device_id in merge_device_ids
                if merge_device_id != self._modification_entry_id
            ]

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
            k: _normalize_device_value(k, v)
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
                    self.hass,
                ),
            )

        self._modification_data = _user_input_to_modification_data(
            user_input, self._modification_original_data, self._modification_type
        )

        if CONF_CONNECTIONS in self._modification_data:
            if _connections_have_invalid_format(self._modification_data[CONF_CONNECTIONS]):
                return self.async_show_form(
                    step_id="modify_device",
                    data_schema=_get_options_schema(
                        self._modification_type,
                        self._modification_entry_id,
                        self._modification_original_data,
                        self._modification_data,
                        self.hass,
                    ),
                    errors={"base": "connections_invalid_format"},
                )
            colliding = _check_connections_collision(
                self._modification_data[CONF_CONNECTIONS],
                self._modification_entry_id,
                self._device_registry,
            )
            if colliding is not None:
                return self.async_show_form(
                    step_id="modify_device",
                    data_schema=_get_options_schema(
                        self._modification_type,
                        self._modification_entry_id,
                        self._modification_original_data,
                        self._modification_data,
                        self.hass,
                    ),
                    errors={"base": "connections_collision"},
                    description_placeholders={
                        "device": colliding.name or colliding.id
                    },
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
                    self.hass,
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
            self.hass,
        )

        if user_input is None:
            return self.async_show_form(
                step_id="init",
                data_schema=schema,
            )

        if modification_type in [ModificationType.DEVICE, ModificationType.ENTITY]:
            modification_data = _options_flow_user_input_to_modification_data(
                user_input,
                modification_type,
            )
        elif modification_type == ModificationType.MERGE:
            modification_data = {}

        if (
            modification_type == ModificationType.DEVICE
            and CONF_CONNECTIONS in modification_data
        ):
            if _connections_have_invalid_format(modification_data[CONF_CONNECTIONS]):
                return self.async_show_form(
                    step_id="init",
                    data_schema=_get_options_schema(
                        modification_type,
                        modification_entry_id,
                        modification_original_data,
                        modification_data,
                        self.hass,
                    ),
                    errors={"base": "connections_invalid_format"},
                )
            colliding = _check_connections_collision(
                modification_data[CONF_CONNECTIONS],
                modification_entry_id,
                self._device_registry,
            )
            if colliding is not None:
                return self.async_show_form(
                    step_id="init",
                    data_schema=_get_options_schema(
                        modification_type,
                        modification_entry_id,
                        modification_original_data,
                        modification_data,
                        self.hass,
                    ),
                    errors={"base": "connections_collision"},
                    description_placeholders={
                        "device": colliding.name or colliding.id
                    },
                )

        return self.async_create_entry(
            data={CONF_MODIFICATION_DATA: modification_data},
        )
