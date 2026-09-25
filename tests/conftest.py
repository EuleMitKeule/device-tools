"""Fixtures for Device Tools tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.device_tools.const import (
    CONF_MODIFICATION_DATA,
    CONF_MODIFICATION_ENTRY_ID,
    CONF_MODIFICATION_ENTRY_NAME,
    CONF_MODIFICATION_IS_CUSTOM_ENTRY,
    CONF_MODIFICATION_ORIGINAL_DATA,
    CONF_MODIFICATION_TYPE,
    DOMAIN,
    ModificationType,
)

SOURCE_DOMAIN = "test"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Enable custom integrations in all tests."""
    return


@pytest.fixture
def source_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return the config entry of an integration providing devices and entities."""
    config_entry = MockConfigEntry(domain=SOURCE_DOMAIN, title="Source")
    config_entry.add_to_hass(hass)
    return config_entry


def create_device(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    identifier: str,
    **kwargs: Any,
) -> dr.DeviceEntry:
    """Create or update a device as an integration would."""
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(SOURCE_DOMAIN, identifier)},
        **{"name": identifier, **kwargs},
    )


def create_entity(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    unique_id: str,
    device: dr.DeviceEntry | None = None,
    **kwargs: Any,
) -> er.RegistryEntry:
    """Create or update an entity as an integration would."""
    return er.async_get(hass).async_get_or_create(
        "sensor",
        SOURCE_DOMAIN,
        unique_id,
        config_entry=config_entry,
        device_id=device.id if device is not None else None,
        **kwargs,
    )


def modification_entry(
    modification_type: ModificationType,
    modification_entry_id: str,
    modification_data: dict[str, Any] | None = None,
    *,
    original_data: dict[str, Any] | None = None,
    is_custom_entry: bool = False,
    name: str = "Test",
) -> MockConfigEntry:
    """Return the config entry of a modification."""
    return MockConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=1,
        title=f"{modification_type.friendly_name}: {name}",
        unique_id=f"{modification_type}_{modification_entry_id}",
        data={
            CONF_MODIFICATION_TYPE: modification_type,
            CONF_MODIFICATION_ENTRY_ID: modification_entry_id,
            CONF_MODIFICATION_ENTRY_NAME: name,
            CONF_MODIFICATION_IS_CUSTOM_ENTRY: is_custom_entry,
            CONF_MODIFICATION_ORIGINAL_DATA: original_data or {},
        },
        options={CONF_MODIFICATION_DATA: modification_data or {}},
    )


async def setup_entry(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Add and set up a config entry."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def update_options(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    modification_data: dict[str, Any],
) -> None:
    """Change the modification data of a config entry."""
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_MODIFICATION_DATA: modification_data}
    )
    await hass.async_block_till_done()
