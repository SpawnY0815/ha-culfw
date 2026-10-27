"""Runtime of a loaded culfw config entry."""

import asyncio
from collections import deque
from collections.abc import Coroutine, Mapping
from datetime import datetime, timedelta
import logging
from typing import Any, NamedTuple, Self

from homeassistant.components import usb
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ASSIGNMENT_MANUAL,
    ASSIGNMENT_SUGGESTED,
    BY_ID_DIR,
    CONF_ALLOW_REBOOT,
    CONF_ALLOW_USB_RESET,
    CONF_AUTO_ADD_DEVICES,
    CONF_CONTACT_THERMOSTATS,
    CONF_CONTACT_TYPES,
    CONF_FHT80B_STALE_HOURS,
    CONF_FHT80TF_STALE_HOURS,
    CONF_HOUSE_CODE,
    CONF_IGNORED_DEVICES,
    CONF_READ_WEEK_PROGRAMS,
    CONNECTION_HOUSE_CODE,
    CONTACT_TYPE_DOOR,
    CONTACT_TYPE_WINDOW,
    CUL_IDENTIFIER,
    CUL_MODEL,
    CUL_UNREACHABLE_AFTER,
    DEFAULT_FHT80B_STALE_HOURS,
    DEFAULT_FHT80TF_STALE_HOURS,
    DEFAULT_READ_WEEK_PROGRAMS,
    DOMAIN,
    EVENT_CHANNEL_BROKEN,
    EVENT_COMMAND_EXPIRED,
    EVENT_WATCHDOG,
    RAW_LINE_HISTORY,
    RAW_LINE_MAX_LENGTH,
    SAVE_DELAY_SECONDS,
    SECTION_RECOVERY,
    STALE_CHECK_INTERVAL,
    TTY_NODE_PREFIX,
    signal_command_update,
    signal_cul_update,
    signal_device_removed,
    signal_device_update,
    signal_new_device,
    signal_tick,
)
from .coordinator import CulCoordinator, CulStatus
from .issues import IssueTracker, async_delete_issues
from .pyculfw import (
    TEMP_STEP,
    CandidateUpdate,
    ChannelBroken,
    ChannelRecovered,
    CommandsDropped,
    CulTransport,
    CulWatchdog,
    DeviceType,
    DeviceUpdate,
    FhtCode,
    FhtDevice,
    FhtMode,
    FhtNetwork,
    FhtOutbox,
    FhtRoomController,
    FhtWindowContact,
    InvalidationReason,
    MessageSent,
    NoticeKind,
    NoticeUpdate,
    OutboxEvent,
    PendingCommand,
    PendingRetired,
    RefreshPlanner,
    UsbLinkReset,
    WatchdogEvent,
    WatchdogEventKind,
    WatchdogStep,
    device_label,
    format_display_code,
    is_week_program,
    parse_line,
    week_program_reading,
)
from .store import ThrottledSave, create_store
from .timesync import TimeSync

_LOGGER = logging.getLogger(__name__)

type FhtCulConfigEntry = ConfigEntry[FhtCulRuntime]

# The commands whose value is a temperature in half degrees.
_TEMPERATURE_CODES = frozenset(
    {
        FhtCode.DESIRED_TEMP,
        FhtCode.DAY_TEMP,
        FhtCode.NIGHT_TEMP,
        FhtCode.WINDOWOPEN_TEMP,
    }
)
# Two readings of the uptime of the CUL differ by the time between the polls and by the
# time the polls took, so only a drop by more than this is a restart of the CUL.
_UPTIME_JITTER = timedelta(seconds=5)


def command_name(code: int) -> str:
    """Return the name of a command for the event: `desired_temp`, `mon-from1`."""
    if is_week_program(code):
        return week_program_reading(code)
    try:
        return FhtCode(code).name.lower()
    except ValueError:
        return f"{code:#04x}"


def _requested_value(command: PendingCommand) -> str | float:
    """Return the value that was requested, in the unit of the device."""
    if command.code in _TEMPERATURE_CODES:
        return command.raw * TEMP_STEP
    if command.code == FhtCode.MODE:
        try:
            return FhtMode(command.raw).name.lower()
        except ValueError:
            return command.raw
    return command.raw


def firmware_version(version: str | None) -> str | None:
    """Return the culfw version without the "V " that the CUL puts in front of it."""
    return (version or "").removeprefix("V ") or None


