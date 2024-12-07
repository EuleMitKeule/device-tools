import uuid
from typing import Any, Callable, Dict, Optional, Union

import pytest
from homeassistant.helpers.device_registry import DeviceInfo
from pytest_homeassistant_custom_component.common import MockEntity

DeviceInfoType = Union[None, str, Dict[str, Any], DeviceInfo]


@pytest.fixture
def random_device_info_factory() -> Callable[[], DeviceInfo]:
    """Return a factory function that creates a random DeviceInfo.

    Returns:
        Callable[[], DeviceInfo]: A callable that returns a random DeviceInfo.
    """

    def create_random_device_info() -> DeviceInfo:
        """Create a random DeviceInfo.

        Returns:
            DeviceInfo: A random DeviceInfo instance.
        """
        return DeviceInfo(
            identifiers={(str(uuid.uuid4()), str(uuid.uuid4()))},
            name=f"Device {uuid.uuid4()}",
            model=f"Model {uuid.uuid4()}",
            manufacturer=f"Manufacturer {uuid.uuid4()}",
            sw_version=f"Version {uuid.uuid4()}",
        )

    return create_random_device_info


@pytest.fixture
def mock_entity_maker() -> Callable[[Optional[DeviceInfoType]], MockEntity]:
    """Return a factory function that creates mock entities.

    This factory can handle:
    - device_info=None for no device info
    - device_info="random" for random device info
    - device_info=dict(...) for specified device info
    - device_info=DeviceInfo instance for a given device info

    Returns:
        Callable[[Optional[DeviceInfoType]], MockEntity]: A callable that returns a MockEntity.
    """

    def create_mock_entity(device_info: Optional[DeviceInfoType] = None) -> MockEntity:
        """Create a MockEntity.

        Args:
            device_info (Optional[DeviceInfoType]): Device info configuration.

        Returns:
            MockEntity: A mock entity instance.
        """
        if device_info == "random":
            device_info = DeviceInfo(
                identifiers={(str(uuid.uuid4()), str(uuid.uuid4()))},
                name=f"Device {uuid.uuid4()}",
                model=f"Model {uuid.uuid4()}",
                manufacturer=f"Manufacturer {uuid.uuid4()}",
                sw_version=f"Version {uuid.uuid4()}",
            )
        elif isinstance(device_info, dict):
            device_info = DeviceInfo(**device_info)
        elif not (device_info is None or isinstance(device_info, DeviceInfo)):
            raise ValueError(
                "device_info must be None, 'random', a dict, or a DeviceInfo instance."
            )

        return MockEntity(device_info=device_info)

    return create_mock_entity
