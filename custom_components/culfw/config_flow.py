"""Config flow for the culfw integration."""

import asyncio
from collections.abc import Iterable
import logging
from pathlib import Path
from typing import Any, override

import probatio

from homeassistant.components import usb
from homeassistant.config_entries import (
    SOURCE_IGNORE,
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_DEVICE
from homeassistant.core import callback
from homeassistant.data_entry_flow import SectionConfig, section
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    SerialPortSelector,
)
from homeassistant.helpers.service_info.usb import UsbServiceInfo
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from .const import (
    BY_ID_DIR,
    CONF_ADD_CARD,
    CONF_ALLOW_REBOOT,
    CONF_ALLOW_USB_RESET,
    CONF_AUTO_ADD_DEVICES,
    CONF_CANDIDATES_TO_ADD,
    CONF_CANDIDATES_TO_IGNORE,
    CONF_CONTACT_THERMOSTATS,
    CONF_CONTACT_TYPES,
    CONF_FHT80B_STALE_HOURS,
    CONF_FHT80TF_STALE_HOURS,
    CONF_FIRST_PAIR,
    CONF_HOUSE_CODE,
    CONF_IGNORED_DEVICES,
    CONF_READ_WEEK_PROGRAMS,
    CONF_SECOND_PAIR,
    CONTACT_TYPE_DOOR,
    CONTACT_TYPE_WINDOW,
    CUL_IDENTIFIER,
    CUL_MODEL,
    DEFAULT_ADD_CARD,
    DEFAULT_FHT80B_STALE_HOURS,
    DEFAULT_FHT80TF_STALE_HOURS,
    DEFAULT_READ_WEEK_PROGRAMS,
    DOMAIN,
    LISTEN_DURATION,
    LISTEN_TICK,
    LOCAL_DEVICE_DIR,
    SECTION_RECOVERY,
    THERMOSTAT_NONE,
)
from .pyculfw import (
    DISPLAY_PART_MAX,
    DISPLAY_PART_MIN,
    CulConnectionError,
    CulError,
    CulInfo,
    CulPortBusyError,
    CulPortMissingError,
    CulPortPermissionError,
    CulProtocolError,
    CulTimeoutError,
    CulTransport,
    DeviceType,
    DeviceUpdate,
    Evidence,
    FhtCandidate,
    FhtDevice,
    FhtNetwork,
    FhtRoomController,
    FhtWindowContact,
    code_to_display_pair,
    device_label,
    display_pair_to_code,
    format_display_code,
    normalize_fht_house_code,
    parse_line,
)
from .runtime import FhtCulConfigEntry, async_stable_port, contact_type

_LOGGER = logging.getLogger(__name__)

PORT_SCHEMA = probatio.Schema({probatio.Required(CONF_DEVICE): SerialPortSelector()})


def _pair_selector() -> NumberSelector:
    """Return the selector of one of the two numbers that an FHT80b shows."""
    return NumberSelector(
        NumberSelectorConfig(
            min=DISPLAY_PART_MIN,
            max=DISPLAY_PART_MAX,
            step=1,
            mode=NumberSelectorMode.BOX,
        )
    )


HOUSE_CODE_FIELDS: dict[Any, Any] = {
    probatio.Required(CONF_FIRST_PAIR): _pair_selector(),
    probatio.Required(CONF_SECOND_PAIR): _pair_selector(),
}
HOUSE_CODE_SCHEMA = probatio.Schema(HOUSE_CODE_FIELDS)
RECONFIGURE_SCHEMA = probatio.Schema(
    {probatio.Required(CONF_DEVICE): SerialPortSelector(), **HOUSE_CODE_FIELDS}
)

# The probe sends no house code, but the transport needs a valid one to be created.
PROBE_HOUSE_CODE = "0101"


class FhtCulConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a CUL stick.

    The flow reads the version and the central code (the house code of the CUL, which
    FHEM calls FHTID) from the CUL before it asks for the code, and the read changes
    nothing. Setting a different central code rewrites the EEPROM of the CUL and clears
    its FHT send buffers during setup, so the flow asks for confirmation first.

    A setup then listens to the radio, because a device announces itself only when it
    transmits. The user chooses between listening and skipping it, which is how the
    flow stays short for a user who has no battery in the devices yet. A progress
    step cannot take input, so the choice has to come before it, and the progress
    step ends by itself. The listening reads through a transport of its own with the
    central code that the CUL holds, so it writes nothing to the CUL but the report
    mode, and the entry is created only after the summary, when the port is free
    again.
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._device = ""
        self._cul_house_code = ""
        self._house_code = ""
        self._heard = FhtNetwork(now=dt_util.utcnow)
        self._listen_task: asyncio.Task[None] | None = None
        self._listen_failed = False

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: FhtCulConfigEntry) -> FhtCulOptionsFlow:
        """Return the options flow."""
        return FhtCulOptionsFlow()

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the serial port and read the CUL on it."""
        # The CUL868 has no serial number, so the domain is the unique ID and one CUL
        # is supported. The abort comes before any probe, because a configured entry
        # holds the port. A USB discovery that waits for its confirmation does not
        # block this flow, so the user can still set the CUL up by hand.
        await self.async_set_unique_id(DOMAIN, raise_on_progress=False)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            # The entry stores the stable path, so the probe reads the CUL through it.
            device = await async_stable_port(self.hass, user_input[CONF_DEVICE].strip())
            if (info := await self._async_probe(device, errors)) is not None:
                self._device = device
                self._cul_house_code = info.house_code
                return await self.async_step_house_code()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(PORT_SCHEMA, user_input),
            errors=errors,
            last_step=False,
        )

    @override
    async def async_step_usb(self, discovery_info: UsbServiceInfo) -> ConfigFlowResult:
        """Handle a CUL found by USB discovery."""
        entry = await self.async_set_unique_id(DOMAIN)
        device = await async_stable_port(self.hass, discovery_info.device)
        updates = await self._async_updated_port(entry, device)
        # The abort also reloads an entry that waits for its next setup retry, so the
        # CUL is used within seconds of the replug.
        self._abort_if_unique_id_configured(updates=updates)
        self._device = device
        self.context["title_placeholders"] = {
            "name": usb.human_readable_device_name(
                device,
                discovery_info.serial_number,
                discovery_info.manufacturer,
                discovery_info.description,
                discovery_info.vid,
                discovery_info.pid,
            )
        }
        return await self.async_step_usb_confirm()

    async def async_step_usb_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the discovered CUL and read it."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if (info := await self._async_probe(self._device, errors)) is not None:
                self._cul_house_code = info.house_code
                return await self.async_step_house_code()

        self._set_confirm_only()
        return self.async_show_form(
            step_id="usb_confirm",
            description_placeholders={CONF_DEVICE: self._device},
            errors=errors,
        )

    async def async_step_house_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the central code as two numbers.

        The numbers that the CUL stores are suggested.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            if (house_code := self._parse_house_code(user_input, errors)) is not None:
                return await self._async_use_house_code(house_code)

        return self.async_show_form(
            step_id="house_code",
            data_schema=self.add_suggested_values_to_schema(
                HOUSE_CODE_SCHEMA,
                user_input or _suggested_numbers(self._cul_house_code),
            ),
            description_placeholders={"current": _code_text(self._cul_house_code)},
            errors=errors,
            last_step=False,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the serial port or the central code."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if (house_code := self._parse_house_code(user_input, errors)) is not None:
                device = await async_stable_port(
                    self.hass, user_input[CONF_DEVICE].strip()
                )
                cul_house_code = await self._async_stored_house_code(
                    entry, device, errors
                )
                if cul_house_code is not None:
                    self._device = device
                    self._cul_house_code = cul_house_code
                    return await self._async_use_house_code(house_code)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                RECONFIGURE_SCHEMA,
                user_input
                or {
                    CONF_DEVICE: entry.data[CONF_DEVICE],
                    **_suggested_numbers(entry.data[CONF_HOUSE_CODE]),
                },
            ),
            description_placeholders={
                "current": _code_text(entry.data[CONF_HOUSE_CODE])
            },
            errors=errors,
        )

    async def async_step_confirm_house_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm overwriting the central code stored in the CUL."""
        if user_input is not None:
            return await self._async_finish()
        return self.async_show_form(
            step_id="confirm_house_code",
            description_placeholders={
                "current": _code_text(self._cul_house_code),
                "new": _code_text(self._house_code),
            },
            last_step=False,
        )

    def _parse_house_code(
        self, user_input: dict[str, Any], errors: dict[str, str]
    ) -> str | None:
        """Return the central code of the entered numbers, or None with `errors`."""
        try:
            return _house_code_from_numbers(
                user_input[CONF_FIRST_PAIR], user_input[CONF_SECOND_PAIR]
            )
        except ValueError:
            errors["base"] = "invalid_house_code"
        return None

    async def _async_probe(self, device: str, errors: dict[str, str]) -> CulInfo | None:
        """Read the CUL on a port, and set `errors` when that fails."""
        try:
            return await CulTransport(device, PROBE_HOUSE_CODE).probe()
        except CulPortMissingError:
            errors["base"] = "port_missing"
        except CulPortBusyError:
            errors["base"] = "port_in_use"
        except CulPortPermissionError:
            errors["base"] = "permission_denied"
        except CulConnectionError:
            errors["base"] = "cannot_connect"
        except CulTimeoutError:
            errors["base"] = "no_answer"
        except CulProtocolError as err:
            # Another device on the selected port is an expected mistake, so no traceback.
            _LOGGER.debug("Unexpected answer from %s: %s", device, err)
            errors["base"] = "not_culfw"
        except Exception:
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        return None

    async def _async_stored_house_code(
        self, entry: FhtCulConfigEntry, device: str, errors: dict[str, str]
    ) -> str | None:
        """Return the house code that the CUL on a port stores, or None with `errors`."""
        if device == entry.data[CONF_DEVICE] and entry.state is ConfigEntryState.LOADED:
            # The running integration holds the port exclusively, and the CUL has the
            # configured house code since it was set up.
            house_code: str = entry.data[CONF_HOUSE_CODE]
            return house_code
        info = await self._async_probe(device, errors)
        return None if info is None else info.house_code

    async def _async_updated_port(
        self, entry: ConfigEntry | None, device: str
    ) -> dict[str, str] | None:
        """Return the entry data for a rediscovered CUL, or None to keep the port.

        The domain is the unique ID, so every busware stick matches the entry. The
        stored port changes only when it is a device node that is gone and the CUL
        now has a stable by-id path. A port that still exists belongs to the
        configured CUL, a URL points to a remote serial port, and a plain tty node
        would replace a stable path by one that changes with every replug.
        """
        if entry is None or entry.source == SOURCE_IGNORE:
            return None
        stored: str = entry.data[CONF_DEVICE]
        if not stored.startswith(LOCAL_DEVICE_DIR) or not device.startswith(BY_ID_DIR):
            return None
        if await self.hass.async_add_executor_job(Path(stored).exists):
            return None
        return {CONF_DEVICE: device}

    async def _async_use_house_code(self, house_code: str) -> ConfigFlowResult:
        """Continue with the chosen house code, after a confirmation if it is new."""
        self._house_code = house_code
        if house_code != self._cul_house_code:
            return await self.async_step_confirm_house_code()
        return await self._async_finish()

    async def _async_finish(self) -> ConfigFlowResult:
        """Update the entry that is reconfigured, or go on to find the devices."""
        if self.source == SOURCE_RECONFIGURE:
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(),
                data_updates={
                    CONF_DEVICE: self._device,
                    CONF_HOUSE_CODE: self._house_code,
                },
            )
        return await self.async_step_listen_menu()

    async def async_step_listen_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer to listen for the devices, or to set up without them."""
        return self.async_show_menu(
            step_id="listen_menu",
            menu_options=["listen", "summary"],
            description_placeholders={"minutes": _listen_minutes()},
        )

    async def async_step_listen(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Listen to the radio for a while and show the devices that are heard.

        Home Assistant calls the step again when the task ends, and the frontend asks
        for it again when a device is heard, which updates the placeholders.
        """
        if self._listen_task is None:
            self._heard = FhtNetwork(now=dt_util.utcnow)
            self._listen_failed = False
            # A background task, because the listening lasts minutes and must not hold
            # up the shutdown of Home Assistant, which cancels it.
            self._listen_task = self.hass.async_create_background_task(
                self._async_listen(), "culfw listen"
            )
            # The task may be done already, because it starts eagerly. The progress is
            # shown first anyway, so that the flow manager sees the end of the task.
        elif self._listen_task.done():
            task, self._listen_task = self._listen_task, None
            self._check_listen_task(task)
            return self.async_show_progress_done(next_step_id="listen_done")
        return self.async_show_progress(
            step_id="listen",
            progress_action="listen",
            description_placeholders={
                "minutes": _listen_minutes(),
                **self._heard_placeholders(),
            },
            progress_task=self._listen_task,
        )

    async def async_step_listen_done(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Continue with the summary, or stop when the CUL could not be read."""
        if self._listen_failed:
            return self.async_abort(
                reason="cannot_listen",
                description_placeholders={CONF_DEVICE: self._device},
            )
        return await self.async_step_summary()

    async def async_step_summary(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the devices that were heard, ask about them and create the entry.

        The options that the entry starts with are the answers: what each contact
        watches and whether the integration reads the week programs. A contact is
        asked for here because it cannot tell a window from a door.
        """
        contacts = {
            device_id: _contact_label(device_id, device.label)
            for device_id, device in sorted(self._heard.devices.items())
            if isinstance(device, FhtWindowContact)
        }
        if user_input is not None:
            options: dict[str, Any] = {
                CONF_READ_WEEK_PROGRAMS: user_input[CONF_READ_WEEK_PROGRAMS]
            }
            if doors := {
                device_id: CONTACT_TYPE_DOOR
                for device_id, label in contacts.items()
                if user_input[label] == CONTACT_TYPE_DOOR
            }:
                options[CONF_CONTACT_TYPES] = doors
            return self.async_create_entry(
                title=CUL_MODEL,
                data={CONF_DEVICE: self._device, CONF_HOUSE_CODE: self._house_code},
                options=options,
            )

        fields: dict[Any, Any] = {
            probatio.Required(label, default=CONTACT_TYPE_WINDOW): _contact_selector()
            for label in contacts.values()
        }
        fields[
            probatio.Required(
                CONF_READ_WEEK_PROGRAMS, default=DEFAULT_READ_WEEK_PROGRAMS
            )
        ] = BooleanSelector()
        return self.async_show_form(
            step_id="summary",
            data_schema=probatio.Schema(fields),
            description_placeholders=self._heard_placeholders(),
        )

    async def _async_listen(self) -> None:
        """Hold the CUL open for the listening time and report the progress.

        The transport belongs to this task, so it is closed however the task ends,
        which includes the cancellation when the user abandons the flow.
        """
        transport = CulTransport(
            self._device, self._cul_house_code, on_message=self._handle_line
        )
        await transport.connect()
        try:
            steps = max(1, round(LISTEN_DURATION / LISTEN_TICK))
            for step in range(1, steps + 1):
                await asyncio.sleep(LISTEN_TICK.total_seconds())
                self.async_update_progress(step / steps)
        finally:
            await transport.close()

    def _check_listen_task(self, task: asyncio.Task[None]) -> None:
        """Remember that the listening failed, and why."""
        if task.cancelled():
            # Home Assistant cancels its background tasks when it stops.
            self._listen_failed = True
            return
        try:
            task.result()
        except CulError as err:
            _LOGGER.warning("Could not listen to the CUL on %s: %s", self._device, err)
            self._listen_failed = True
        except Exception:
            _LOGGER.exception("Unexpected exception")
            self._listen_failed = True

    @callback
    def _handle_line(self, line: str) -> None:
        """Take a line of the CUL, and tell the frontend about a new device."""
        update = self._heard.process(parse_line(line))
        if isinstance(update, DeviceUpdate) and update.new:
            self.async_notify_flow_changed()

    def _heard_placeholders(self) -> dict[str, str]:
        """Return the devices heard so far as the texts of the two lists."""
        devices = self._heard.devices.values()
        return {
            "thermostats": _heard_text(
                device for device in devices if isinstance(device, FhtRoomController)
            ),
            "contacts": _heard_text(
                device for device in devices if isinstance(device, FhtWindowContact)
            ),
        }


class FhtCulOptionsFlow(OptionsFlow):
    """Liveness thresholds, new devices, ignored devices, recovery and contact types.

    The entry has no update listener, so the flow reloads it exactly once when it saves
    changed options, and not at all when the options stay as they are. It stores the
    options itself before it adds the devices that the user picked, so that a contact
    that is added as a door comes up as a door with the entity ID of a door, and not
    as a window that the reload turns into a door afterwards. Turning off the automatic
    adding of devices makes the devices that are heard from then on candidates, and the
    form offers the candidates to add or to ignore. That choice is an action and no option: it is carried out when
    the flow ends and never stored. When the entry has FHT80 TF contacts, or the user
    adds one, a second step asks for each of them whether it watches a window or a
    door, because the contact cannot tell. A third step asks for the thermostat of each
    contact, because the thermostat does not tell either. It offers the thermostat that
    the radio traffic suggests as the default, and the user confirms it by saving.
    """

    def __init__(self) -> None:
        """Initialize the flow."""
        self._options: dict[str, Any] = {}
        self._to_add: list[str] = []
        self._to_ignore: list[str] = []
        self._contacts: dict[str, str] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            options = dict(user_input)
            to_add: list[str] = options.pop(CONF_CANDIDATES_TO_ADD, [])
            to_ignore: list[str] = options.pop(CONF_CANDIDATES_TO_IGNORE, [])
            if set(to_add) & set(to_ignore):
                errors["base"] = "candidate_conflict"
            else:
                options[CONF_IGNORED_DEVICES] = sorted(
                    {*options.get(CONF_IGNORED_DEVICES, []), *to_ignore}
                )
                for key in (CONF_CONTACT_TYPES, CONF_CONTACT_THERMOSTATS):
                    if key in self.config_entry.options:
                        options[key] = self.config_entry.options[key]
                self._options = options
                self._to_add = to_add
                self._to_ignore = to_ignore
                if self._contacts_to_ask(to_add):
                    return await self.async_step_contact_types()
                return self._async_finish()

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                self._options_schema(), user_input or self.config_entry.options
            ),
            errors=errors,
            # Any contact that is known or heard may need the second step.
            last_step=not self._contacts_to_ask(list(self._candidates())),
        )

    async def async_step_contact_types(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for each FHT80 TF contact whether it watches a window or a door.

        The contact cannot tell, and the state of its binary sensor needs it. The
        contacts that the user adds in the first step are asked for here as well, so
        that they start with the right class.
        """
        contacts = self._contacts_to_ask(self._to_add)
        if user_input is not None:
            doors = {
                device_id
                for device_id, label in contacts.items()
                if user_input.get(label) == CONTACT_TYPE_DOOR
            }
            # Contacts that are not asked for stay as they are, for example one that
            # was forgotten and returns later.
            stored: dict[str, str] = self._options.get(CONF_CONTACT_TYPES, {})
            kept = {k: v for k, v in stored.items() if k not in contacts}
            if types := {**kept, **dict.fromkeys(sorted(doors), CONTACT_TYPE_DOOR)}:
                self._options[CONF_CONTACT_TYPES] = types
            else:
                self._options.pop(CONF_CONTACT_TYPES, None)
            if self._thermostats_to_ask(self._to_add):
                return await self.async_step_contact_thermostats()
            return self._async_finish()

        selector = _contact_selector()
        # The field names are the labels of the contacts, so the user sees which
        # contact a field belongs to. They cannot have a translation of their own.
        return self.async_show_form(
            step_id="contact_types",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        label,
                        default=contact_type(self._options, device_id),
                    ): selector
                    for device_id, label in contacts.items()
                }
            ),
            last_step=not self._thermostats_to_ask(self._to_add),
        )

    async def async_step_contact_thermostats(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for each FHT80 TF contact which thermostat it is paired with.

        A thermostat shows only the state of each of its contact slots, and the radio
        tells only by the window flag that follows a contact. So the user says, and the
        thermostat that the traffic suggests is the default of the contact, labeled as
        a suggestion with its confidence in words. Saving it confirms it. Turning a
        suggestion down is recorded, so that it is not suggested again.
        """
        contacts = self._contacts_to_ask(self._to_add)
        thermostats = self._thermostats_to_ask(self._to_add)
        stored: dict[str, str] = self._options.get(CONF_CONTACT_THERMOSTATS, {})
        if user_input is not None:
            chosen = {}
            for contact_id, label in contacts.items():
                thermostat_id = user_input[label]
                if thermostat_id != THERMOSTAT_NONE or self._evidence(contact_id):
                    chosen[contact_id] = thermostat_id
            # Contacts that are not asked for stay as they are, for example one that
            # was forgotten and returns later.
            kept = {k: v for k, v in stored.items() if k not in contacts}
            if assigned := {**kept, **chosen}:
                self._options[CONF_CONTACT_THERMOSTATS] = assigned
            else:
                self._options.pop(CONF_CONTACT_THERMOSTATS, None)
            return self._async_finish()

        texts = await async_get_translations(
            self.hass, self.hass.config.language, "selector", [DOMAIN]
        )
        none = texts[f"component.{DOMAIN}.selector.contact_thermostat.options.none"]
        prefix = f"component.{DOMAIN}.selector.contact_thermostat.options"
        fields: dict[Any, Any] = {}
        for contact_id, label in contacts.items():
            evidence = self._evidence(contact_id)
            suggestion = None if evidence is None else evidence.thermostat
            options = [SelectOptionDict(value=THERMOSTAT_NONE, label=none)]
            for thermostat_id, thermostat_label in thermostats.items():
                text = thermostat_label
                if evidence is not None and thermostat_id == suggestion:
                    text = texts[f"{prefix}.suggested_{evidence.confidence}"].format(
                        thermostat=thermostat_label
                    )
                options.append(SelectOptionDict(value=thermostat_id, label=text))
            current = stored.get(contact_id, suggestion)
            fields[
                probatio.Required(
                    label,
                    default=current if current in thermostats else THERMOSTAT_NONE,
                )
            ] = SelectSelector(
                SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
            )
        return self.async_show_form(
            step_id="contact_thermostats", data_schema=probatio.Schema(fields)
        )

    @callback
    def _async_finish(self) -> ConfigFlowResult:
        """Store the options, carry out the actions on the candidates and reload."""
        entry = self.config_entry
        changed = self.hass.config_entries.async_update_entry(
            entry, options=self._options
        )
        self._apply_candidates(self._to_add, self._to_ignore)
        if changed:
            self.hass.config_entries.async_schedule_reload(entry.entry_id)
        return self.async_create_entry(data=self._options)

    def _contacts_to_ask(self, to_add: list[str]) -> dict[str, str]:
        """Return the labels of the contacts to ask for, by device ID.

        These are the contacts of the registry that are not ignored, and the candidates
        among `to_add` that are contacts. The label holds the address and, when the
        user or Home Assistant gave the contact another name, that name.
        """
        return self._devices_to_ask(DeviceType.FHT80TF, to_add)

    def _thermostats_to_ask(self, to_add: list[str]) -> dict[str, str]:
        """Return the labels of the thermostats that a contact can belong to.

        These are the thermostats of the registry that are not ignored, and the
        candidates among `to_add` that are thermostats.
        """
        return self._devices_to_ask(DeviceType.FHT80B, to_add)

    def _devices_to_ask(
        self, device_type: DeviceType, to_add: list[str]
    ) -> dict[str, str]:
        """Return the labels of the devices of a type that are not ignored.

        The devices are the ones of the registry and the candidates among `to_add`.
        """
        ignored = {
            *self._options.get(CONF_IGNORED_DEVICES, []),
            *self.config_entry.options.get(CONF_IGNORED_DEVICES, []),
        }
        labels = {
            device_id: label
            for device_id, label in self._known_devices().items()
            if device_id.startswith(f"{device_type}_") and device_id not in ignored
        }
        candidates = self._candidates()
        for device_id in to_add:
            if (candidate := candidates.get(device_id)) is not None:
                if candidate.type is device_type:
                    labels[device_id] = candidate.label
        return {
            device_id: _contact_label(device_id, name)
            for device_id, name in sorted(labels.items())
        }

    def _evidence(self, contact_id: str) -> Evidence | None:
        """Return the thermostat that the radio traffic suggests for a contact, and why.

        Only a loaded entry has listened, because the votes live in its runtime.
        """
        if self.config_entry.state is not ConfigEntryState.LOADED:
            return None
        evidence: Evidence | None = (
            self.config_entry.runtime_data.network.pairing.evidence(contact_id)
        )
        return evidence

    def _candidates(self) -> dict[str, FhtCandidate]:
        """Return the devices that wait to be added, by device ID.

        Only a loaded entry has heard any, because the candidates live in its runtime.
        """
        if self.config_entry.state is not ConfigEntryState.LOADED:
            return {}
        candidates: dict[str, FhtCandidate] = (
            self.config_entry.runtime_data.network.candidates
        )
        return candidates

    def _apply_candidates(self, to_add: list[str], to_ignore: list[str]) -> None:
        """Add the devices that the user picked and drop the ones that are ignored.

        The candidates live in the runtime, so an entry that is not loaded has none and
        nothing to do. The ignored devices still reach the options of such an entry.
        """
        if not (to_add or to_ignore):
            return
        if self.config_entry.state is not ConfigEntryState.LOADED:
            return
        runtime = self.config_entry.runtime_data
        for device_id in to_add:
            runtime.async_adopt_candidate(device_id)
        for device_id in to_ignore:
            runtime.network.ignore(device_id)

    def _options_schema(self) -> probatio.Schema:
        """Return the form, with the devices that can be ignored as options.

        The defaults belong to the schema, so an entry that never saved its options
        shows them, and the options stored so far are suggested values on top. The
        candidates are offered only while there are some.
        """
        hours = NumberSelector(
            NumberSelectorConfig(
                min=0.5,
                max=48,
                step=0.5,
                unit_of_measurement="h",
                mode=NumberSelectorMode.BOX,
            )
        )
        devices = [
            SelectOptionDict(value=device_id, label=label)
            for device_id, label in self._known_devices().items()
        ]
        fields: dict[Any, Any] = {
            probatio.Required(
                CONF_FHT80B_STALE_HOURS, default=DEFAULT_FHT80B_STALE_HOURS
            ): hours,
            probatio.Required(
                CONF_FHT80TF_STALE_HOURS, default=DEFAULT_FHT80TF_STALE_HOURS
            ): hours,
            probatio.Required(CONF_AUTO_ADD_DEVICES, default=True): BooleanSelector(),
        }
        if candidates := self._candidates():
            selector = SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=device_id, label=_candidate_label(c))
                        for device_id, c in candidates.items()
                    ],
                    multiple=True,
                    mode=SelectSelectorMode.DROPDOWN,
                    sort=True,
                )
            )
            fields[probatio.Optional(CONF_CANDIDATES_TO_ADD, default=list)] = selector
            fields[probatio.Optional(CONF_CANDIDATES_TO_IGNORE, default=list)] = (
                selector
            )
        fields[probatio.Optional(CONF_IGNORED_DEVICES, default=list)] = SelectSelector(
            SelectSelectorConfig(
                options=devices,
                multiple=True,
                mode=SelectSelectorMode.DROPDOWN,
                sort=True,
            )
        )
        fields[
            probatio.Required(
                CONF_READ_WEEK_PROGRAMS, default=DEFAULT_READ_WEEK_PROGRAMS
            )
        ] = BooleanSelector()
        fields[probatio.Required(CONF_ADD_CARD, default=DEFAULT_ADD_CARD)] = (
            BooleanSelector()
        )
        fields[probatio.Required(SECTION_RECOVERY)] = section(
            probatio.Schema(
                {
                    probatio.Required(
                        CONF_ALLOW_REBOOT, default=False
                    ): BooleanSelector(),
                    probatio.Required(
                        CONF_ALLOW_USB_RESET, default=False
                    ): BooleanSelector(),
                }
            ),
            SectionConfig(collapsed=True),
        )
        return probatio.Schema(fields)

    def _known_devices(self) -> dict[str, str]:
        """Return the labels of the FHT devices that can be ignored, by device ID.

        A label is the name of the device without its ID, such as "FHT80b 063 072". An
        ignored device that has left the device registry has no name any more, so its
        label is made from its ID.
        """
        entry_id = self.config_entry.entry_id
        known: dict[str, str] = {}
        registry = dr.async_get(self.hass)
        for device in dr.async_entries_for_config_entry(registry, entry_id):
            for domain, device_id in device.identifiers:
                if domain == DOMAIN and device_id != CUL_IDENTIFIER:
                    known[device_id] = (
                        device.name_by_user or device.name or device_label(device_id)
                    )
        for device_id in self.config_entry.options.get(CONF_IGNORED_DEVICES, []):
            known.setdefault(device_id, device_label(device_id))
        return dict(sorted(known.items()))


