# Week program card

The card `fht-schedule-card` shows the week heating program of an FHT80b thermostat and edits it. It is a Lovelace card written in TypeScript with Lit. The integration ships the built file `custom_components/culfw/frontend/fht-schedule-card.js`. The sources are in `frontend/`.

This page describes the card, how the integration serves and registers it, the websocket commands it uses, and how to build, test and release it. The README has the short version for users, [Week program card](../README.md#week-program-card).

## Use

Add the card with the visual editor (it is listed with the custom cards as **FHT week program**, or **FHT Wochenprogramm** when Home Assistant is set to German) or in YAML:

```yaml
type: custom:fht-schedule-card
entity: climate.living_room
```

| Option | Required | Meaning |
| --- | --- | --- |
| `entity` | yes | The climate entity of an FHT80b of this integration. |
| `name` | no | The name in the header. It takes what the `entity_name` selector of the editor produces, and defaults to the name of the entity. |

The card talks to the integration through the websocket commands `culfw/schedule/subscribe`, `set` and `refresh`, so a user who may control the climate entity may edit its program, and the button Refresh schedule can stay disabled. It never calls an action.

## What the card shows

- The header has the name of the thermostat, the day and night temperature (read only, they are numbers of their own) and whether the thermostat can be reached: the radio stick is connected and the thermostat is not silent.
- A grid has one row for each weekday, Monday first, on a 24 hour axis. A heating period is a bar. The thermostat regulates to the day temperature inside the periods and to the night temperature outside of them, and the legend says so, so color is never the only sign.
- Every day has a status chip with a symbol and a word: not read, saved, queued, sending, not confirmed, error, and edited for a change that is not saved. The first six come from the integration. A day that waits in the outbox or is on its way shows the requested periods with a hatched fill, never as if the thermostat had confirmed them.
- A day that was never read is hatched with a question mark.

On a wide card every row can be edited in place, and the editor of the selected day sits below the grid. On a narrow card (below 540 pixels, for example a phone in portrait) the rows are buttons, and a tap opens the expanded editor of the day with large handles and the axis in steps of 3 hours.

## Editing

A change is a draft until the user saves it, because every day takes one time slot of the thermostat (about 2 minutes) and a sent day cannot be taken back.

| Action | Mouse and finger | Keyboard |
| --- | --- | --- |
| Add a period | Tap free space (one hour, up to the next period or the end of the day). The button Add heating period does the same. | Button Add heating period |
| Change the start or the end | Drag a handle | Focus a handle, then the arrow keys move by 10 minutes, Shift and the arrow keys by 1 hour, Home and End to the limit |
| Move a period | Drag its bar | Focus the bar (a slider named "move"), then the same keys |
| Remove a period | Button Remove | Delete on a handle or on the bar |
| Enter an exact time | Text field with the buttons for 10 minutes earlier and later | The same, Enter applies the time |

The times snap to 10 minutes, and a period stops at its neighbor and at the ends of the day. A period that touches the next one is allowed, because the thermostat takes it, and the button Merge touching periods joins them. A time that is typed is checked with the rules of the integration and refused in words (not a time of day, not a multiple of 10 minutes, too many periods, backwards, overlap) while the field keeps what the user typed. The unit tests and `tests/test_schedule_card_parity.py` read one file of cases (`frontend/test/fixtures/day_validation.json`), so the card and the integration cannot drift apart.

The footer has Save and Discard. Save sends only the days that differ from what the integration shows (`culfw/schedule/set`), and the integration drops the days that it holds already. Before it sends a day that was never read, the card asks for a confirmation, because saving replaces the whole day. The button Copy to other days opens a dialog with the presets Weekdays, Weekend and All days. A copy is a draft too.

The card keeps working when the thermostat is silent or the radio stick is disconnected: a banner says that the changes wait in the queue. The integration refuses a request only when it cannot queue it (for example the thermostat is unknown, or it stopped echoing commands), and the card shows the reason in words, with the texts of the card, and with the message of the integration for a reason that it has no text for.

When no day was read yet, the card shows an empty state with the button Read now (`culfw/schedule/refresh`) and the choice to edit an empty program. A read takes about 35 minutes, and the days appear as they arrive. A saved draft of a day wins over a later push from the server, and the last save wins when two people edit.

## Touch

A vertical swipe on the page still scrolls: the track and the bars use `touch-action: pan-y`, and only the handles use `touch-action: none`. A drag starts after 6 pixels on a bar and on free space, a cancelled pointer (the browser took over for a scroll) restores the periods from before the drag, and a bubble above the handle shows the time while the handle moves. The hit area of a handle reaches mostly outside of its bar, so the middle of a short bar stays free for moving it. A touch that lands on a bar picks the bar and not a handle near it, because the bar is a focusable control of its own, which is how a browser chooses the target of a touch. The numeric fields and the 10 minute buttons are the way to set an exact time without dragging.

## Registration

`frontend_registration.py` serves the file and makes the dashboards load it.

- `async_setup` (once for the domain) registers the static path `/culfw/frontend/fht-schedule-card.js` for that one file, without cache headers, and builds the address with a cache buster: `?v=<version of the manifest>-<first 12 hex digits of the SHA-256 of the file>`. The hash is read in the executor. The address is the same on every start for the same file, and it changes with the version and with every rebuilt bundle, so a browser never keeps an old card. If the file cannot be read, the integration logs a warning and goes on without the card, because the thermostats do not depend on it.
- `async_setup_entry` adds the card when the option **Add the week program card automatically** (`add_card`, default on, in the options flow and mentioned in one sentence in the text of the last setup step) is on. In the storage mode of the dashboards the address becomes a dashboard resource of the type module. The resource is looked up by its path, so an entry of an older version, or one that a user added without a query, is changed in place (address and type) instead of getting a twin, and no other resource is touched. The collection is loaded the way the websocket command of the dashboards loads it.
- Where the resource cannot be added, the frontend gets the address with `frontend.add_extra_js_url()`, and the integration removes it again when the entry unloads. That is the case when the resources are in YAML mode (the integration cannot edit them and writes one debug line that says so) and when the storage refuses the write (a warning). The frontend loads an extra module in parallel to its first drawing, so the dashboards see the card a moment later than a resource. The bundle defines its element only once and registers itself in `window.customCards` once, so listing the file by hand as well loads it twice and breaks nothing.
- Unloading the entry, and turning the option off, leave an existing resource, because the dashboards that use the card would break while it is gone. Removing the entry (`async_remove_entry`) deletes the resource when its address is still the one the integration would set, so a resource that a user edited stays.
- The manifest lists `http` and `websocket_api` as dependencies and `frontend` and `lovelace` as `after_dependencies`. Home Assistant then sets the frontend and the dashboards up before the integration when the configuration has them (`default_config` does), and does not pull them in when it has not, so a setup without a user interface stays light. The integration serves the file and adds the card once the frontend is set up: at once when it is there already, otherwise when `homeassistant_component_loaded` announces it (the entry unloads the listener with itself). A web server that refuses a new path (aiohttp does after it started, which only a test client causes) is logged once at debug level, and the card stays out of the dashboards. The tests set up the real frontend and dashboards where they need them (the development environment has the `home-assistant-frontend` package for that), and `tests/test_frontend_registration.py` covers the storage and YAML modes, the older entry, the wrong type, the failing write, the option, the unload and the removal, a setup without the frontend, a frontend that comes later and the refused path.

## Websocket commands

The card uses `subscribe`, `set` and `refresh` and no action. `get` serves other clients and tools. The commands are registered by `websocket_api.py` and take the `entity_id` of the climate entity of a thermostat. A user needs the permission to read the entity for `get` and `subscribe` and the permission to control it for `set` and `refresh`, so no administrator is required. The permission is checked first, so a user without it learns nothing about the entity. An entity that is no thermostat of the integration is answered with the error `schedule_entity_unknown`. The errors of `set` have the translation keys of the exceptions of the action `set_schedule`.

`culfw/schedule/get` and the events of `culfw/schedule/subscribe` have the same data. A day has its `status` (`unknown`, `saved`, `queued`, `sending`, `unconfirmed` or `error`), the `periods` that the thermostat reported (`null` while the day is unknown), and, while a write waits or is on its way, the `requested` periods, which are not confirmed, and `pending_since`. The `limits` tell the card what the thermostat takes.

```json
{"id": 7, "type": "culfw/schedule/get", "entity_id": "climate.living_room"}
```

```json
{
  "id": 7,
  "type": "result",
  "success": true,
  "result": {
    "limits": {"step_minutes": 10, "max_periods": 2, "day_end": "24:00"},
    "days": {
      "monday": {
        "status": "saved",
        "periods": [{"start": "06:00", "end": "08:30"}, {"start": "17:00", "end": "22:00"}],
        "requested": null,
        "pending_since": null
      },
      "tuesday": {
        "status": "queued",
        "periods": [{"start": "06:00", "end": "08:30"}],
        "requested": [{"start": "06:30", "end": "09:00"}],
        "pending_since": "2026-10-20T06:12:45+00:00"
      },
      "wednesday": {"status": "unknown", "periods": null, "requested": null, "pending_since": null}
    },
    "week_program_read_at": "2026-10-20T04:11:02+00:00",
    "day_temperature": 21.0,
    "night_temperature": 17.0,
    "link_up": true,
    "reachable": true
  }
}
```

(The real answer has all seven days, `monday` to `sunday`.)

`culfw/schedule/subscribe` answers with an empty result and then sends an event with the data above, and again after every change: a telegram of the thermostat, a write that is staged or sent, a write that expires, a change of the link and a thermostat that turns silent or answers again. An event is sent only when the data differ from the last one. When the entity goes away, for example because the entry reloads, the last event is `{"closed": true}` and the client subscribes again. The card does that, and it stops listening when it leaves the page.

```json
{"id": 8, "type": "culfw/schedule/subscribe", "entity_id": "climate.living_room"}
```

`culfw/schedule/set` takes `days`, a mapping from weekday names to lists of ranges with the rules of the action `set_schedule`, for one day or more. Every day is checked before one is sent. The command sends the days that differ from what the thermostat holds or has on its way, and always a day that is unknown, unconfirmed or lost. It returns once the days are staged, like the action, and an event of a subscription can arrive before the result, because the entity stages a day first.

```json
{
  "id": 9,
  "type": "culfw/schedule/set",
  "entity_id": "climate.living_room",
  "days": {
    "tuesday": [{"start": "06:30", "end": "09:00"}],
    "wednesday": []
  }
}
```

```json
{"id": 9, "type": "result", "success": true, "result": {"sent": ["tuesday"], "unchanged": ["wednesday"]}}
```

`culfw/schedule/refresh` asks the thermostat to report its week program, for the weekdays in `days` or for the whole week without it. It works while the button Refresh schedule is disabled, and the request counts as one of the user. The thermostat answers in its time slots, so a week takes about 35 minutes.

```json
{"id": 10, "type": "culfw/schedule/refresh", "entity_id": "climate.living_room", "days": ["friday"]}
```

```json
{"id": 10, "type": "result", "success": true, "result": {"days": ["friday"]}}
```

A request that cannot be queued is answered with an error, for example when the thermostat is unknown or has stopped echoing commands. A thermostat that is silent, or a link that is down, does not refuse a request: it waits in the queue like the other requests of the integration.

## Architecture

- `frontend/src/model.ts`: the pure logic. It has the snapping to 10 minutes, the checks that mirror `schedule.py` (shared cases in `test/fixtures/day_validation.json`, read by Vitest and by `tests/test_schedule_card_parity.py`), the editing of periods, the day diff between a draft and the saved program, and the copy presets. It has no DOM and no Lit, so the unit tests need no browser.
- `frontend/src/ws.ts`: the three websocket calls of the card (subscribe, set and refresh), the conversion of the payload and the errors. `types.ts` has the types of the payload and of the `hass` object.
- `frontend/src/day-track.ts`: the track of one day, a Lit element with the pointer handling (handles, bars, free space), the keyboard handling and the bubble above a dragged handle.
- `frontend/src/card.ts`: the card. It subscribes in `connectedCallback`, keeps the drafts per day (a draft wins over a push of the server), shows the status chips, the banners, the editor, the copy dialog and the footer, and sends only the changed days. `i18n.ts` has the English and German texts, `styles.ts` the styles.
- `frontend/src/index.ts`: defines the element and registers the card for the picker, each only once. The picker shows one fixed name and description and has no hook for a translation, so the entry in `window.customCards` reads them through getters, which the picker calls when it builds its list, and takes the language from the `hass` object of the `home-assistant` element (`pickerText()` in `i18n.ts` has the texts). The picker searches the name and the description, so each text also holds the name in the other language.
- `custom_components/culfw/frontend/fht-schedule-card.js`: the build of the above, one ES module with Lit inside, and checked in.

A day has three layers that the card keeps apart: what the thermostat reported (`periods`), the draft in the browser, and the transfer (`status`, `requested`). The card never shows a requested value as confirmed.

## Release

1. Change the sources in `frontend/` and the tests with them.
2. Run `scripts/build_frontend.sh --write` and commit the new bundle together with the sources. CI fails when the bundle is not what the sources build.
3. Raise the version for a release (the manifest, `pyproject.toml`, `uv.lock` and the version of the card package together). The bundle hash in the address changes by itself with every rebuilt file, so a release needs no extra step for the cache.
4. HACS and manual installs copy `custom_components/culfw/`, which holds the bundle. Nobody builds on the Home Assistant host. After an update the browsers need a reload of the page to get the new card (the address changes, but an open page keeps the old module).

## Languages and themes

The texts are in English and German and follow `hass.language`, the entry in the card picker included. Error texts of the integration use the same keys as its translated exceptions, so German users read the German text and others read the message of the integration.

The card takes its colors from the theme variables of the frontend: `--primary-color`, `--primary-text-color`, `--secondary-text-color`, `--text-primary-color`, `--card-background-color`, `--secondary-background-color`, `--divider-color`, `--error-color`, `--warning-color`, `--success-color` and `--info-color`. The developer documentation names only three of them (`--primary-color`, `--primary-text-color` and `--card-background-color`) and says that the older variables without the `--ha-` prefix are still what most themes set. The others were checked in the shipped frontend (home-assistant-frontend 20260930.4), where the default theme defines them, and user themes set them too. For sizes the card uses the documented tokens `--ha-space-*`, `--ha-border-radius-*` and `--ha-font-*`. Three more are not named by the developer documentation but exist in the shipped frontend: `--ha-card-header-color`, `--ha-card-header-font-size` and `--ha-color-focus`. Every use has a fallback value, so the card also renders outside of Home Assistant. Dark mode comes from the theme, the card computes no colors. Spacing uses logical properties, and the time axis stays left to right in every language.

## Untrusted data

The card trusts nothing that arrives from the server, from the name of an entity or from the configuration of a dashboard.

- Every text reaches the page through a Lit template, which escapes it. ESLint forbids `eval`, `new Function`, script addresses, `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `srcdoc` and the unsafe directives of Lit in `src/`. `test/unit/security.test.ts` looks for the same and for requests, browser storage and event handler attributes in the sources and in the bundle. The only `innerHTML` in the bundle is the one of Lit that parses the static strings of its templates.
- `isWireState()` in `src/ws.ts` checks the form of every event before the card renders it. An event of another form (a missing day, a status that the card does not know, a step of zero) shows the message "The data from Home Assistant has an unexpected form." with a button to try again, and the next good state replaces it.
- The browser tests load the page with a Content Security Policy that allows scripts from the same origin only, no `eval`, no request and no frame, so a violation fails them. The card sets the position of its bars with style attributes, as the frontend of Home Assistant does, so a policy for it has to allow inline styles.
- `test/e2e/hostile.spec.ts` shows that markup in the name of an entity, in an error message with and without a translation and in a refused subscription stays text.

## Build and test

Node 22.13 or newer is needed. All commands run in `frontend/`:

```bash
npm ci
npm run typecheck   # tsc, strict
npm run lint        # ESLint
npm run format:check  # Prettier (npm run format fixes it)
npm test            # Vitest with coverage, 90 percent of model.ts is required
npm run build       # writes custom_components/culfw/frontend/fht-schedule-card.js
npm run test:e2e    # Playwright with headless Chromium, uses the built bundle
```

`scripts/build_frontend.sh` installs from the lock file, type checks, runs the unit tests, builds into a temporary folder and fails when the checked-in bundle differs from the fresh build. `scripts/build_frontend.sh --write` replaces the bundle. The build is deterministic. The bundle is checked in because HACS and manual installs copy the repository and nobody builds on the Home Assistant host.

The Playwright tests need no Home Assistant. They serve a static page with a mock `hass` object (`frontend/test/e2e/mock-hass.js`) that behaves like the websocket commands, with the real bundle, in two projects: a desktop browser, and an emulated Pixel 7 for the touch tests (the finger events go through the protocol of the browser so that `touch-action` applies). The tests take screenshots into `frontend/test-results/screens/` and compare none of them. The Playwright version fixes the Chromium revision that it wants, so the version in `package.json` is the one whose revision is installed with `npx playwright install chromium`.

CI runs the same checks in its `frontend` stages, only when `frontend/`, the bundle, `scripts/build_frontend.sh` or the CI file change, on the default branch and for tags:

- `frontend-lint` (Node image): `npm run typecheck`, `npm run lint` (ESLint with the typed rules of typescript-eslint) and `npm run format:check` (Prettier). `npm run format` fixes the formatting.
- `frontend-build` (Node image): `npm run build`, then `git diff --exit-code` on `custom_components/culfw/frontend/`. It fails when the bundle was not rebuilt.
- `frontend-test` (the Playwright image, pinned to the version of `@playwright/test`, with Chromium inside): `npm test` and `npm run test:e2e`. It waits for `frontend-build`, because the browser tests load the checked-in bundle. The screenshots are an artifact.

`tests/test_manifest.py` checks that the image tags match `package.json` and that the jobs run for these changes only.

## Dependencies and licenses

Every package is pinned to an exact version that was published at least two weeks before it was chosen, and `package-lock.json` pins the tree. No code of another card is used. Direct dependencies:

| Package | Version | License | Use |
| --- | --- | --- | --- |
| lit | 3.3.3 | BSD-3-Clause | In the bundle (with lit-html, lit-element and @lit/reactive-element of the same project) |
| @eslint/js | 10.0.1 | MIT | Lint rules |
| @playwright/test | 1.62.1 | Apache-2.0 | Browser tests |
| @types/node | 24.19.1 | MIT | Types of the tests |
| @vitest/coverage-v8 | 5.0.3 | MIT | Coverage of the unit tests |
| eslint | 10.12.0 | MIT | Lint |
| globals | 17.13.0 | MIT | Names of the browser globals for the lint |
| prettier | 3.9.9 | MIT | Formatting |
| typescript | 6.0.3 | Apache-2.0 | Build and type check |
| typescript-eslint | 8.71.1 | MIT | Typed lint rules |
| vite | 8.3.3 | MIT | Build |
| vitest | 5.0.3 | MIT | Unit tests |

The lock file has 150 packages without the platform binaries: 111 MIT, 18 Apache-2.0, 7 BSD-3-Clause, 6 BSD-2-Clause, 6 ISC, 1 MPL-2.0 and 1 BlueOak-1.0.0. The platform binaries of `lightningcss` (MPL-2.0) and of the build tools (MIT) come on top and install for the current platform only. Everything but Lit and its three helper packages is a build or test tool that is not part of the bundle and not distributed with it:

- `lightningcss` (MPL-2.0) is required by Vite for building. Its license does not reach the Apache-2.0 license of this repository, because the bundle does not contain it.
- `minimatch` (BlueOak-1.0.0) is a permissive license. The package is used by the lint tools only.

`tests/test_manifest.py` fails when the lock file holds a license outside of the list above and when this table differs from `package.json`. Only Lit ends up in the bundle, and its notice is at the top of the file and below.

```text
BSD 3-Clause License

Copyright (c) 2017 Google LLC. All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```
