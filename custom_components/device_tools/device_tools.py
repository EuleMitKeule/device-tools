"""Module for Device Tools class."""

import logging

import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.entity_registry as er
from homeassistant.core import Event, HomeAssistant

from custom_components.device_tools.device_listener import DeviceListener
from custom_components.device_tools.device_modification_registry import (
    DeviceModificationRegistry,
)

from .models import (
    AttributeModification,
    DeviceModification,
    DeviceToolsHistoryData,
)

_LOGGER = logging.getLogger(__name__)


class DeviceTools:
    """Device Tools class.

    This class is responsible for applying and reverting device modifications for each config entry.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_modification_registry: DeviceModificationRegistry,
        device_tools_history_data: DeviceToolsHistoryData,
        device_listener: DeviceListener,
    ) -> None:
        """Initialize Device Tools."""
        self._hass = hass
        self._device_modification_registry = device_modification_registry
        self._device_tools_history_data = device_tools_history_data
        self._device_listener = device_listener

        self._device_registry = dr.async_get(hass)
        self._entity_registry = er.async_get(hass)

        self._device_modification_registry.register_callbacks(
            self._async_on_modification_added,
            self._async_on_modification_removed,
        )

    async def _async_on_modification_added(
        self, device_modification: DeviceModification
    ) -> None:
        """Handle device modification added."""
        await self._async_apply(device_modification)

    async def _async_on_modification_removed(
        self, device_modification: DeviceModification
    ) -> None:
        """Handle device modification removed."""
        await self._async_revert(device_modification)

    async def _async_on_device_updated(
        self, device: dr.DeviceEntry, _event: Event[dr.EventDeviceRegistryUpdatedData]
    ) -> None:
        """Handle device registry updated."""
        relevant_modification = (
            self._device_modification_registry.get_modification_for_device(device.id)
        )

        device_info_by_integration = device.dict_repr

        if relevant_modification and (
            attribute_modification := relevant_modification["attribute_modification"]
        ):
            for attribute, value in attribute_modification.items():
                if device_info_by_integration.get(attribute) == value:
                    device_info_by_integration.pop(attribute)

        self._device_tools_history_data.update_attribute_history(
            device.id, device_info_by_integration
        )

        if not relevant_modification:
            return

        await self._async_apply(relevant_modification)

    async def _async_apply(self, device_modification: DeviceModification) -> None:
        """Apply device modification."""
        device = self._device_registry.async_get(device_modification["device_id"])

        if device is None:
            _LOGGER.error(
                "[%s] Device not found (id: %s)",
                device_modification["device_name"],
                device_modification["device_id"],
            )
            return

        self._device_tools_history_data.update_attribute_history(
            device.id, device.dict_repr
        )

        self._device_listener.unregister_callback(
            device.id, self._async_on_device_updated
        )

        if device_modification["attribute_modification"] is not None:
            await self._async_apply_attribute_modification(
                device, device_modification["attribute_modification"]
            )

        self._device_listener.register_callback(
            device.id, self._async_on_device_updated
        )

    async def _async_revert(self, device_modification: DeviceModification) -> None:
        """Revert device modification."""
        device = self._device_registry.async_get(device_modification["device_id"])

        if device is None:
            _LOGGER.error(
                "[%s] Device not found (id: %s)",
                device_modification["device_name"],
                device_modification["device_id"],
            )
            return

        self._device_listener.unregister_callback(
            device.id, self._async_on_device_updated
        )

        if device_modification["attribute_modification"] is not None:
            await self._async_revert_attribute_modification(device)

    async def _async_apply_attribute_modification(
        self, device: dr.DeviceEntry, attribute_modification: AttributeModification
    ) -> None:
        """Apply an attribute modification."""
        self._device_registry.async_update_device(
            device.id,
            **attribute_modification,
        )

    async def _async_revert_attribute_modification(
        self, device: dr.DeviceEntry
    ) -> None:
        """Revert an attribute modification."""
        if device.id not in self._device_tools_history_data.device_attribute_history:
            _LOGGER.error(
                "[%s] Original device attributes not found (id: %s)",
            )
            return

        self._device_registry.async_update_device(
            device.id,
            **self._device_tools_history_data.device_attribute_history[device.id],
        )
