import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import (
    DeviceEntry,
)
from homeassistant.helpers.device_registry import (
    async_get as async_get_device_registry,
)

from .const import DOMAIN, SCAN_INTERVAL, ModificationType
from .models.attribute_modification import AttributeModification
from .models.config_entry_data import DeviceToolsConfigEntryData
from .models.device_modification import DeviceModification


class DeviceTools:
    def __init__(self, hass: HomeAssistant, logger: logging.Logger) -> None:
        self._hass = hass
        self._logger = logger
        self._device_registry = async_get_device_registry(hass)
        self._run_task = hass.async_create_background_task(self.async_run(), DOMAIN)
        self._device_modifications: list[DeviceModification] = []

    @callback
    def async_on_entries_changed(self) -> None:
        config_entries = self._hass.config_entries.async_entries(DOMAIN)
        config_entry_datas: list[DeviceToolsConfigEntryData] = [
            config_entry.data for config_entry in config_entries
        ]

        self._device_modifications = [
            config_entry_data["device_modification"]
            for config_entry_data in config_entry_datas
        ]

    @callback
    async def async_run(self):
        """Run the background task."""

        while True:
            try:
                self.async_on_entries_changed()
                await self.async_update()
            except Exception as e:  # pylint: disable=broad-except
                self._logger.error("Error during update: %s", e)

            await asyncio.sleep(SCAN_INTERVAL)

    @callback
    async def async_update(self) -> None:
        """Update devices."""

        if len(self._device_modifications) == 0:
            return

        for device_modification in self._device_modifications:
            device = self._device_registry.async_get(device_modification["device_id"])

            if device is None:
                self._logger.error(
                    "[%s] Device not found (id: %s)",
                    device_modification["device_name"],
                    device_modification["device_id"],
                )
                continue

            match device_modification["modification_type"]:
                case ModificationType.ATTRIBUTES:
                    await self._async_apply_attribute_modification(
                        device, device_modification
                    )
                case _:
                    self._logger.error(
                        "[%s] Unknown modification type: %s",
                        device_modification["device_name"],
                        type(device_modification),
                    )

        await asyncio.sleep(1)

    async def _async_apply_attribute_modification(
        self, device: DeviceEntry, attribute_modification: AttributeModification
    ) -> None:
        """Apply attribute modification to a device."""
        has_differences: bool = False

        if (
            attribute_modification["manufacturer"] is not None
            and device.manufacturer != attribute_modification["manufacturer"]
        ):
            has_differences = True
        if (
            attribute_modification["model"] is not None
            and device.model != attribute_modification["model"]
        ):
            has_differences = True
        if (
            attribute_modification["sw_version"] is not None
            and device.sw_version != attribute_modification["sw_version"]
        ):
            has_differences = True
        if (
            attribute_modification["hw_version"] is not None
            and device.hw_version != attribute_modification["hw_version"]
        ):
            has_differences = True
        if (
            attribute_modification["via_device"] is not None
            and device.via_device != attribute_modification["via_device"]
        ):
            has_differences = True
        if (
            attribute_modification["connections"] is not None
            and device.connections != attribute_modification["connections"]
        ):
            has_differences = True

        if not has_differences:
            return

        args: dict[str, Any] = {}

        if attribute_modification["manufacturer"] is not None:
            args["manufacturer"] = attribute_modification["manufacturer"]
        if attribute_modification["model"] is not None:
            args["model"] = attribute_modification["model"]
        if attribute_modification["sw_version"] is not None:
            args["sw_version"] = attribute_modification["sw_version"]
        if attribute_modification["hw_version"] is not None:
            args["hw_version"] = attribute_modification["hw_version"]
        if attribute_modification["via_device"] is not None:
            args["via_device"] = attribute_modification["via_device"]
        if attribute_modification["connections"] is not None:
            args["merge_connections"] = attribute_modification["connections"]

        self._device_registry.async_update_device(
            device.id,
            **args,
        )
