"""Entry handlers for entities and devices."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_registry import EntityCategory

from .const import (
    CONF_ASSIGNED_ENTITIES,
    CONF_DEVICE_ID,
    CONF_ENTITY_CATEGORY,
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_TYPE,
    MODIFIABLE_ATTRIBUTES,
    ModificationType,
)
from .original_data_store import OriginalDataStore

_LOGGER = logging.getLogger(__name__)


class EntryHandler(ABC):
    """Base handler for a single entity or device targeted by one or more config entries."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        store: OriginalDataStore,
        get_active_entries: Callable[[], list[ConfigEntry[Any]]],
    ) -> None:
        """Initialize the handler."""
        self._hass = hass
        self._entry_id = entry_id
        self._store = store
        self._get_active_entries = get_active_entries
        self._unsub_listener: CALLBACK_TYPE | None = None

    @property
    def entry_id(self) -> str:
        """Return the entity_id or device_id this handler manages."""
        return self._entry_id

    @abstractmethod
    def _get_original_data(self) -> dict[str, Any]:
        """Return original data from store. Raises if not set."""

    @abstractmethod
    async def async_apply(self, config_entries: list[ConfigEntry[Any]]) -> None:
        """Apply all relevant config entries in priority order."""

    @abstractmethod
    async def async_revert(self) -> None:
        """Revert to original_data."""

    @abstractmethod
    async def async_start_listening(self) -> None:
        """Register single registry listener."""

    async def async_stop_listening(self) -> None:
        """Unregister registry listener."""
        if self._unsub_listener is not None:
            self._unsub_listener()
            self._unsub_listener = None


class EntityHandler(EntryHandler):
    """Handler for a single entity targeted by one or more config entries."""

    def _get_original_data(self) -> dict[str, Any]:
        """Return original data from store."""
        data = self._store.get_entity(self._entry_id)
        if data is None:
            raise ValueError(
                f"Original data for entity {self._entry_id} not found in store"
            )
        return data

    async def async_apply(self, config_entries: list[ConfigEntry[Any]]) -> None:
        """Apply all relevant config entries in priority order.

        Priority: MERGE first, then DEVICE, then ENTITY.
        """
        await self.async_stop_listening()
        try:
            merged: dict[str, Any] = {}

            for entry in config_entries:
                mod_type = ModificationType(entry.data[CONF_MODIFICATION_TYPE])
                mod_data: dict[str, Any] = entry.options.get(CONF_MODIFICATION_DATA, {})
                mod_entry_id: str = entry.data[CONF_MODIFICATION_ENTRY_ID]

                if mod_type == ModificationType.MERGE:
                    merged[CONF_DEVICE_ID] = mod_entry_id
                elif mod_type == ModificationType.DEVICE:
                    if (
                        CONF_ASSIGNED_ENTITIES in mod_data
                        and self._entry_id in mod_data.get(CONF_ASSIGNED_ENTITIES, [])
                    ):
                        merged[CONF_DEVICE_ID] = mod_entry_id
                elif mod_type == ModificationType.ENTITY:
                    merged.update(mod_data)

            if not merged:
                return

            update_kwargs: dict[str, Any] = {
                key: value
                for key, value in merged.items()
                if (
                    key in MODIFIABLE_ATTRIBUTES[ModificationType.ENTITY]
                    or key == CONF_DEVICE_ID
                )
            }

            if not update_kwargs:
                return

            entity_registry = er.async_get(self._hass)
            entity = entity_registry.async_get(self._entry_id)
            if entity is None:
                _LOGGER.warning("Entity %s not found, cannot apply", self._entry_id)
                return

            _LOGGER.debug(
                "Applying entity modifications to %s: %s",
                self._entry_id,
                update_kwargs,
            )
            if CONF_ENTITY_CATEGORY in update_kwargs:
                raw = update_kwargs[CONF_ENTITY_CATEGORY]
                update_kwargs[CONF_ENTITY_CATEGORY] = (
                    EntityCategory(raw) if raw and raw != "default" else None
                )
            entity_registry.async_update_entity(entity.entity_id, **update_kwargs)
        finally:
            await self.async_start_listening()

    async def async_revert(self) -> None:
        """Revert to original_data."""
        await self.async_stop_listening()
        try:
            original = self._get_original_data()
            entity_registry = er.async_get(self._hass)
            entity = entity_registry.async_get(self._entry_id)
            if entity is None:
                _LOGGER.warning("Entity %s not found, cannot revert", self._entry_id)
                return

            revert_kwargs: dict[str, Any] = {
                k: v
                for k, v in original.items()
                if k in MODIFIABLE_ATTRIBUTES[ModificationType.ENTITY]
                or k == CONF_DEVICE_ID
            }
            if revert_kwargs:
                _LOGGER.debug(
                    "Reverting entity %s to original data: %s",
                    self._entry_id,
                    revert_kwargs,
                )
                entity_registry.async_update_entity(entity.entity_id, **revert_kwargs)
        finally:
            await self.async_start_listening()

    async def async_start_listening(self) -> None:
        """Register single entity registry listener."""
        if self._unsub_listener is not None:
            return
        self._unsub_listener = self._hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED,
            self._async_on_entity_registry_updated,
        )

    async def _async_on_entity_registry_updated(
        self,
        event: Event[er.EventEntityRegistryUpdatedData],
    ) -> None:
        """Handle entity registry updated event."""
        if event.data["action"] != "update":
            return
        if event.data["entity_id"] != self._entry_id:
            return

        entity_registry = er.async_get(self._hass)
        entity = entity_registry.async_get(self._entry_id)
        if entity is None:
            return

        active_entries = self._get_active_entries()

        changes: dict[str, Any] = event.data.get("changes", {})
        new_data = entity.extended_dict
        external_changes = {key: new_data[key] for key in changes if key in new_data}

        if external_changes:
            await self._store.async_update_entity(self._entry_id, external_changes)

        # Re-apply so controlled keys remain correct
        await self.async_apply(active_entries)


