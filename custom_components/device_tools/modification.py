"""Class to handle a modification."""

from abc import ABC, abstractmethod
from types import MappingProxyType
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_NAME,
    CONF_MODIFICATION_TYPE,
    ModificationType,
)


class Modification(ABC):
    """Class to handle a modification."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        modification_entry_data: MappingProxyType[str, Any] | None = None,
    ) -> None:
        """Initialize the modification."""
        self._hass = hass
        self._config_entry: ConfigEntry = config_entry
        self._modification_entry_data = modification_entry_data

    @abstractmethod
    async def apply(self) -> None:
        """Apply modification."""

    @abstractmethod
    async def revert(self) -> None:
        """Revert modification."""

    @property
    def modification_type(self) -> ModificationType:
        """Return the modification type."""
        return cast(ModificationType, self._config_entry.data[CONF_MODIFICATION_TYPE])

    @property
    def modification_entry_name(self) -> str:
        """Return the modification entry name."""
        return cast(str, self._config_entry.data[CONF_MODIFICATION_ENTRY_NAME])

    @property
    def modification_data(self) -> MappingProxyType[str, Any]:
        """Return the modification data."""
        if self._modification_entry_data is not None:
            return self._modification_entry_data
        return MappingProxyType(self._config_entry.options[CONF_MODIFICATION_DATA])
