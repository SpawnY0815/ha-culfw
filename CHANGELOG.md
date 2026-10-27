# Changelog

All notable changes to the culfw integration are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The version of the integration is the `version` in `custom_components/culfw/manifest.json`.

## [Unreleased]

### Changed

- The README and the texts of the setup and the repairs describe the integration on its own: the busware CUL868, culfw and the FHT devices. The README also says why the integration exists: the devices are old, but as long as they work, keeping them in use is more sustainable than replacing them.

## [0.3.0] - 2026-10-27

The first public release. The integration is named after culfw, the firmware of the busware sticks, because the FHT devices are the first protocol it supports and not necessarily the last one.

### Changed

- The domain is `culfw` instead of `fht_cul`, and the integration shows as **culfw (CUL)**. With the domain the names of everything that carries it changed: the actions `culfw.set_holiday`, `culfw.get_schedule` and `culfw.set_schedule`, the events `culfw_watchdog`, `culfw_command_expired` and `culfw_channel_broken`, the websocket commands `culfw/schedule/get`, `subscribe`, `set` and `refresh`, and the address of the week program card, `/culfw/frontend/fht-schedule-card.js`. The card keeps its type `custom:fht-schedule-card`. Entity IDs, unique IDs and device identifiers keep their values.
- The protocol library inside the integration is the package `pyculfw`.
- The code and the issue tracker are on GitHub.

## [0.2.0] - 2026-10-21

The first version that runs on a real busware CUL868 in a house with FHT80b thermostats and FHT80 TF window contacts. It was rebuilt to the conventions of Home Assistant 2026.10, with a setup that needs no knowledge of the radio protocol, and the CUL takes the role of the central of the FHT system. Version 0.1.0 was the development state with read-only entities and a first climate control and was never tagged. Version 0.2.0 was not published, and its code is part of 0.3.0.

### Added

- Setup and discovery:
  - USB discovery recognizes the CUL868 by its USB IDs, its manufacturer and its product name, and the setup form lists the serial ports.
  - The setup reads the stick before it asks for anything and tells a missing port, a port in use, a missing permission, a device that is not a CUL and a stick that does not answer apart.
  - The central code is entered as two numbers from 1 to 99, as the thermostat display shows them, and a different code is written to the stick only after a confirmation.
  - The setup listens for devices for five minutes, lists the thermostats and window contacts it heard with their signal strength, and asks for each contact whether it sits at a window or at a door.
  - A serial port chosen as `/dev/ttyACM0` is stored as its stable path under `/dev/serial/by-id/`.
  - A reconfigure flow changes the port or the central code, and an options flow changes the thresholds, ignored devices, week program reading, the card, the type of each contact and the thermostat of each contact.
- Connection and recovery:
  - The integration reconnects by itself with a growing delay, as soon as Home Assistant sees the stick plugged in again, and when the stick stays away for 15 minutes the devices become unavailable.
  - A watchdog resets the stick in steps. Rebooting the stick and resetting the USB link are off by default and can be turned on in the options.
  - Repair issues with fix texts tell about an unreachable or silent CUL, a silent device, a low battery, an almost full send buffer, a missing time sync and a thermostat that does not collect commands.
- Devices and entities:
  - Every FHT80b property the radio reports is on an entity or in the attributes: temperature, setpoint, mode, valve position, battery state, warnings, the day, night and window open temperature, the low temperature alarm offset, the holiday end and the signal strength.
  - A climate entity per FHT80b with the HVAC modes auto, heat and off, the presets comfort and eco, a holiday that ends on a date you choose, and the display of the valve switches On (heating pause) and OFF.
  - Sensors for the temperature, the valve position, the actuator state, the end of a holiday, the signal strength, the last time a device was heard, the time acknowledgment and the status of the week program.
  - Binary sensors for each window contact, the low temperature alarm, a window sensor fault, the battery state and the connectivity.
  - Number entities for the day, night and window open temperature and the low temperature alarm offset.
  - Entities for the CUL itself: the free FHT buffer, the duty cycle credit, the uptime, the counters of buffer and duty cycle overflows, and the buttons to sync the time and to refresh the settings and the week program.
  - A calendar entity that shows the heating phases of the week program of a thermostat.
  - Thermostats are named after the security code on their display, for example FHT80b 063 072, and devices that are added later wait as candidates when automatic adding is off.
  - Devices that are deleted and keep transmitting are ignored, and devices that left the network lose their repair issues.
