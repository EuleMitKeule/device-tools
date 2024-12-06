"""Tests for the device_tools module."""

from unittest.mock import MagicMock

from custom_components.device_tools.device_tools import DeviceTools


def test_init() -> None:
    hass = MagicMock()
    logger = MagicMock()

    device_tools = DeviceTools(hass, logger)

    assert device_tools._hass == hass
