"""Listener for entity registry updates."""

from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import entity_registry as er

from .listener import Listener


class EntityListener(Listener[er.RegistryEntry, er.EventEntityRegistryUpdatedData]):
    """Entity listener.

    Listens for entity registry updates and notifies listeners.
    """

    def __init__(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the entity listener."""
        super().__init__(hass)
        self._entity_registry = er.async_get(hass)

        self._hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED, self._async_on_entity_registry_updated
        )

    async def _async_on_entity_registry_updated(
        self, event: Event[er.EventEntityRegistryUpdatedData]
    ) -> None:
        """Handle entity registry updated."""
        entity_id = event.data["entity_id"]
        entity = self._entity_registry.async_get(entity_id)

        if entity is None:
            return

        for callback in self._callbacks[entity_id]:
            await callback(entity, event)