- Control:
  - Commands are queued, merged and sent in the time slot of each thermostat, and a command stays pending until the thermostat echoes it. The pending value, its age and the failed ones are visible, and an expired command fires the event `culfw_command_expired` and shows in the logbook.
  - The integration sends the date and the time to every thermostat every night and after the UTC offset changed.
  - The radio budget (the duty cycle credit) is watched: a command of yours waits for it for up to 8 minutes, and what the integration sends on its own keeps a reserve for you.
  - The week program is read automatically (option, on by default), and the actions `culfw.set_holiday`, `culfw.get_schedule` and `culfw.set_schedule` set a holiday and read and write the week program.
- Week program card:
  - A custom card edits the week program of a thermostat with bars per day, a copy dialog, drafts and the transfer status of each day. It is in English and German, takes the colors of the theme and shows its name in the card picker in the language of Home Assistant.
  - The integration serves the card and adds it to the dashboards (option, on by default), and the card talks to the integration through websocket commands.
- Window contact pairing:
  - The integration learns from the radio traffic which window contact belongs to which thermostat, shows the evidence behind a suggestion and lets you assign contacts in the options.
- Diagnostics and documentation:
  - A diagnostics download with the transport, the counters, the devices, the queues and the send log. It hides the central code, the addresses of remote ports and secrets.
  - A README in the structure of the Home Assistant integration pages, with screens of every flow, troubleshooting and a list of the binding decisions.
  - The quality scale file `quality_scale.yaml` with the status of every rule, checked against the source by the tests.
- Development:
  - The protocol library `culfw` is free of Home Assistant, and a simulated CUL with simulated thermostats runs the tests with virtual time, including soak, fault injection and blocking call checks.
  - Continuous integration with prek, mypy, pytest with a coverage gate, hassfest, a HACS check, the checks of the card and a canary job against the next Home Assistant release.
  - `scripts/ci_local.sh` runs the pytest and hassfest jobs locally in the images of the pipeline.

### Changed

- The integration is licensed under the Apache License 2.0.
- The code, the comments and the documentation follow the conventions of Home Assistant core (ruff, mypy, American English, the layout of a core integration), and every text of a screen is in the translation files in English and German.
- Home Assistant 2026.10.2 is the version the tests run on, and `hacs.json` names 2026.10.0 as the minimum.
- The boost preset of the thermostat was removed, because the thermostat has no such function.
- Entity names and unique IDs are fixed and stay as they are in later versions, and the device model names are constants.

### Fixed

- A repeated switch time of the week program counts once per read, and the pending time of a day counts from the sending of its message.
- A telegram that the end of the stream cut off no longer becomes a device that does not exist.
- The import of the USB library no longer blocks the event loop of Home Assistant.
- A refused schedule time or holiday end no longer repeats the typed text in the log, so a line break cannot forge a log line.
- Line noise, an overlong line and a failing message callback are logged once per connection and then at debug level.
- A loss of the CUL is logged once and its recovery once, and a status poll that fails during an outage is not logged again.
- A restart of Home Assistant keeps the repair issues, the pending commands and the echoes of the thermostats.

### Security

- The diagnostics hide the host of a remote serial port, such as `socket://192.168.1.50:2000`, and every central code.
- Only the commands of the integration reach the stick, and the allow list of serial commands is tested against an independent check and with random input.
- The card renders nothing as HTML, refuses data of an unexpected form, and its browser tests run under a Content Security Policy that allows scripts of the same origin only.
- The websocket commands of the card check the permission of the user for the entity, read for the state and control for a change.
- Vite was updated to close the advisories of its `launch-editor` dependency in the development tools of the card.

[Unreleased]: https://github.com/SpawnY0815/ha-culfw/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/SpawnY0815/ha-culfw/releases/tag/v0.3.0
[0.2.0]: https://github.com/SpawnY0815/ha-culfw/releases/tag/v0.3.0
