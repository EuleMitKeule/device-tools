"""Tests for the device_tools module."""

from unittest.mock import MagicMock

from custom_components.device_tools.device_tools import DeviceTools


def test_init() -> None:
    hass = MagicMock()
    logger = MagicMock()

    device_tools = DeviceTools(hass, logger)

    assert device_tools._hass == hass


# @pytest.mark.asyncio
# async def test_attributes(
#     mock_device_info_factory: Callable[[], DeviceInfo],
#     mock_entity_maker: Callable[[DeviceInfo], MockEntity],
# ) -> None:
#     device_info = mock_device_info_factory()
#     entity = mock_entity_maker(device_info)

#     assert entity.device_info == device_info
#     assert entity.device_info.name == device_info.name
#     assert entity.device_info.model == device_info.model
#     assert entity.device_info.manufacturer == device_info.manufacturer
