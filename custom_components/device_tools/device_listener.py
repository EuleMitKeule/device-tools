"""Listener for device registry updates."""

import asyncio

from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr

from .listener import Listener


class DeviceListener(Listener[dr.DeviceEntry, dr.EventDeviceRegistryUpdatedData]):
    """Device listener.

    Listens for device registry updates and notifies listeners.
    """

    def __init__(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the device listener."""
        super().__init__(hass)
        self._device_registry = dr.async_get(hass)

        self._hass.bus.async_listen(
            dr.EVENT_DEVICE_REGISTRY_UPDATED, self._async_on_device_registry_updated
        )

    async def _async_on_device_registry_updated(
        self, event: Event[dr.EventDeviceRegistryUpdatedData]
    ) -> None:
        """Handle device registry updated."""
        device_id = event.data["device_id"]
        device = self._device_registry.async_get(device_id)

        if device is None:
            return

        for callback in self._callbacks[device_id]:
            if asyncio.iscoroutinefunction(callback):
                await callback(device, event)
            else:
                callback(device, event)
