"""Module containing the device listener for the device-tools integration."""

from collections import defaultdict
from typing import Awaitable, Callable

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr


class DeviceListener:
    """Device listener.

    Listens for device registry updates and applies device modifications.
    """

    def __init__(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the device listener."""
        self._hass = hass
        self._device_registry = dr.async_get(hass)
        self._callbacks: defaultdict[
            str,
            list[
                Callable[
                    [dr.DeviceEntry, Event[dr.EventDeviceRegistryUpdatedData]],
                    Awaitable[None],
                ]
            ],
        ] = defaultdict(list)
        self._ignored_callbacks: defaultdict[
            str,
            list[
                Callable[
                    [dr.DeviceEntry, Event[dr.EventDeviceRegistryUpdatedData]],
                    Awaitable[None],
                ]
            ],
        ] = defaultdict(list)

        self._hass.bus.async_listen(
            dr.EVENT_DEVICE_REGISTRY_UPDATED, self._async_on_device_registry_updated
        )

    def register_callback(
        self,
        device_id: str,
        callback: Callable[
            [dr.DeviceEntry, Event[dr.EventDeviceRegistryUpdatedData]], Awaitable[None]
        ],
    ) -> None:
        """Register a callback for when a device is updated."""
        if callback not in self._callbacks[device_id]:
            self._callbacks[device_id].append(callback)

    def unregister_callback(
        self,
        device_id: str,
        callback: Callable[
            [dr.DeviceEntry, Event[dr.EventDeviceRegistryUpdatedData]], Awaitable[None]
        ],
    ) -> None:
        """Unregister a callback for when a device is updated."""
        if callback in self._callbacks[device_id]:
            self._callbacks[device_id].remove(callback)

    def ignore_next_update(
        self,
        device_id: str,
        callback: Callable[
            [dr.DeviceEntry, Event[dr.EventDeviceRegistryUpdatedData]], Awaitable[None]
        ],
    ) -> None:
        """Ignore the next update for a device."""
        if callback not in self._ignored_callbacks[device_id]:
            self._ignored_callbacks[device_id].append(callback)

    @callback
    async def _async_on_device_registry_updated(
        self, event: Event[dr.EventDeviceRegistryUpdatedData]
    ) -> None:
        """Handle device registry updated."""
        device_id = event.data["device_id"]
        device = self._device_registry.async_get(device_id)

        for callback in self._callbacks[device_id]:
            if callback in self._ignored_callbacks[device_id]:
                self._ignored_callbacks[device_id].remove(callback)
                continue

            await callback(device, event)
