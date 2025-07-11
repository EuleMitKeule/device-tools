"""Class to handle a merge modification."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import CONF_DISABLE_MERGED_DEVICES, CONF_DISABLED_BY, CONF_ENTITIES
from .device_listener import DeviceListener
from .entity_listener import EntityListener
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

        self._device_listener = device_listener
        self._entity_listener = entity_listener
        self._device_registry = dr.async_get(hass)
        self._entity_registry = er.async_get(hass)

        self._device = self._device_registry.async_get(self.modification_entry_id)
        if self._device is None:
            raise ValueError(f"Device with ID {self.modification_entry_id} not found")

        for merge_device_entry_id in self.merge_device_entry_ids:
            self._device_listener.register_callback(
                merge_device_entry_id,
                self._on_merge_device_updated,
            )

        for entity_entry_id in self.merge_entity_entry_ids:
            self._entity_listener.register_callback(
                entity_entry_id, self._on_merge_entity_updated
            )

    @property
    def merge_device_entry_ids(self) -> set[str]:
        """Return the device IDs for merge modifications."""
        return set(self.modification_original_data.keys())

    @property
    def merge_entity_entry_ids(self) -> set[str]:
        """Return the entity entry IDs associated with the merge modification."""
        return {
            merge_entity_entry_id
            for merge_device_entry_id in self.merge_device_entry_ids
            for merge_entity_entry_id in self.modification_original_data[
                merge_device_entry_id
            ][CONF_ENTITIES]
        }

    @property
    def merge_entity_ids(self) -> set[str]:
        """Return the entity IDs associated with the merge modification."""
        return {
            (entry := self._entity_registry.async_get(merge_entity_entry_id))
            and entry.entity_id
            for merge_device_entry_id in self.merge_device_entry_ids
            for merge_entity_entry_id in self.modification_original_data[
                merge_device_entry_id
            ][CONF_ENTITIES]
        }

    async def apply(self) -> None:
        """Apply modification."""
        for merge_device_entry_id in self.merge_device_entry_ids:
            self._device_listener.unregister_callback(
                merge_device_entry_id, self._on_merge_device_updated
            )
        for merge_entity_entry_id in self.merge_entity_entry_ids:
            self._entity_listener.unregister_callback(
                merge_entity_entry_id, self._on_merge_entity_updated
            )

        self._device_registry.async_update_device(
            self.modification_entry_id,
            add_config_entry_id=self._config_entry.entry_id,
        )
        for merge_device_entry_id in self.merge_device_entry_ids:
            self._device_registry.async_update_device(
                merge_device_entry_id,
                add_config_entry_id=self._config_entry.entry_id,
            )
            if self.modification_data.get(CONF_DISABLE_MERGED_DEVICES, True):
                self._device_registry.async_update_device(
                    merge_device_entry_id,
                    disabled_by=dr.DeviceEntryDisabler.CONFIG_ENTRY,
                )
        for merge_entity_id in self.merge_entity_ids:
            self._entity_registry.async_update_entity(
                merge_entity_id,
                device_id=self.modification_entry_id,
            )

        for merge_entity_entry_id in self.merge_entity_entry_ids:
            self._entity_listener.register_callback(
                merge_entity_entry_id, self._on_merge_entity_updated
            )
        for merge_device_entry_id in self.merge_device_entry_ids:
            self._device_listener.register_callback(
                merge_device_entry_id, self._on_merge_device_updated
            )

    async def revert(self) -> None:
        """Revert modification."""
        for merge_device_entry_id in self.merge_device_entry_ids:
            self._device_listener.unregister_callback(
                merge_device_entry_id, self._on_merge_device_updated
            )
        for merge_entity_entry_id in self.merge_entity_entry_ids:
            self._entity_listener.unregister_callback(
                merge_entity_entry_id, self._on_merge_entity_updated
            )

        self._device_registry.async_update_device(
            self.modification_entry_id,
            remove_config_entry_id=self._config_entry.entry_id,  # TODO only do this if we are the only modification for this device
        )
        for merge_device_entry_id in self.merge_device_entry_ids:
            self._device_registry.async_update_device(
                merge_device_entry_id,
                remove_config_entry_id=self._config_entry.entry_id,  # TODO only do this if we are the only modification for this device
                disabled_by=self.modification_original_data[merge_device_entry_id].get(
                    CONF_DISABLED_BY, None
                ),
            )
        for merge_entity_id, merge_entity_entry_id in zip(
            self.merge_entity_ids, self.merge_entity_entry_ids, strict=True
        ):
            self._entity_registry.async_update_entity(
                merge_entity_id,
                device_id=self._get_device_entry_id_for_entity_entry_id(
                    merge_entity_entry_id
                ),
            )

    def _get_device_entry_id_for_entity_entry_id(self, entity_entry_id: str) -> str:
        """Get the device entry ID for a given entity entry ID from the original data."""
        for (
            merge_device_entry_id,
            merge_device_entry_data,
        ) in self.modification_original_data.items():
            if entity_entry_id in merge_device_entry_data[CONF_ENTITIES]:
                return merge_device_entry_id

        raise ValueError(
            f"Entity entry ID {entity_entry_id} not found in the original data of modification {self.modification_entry_id}"
        )

    def _on_entry_updated(
        self, device: dr.DeviceEntry, event: Event[dr.EventDeviceRegistryUpdatedData]
    ) -> None:
        """Handle updates to the device entry."""

    def _on_merge_device_updated(
        self, device: dr.DeviceEntry, event: Event[dr.EventDeviceRegistryUpdatedData]
    ) -> None:
        """Handle updates to the merged device."""

    def _on_merge_entity_updated(
        self, entity: er.RegistryEntry, event: Event[er.EventEntityRegistryUpdatedData]
    ) -> None:
        """Handle updates to the merged entity."""