def _contact_selector() -> SelectSelector:
    """Return the selector of what a contact watches."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[CONTACT_TYPE_WINDOW, CONTACT_TYPE_DOOR],
            mode=SelectSelectorMode.DROPDOWN,
            translation_key="contact_type",
        )
    )


def _listen_minutes() -> str:
    """Return the listening time in whole minutes, for the texts."""
    return f"{round(LISTEN_DURATION.total_seconds() / 60)}"


def _heard_text(devices: Iterable[FhtDevice]) -> str:
    """Return the number of devices and a line for each: its name and signal strength.

    The text holds no words, so that it reads the same in every language. The signal
    strength tells a device of the house from one of a neighbor.
    """
    heard = sorted(devices, key=lambda device: device.device_id)
    lines = [f"- {device.label} ({device.rssi_dbm:.0f} dBm)" for device in heard]
    return "\n".join([str(len(heard)), *lines])


def _code_text(code: str) -> str:
    """Return a central code for a text: the two numbers and the hex code.

    The setup asks for the numbers, the CUL stores the hex code, and a user who knows
    FHEM knows the hex form, so the texts show both. A code without numbers, which a
    display cannot show, comes back as its hex code alone.
    """
    hex_code = code.upper()
    if code_to_display_pair(hex_code) is None:
        return f"hex {hex_code}"
    return f"{format_display_code(hex_code)} (hex {hex_code})"


def _house_code_from_numbers(first: float, second: float) -> str:
    """Return the central code for the two entered numbers, or raise ValueError.

    The number fields return floats, and a box accepts a fraction although the step is 1.
    """
    if first % 1 or second % 1:
        raise ValueError(
            f"Display code numbers must be whole, got {first} and {second}"
        )
    return normalize_fht_house_code(display_pair_to_code(int(first), int(second)))


def _suggested_numbers(house_code: str) -> dict[str, int]:
    """Return the two numbers of a central code, to suggest them.

    A code that the display cannot show has nothing to suggest.
    """
    if (pair := code_to_display_pair(house_code)) is None:
        return {}
    return {CONF_FIRST_PAIR: pair[0], CONF_SECOND_PAIR: pair[1]}


def _contact_label(device_id: str, name: str) -> str:
    """Return the label of a device: its code, and its name if that differs.

    For a contact the label is the name of the field in the form, so it must differ
    between contacts.
    """
    address = device_label(device_id)
    return address if name == address else f"{address} ({name})"


def _candidate_label(candidate: FhtCandidate) -> str:
    """Return the label of a candidate: its name and the signal strength.

    The signal strength tells a device of the house from one of a neighbor.
    """
    return f"{candidate.label} ({candidate.rssi_dbm:.0f} dBm)"
