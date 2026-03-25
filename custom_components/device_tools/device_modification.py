"""Class to handle a device modification."""

from collections.abc import Callable
import logging
from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    CONF_ASSIGNED_ENTITIES,
    CONF_DEVICE_ID,
    CONF_ENTITY_ORIGINAL_DEVICE_IDS,
    CONF_MODIFICATION_ORIGINAL_DATA,
    MODIFIABLE_ATTRIBUTES,
)
from .data import DATA_KEY
from .device_listener import DeviceListener
from .entity_listener import EntityListener
from .entity_modification import EntityModification
from .entry_modification import EntryModification

_LOGGER = logging.getLogger(__name__)


class DeviceModification(EntryModification):
    """Class to handle a device modification."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry[Any],
        listener: DeviceListener,
        entity_listener: EntityListener | None = None,
        modification_entry_id: str | None = None,
        modification_entry_data: MappingProxyType[str, Any] | None = None,
        func_get_modification_original_data: Callable[
            [ConfigEntry[Any]], MappingProxyType[str, Any]
        ]
        | None = None,
        func_update_modification_original_data: Callable[
            [ConfigEntry[Any], dict[str, Any]], None
        ]
        | None = None,
    ) -> None:
        """Initialize the modification."""
        super().__init__(
            hass=hass,
            config_entry=config_entry,
            modification_entry_id=modification_entry_id,
            modification_entry_data=modification_entry_data,
            func_get_modification_original_data=func_get_modification_original_data,
            func_update_modification_original_data=func_update_modification_original_data,
        )

        self._registry = dr.async_get(hass)
        self._listener: DeviceListener = listener
        self._entity_listener = entity_listener

        self._listener.register_callback(
            self.modification_entry_id,
            self._on_entry_updated,
        )
        for entity_id in self.modification_data.get(CONF_ASSIGNED_ENTITIES, []):
            if self._entity_listener:
                self._entity_listener.register_callback(
                    entity_id, self._on_assigned_entity_updated
                )

    async def apply(self) -> None:
        """Apply modification."""
        self._listener.unregister_callback(
            self.modification_entry_id,
            self._on_entry_updated,
        )
        _LOGGER.debug(
            "Applying device modification %s with data: %s",
            self.modification_entry_id,
            self.modification_data,
        )
        device_update_data = {
            k: v
            for k, v in self.modification_data.items()
            if k != CONF_ASSIGNED_ENTITIES
        }
        self._registry.async_update_device(
            self.modification_entry_id,
            add_config_entry_id=self._config_entry.entry_id,
            **device_update_data,
        )

        entity_registry = er.async_get(self._hass)
        assigned_entities: list[str] = list(
            self.modification_data.get(CONF_ASSIGNED_ENTITIES, [])
        )
        if assigned_entities:
            entity_original_device_ids: dict[str, str | None] = dict(
                self.modification_original_data.get(CONF_ENTITY_ORIGINAL_DEVICE_IDS, {})
            )
            for entity_id in assigned_entities:
                if self._entity_listener:
                    self._entity_listener.unregister_callback(
                        entity_id, self._on_assigned_entity_updated
                    )
            changed = False
            for entity_id in assigned_entities:
                if self._is_entity_managed_by_entity_modification(entity_id):
                    continue
                entity = entity_registry.async_get(entity_id)
                if entity is None:
                    continue
                if entity_id not in entity_original_device_ids:
                    entity_original_device_ids[entity_id] = entity.device_id
                    changed = True
                entity_registry.async_update_entity(
                    entity_id,
                    device_id=self.modification_entry_id,
                )
            if changed:
                self._hass.config_entries.async_update_entry(
                    self._config_entry,
                    data={
                        **self._config_entry.data,
                        CONF_MODIFICATION_ORIGINAL_DATA: {
                            **dict(self.modification_original_data),
                            CONF_ENTITY_ORIGINAL_DEVICE_IDS: entity_original_device_ids,
                        },
                    },
                )
            for entity_id in assigned_entities:
                if self._entity_listener:
                    self._entity_listener.register_callback(
                        entity_id, self._on_assigned_entity_updated
                    )

        self._listener.register_callback(
            self.modification_entry_id,
            self._on_entry_updated,
        )

    async def revert(self) -> None:
        """Revert modification."""
        self._listener.unregister_callback(
            self.modification_entry_id,
            self._on_entry_updated,
        )

        entity_registry = er.async_get(self._hass)
        entity_original_device_ids: dict[str, str | None] = dict(
            self.modification_original_data.get(CONF_ENTITY_ORIGINAL_DEVICE_IDS, {})
        )
        for entity_id in entity_original_device_ids:
            if self._entity_listener:
                self._entity_listener.unregister_callback(
                    entity_id, self._on_assigned_entity_updated
                )
        for entity_id, original_device_id in entity_original_device_ids.items():
            if self._is_entity_managed_by_entity_modification(entity_id):
                continue
            entity = entity_registry.async_get(entity_id)
            if entity is None:
                continue
            entity_registry.async_update_entity(
                entity_id,
                device_id=original_device_id,
            )

        if (device := self._registry.async_get(self.modification_entry_id)) and len(
            device.config_entries
        ) > 1:
            self._registry.async_update_device(
                self.modification_entry_id,
                remove_config_entry_id=self._config_entry.entry_id,
                **self._overwritten_original_data,
            )

    async def _on_entry_updated(
        self,
        device: dr.DeviceEntry,
        event: Event[dr.EventDeviceRegistryUpdatedData],
    ) -> None:
        """Handle entry updated by another integration."""
        if event.data["action"] != "update":
            return

        new_data = device.dict_repr
        modification_original_data = dict(self.modification_original_data)
        modification_original_data.update(
            {key: new_data[key] for key in event.data["changes"] if key in new_data}
        )
        self._update_modification_original_data(modification_original_data)

        await self.apply()

    async def _on_assigned_entity_updated(
        self,
        entity: er.RegistryEntry,
        event: Event[er.EventEntityRegistryUpdatedData],
    ) -> None:
        """Handle an assigned entity being updated by another integration."""
        if event.data["action"] != "update":
            return
        if "device_id" not in event.data.get("changes", {}):
            return

        entity_id: str = event.data["entity_id"]

        entity_original_device_ids: dict[str, str | None] = dict(
            self.modification_original_data.get(CONF_ENTITY_ORIGINAL_DEVICE_IDS, {})
        )
        entity_original_device_ids[entity_id] = entity.device_id

        self._update_modification_original_data(
            {
                **dict(self.modification_original_data),
                CONF_ENTITY_ORIGINAL_DEVICE_IDS: entity_original_device_ids,
            }
        )

        await self.apply()

    def _update_modification_original_data(self, data: dict[str, Any]) -> None:
        """Update the original data, preserving entity original device IDs."""
        if self._func_update_modification_original_data is not None:
            self._func_update_modification_original_data(self._config_entry, data)
            return

        filtered: dict[str, Any] = {
            k: v
            for k, v in data.items()
            if k in MODIFIABLE_ATTRIBUTES[self.modification_type]
        }
        if CONF_ENTITY_ORIGINAL_DEVICE_IDS in data:
            filtered[CONF_ENTITY_ORIGINAL_DEVICE_IDS] = data[
                CONF_ENTITY_ORIGINAL_DEVICE_IDS
            ]

        self._hass.config_entries.async_update_entry(
            self._config_entry,
            data={
                **self._config_entry.data,
                CONF_MODIFICATION_ORIGINAL_DATA: filtered,
            },
        )

    def _is_entity_managed_by_entity_modification(self, entity_id: str) -> bool:
        """Return True if an EntityModification sets device_id for the given entity."""

        device_tools_data = self._hass.data.get(DATA_KEY)
        if device_tools_data is None:
            return False
        for modification in device_tools_data.modifications.values():
            if (
                isinstance(modification, EntityModification)
                and modification.modification_entry_id == entity_id
                and CONF_DEVICE_ID in modification.modification_data
            ):
                return True
        return False
