"""Module to handle a registry entry modification."""

from collections.abc import Callable
from types import MappingProxyType
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_ORIGINAL_DATA,
    MODIFIABLE_ATTRIBUTES,
)
from .modification import Modification


class EntryModification(Modification):
    """Class to handle a registry entry modification."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry[Any],
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
            hass,
            config_entry,
            modification_entry_data=modification_entry_data,
        )
        self._modification_entry_id = modification_entry_id
        self._func_get_modification_original_data = func_get_modification_original_data
        self._func_update_modification_original_data = (
            func_update_modification_original_data
        )

    @property
    def modification_entry_id(self) -> str:
        """Return the modification entry ID."""
        if self._modification_entry_id is not None:
            return self._modification_entry_id
        return cast(str, self._config_entry.data[CONF_MODIFICATION_ENTRY_ID])

    @property
    def modification_original_data(self) -> MappingProxyType[str, Any]:
        """Return the original data before modification."""
        if self._func_get_modification_original_data is not None:
            return self._func_get_modification_original_data(self._config_entry)
        return MappingProxyType(
            self._config_entry.data[CONF_MODIFICATION_ORIGINAL_DATA]
        )

    @property
    def _overwritten_original_data(self) -> MappingProxyType[str, Any]:
        """Return relevant original data."""
        return MappingProxyType(
            {
                key: value
                for key, value in self.modification_original_data.items()
                if key in self.modification_data
            }
        )

    def _update_modification_original_data(self, data: dict[str, Any]) -> None:
        """Update the original data in the config entry."""
        if self._func_update_modification_original_data is not None:
            self._func_update_modification_original_data(
                self._config_entry,
                data,
            )
            return
        self._hass.config_entries.async_update_entry(
            self._config_entry,
            data={
                **self._config_entry.data,
                CONF_MODIFICATION_ORIGINAL_DATA: {
                    k: v
                    for k, v in data.items()
                    if k in MODIFIABLE_ATTRIBUTES[self.modification_type]
                },
            },
        )