class DeviceHandler(EntryHandler):
    """Handler for a single device targeted by one or more config entries."""

    def _get_original_data(self) -> dict[str, Any]:
        """Return original data from store."""
        data = self._store.get_device(self._entry_id)
        if data is None:
            raise ValueError(
                f"Original data for device {self._entry_id} not found in store"
            )
        return data

    async def async_apply(self, config_entries: list[ConfigEntry[Any]]) -> None:
        """Apply all relevant config entries in priority order.

        Priority: MERGE first, then DEVICE.
        """
        await self.async_stop_listening()
        try:
            device_registry = dr.async_get(self._hass)
            device = device_registry.async_get(self._entry_id)
            if device is None:
                _LOGGER.warning("Device %s not found, cannot apply", self._entry_id)
                return

            for entry in config_entries:
                device_registry.async_update_device(
                    self._entry_id,
                    add_config_entry_id=entry.entry_id,
                )

            merged: dict[str, Any] = {
                k: v
                for entry in config_entries
                if ModificationType(entry.data[CONF_MODIFICATION_TYPE])
                == ModificationType.DEVICE
                for k, v in entry.options.get(CONF_MODIFICATION_DATA, {}).items()
                if k in MODIFIABLE_ATTRIBUTES[ModificationType.DEVICE]
            }

            if merged:
                _LOGGER.debug(
                    "Applying device modifications to %s: %s",
                    self._entry_id,
                    merged,
                )
                device_registry.async_update_device(self._entry_id, **merged)
        finally:
            await self.async_start_listening()

    async def async_revert(self) -> None:
        """Revert to original_data."""
        await self.async_stop_listening()
        try:
            original = self._get_original_data()
            device_registry = dr.async_get(self._hass)
            device = device_registry.async_get(self._entry_id)
            if device is None:
                _LOGGER.warning("Device %s not found, cannot revert", self._entry_id)
                return

            revert_kwargs: dict[str, Any] = {
                k: v
                for k, v in original.items()
                if k in MODIFIABLE_ATTRIBUTES[ModificationType.DEVICE]
            }
            if revert_kwargs:
                _LOGGER.debug(
                    "Reverting device %s to original data: %s",
                    self._entry_id,
                    revert_kwargs,
                )
                device_registry.async_update_device(self._entry_id, **revert_kwargs)

            # Remove each DT config entry from the device.
            # Guard against removing the last config entry — that would delete the device.
            for entry in self._get_active_entries():
                current = device_registry.async_get(self._entry_id)
                if current is None or len(current.config_entries) <= 1:
                    break
                device_registry.async_update_device(
                    self._entry_id,
                    remove_config_entry_id=entry.entry_id,
                )
        finally:
            await self.async_start_listening()

    async def async_start_listening(self) -> None:
        """Register single device registry listener."""
        if self._unsub_listener is not None:
            return
        self._unsub_listener = self._hass.bus.async_listen(
            dr.EVENT_DEVICE_REGISTRY_UPDATED,
            self._async_on_device_registry_updated,
        )

    async def _async_on_device_registry_updated(
        self,
        event: Event[dr.EventDeviceRegistryUpdatedData],
    ) -> None:
        """Handle device registry updated event."""
        if event.data["action"] != "update":
            return
        if event.data["device_id"] != self._entry_id:
            return

        device_registry = dr.async_get(self._hass)
        device = device_registry.async_get(self._entry_id)
        if device is None:
            return

        active_entries = self._get_active_entries()

        changes: dict[str, Any] = event.data.get("changes", {})
        new_data = device.dict_repr
        external_changes = {key: new_data[key] for key in changes if key in new_data}

        if external_changes:
            await self._store.async_update_device(self._entry_id, external_changes)

        await self.async_apply(active_entries)
