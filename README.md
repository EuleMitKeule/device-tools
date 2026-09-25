[![My Home Assistant](https://img.shields.io/badge/Home%20Assistant-%2341BDF5.svg?style=flat&logo=home-assistant&label=My)](https://my.home-assistant.io/redirect/hacs_repository/?owner=EuleMitKeule&repository=device-tools&category=integration)

![GitHub License](https://img.shields.io/github/license/eulemitkeule/device-tools)
![GitHub Sponsors](https://img.shields.io/github/sponsors/eulemitkeule?logo=GitHub-Sponsors)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=EuleMitKeule_device-tools&metric=coverage)](https://sonarcloud.io/summary/new_code?id=EuleMitKeule_device-tools)

[![Code Quality](https://github.com/EuleMitKeule/device-tools/actions/workflows/quality.yml/badge.svg)](https://github.com/EuleMitKeule/device-tools/actions/workflows/quality.yml)
[![Bugs](https://sonarcloud.io/api/project_badges/measure?project=EuleMitKeule_device-tools&metric=bugs)](https://sonarcloud.io/summary/new_code?id=EuleMitKeule_device-tools)
[![Code Smells](https://sonarcloud.io/api/project_badges/measure?project=EuleMitKeule_device-tools&metric=code_smells)](https://sonarcloud.io/summary/new_code?id=EuleMitKeule_device-tools)

# Device Tools for Home Assistant

A custom integration to change devices and entities that other integrations provide:

* Change device attributes like manufacturer, model or firmware version
* Assign entities to any device, e.g. template sensors or helpers to the device they describe
* Create new devices and assign entities to them
* Merge devices by moving all entities of several devices to one device
* Change the device and category of single entities

Every change is reverted as soon as you delete or disable the modification.

> [!CAUTION]
> Device Tools changes the device and entity registries of Home Assistant. Make a backup before installing or updating it.

## Requirements

Home Assistant 2026.9 or newer.

## Installation

1. Install [HACS](https://hacs.xyz/).
2. Click the badge at the top of this page or search for *Device Tools* in HACS and download it.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration** and add *Device Tools*.

Every modification is a separate entry of the Device Tools integration. Add another entry to create another modification.

## Modifications

When adding an entry, choose what you want to do.

### Change a device

Select a device, then change any of its attributes:

| Attribute | Description |
| --- | --- |
| Manufacturer, model, model ID | Shown on the device page |
| Software and hardware version | Shown on the device page |
| Serial number | Shown on the device page |
| Connected via | The device this device is connected through, e.g. a hub |
| Configuration URL | The link to configure the device, must start with `http://`, `https://` or `homeassistant://` |
| Entry type | Choose *Service* for things that are not physical devices |

Fields are prefilled with the current values. Only fields you change are modified. Clearing a field or setting it back to its original value stops modifying it.

Below the attributes you can assign entities of other devices, or entities without a device, to this device. Removing an entity from the list moves it back to its original device.

### Create a device

Creates a new device with the name you enter. Everything else works like changing a device, so you can set its attributes and assign entities to it. This is useful for entities without a device, e.g. from Modbus, MQTT, templates or helpers.

The device is removed together with the modification. Other modifications referencing it are updated accordingly.

### Change an entity

Select an entity to change its device or its entity category. Configuration and diagnostic entities are shown in separate sections of the device page.

### Merge devices

Select a device and the devices to merge into it. All entities of the merged devices are moved to the device, including entities the integration adds to them later. The merged devices themselves are kept, since Home Assistant does not allow removing devices of other integrations. Removing a device from the list moves its entities back.

### Editing a modification

Click **Configure** on a modification to edit it. The device or entity it changes is shown at the bottom of the dialog.

## How it works

Device Tools remembers the original value of everything it changes. Integrations often update their devices and entities, e.g. on every restart or after a firmware update. Device Tools notices these updates, remembers the new value as the original value and applies your modification again. When you delete or disable a modification, the latest original values are restored.

If several modifications change the device of the same entity, the most specific one wins: an entity modification wins over a merge, which wins over entities assigned to a device.

When an entity is renamed, all modifications are updated automatically. When a device or entity referenced by a modification no longer exists, Home Assistant shows a repair issue. The modification keeps working for everything else and recovers automatically if the device or entity comes back.

## Upgrading

### From 1.x

Modifications of Device Tools 1.x are migrated automatically when Home Assistant starts:

* Each modification keeps its name and becomes a device modification containing the changed attributes and assigned entities. Devices created by Device Tools keep their id, name and area, so automations using them keep working.
* Merges become a separate merge modification named *Merge: &lt;device&gt;*.
* Entities and devices that no longer exist are skipped.

Device Tools 1.x did not persist original values. Until an integration updates its devices and entities for the first time after the upgrade, which usually happens on the next restart, the modified values are treated as original values.

### Home Assistant 2026.8

Home Assistant 2026.8 changed devices to belong to a single integration. Previous versions of Device Tools added themselves to the devices they modified, so Home Assistant split these devices into separate devices. Device Tools cleans up after this automatically: modifications are moved to the device of the original integration, entities of merged devices that Home Assistant moved to one of the duplicates are merged again, and the leftover empty duplicates owned by Device Tools are removed.

## Troubleshooting

* **Repairs**: Check **Settings → System → Repairs** for modifications referencing missing devices or entities.
* **Diagnostics**: Download diagnostics from the menu of a modification. They contain the current, desired and original values of everything it changes. Please attach them to bug reports.
* **Debug logs**: Enable debug logging for Device Tools on the integration page, or add the following to your `configuration.yaml`:

  ```yaml
  logger:
    logs:
      custom_components.device_tools: debug
  ```

Please report bugs and ideas on [GitHub](https://github.com/EuleMitKeule/device-tools/issues).

## Development

The project uses [uv](https://docs.astral.sh/uv/).

```shell
uv sync --all-groups
uv run ruff check .
uv run ruff format .
uv run ty check
uv run pytest --cov
```

Tests run against a real Home Assistant instance using [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component). Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/), releases are created by semantic-release.
