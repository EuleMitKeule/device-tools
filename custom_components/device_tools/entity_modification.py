"""Class to handle an entity modification."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import entity_registry as er

from .entity_listener import EntityListener
from .modification import Modification


class EntityModification(Modification):
    """Class to handle an entity modification."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        listener: EntityListener,
    ) -> None:
        """Initialize the modification."""
        super().__init__(
            hass=hass,
            config_entry=config_entry,
        )

        self._registry = er.async_get(hass)
        self._listener = listener

        self._listener.register_callback(
            self.modification_entry_id, self._on_entry_updated
        )

    @property
    async def entity_id(self) -> str:
        """Return the entity id associated with this modification."""
        entity = self._registry.async_get(self.modification_entry_id)
        if entity is None:
            raise ValueError(f"Entity with ID {self.modification_entry_id} not found")
        return entity.entity_id

    async def apply(self) -> None:
        """Apply modification."""
        self._listener.unregister_callback(
            self.modification_entry_id,
            self._on_entry_updated,
        )
        self._registry.async_update_entity(
            await self.entity_id,
            **self.modification_data,
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
        self._registry.async_update_entity(
            await self.entity_id,
            **self._overwritten_original_data,
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
        modification_original_data = dict(self.modification_original_data)
        modification_original_data.update(
            {key: new_data[key] for key in event.data["changes"] if key in new_data}
        )
        self._update_modification_original_data(modification_original_data)

        await self.apply()