def contact_type(options: Mapping[str, Any], device_id: str) -> str:
    """Return what an FHT80 TF contact watches: a door if the options say so."""
    doors: Mapping[str, str] = options.get(CONF_CONTACT_TYPES, {})
    if doors.get(device_id) == CONTACT_TYPE_DOOR:
        return CONTACT_TYPE_DOOR
    return CONTACT_TYPE_WINDOW


class ContactAssignment(NamedTuple):
    """The thermostat of a window contact, and who says so.

    The confidence and the events say how strong the radio evidence for a suggested
    thermostat is. They are None for a thermostat that the user chose, because the
    radio did not choose it.
    """

    thermostat: FhtRoomController | None
    source: str | None
    confidence: str | None = None
    events: int | None = None


def _by_id_or_port(port: str) -> str:
    """Return the by-id path of a device node, or the port itself without one."""
    try:
        return usb.get_serial_by_id(port)
    except OSError:
        # udev removes the by-id directory with the last link in it, which can happen
        # between the check of the lookup and its scan.
        return port


async def async_stable_port(hass: HomeAssistant, port: str) -> str:
    """Return the /dev/serial/by-id path of a tty node, or the port as it is.

    The number of a tty node depends on the order in which the host enumerates its
    serial devices, so another device can take it after a replug. A URL and a path
    that is not a tty node have nothing to look up, and a tty node without a link
    stays as it is.
    """
    if not port.startswith(TTY_NODE_PREFIX):
        return port
    return await hass.async_add_executor_job(_by_id_or_port, port)


def _create_usb_reset(port: str) -> UsbLinkReset | None:
    """Return the USB reset hook for the port, or None when the port rules it out.

    The tty node of a stick can change when the kernel binds it again after a reset, so
    only a link under /dev/serial/by-id/ finds the stick afterwards. Without one the
    watchdog gets no hook, which is better than a reset after which the integration
    cannot reach the stick.
    """
    if port.startswith(BY_ID_DIR):
        return UsbLinkReset(port)
    _LOGGER.warning(
        "Not using the option to reset the USB link of the CUL, because its port %s is"
        " not a link under %s. Select the by-id path of the CUL in the reconfigure flow"
        " or turn the option off",
        port,
        BY_ID_DIR,
    )
    return None


