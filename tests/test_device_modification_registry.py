import pytest

from custom_components.device_tools.device_modification_registry import (
    DeviceModificationRegistry,
)
from custom_components.device_tools.models import DeviceModification


@pytest.fixture(scope="function")
def mock_registry():
    return DeviceModificationRegistry()


@pytest.fixture(scope="function")
def mock_device_modification():
    return DeviceModification(device_id="device_1", modification_data={"key": "value"})


async def test_add_entry(
    mock_registry: DeviceModificationRegistry,
    mock_device_modification: DeviceModification,
):
    await mock_registry.add_entry("entry_1", mock_device_modification)
    assert "entry_1" in mock_registry._device_modifications
    assert mock_registry._device_modifications["entry_1"] == mock_device_modification


async def test_add_entry_duplicate(
    mock_registry: DeviceModificationRegistry,
    mock_device_modification: DeviceModification,
):
    await mock_registry.add_entry("entry_1", mock_device_modification)
    with pytest.raises(
        ValueError, match="Device modification with entry_id entry_1 already exists"
    ):
        await mock_registry.add_entry("entry_1", mock_device_modification)


async def test_remove_entry(
    mock_registry: DeviceModificationRegistry,
    mock_device_modification: DeviceModification,
):
    await mock_registry.add_entry("entry_1", mock_device_modification)
    await mock_registry.remove_entry("entry_1")
    assert "entry_1" not in mock_registry._device_modifications


async def test_remove_entry_nonexistent(mock_registry):
    with pytest.raises(
        ValueError, match="Device modification with entry_id entry_1 does not exist"
    ):
        await mock_registry.remove_entry("entry_1")


async def test_register_callbacks(
    mock_registry: DeviceModificationRegistry,
    mock_device_modification: DeviceModification,
):
    async def added_callback(modification):
        assert modification == mock_device_modification

    async def removed_callback(modification):
        assert modification == mock_device_modification

    mock_registry.register_callbacks(added_callback, removed_callback)
    await mock_registry.add_entry("entry_1", mock_device_modification)
    await mock_registry.remove_entry("entry_1")


def test_get_modifications_for_device(
    mock_registry: DeviceModificationRegistry,
    mock_device_modification: DeviceModification,
):
    mock_registry._device_modifications["entry_1"] = mock_device_modification
    modification = mock_registry.get_modification_for_device("device_1")
    assert modification == mock_device_modification


async def test_add_entry_device_id_duplicate(
    mock_registry: DeviceModificationRegistry,
    mock_device_modification: DeviceModification,
):
    await mock_registry.add_entry("entry_1", mock_device_modification)
    duplicate_device_modification = DeviceModification(
        device_id="device_1", modification_data={"key": "new_value"}
    )
    with pytest.raises(
        ValueError, match="Device modification for device_id device_1 already exists"
    ):
        await mock_registry.add_entry("entry_2", duplicate_device_modification)
