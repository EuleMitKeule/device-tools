"""Class to handle an entity modification."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import entity_registry as er

from .entity_listener import EntityListener
from .models import EntityData, PersistentModificationData
from .modification import Modification
from .storage import Storage


class EntityModification(Modification[EntityData, EntityListener]):
    """Class to handle an entity modification."""

    def __init__(
        self,
        hass: HomeAssistant,
        listener: EntityListener,
        storage: Storage,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the modification."""
        super().__init__(
            hass=hass,
            listener=listener,
            storage=storage,
            config_entry=config_entry,
        )

        self._registry = er.async_get(hass)

        entity = self._registry.async_get(self._entry_id)
        if entity is None:
            raise ValueError(f"Entity with ID {self._entry_id} not found")

        self._storage.init_entry_data(
            self._entry_id,
            PersistentModificationData(original_data=entity.extended_dict()),
        )

        self._listener.register_callback(self._entry_id, self._on_entry_updated)

    @property
    async def entity_id(self) -> str:
        """Return the entity id associated with this modification."""
        entity = self._registry.async_get(self._entry_id)
        if entity is None:
            raise ValueError(f"Entity with ID {self._entry_id} not found")
        return entity.entity_id

    async def apply(self) -> None:
        """Apply modification."""
        self._listener.unregister_callback(
            self._entry_id,
            self._on_entry_updated,
        )
        self._registry.async_update_entity(
            await self.entity_id,
            **self._data,
        )
        self._listener.register_callback(
            self._entry_id,
            self._on_entry_updated,
        )

    async def revert(self) -> None:
        """Revert modification."""
        self._listener.unregister_callback(self._entry_id, self._on_entry_updated)
        self._registry.async_update_entity(
            await self.entity_id,
            **self._relevant_original_data,
        )

    async def _on_entry_updated(
        self,
        entity: er.RegistryEntry,
        event: Event[er.EventEntityRegistryUpdatedData],
    ) -> None:
        """Handle entry updated by another integration."""
        if event.data["action"] != "update":
            return

        new_data = entity.extended_dict()
        current_data = self._storage.get_entry_data(self._entry_id)
        current_data.update(
            {key: new_data[key] for key in event.data["changes"] if key in new_data}
        )
        self._storage.set_entry_data(self._entry_id, current_data)

        await self.apply()
