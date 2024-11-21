[![My Home Assistant](https://img.shields.io/badge/Home%20Assistant-%2341BDF5.svg?style=flat&logo=home-assistant&label=My)](https://my.home-assistant.io/redirect/hacs_repository/?owner=EuleMitKeule&repository=device-tools&category=integration)

![GitHub License](https://img.shields.io/github/license/eulemitkeule/eq3btsmart)
![GitHub Sponsors](https://img.shields.io/github/sponsors/eulemitkeule?logo=GitHub-Sponsors)

# Device tools for Home Assistant

A custom Home Assistant integration that allows you to modify and interact with devices.

> [!CAUTION]
> This integration is still in development and has the potential to permanently modify your configuration in a bad way.

## Known Issues

* Some entities seem to not be configurable. (see [#4](https://github.com/EuleMitKeule/device-tools/issues/4) and [#6](https://github.com/EuleMitKeule/device-tools/issues/6))
* Changing a modified virtual device's area requires a HA restart for the entities assigned to the device to reappear. (see [#20](https://github.com/EuleMitKeule/device-tools/issues/20))
* Reverting certain modifications like assigning entities to virtual devices does not work in some situations. (see [#22](https://github.com/EuleMitKeule/device-tools/issues/20))

## Roadmap

The integration will allow the user to...
* [x] Modify static device attributes
* [x] Assign entities to devices
* [x] Create new devices
* [x] Merge devices
* [x] Automatically revert any modification on removal

# Installation

1. Install the [HACS](https://hacs.xyz/) integration
2. Click the My Home Assistant link at the top of the readme
