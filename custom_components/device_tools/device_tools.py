import asyncio
import logging

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import (
    DeviceEntry,
)
from homeassistant.helpers.device_registry import (
    async_get as async_get_device_registry,
)
from homeassistant.helpers.entity_registry import (
    async_get as async_get_entity_registry,
)

from .const import DOMAIN, SCAN_INTERVAL
from .models import AttributeModification, DeviceModification, EntityModification


class DeviceTools:
    """Device Tools class."""

    def __init__(self, hass: HomeAssistant, logger: logging.Logger) -> None:
        """Initialize."""

        self._hass = hass
        self._logger = logger
        self._device_registry = async_get_device_registry(hass)
        self._entity_registry = async_get_entity_registry(hass)
        self._run_task = hass.async_create_background_task(self.async_run(), DOMAIN)
        self._device_modifications: dict[str, DeviceModification] = {}

    @callback
    def async_get_entries(self) -> None:
        """Handle config entry changes."""

        config_entries = self._hass.config_entries.async_entries(DOMAIN)

        self._device_modifications = {
            config_entry.entry_id: config_entry.data["device_modification"]
            for config_entry in config_entries
            if config_entry.state == ConfigEntryState.LOADED
        }

    @callback
    async def async_run(self):
        """Run the background task."""

        while True:
            try:
                self.async_get_entries()
                await self.async_update()
            except Exception as e:  # pylint: disable=broad-except
                self._logger.exception(e)

            await asyncio.sleep(SCAN_INTERVAL)

    @callback
    async def async_update(self) -> None:
        """Update devices."""

        if len(self._device_modifications) == 0:
            return

        for entry_id, device_modification in self._device_modifications.items():
            device_id = device_modification["device_id"]
            device: DeviceEntry | None = None

            if device_id is None:
                device = self._device_registry.async_get_or_create(
                    config_entry_id=entry_id,
                    name=device_modification["device_name"],
                    identifiers={(DOMAIN, entry_id)},
                )
                device_modification["device_id"] = device.id
            else:
                device = self._device_registry.async_get(device_id)

            if device is None:
                self._logger.error(
                    "[%s] Device not found (id: %s)",
                    device_modification["device_name"],
                    device_modification["device_id"],
                )
                continue

            if device_modification["attribute_modification"] is not None:
                await self._async_apply_attribute_modification(
                    device, device_modification["attribute_modification"]
                )

            if device_modification["entity_modification"] is not None:
                await self._async_apply_entity_modification(
                    device, device_modification["entity_modification"]
                )

            self._device_registry.async_update_device(
                device.id,
                add_config_entry_id=entry_id,
            )

    async def _async_apply_attribute_modification(
        self, device: DeviceEntry, attribute_modification: AttributeModification
    ) -> None:
        """Apply attribute modification to a device."""

        manufacturer: str | None = attribute_modification.get("manufacturer")
        model: str | None = attribute_modification.get("model")
        sw_version: str | None = attribute_modification.get("sw_version")
        hw_version: str | None = attribute_modification.get("hw_version")
        serial_number: str | None = attribute_modification.get("serial_number")
        via_device_id: str | None = attribute_modification.get("via_device_id")

        self._device_registry.async_update_device(
            device.id,
            manufacturer=manufacturer,
            model=model,
            sw_version=sw_version,
            hw_version=hw_version,
            serial_number=serial_number,
            via_device_id=via_device_id,
        )

        self._device_registry.async_update_device(device.id)

    async def _async_apply_entity_modification(
        self, device: DeviceEntry, entity_modification: EntityModification
    ) -> None:
        """Apply entity modification to a device."""

        entities = [
            self._entity_registry.async_get(entity_id)
            for entity_id in entity_modification["entities"]
        ]

        for entity in entities:
            if entity is None:
                self._logger.error(
                    "[%s] Entity not found (id: %s)",
                    device.name,
                    entity_modification["entities"],
                )
                continue

            if entity.device_id == device.id:
                continue

            self._entity_registry.async_update_entity(
                entity.entity_id, device_id=device.id
            )