class FhtCulRuntime:
    """Everything a loaded config entry keeps (entry.runtime_data)."""

    # These four exist once async_start() got to them.
    cul: CulCoordinator
    # The registry id of the CUL, which is the via_device_id of the FHT devices.
    cul_device_id: str
    timesync: TimeSync

    def __init__(
        self,
        hass: HomeAssistant,
        entry: FhtCulConfigEntry,
        store: Store[dict[str, Any]],
        stored: dict[str, Any] | None,
    ) -> None:
        """Initialize the runtime with the parts that do not need the open port."""
        self._hass = hass
        self._entry = entry
        options = entry.options
        self._ignored = frozenset(options.get(CONF_IGNORED_DEVICES, []))

        self.network = FhtNetwork(
            now=dt_util.utcnow,
            stale_after={
                DeviceType.FHT80B: timedelta(
                    hours=options.get(
                        CONF_FHT80B_STALE_HOURS, DEFAULT_FHT80B_STALE_HOURS
                    )
                ),
                DeviceType.FHT80TF: timedelta(
                    hours=options.get(
                        CONF_FHT80TF_STALE_HOURS, DEFAULT_FHT80TF_STALE_HOURS
                    )
                ),
            },
            ignored=self._ignored,
            auto_add=options.get(CONF_AUTO_ADD_DEVICES, True),
        )
        self.network.load(stored)
        self.network.on_pending_retired = self._handle_pending_retired
        self.network.on_pairing_changed = self._handle_pairing_changed
        self.saver = ThrottledSave(store, self.network.to_dict, SAVE_DELAY_SECONDS)
        self.issues = IssueTracker(
            hass, entry.entry_id, self.network, entry.data[CONF_DEVICE]
        )
        # Latest lines for the diagnostics download.
        self.raw_lines: deque[tuple[datetime, str]] = deque(maxlen=RAW_LINE_HISTORY)

        port = entry.data[CONF_DEVICE]
        recovery = options.get(SECTION_RECOVERY, {})
        self.transport = CulTransport(
            port,
            entry.data[CONF_HOUSE_CODE],
            on_message=self._handle_line,
            on_connection_change=self._handle_connection,
            allow_reboot=recovery.get(CONF_ALLOW_REBOOT, False),
            create_task=self._create_task,
        )
        self.watchdog = CulWatchdog(
            self.transport,
            on_event=self._handle_watchdog_event,
            usb_reset=(
                _create_usb_reset(port)
                if recovery.get(CONF_ALLOW_USB_RESET, False)
                else None
            ),
            create_task=self._create_task,
        )

        self.outbox = FhtOutbox(
            self.transport,
            self.network,
            spawn=self._create_task,
            listener=self._handle_outbox_event,
            local_now=dt_util.now,
        )
        self.refresh = RefreshPlanner(
            self.network,
            self.outbox,
            spawn=self._create_task,
            read_week_programs=options.get(
                CONF_READ_WEEK_PROGRAMS, DEFAULT_READ_WEEK_PROGRAMS
            ),
        )

        self._has_timesync = False
        self._link_lost = False
        # The thermostat that the log said each contact seems to belong to.
        self._announced: dict[str, str] = {}
        # Whether the commands were dropped already for the outage that is going on.
        self._outage_dropped = False
        self._house_code_writes = 0
        self._uptime: timedelta | None = None
        self._shut_down = False
        self._shutdown_lock = asyncio.Lock()
        self._unsubscribers: list[CALLBACK_TYPE] = []

    @classmethod
    async def async_create(cls, hass: HomeAssistant, entry: FhtCulConfigEntry) -> Self:
        """Restore the device state and build the runtime; the port stays shut."""
        store = create_store(hass, entry.entry_id)
        return cls(hass, entry, store, await store.async_load())

    async def async_start(self) -> None:
        """Poll the CUL once, register its device and start the background work.

        The port has to be open. Whatever fails here, async_shutdown() releases it.
        """
        hass = self._hass
        self.cul = CulCoordinator(hass, self._entry, self.transport)
        await self.cul.async_config_entry_first_refresh()
        self._restore_pending(self.cul.data)

        self.cul_device_id = self._async_register_devices()
        self.timesync = TimeSync(hass, self.network, self.outbox, self.issues)
        self._has_timesync = True
        self.watchdog.start()
        self.timesync.start()
        self._unsubscribers.append(
            async_track_time_interval(hass, self._handle_tick, STALE_CHECK_INTERVAL)
        )
        self._unsubscribers.append(self.cul.async_add_listener(self._handle_cul_poll))
        self.issues.async_cul_status(self.cul.data)
        self.issues.async_start()

    async def async_shutdown(self, _event: Event | None = None) -> None:
        """Stop the background work, save the state and close the port.

        Home Assistant starts the on_unload callbacks of an entry one after the other
        without waiting for each to finish, so the order has to live in one function.
        The stop event calls it too (hence the unused event), and later calls do
        nothing.
        """
        async with self._shutdown_lock:
            if self._shut_down:
                return
            self._shut_down = True
            while self._unsubscribers:
                self._unsubscribers.pop()()
            try:
                if self._has_timesync:
                    self.timesync.stop()
                await self.refresh.async_stop()
                await self.outbox.async_stop()
                await self.watchdog.stop()
                await self.saver.async_save_now()
            finally:
                # The port has to close even when the save fails.
                await self.transport.close()
                self.issues.async_stop()
                if self._entry.disabled_by is not None:
                    # Issues carry no config entry in this release, so nothing else
                    # removes them. On a plain unload they stay for the dismissals.
                    async_delete_issues(self._hass)

    def _restore_pending(self, status: CulStatus) -> None:
        """Keep the commands in flight from the store if the CUL still holds them.

        The messages of an earlier run are in the buffers of the CUL only if it did not
        boot since, and a command that is older than the timeout is over whatever the
        CUL holds. Whatever stays is waited for again like a message of this run.
        """
        self._uptime = dt_util.utcnow() - status.booted_at
        if self.network.note_cul_boot(status.booted_at):
            self.network.invalidate_pending(InvalidationReason.CUL_RESET)
        self.network.expire_pending()
        self.outbox.resume(status.fht_buffer_free_bytes)

    def _create_task(
        self, coro: Coroutine[Any, Any, None], name: str
    ) -> asyncio.Task[None]:
        """Start a task that Home Assistant cancels when the entry unloads or stops."""
        return self._entry.async_create_background_task(self._hass, coro, name)

    def _async_register_devices(self) -> str:
        """Register the CUL device and drop the ignored devices; return the CUL id."""
        device_registry = dr.async_get(self._hass)
        entry_id = self._entry.entry_id
        # The CUL device must exist before the FHT devices name it as their via device.
        house_code = self.transport.house_code
        connections = {(CONNECTION_HOUSE_CODE, house_code)}
        cul_device = device_registry.async_get_or_create(
            config_entry_id=entry_id,
            identifiers={(DOMAIN, CUL_IDENTIFIER)},
            connections=connections,
            manufacturer="busware",
            model=CUL_MODEL,
            name="CUL",
            # The stick has no serial number, so this is the code it is known by: the
            # house code as the numbers of the display, as the user typed it.
            serial_number=format_display_code(house_code),
            sw_version=firmware_version(self.transport.version),
        )
        if cul_device.connections != connections:
            # The registry only adds connections, so the house code that the user
            # replaced in the reconfigure flow would stay next to the new one.
            device_registry.async_update_device(
                cul_device.id, new_connections=connections
            )
        # Ignored devices leave Home Assistant together with their entities.
        for device_id in self._ignored:
            if device := device_registry.async_get_device_by_identifier(
                (DOMAIN, device_id), entry_id
            ):
                device_registry.async_remove_device(device.id)
        return cul_device.id

    @callback
    def _handle_line(self, line: str) -> None:
        _LOGGER.debug("Received from CUL: %s", line)
        self.raw_lines.append((dt_util.utcnow(), line[:RAW_LINE_MAX_LENGTH]))
        self.watchdog.handle_line(line)
        update = self.network.process(parse_line(line))
        self.outbox.handle_update(update)
        self.refresh.handle_update(update)
        entry_id = self._entry.entry_id
        if isinstance(update, DeviceUpdate):
            if update.new:
                self._announce_new_device(update.device)
            else:
                async_dispatcher_send(
                    self._hass, signal_device_update(entry_id, update.device.device_id)
                )
            self.issues.async_check_device(update.device)
            self.saver.schedule()
        elif isinstance(update, CandidateUpdate):
            if update.new:
                _LOGGER.info(
                    "Heard FHT device %s, which is not added, because new devices are"
                    " not added automatically",
                    update.candidate.label,
                )
                self.saver.schedule()
        elif isinstance(update, NoticeUpdate):
            if update.kind is NoticeKind.EOB and not update.claimed:
                # Some message did not fit, and which one is unknown.
                self.network.invalidate_pending(InvalidationReason.UNCLAIMED_EOB)
            async_dispatcher_send(self._hass, signal_cul_update(entry_id))

    def _announce_new_device(self, device: FhtDevice) -> None:
        """Log a device that joined the network and let the platforms add it."""
        _LOGGER.info("New FHT device %s", device.label)
        async_dispatcher_send(
            self._hass, signal_new_device(self._entry.entry_id), device
        )

    @callback
    def async_adopt_candidate(self, device_id: str) -> bool:
        """Add a device that the user picked from the candidates; False if it is gone."""
        device = self.network.adopt(device_id)
        if device is None:
            return False
        self._announce_new_device(device)
        self.saver.schedule()
        return True

    def contact_assignment(self, contact_id: str) -> ContactAssignment:
        """Return the thermostat of a window contact and where that comes from.

        The choice of the user always wins, also when it is none. Without one, the
        thermostat that the radio traffic suggests counts, as a suggestion only. A
        thermostat that the network does not know any more is no thermostat.
        """
        chosen: Mapping[str, str] = self._entry.options.get(
            CONF_CONTACT_THERMOSTATS, {}
        )
        confidence: str | None = None
        events: int | None = None
        if (thermostat_id := chosen.get(contact_id)) is not None:
            source = ASSIGNMENT_MANUAL
        else:
            source = ASSIGNMENT_SUGGESTED
            if evidence := self.network.pairing.evidence(contact_id):
                thermostat_id = evidence.thermostat
                confidence = evidence.confidence.value
                events = evidence.events
        thermostat = self.network.devices.get(thermostat_id or "")
        if isinstance(thermostat, FhtRoomController):
            return ContactAssignment(thermostat, source, confidence, events)
        return ContactAssignment(None, None)

    def window_contacts(self, thermostat_id: str) -> list[str]:
        """Return the addresses of the window contacts that the user gave a thermostat.

        A suggestion is not included, because it is not applied until the user says so.
        """
        chosen: Mapping[str, str] = self._entry.options.get(
            CONF_CONTACT_THERMOSTATS, {}
        )
        return sorted(
            contact.code.upper()
            for contact_id, chosen_id in chosen.items()
            if chosen_id == thermostat_id
            and isinstance(
                contact := self.network.devices.get(contact_id), FhtWindowContact
            )
        )

    @callback
    def async_remove_device(self, device_id: str) -> None:
        """Remove a device that the user deleted from the device registry.

        A device that is silent is forgotten and returns with its next telegram. One
        that still transmits would come back at once, so it is ignored: its ID joins
        the ignored devices of the options, which this does not reload.
        """
        device = self.network.devices.get(device_id)
        if device is not None and not self.network.is_stale(device):
            self.network.ignore(device_id)
            options = self._entry.options
            ignored = {*options.get(CONF_IGNORED_DEVICES, []), device_id}
            self._hass.config_entries.async_update_entry(
                self._entry,
                options={**options, CONF_IGNORED_DEVICES: sorted(ignored)},
            )
        self.network.remove(device_id)
        self._announced.pop(device_id, None)
        self.timesync.async_forget_device(device_id)
        self.issues.async_forget_device(device_id)
        # The platforms drop the device, so that its next telegram adds it again.
        async_dispatcher_send(
            self._hass, signal_device_removed(self._entry.entry_id), device_id
        )
        self.saver.schedule()

    @callback
    def _handle_pairing_changed(self, contact_id: str) -> None:
        """Tell the contact, and the log if the radio suggests another thermostat."""
        suggested = self.network.pairing.suggestion(contact_id)
        if suggested is None:
            self._announced.pop(contact_id, None)
            _LOGGER.debug("The suggested thermostat of %s is unclear now", contact_id)
        elif suggested != self._announced.get(contact_id):
            # More evidence for the same thermostat changes the attributes only.
            self._announced[contact_id] = suggested
            if contact_id not in self._entry.options.get(CONF_CONTACT_THERMOSTATS, {}):
                _LOGGER.info(
                    "%s seems to belong to %s, because the thermostat reacted when the"
                    " contact changed its state. You can assign it under Configure",
                    device_label(contact_id),
                    device_label(suggested),
                )
        self._notify_device(contact_id)

    @callback
    def _handle_connection(self, connected: bool) -> None:
        if self._shut_down:
            # Closing the port is part of the shutdown and no loss of the link.
            return
        # The entities read the outage from the network when the signal arrives.
        self.network.set_link(connected)
        # A connect is a recovery only after a loss, and a loss is new only while the
        # link was up, so the first connect and a repeated report change nothing.
        changed = connected == self._link_lost
        self._link_lost = not connected
        if changed:
            self._log_connection(connected)
        if connected:
            self._outage_dropped = False
            self.refresh.note_connected()
            self._drop_lost_commands()
        self.issues.async_cul_connection(connected)
        self.watchdog.handle_connection(connected)
        async_dispatcher_send(self._hass, signal_cul_update(self._entry.entry_id))
        if changed and connected:
            # The next poll can be minutes away, and the CUL may have lost its state.
            self._create_task(
                self.cul.async_request_refresh(), "culfw refresh after reconnect"
            )

    def _drop_lost_commands(self) -> None:
        """Retire the commands in flight that a connect shows to be lost.

        The send buffers are empty when the CUL started since, and when the transport
        wrote the house code, which clears them. Commands for the controllers may be
        gone then, and the controllers are read again.
        """
        writes = self.transport.house_code_writes
        if writes != self._house_code_writes:
            self._house_code_writes = writes
            self.network.invalidate_pending(InvalidationReason.HOUSE_CODE_REWRITE)
            self.refresh.note_cul_reset()
        if self.transport.cul_was_reset:
            self.network.invalidate_pending(InvalidationReason.CUL_RESET)
            self.refresh.note_cul_reset()

    def _log_connection(self, connected: bool) -> None:
        """Log the loss of the link or its recovery, one line each.

        The transport reports a loss only when a working connection ends, so a CUL
        that stays away adds no line however often the reconnect fails.
        """
        port = self.transport.port
        if connected:
            _LOGGER.info("CUL on %s is back online", port)
        else:
            _LOGGER.info(
                "CUL on %s is unavailable: %s",
                port,
                self.transport.statistics.last_error,
            )

    @callback
    def _handle_outbox_event(self, event: OutboxEvent) -> None:
        if isinstance(event, CommandsDropped):
            # The outbox logged the drop. The request returned long ago, so the event
            # is how the logbook and the automations learn that the value never left.
            self._fire_command_expired(
                event.device_id, event.commands, event.failure.value
            )
            self._notify_device(event.device_id)
        elif isinstance(event, ChannelBroken):
            # Nothing automatic goes to the controller now, and nobody would notice
            # that its clock runs off, so the user is told.
            self._hass.bus.async_fire(EVENT_CHANNEL_BROKEN, {"device": event.device_id})
            self.issues.async_channel_broken(event.device_id)
        elif isinstance(event, ChannelRecovered):
            self.issues.async_channel_recovered(event.device_id)
        elif isinstance(event, MessageSent):
            # The commands wait for the echo from now on, which a view of the pending
            # requests tells apart from waiting for the turn.
            async_dispatcher_send(
                self._hass, signal_command_update(self._entry.entry_id, event.device_id)
            )
        if isinstance(event, CommandsDropped | ChannelRecovered):
            # What the controller holds is unknown now, so it is read again.
            self.refresh.note_commands_lost(event.device_id)

    @callback
    def _handle_pending_retired(self, retired: PendingRetired) -> None:
        """Tell the user and the entities that requested commands are gone.

        The request returned long ago, so the log line and the event are how the user
        learns that the controller did not take the value. The controllers are read
        again, because what they hold is unknown now.
        """
        reason = retired.reason.value
        _LOGGER.info(
            "Pending FHT80b commands are gone (%d): %s",
            len(retired.commands),
            reason.replace("_", " "),
        )
        device_ids = sorted({device_id for device_id, _ in retired.commands})
        for device_id in device_ids:
            self._fire_command_expired(
                device_id,
                tuple(c for d, c in retired.commands if d == device_id),
                reason,
            )
            self.refresh.note_commands_lost(device_id)
            self._notify_device(device_id)
            if retired.reason is InvalidationReason.EXPIRED:
                self.outbox.reset(device_id)
        if retired.reason is not InvalidationReason.EXPIRED:
            # The buffers of the CUL cannot be trusted, so no message is awaited.
            self.outbox.reset()
        self.saver.schedule()

    def _fire_command_expired(
        self, device_id: str, commands: tuple[PendingCommand, ...], reason: str
    ) -> None:
        """Fire the event of each command that no echo confirmed."""
        for command in commands:
            self._hass.bus.async_fire(
                EVENT_COMMAND_EXPIRED,
                {
                    "device": device_id,
                    "code": command_name(command.code),
                    "requested": _requested_value(command),
                    "reason": reason,
                },
            )

    def _notify_device(self, device_id: str) -> None:
        """Let the entities of a controller write their state again."""
        async_dispatcher_send(
            self._hass, signal_device_update(self._entry.entry_id, device_id)
        )

    @callback
    def _handle_watchdog_event(self, event: WatchdogEvent) -> None:
        if (
            event.kind is WatchdogEventKind.SUCCEEDED
            and event.step is WatchdogStep.CLEAR_BUFFER
        ):
            # The purge emptied the buffers, so every command in flight is gone.
            self.network.invalidate_pending(InvalidationReason.BUFFER_PURGE)
        self.issues.async_watchdog_event(event)
        self._hass.bus.async_fire(
            EVENT_WATCHDOG,
            {
                "kind": event.kind,
                "reason": event.reason,
                "step": event.step,
                "detail": event.detail,
            },
        )

    @callback
    def _handle_tick(self, _now: datetime) -> None:
        async_dispatcher_send(self._hass, signal_tick(self._entry.entry_id))
        self._drop_commands_of_long_outage()
        self.network.expire_pending()
        self.issues.async_check_all()
        self.refresh.tick()

    def _drop_commands_of_long_outage(self) -> None:
        """Retire all commands once the link was down for longer than the grace period.

        The entities are unavailable then, and a value that was requested before the
        outage is too old to be sent when the link returns. It happens once per outage.
        """
        down = self.network.link_down_for()
        if down is None or down <= CUL_UNREACHABLE_AFTER or self._outage_dropped:
            return
        self._outage_dropped = True
        self.network.invalidate_pending(
            InvalidationReason.LINK_OUTAGE, include_staged=True
        )

    @callback
    def _handle_cul_poll(self) -> None:
        if not self.cul.last_update_success:
            self.issues.async_cul_status(None)
            return
        status = self.cul.data
        self.issues.async_cul_status(status)
        uptime = dt_util.utcnow() - status.booted_at
        previous, self._uptime = self._uptime, uptime
        self.network.cul_booted_at = status.booted_at
        if previous is not None and uptime < previous - _UPTIME_JITTER:
            # The CUL started since the last poll and lost its buffers with it.
            self.network.invalidate_pending(InvalidationReason.CUL_RESET)
            self.refresh.note_cul_reset()
