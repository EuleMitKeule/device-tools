"""Module for Device Tools class."""

import logging
from typing import TYPE_CHECKING

import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.entity_registry as er
from homeassistant.core import HomeAssistant

from custom_components.device_tools.device_modification_registry import (
    DeviceModificationRegistry,
)

from .models import (
    AttributeModification,
    DeviceModification,
    DeviceToolsHistoryData,
    EntityModification,
    MergeModification,
)


class DeviceTools:
    """Device Tools class.

    This class is responsible for applying and reverting device modifications for each config entry.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        device_modification_registry: DeviceModificationRegistry,
        device_tools_history_data: DeviceToolsHistoryData,
    ) -> None:
        """Initialize Device Tools."""
        self._hass = hass
        self._logger = logger
        self._device_modification_registry = device_modification_registry

        self._device_registry = dr.async_get(hass)
        self._entity_registry = er.async_get(hass)
        self._device_tools_history_data = device_tools_history_data

        self._device_modification_registry.register_callbacks(
            self._async_on_modification_added,
            self._async_on_modification_removed,
        )
        # self._run_task = hass.async_create_background_task(self.async_run(), DOMAIN)

    async def _async_on_modification_added(
        self, device_modification: DeviceModification
    ) -> None:
        """Handle device modification added."""
        device = self._device_registry.async_get(device_modification["device_id"])

        if device is None:
            self._logger.error(
                "[%s] Device not found (id: %s)",
                device_modification["device_name"],
                device_modification["device_id"],
            )
            return

        await self._async_apply(device, device_modification)

    async def _async_on_modification_removed(
        self, device_modification: DeviceModification
    ) -> None:
        """Handle device modification removed."""
        device = self._device_registry.async_get(device_modification["device_id"])

        if device is None:
            self._logger.error(
                "[%s] Device not found (id: %s)",
                device_modification["device_name"],
                device_modification["device_id"],
            )
            return

        await self._async_revert(device, device_modification)

    async def _async_apply(
        self, device: dr.DeviceEntry, device_modification: DeviceModification
    ) -> None:
        """Apply device modification."""
        await self._async_save_original_device_config(device)

        if device_modification["attribute_modification"] is not None:
            await self._async_apply_attribute_modification(
                device, device_modification["attribute_modification"]
            )

        if device_modification["entity_modification"] is not None:
            await self._async_apply_entity_modification(
                device, device_modification["entity_modification"]
            )

        # if device_modification["merge_modification"] is not None:
        #     await self._apply_merge_modification(
        #         device_modification["merge_modification"]
        #     )

    async def _async_revert(
        self, device: dr.DeviceEntry, device_modification: DeviceModification
    ) -> None:
        """Revert device modification."""
        if device_modification["attribute_modification"] is not None:
            await self._async_revert_attribute_modification(device)

        # if device_modification["entity_modification"] is not None:
        #     await self._revert_entity_modification(
        #         device_modification["entity_modification"]
        #     )

        # if device_modification["attribute_modification"] is not None:
        #     await self._revert_attribute_modification(
        #         device_modification["attribute_modification"]
        #     )

    ### Old code ###

    # async def async_run(self):
    #     """Run the background task."""
    #     while True:
    #         try:
    #             self.async_get_entries()
    #             await self.async_update()
    #         except Exception as e:  # pylint: disable=broad-except
    #             self._logger.exception(e)

    #         await asyncio.sleep(SCAN_INTERVAL)

    # async def async_update(self) -> None:
    #     """Update devices."""
    #     await self._async_revert()
    #     self._previous_device_modifications = deepcopy(self._device_modifications)

    #     if len(self._device_modifications) == 0:
    #         return

    #     await self._async_validate()

    #     for entry_id, device_modification in self._device_modifications.items():
    #         if TYPE_CHECKING:
    #             assert device_modification["device_id"] is not None

    #         device: DeviceEntry | None = self._device_registry.async_get(
    #             device_modification["device_id"]
    #         )

    #         if device is None:
    #             self._logger.error(
    #                 "[%s] Device not found (id: %s)",
    #                 device_modification["device_name"],
    #                 device_modification["device_id"],
    #             )
    #             continue

    #         await self._async_save_original_device_config(device.id)

    #         if device_modification["attribute_modification"] is not None:
    #             await self._async_apply_attribute_modification(
    #                 device, device_modification["attribute_modification"]
    #             )

    #         if device_modification["entity_modification"] is not None:
    #             await self._async_apply_entity_modification(
    #                 device, device_modification["entity_modification"]
    #             )

    #         if device_modification["merge_modification"] is not None:
    #             await self._async_apply_merge_modification(
    #                 device, device_modification["merge_modification"]
    #             )

    #         if entry_id not in device.config_entries:
    #             self._device_registry.async_update_device(
    #                 device.id,
    #                 add_config_entry_id=entry_id,
    #             )

    # async def _async_validate(self) -> None:
    #     """Validate device modifications."""
    #     validated_devices: set[str] = set()
    #     validated_device_modifications: dict[str, DeviceModification] = {}

    #     for entry_id, device_modification in self._device_modifications.items():
    #         device_id = device_modification["device_id"]
    #         device: DeviceEntry | None = None

    #         if device_id is None:
    #             device = self._device_registry.async_get_or_create(
    #                 config_entry_id=entry_id,
    #                 name=device_modification["device_name"],
    #                 identifiers={(DOMAIN, entry_id)},
    #             )
    #             device_modification["device_id"] = device.id
    #             device_id = device.id
    #         else:
    #             device = self._device_registry.async_get(device_id)

    #         if device is None:
    #             self._logger.error(
    #                 "[%s] Device not found (name: %s)",
    #                 device_modification["modification_name"],
    #                 device_modification["device_name"],
    #             )
    #             continue

    #         if device_id in validated_devices:
    #             self._logger.error(
    #                 "[%s] Device is already a parent device (id: %s)",
    #                 device_modification["modification_name"],
    #                 device_modification["device_id"],
    #             )
    #             continue

    #         if entry_id in validated_device_modifications:
    #             self._logger.error(
    #                 "[%s] Duplicate config entry (id: %s)",
    #                 device_modification["modification_name"],
    #                 entry_id,
    #             )

    #         config_entry = self._hass.config_entries.async_get_entry(entry_id)

    #         if config_entry is None:
    #             self._logger.error(
    #                 "[%s] Config entry not found (id: %s)",
    #                 device_modification["modification_name"],
    #                 entry_id,
    #             )
    #             continue

    #         validated_devices.add(device.id)
    #         validated_device_modifications[entry_id] = device_modification

    #         self._hass.config_entries.async_update_entry(
    #             config_entry,
    #             data={
    #                 **config_entry.data,
    #                 "device_modification": device_modification,
    #             },
    #         )

    #     await self._async_validate_device_modifications(validated_device_modifications)

    #     self._device_modifications = validated_device_modifications

    # async def _async_validate_device_modifications(
    #     self, device_modifications: dict[str, DeviceModification]
    # ) -> None:
    #     """Validate device modifications."""
    #     devices: set[str] = {
    #         device_modification["device_id"]
    #         for config_entry_id, device_modification in device_modifications.items()
    #         if device_modification["device_id"] is not None
    #     }

    #     entities: set[str] = set()
    #     merged_devices: set[str] = set()

    #     for device_modification in device_modifications.values():
    #         if device_modification["entity_modification"] is not None:
    #             unknown_entities: list[str] = []
    #             duplicate_entities: list[str] = []

    #             for entity_id in device_modification["entity_modification"]["entities"]:
    #                 entity = self._entity_registry.async_get(entity_id)

    #                 if entity is None:
    #                     self._logger.warning(
    #                         "[%s] Removing unknown entity (id: %s)",
    #                         device_modification["modification_name"],
    #                         entity_id,
    #                     )

    #                     unknown_entities.append(entity_id)
    #                     continue

    #                 if entity_id in entities:
    #                     self._logger.warning(
    #                         "[%s] Removing duplicate entity (id: %s)",
    #                         device_modification["modification_name"],
    #                         entity_id,
    #                     )

    #                     duplicate_entities.append(entity_id)
    #                     continue

    #                 entities.add(entity_id)

    #             for entity_id in unknown_entities + duplicate_entities:
    #                 device_modification["entity_modification"]["entities"].remove(
    #                     entity_id
    #                 )

    #         if device_modification["merge_modification"] is not None:
    #             unknown_devices: list[str] = []
    #             duplicate_devices: list[str] = []

    #             for merged_device_id in device_modification["merge_modification"][
    #                 "devices"
    #             ]:
    #                 merged_device = self._device_registry.async_get(merged_device_id)

    #                 if merged_device is None:
    #                     self._logger.warning(
    #                         "[%s] Removing unknown device (id: %s)",
    #                         device_modification["modification_name"],
    #                         merged_device_id,
    #                     )

    #                     unknown_devices.append(merged_device_id)
    #                     continue

    #                 if merged_device_id in merged_devices:
    #                     self._logger.warning(
    #                         "[%s] Removing duplicate device (id: %s)",
    #                         device_modification["modification_name"],
    #                         merged_device_id,
    #                     )

    #                     duplicate_devices.append(merged_device_id)
    #                     continue

    #                 if merged_device_id in devices:
    #                     self._logger.warning(
    #                         "[%s] Removing device that has a modification (id: %s)",
    #                         device_modification["modification_name"],
    #                         merged_device_id,
    #                     )

    #                     merged_devices.add(merged_device_id)
    #                     continue

    #                 merged_devices.add(merged_device_id)

    #             for merged_device_id in unknown_devices + duplicate_devices:
    #                 device_modification["merge_modification"]["devices"].remove(
    #                     merged_device_id
    #                 )

    async def _async_save_original_device_config(self, device: dr.DeviceEntry) -> None:
        """Save original device config."""
        if device.id in self._device_tools_history_data.original_device_configs:
            return

        self._device_tools_history_data.original_device_configs[device.id] = {
            "manufacturer": device.manufacturer,
            "model": device.model,
            "sw_version": device.sw_version,
            "hw_version": device.hw_version,
            "serial_number": device.serial_number,
            "via_device_id": device.via_device_id,
            "config_entries": device.config_entries,
            "config_entries_set_by_device_tools": set(),
        }

    async def _async_save_original_entity_config(
        self, entity: er.RegistryEntry
    ) -> None:
        """Save original entity config."""
        if entity.id in self._device_tools_history_data.original_entity_configs:
            return

        self._device_tools_history_data.original_entity_configs[entity.id] = {
            "device_id": entity.device_id,
        }

    # async def _async_add_config_entry(self, device_id: str, config_entry_id: str):
    #     """Add config entry for device."""
    #     await self._async_save_original_device_config(device_id)

    #     original_device_config = self._device_tools_history_data[
    #         "original_device_configs"
    #     ].get(device_id)

    #     if TYPE_CHECKING:
    #         assert original_device_config is not None

    #     original_device_config["config_entries_set_by_device_tools"].add(
    #         config_entry_id
    #     )

    #     self._device_registry.async_update_device(
    #         device_id,
    #         add_config_entry_id=config_entry_id,
    #     )

    # async def _async_revert(self) -> None:
    #     """Revert removed modifications."""
    #     for (
    #         entry_id,
    #         device_modification,
    #     ) in self._previous_device_modifications.items():
    #         if entry_id in self._device_modifications:
    #             continue

    #         device_id: str | None = device_modification["device_id"]

    #         if TYPE_CHECKING:
    #             assert device_id is not None

    #         await self._async_revert_device(device_id)

    #         entities = dr.async_entries_for_device(
    #             self._entity_registry,
    #             device_id,
    #             include_disabled_entities=True,
    #         )

    #         for entity in entities:
    #             await self._async_revert_entity(entity.id)

    #             if entity.id in self._device_tools_data["original_entity_configs"]:
    #                 del self._device_tools_data["original_entity_configs"][entity.id]

    #         if device_id in self._device_tools_data["original_device_configs"]:
    #             del self._device_tools_data["original_device_configs"][device_id]

    # async def _async_revert_entity(self, entity_id: str) -> None:
    #     """Revert entity modifications."""
    #     entity = self._entity_registry.async_get(entity_id)

    #     if entity is None:
    #         raise HomeAssistantError(f"Entity not found (id: {entity_id})")

    #     original_entity_config = self._device_tools_history_data[
    #         "original_entity_configs"
    #     ].get(entity_id)

    #     if original_entity_config is None:
    #         return

    #     self._entity_registry.async_update_entity(
    #         entity.entity_id, device_id=original_entity_config["device_id"]
    #     )

    # async def _async_revert_device(self, device_id: str) -> None:
    #     """Revert device modifications."""
    #     device: dr.DeviceEntry | None = self._device_registry.async_get(device_id)

    #     if device is None:
    #         raise HomeAssistantError(f"Device not found (id: {device_id})")

    #     original_device_config = self._device_tools_history_data[
    #         "original_device_configs"
    #     ].get(device_id)

    #     if original_device_config is None:
    #         self._logger.warning(
    #             "[%s] Original device config not found (id: %s)",
    #         )
    #         return

    #     self._device_registry.async_update_device(
    #         device.id,
    #         manufacturer=original_device_config["manufacturer"],
    #         model=original_device_config["model"],
    #         sw_version=original_device_config["sw_version"],
    #         hw_version=original_device_config["hw_version"],
    #         serial_number=original_device_config["serial_number"],
    #         via_device_id=original_device_config["via_device_id"],
    #     )

    #     for config_entry_id in original_device_config["config_entries"]:
    #         if config_entry_id not in device.config_entries:
    #             self._device_registry.async_update_device(
    #                 device.id,
    #                 add_config_entry_id=config_entry_id,
    #             )

    #     for config_entry_id in device.config_entries:
    #         if (
    #             config_entry_id
    #             in original_device_config["config_entries_set_by_device_tools"]
    #             and config_entry_id not in original_device_config["config_entries"]
    #         ):
    #             self._device_registry.async_update_device(
    #                 device.id,
    #                 remove_config_entry_id=config_entry_id,
    #             )

    async def _async_apply_attribute_modification(
        self, device: dr.DeviceEntry, attribute_modification: AttributeModification
    ) -> None:
        """Apply an attribute modification."""
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

    async def _async_revert_attribute_modification(
        self, device: dr.DeviceEntry
    ) -> None:
        """Revert an attribute modification."""
        original_device_config = (
            self._device_tools_history_data.original_device_configs.get(device.id)
        )

        if original_device_config is None:
            self._logger.error(
                "[%s] Original device config not found (id: %s)",
            )
            return

        self._device_registry.async_update_device(
            device.id,
            manufacturer=original_device_config["manufacturer"],
            model=original_device_config["model"],
            sw_version=original_device_config["sw_version"],
            hw_version=original_device_config["hw_version"],
            serial_number=original_device_config["serial_number"],
            via_device_id=original_device_config["via_device_id"],
        )

    async def _async_apply_entity_modification(
        self, device: dr.DeviceEntry, entity_modification: EntityModification
    ) -> None:
        """Apply an entity modification."""
        entities = [
            self._entity_registry.async_get(entity_uuid)
            for entity_uuid in entity_modification["entities"]
        ]

        for entity in entities:
            if TYPE_CHECKING:
                assert entity is not None

            await self._async_save_original_entity_config(entity)

            self._entity_registry.async_update_entity(
                entity.entity_id, device_id=device.id
            )

    async def _async_revert_entity_modification(
        self, entity_modification: EntityModification
    ) -> None:
        """Revert an entity modification."""

    async def _async_apply_merge_modification(
        self, device: dr.DeviceEntry, merge_modification: MergeModification
    ) -> None:
        """Apply merge modification to a device."""
        devices: dict[str, dr.DeviceEntry | None] = {
            device_id: self._device_registry.async_get(device_id)
            for device_id in merge_modification["devices"]
        }

        for source_device_id, source_device in devices.items():
            if source_device is None:
                self._logger.error(
                    "[%s] Device not found (id: %s)",
                    device.name,
                    source_device_id,
                )
                continue

            await self._async_save_original_device_config(source_device.id)

            entities = dr.async_entries_for_device(
                self._entity_registry,
                source_device.id,
                include_disabled_entities=True,
            )

            for entity in entities:
                await self._async_save_original_entity_config(entity.id)

                self._entity_registry.async_update_entity(
                    entity.entity_id, device_id=device.id
                )

            source_config_entries = source_device.config_entries

            for source_config_entry in source_config_entries:
                await self._async_add_config_entry(device.id, source_config_entry)
