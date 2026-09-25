"""Entry handlers for entities and devices."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity import EntityCategory

from .const import (
    CONF_ENTITY_CATEGORY,
    CONF_ENTRY_TYPE,
    MODIFIABLE_ATTRIBUTES,
    ModificationType,
)
from .original_data_store import KIND_DEVICES, KIND_ENTITIES, OriginalDataStore
from .utils import async_get_device

_LOGGER = logging.getLogger(__name__)


class EntryHandler(ABC):
    """Handler for a single registry entry targeted by one or more modifications.

    The handler reconciles the registry entry with the desired state of all
    modifications targeting it. The original value of every controlled attribute is
    kept in the original data store, so it can be restored once no modification
    controls the attribute anymore.
    """

    kind: str
    modification_type: ModificationType

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        store: OriginalDataStore,
    ) -> None:
        """Initialize the handler."""
        self._hass = hass
        self._entry_id = entry_id
        self._store = store

    @property
    def entry_id(self) -> str:
        """Return the entity id or device id this handler manages."""
        return self._entry_id

    @property
    def original_data(self) -> dict[str, Any]:
        """Return the original values of all controlled attributes."""
        return self._store.get(self.kind, self._entry_id)

    @property
    def current_data(self) -> dict[str, Any]:
        """Return the current attribute values of the registry entry."""
        return self._get_current_data() or {}

    @abstractmethod
    def _get_current_data(self) -> dict[str, Any] | None:
        """Return the current attribute values or None if the entry does not exist."""

    @abstractmethod
    def _update(self, changes: dict[str, Any]) -> None:
        """Write attribute values to the registry."""

    @callback
    def async_rename(self, new_entry_id: str) -> None:
        """Handle the managed registry entry being renamed."""
        self._store.async_rename(self.kind, self._entry_id, new_entry_id)
        self._entry_id = new_entry_id

    @callback
    def async_reconcile(self, desired_data: dict[str, Any], *, release: bool) -> None:
        """Bring the registry entry in line with the desired state.

        Attributes that are no longer desired are restored to their original values
        if release is set. Otherwise they are left untouched, which avoids flapping
        while modifications are still being loaded.
        """
        if (current_data := self._get_current_data()) is None:
            return

        original_data = self.original_data
        changes: dict[str, Any] = {}

        if release:
            for key, original_value in original_data.items():
                if key in desired_data:
                    continue
                if current_data.get(key) != original_value:
                    changes[key] = original_value
                self._store.async_remove(self.kind, self._entry_id, key)

        for key, value in desired_data.items():
            if key not in original_data:
                self._store.async_set(
                    self.kind, self._entry_id, key, current_data.get(key)
                )
            if current_data.get(key) != value:
                changes[key] = value

        if changes:
            _LOGGER.debug("Updating %s %s: %s", self.kind, self._entry_id, changes)
            self._async_update(changes)

    @callback
    def async_on_registry_updated(
        self, desired_data: dict[str, Any], changed_keys: Iterable[str]
    ) -> None:
        """Handle an update of the registry entry.

        A controlled attribute that differs from its desired value was changed by
        someone else, most likely the integration owning the entry. The new value
        becomes the original value before the desired value is applied again.
        """
        if (current_data := self._get_current_data()) is None:
            return

        original_data = self.original_data
        for key in changed_keys:
            if key not in desired_data or key not in original_data:
                continue
            if (value := current_data.get(key)) == desired_data[key]:
                continue
            _LOGGER.debug(
                "Original value of %s of %s %s changed to %s",
                key,
                self.kind,
                self._entry_id,
                value,
            )
            self._store.async_set(self.kind, self._entry_id, key, value)

        self.async_reconcile(desired_data, release=False)

    @callback
    def _async_update(self, changes: dict[str, Any]) -> None:
        """Write changes, falling back to single attributes on failure."""
        try:
            self._update(changes)
        except (HomeAssistantError, ValueError) as err:
            if len(changes) == 1:
                _LOGGER.warning(
                    "Could not update %s of %s %s: %s",
                    next(iter(changes)),
                    self.kind,
                    self._entry_id,
                    err,
                )
                return
            for key, value in changes.items():
                self._async_update({key: value})


class EntityHandler(EntryHandler):
    """Handler for a single entity targeted by one or more modifications."""

    kind = KIND_ENTITIES
    modification_type = ModificationType.ENTITY

    def _get_current_data(self) -> dict[str, Any] | None:
        """Return the current attribute values of the entity."""
        entity_registry = er.async_get(self._hass)
        if (entity := entity_registry.async_get(self._entry_id)) is None:
            return None
        return {
            key: _encode(key, getattr(entity, key))
            for key in MODIFIABLE_ATTRIBUTES[ModificationType.ENTITY]
        }

    def _update(self, changes: dict[str, Any]) -> None:
        """Write attribute values to the entity registry."""
        er.async_get(self._hass).async_update_entity(
            self._entry_id,
            **{key: _decode(key, value) for key, value in changes.items()},
        )


class DeviceHandler(EntryHandler):
    """Handler for a single device targeted by one or more modifications."""

    kind = KIND_DEVICES
    modification_type = ModificationType.DEVICE

    def _get_current_data(self) -> dict[str, Any] | None:
        """Return the current attribute values of the device."""
        device = async_get_device(self._hass, self._entry_id)
        if not isinstance(device, dr.DeviceEntry):
            return None
        return {
            key: _encode(key, getattr(device, key))
            for key in MODIFIABLE_ATTRIBUTES[ModificationType.DEVICE]
        }

    def _update(self, changes: dict[str, Any]) -> None:
        """Write attribute values to the device registry."""
        dr.async_get(self._hass).async_update_device(
            self._entry_id,
            **{key: _decode(key, value) for key, value in changes.items()},
        )


def _encode(key: str, value: Any) -> Any:
    """Return the JSON representation of a registry attribute value."""
    if key in (CONF_ENTITY_CATEGORY, CONF_ENTRY_TYPE) and value is not None:
        return str(value)
    return value


def _decode(key: str, value: Any) -> Any:
    """Return the registry representation of a JSON attribute value."""
    if value is None:
        return None
    if key == CONF_ENTITY_CATEGORY:
        return EntityCategory(value)
    if key == CONF_ENTRY_TYPE:
        return dr.DeviceEntryType(value)
    return value
