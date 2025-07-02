"""Listener for device and entity registry updates."""

from abc import ABC
from collections import defaultdict
from collections.abc import Awaitable, Callable

from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er


class Listener[
    TEntry: (dr.DeviceEntry | er.RegistryEntry),
    TEventData: (dr.EventDeviceRegistryUpdatedData | er.EventEntityRegistryUpdatedData),
](ABC):
    """Listener for device and entity registry updates.

    Listens for device and entity registry updates and notifies listeners.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the listener."""
        self._hass = hass
        self._callbacks: defaultdict[
            str,
            list[
                Callable[
                    [TEntry, Event[TEventData]],
                    Awaitable[None],
                ]
            ],
        ] = defaultdict(list)

    def register_callback(
        self,
        entry_id: str,
        callback: Callable[[TEntry, Event[TEventData]], Awaitable[None]],
    ) -> None:
        """Register a callback for when an entry is updated."""
        if callback not in self._callbacks[entry_id]:
            self._callbacks[entry_id].append(callback)

    def unregister_callback(
        self,
        entry_id: str,
        callback: Callable[[TEntry, Event[TEventData]], Awaitable[None]],
    ) -> None:
        """Unregister a callback for when an entry is updated."""
        if callback in self._callbacks[entry_id]:
            self._callbacks[entry_id].remove(callback)
