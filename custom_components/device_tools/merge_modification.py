"""Class to handle a merge modification."""

import logging
from types import MappingProxyType
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ENTITIES,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_ORIGINAL_DATA,
)
from .device_listener import DeviceListener
from .device_modification import DeviceModification
from .entity_listener import EntityListener
from .entity_modification import EntityModification
from .modification import Modification

_LOGGER = logging.getLogger(__name__)


class MergeModification(Modification):
    """Class to handle a merge modification."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        device_listener: DeviceListener,
        entity_listener: EntityListener,
    ) -> None:
        """Initialize the modification."""
        super().__init__(
            hass=hass,
            config_entry=config_entry,
        )

        self._modifications: list[Modification] = [
            DeviceModification(
                hass,
                config_entry,
                device_listener,
                modification_entry_data=MappingProxyType({}),
                modification_original_data=MappingProxyType({}),
            )
        ]

        for merge_device_entry_id in self.merge_device_entry_ids:
            _LOGGER.debug(
                "MergeModification will modify merged device %s",
                merge_device_entry_id,
            )

            modification = DeviceModification(
                hass,
                config_entry,
                device_listener,
                modification_entry_id=merge_device_entry_id,
                modification_entry_data=MappingProxyType({}),
                modification_original_data=MappingProxyType({}),
            )
            self._modifications.append(modification)

            original_data = self.modification_original_data[merge_device_entry_id]
            entities: dict[str, dict[str, Any]] = original_data.get(CONF_ENTITIES, {})
            for merge_entity_entry_id, merge_entity_original_data in entities.items():
                _LOGGER.debug(
                    "MergeModification will modify merged entity %s",
                    merge_entity_entry_id,
                )

                modification = EntityModification(
                    hass,
                    config_entry,
                    entity_listener,
                    modification_entry_id=merge_entity_entry_id,
                    modification_entry_data=MappingProxyType(
                        {"device_id": self.modification_entry_id}
                    ),
                    modification_original_data=MappingProxyType(
                        merge_entity_original_data
                    ),
                    func_update_modification_original_data=lambda config_entry,
                    data,
                    device_id=merge_device_entry_id,
                    entity_id=merge_entity_entry_id: self._update_entity_modification_original_data(
                        device_id,
                        entity_id,
                        data,
                    ),
                )
                self._modifications.append(modification)

    async def apply(self) -> None:
        """Apply modification."""
        for modification in self._modifications:
            await modification.apply()

    async def revert(self) -> None:
        """Revert modification."""
        for modification in self._modifications:
            await modification.revert()

    @property
    def modification_entry_id(self) -> str:
        """Return the modification entry ID."""
        return cast(
            str,
            self._config_entry.data[CONF_MODIFICATION_ENTRY_ID],
        )

    @property
    def modification_original_data(self) -> MappingProxyType[str, Any]:
        """Return the original data before modification."""
        return MappingProxyType(
            self._config_entry.data[CONF_MODIFICATION_ORIGINAL_DATA]
        )

    @property
    def merge_device_entry_ids(self) -> set[str]:
        """Return the device IDs for merge modifications."""
        return set(self.modification_original_data.keys())

    def _update_entity_modification_original_data(
        self,
        merge_device_entry_id: str,
        merge_entity_entry_id: str,
        data: dict[str, Any],
    ) -> None:
        """Update the original data in the config entry."""
        current_modification_original_data = self._config_entry.data.get(
            CONF_MODIFICATION_ORIGINAL_DATA, {}
        )

        if merge_device_entry_id not in current_modification_original_data:
            current_modification_original_data[merge_device_entry_id] = {}
        if (
            CONF_ENTITIES
            not in current_modification_original_data[merge_device_entry_id]
        ):
            current_modification_original_data[merge_device_entry_id][
                CONF_ENTITIES
            ] = {}
        current_modification_original_data[merge_device_entry_id][CONF_ENTITIES][
            merge_entity_entry_id
        ] = data
        self._hass.config_entries.async_update_entry(
            self._config_entry,
            data={
                **self._config_entry.data,
                CONF_MODIFICATION_ORIGINAL_DATA: current_modification_original_data,
            },
        )
