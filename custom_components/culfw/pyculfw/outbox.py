"""Stage commands for FHT80b room controllers and queue them without clogging the CUL."""

import asyncio
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum, StrEnum
import logging
import string
from typing import Final

from .commands import check_command, date_time_commands
from .const import (
    AUTOMATIC_MIN_CREDIT_10MS,
    BREAKER_THRESHOLD,
    BUFFER_RESERVE_BYTES,
    COALESCE_DELAY,
    CREDIT_WAIT_LIMIT,
    DEFER_RETRY,
    FHT_BUFFER_SIZE_BYTES,
    FHT_MAX_COMMANDS,
    GATE_POLL_INTERVAL,
    GATE_TIMEOUT,
    MIN_CREDIT_10MS,
    SEND_MAX_SILENCE,
    USE_T02_GATE,
)
from .devices import (
    DeviceType,
    DeviceUpdate,
    FhtNetwork,
    FhtRoomController,
    NetworkUpdate,
    display_code,
)
from .errors import CulCommandBlockedError, CulError, FhtValueError
from .parser import FhtCode, FhtMode, is_week_program
from .pending import PendingCommand, PendingQueue, PendingState
from .tasks import CreateTask, cancel_task, start_task
from .transport import CulTransport, TransportState, fht_send_size

_LOGGER = logging.getLogger(__name__)

# The sends that the diagnostics remember, so that the credit around the traffic of a
# restarted controller can be read afterwards.
SEND_LOG_SIZE: Final = 20

_HOLIDAY_MODES: Final = frozenset({FhtMode.HOLIDAY, FhtMode.HOLIDAY_SHORT})
_HOLIDAY_CODES: Final = frozenset({FhtCode.HOLIDAY1, FhtCode.HOLIDAY2})
_REPORT_CODES: Final = frozenset({FhtCode.REPORT1, FhtCode.REPORT2})
_TIME_CODES: Final = frozenset(
    {FhtCode.YEAR, FhtCode.MONTH, FhtCode.DAY, FhtCode.HOUR, FhtCode.MINUTE}
)


def _system_local_now() -> datetime:
    """Return the local time of the system."""
    return datetime.now().astimezone()


# The order inside a message. The mode comes first, because the controller reads the
# holiday end and the temperature that follow in the light of it, and the minute comes
# last, because its echo proves that the whole time message arrived.
_RANK: Final[Mapping[int, int]] = {
    FhtCode.MODE: 0,
    FhtCode.HOLIDAY1: 1,
    FhtCode.HOLIDAY2: 2,
    FhtCode.DESIRED_TEMP: 3,
    FhtCode.MINUTE: 5,
}
_DEFAULT_RANK: Final = 4


class SendFailure(StrEnum):
    """Why a message was not queued."""

    UNKNOWN_DEVICE = "unknown_device"
    DEVICE_SILENT = "device_silent"
    DEVICE_UNCONFIRMED = "device_unconfirmed"
    DEVICE_UNRESPONSIVE = "device_unresponsive"
    NOT_CONNECTED = "not_connected"
    NO_CREDIT = "no_credit"
    CREDIT_EXHAUSTED = "credit_exhausted"
    BUFFER_FULL = "buffer_full"
    NOT_QUEUED = "not_queued"
    BLOCKED = "blocked"
    CUL_ERROR = "cul_error"


# The log text of each failure. Its fields are the placeholders of the translated
# exception, so the library and the integration describe a failure with the same facts.
SEND_FAILURE_DETAILS: Final[Mapping[SendFailure, str]] = {
    SendFailure.UNKNOWN_DEVICE: "FHT80b {code} was never heard",
    SendFailure.DEVICE_SILENT: "FHT80b {code} has been silent for {minutes} minutes",
    SendFailure.DEVICE_UNCONFIRMED: "FHT80b {code} never echoed a command of this CUL",
    SendFailure.DEVICE_UNRESPONSIVE: "FHT80b {code} did not echo the last messages",
    SendFailure.NOT_CONNECTED: "The CUL is {state}",
    SendFailure.NO_CREDIT: "Duty-cycle credit {credit} ms < {minimum} ms",
    SendFailure.CREDIT_EXHAUSTED: (
        "Duty-cycle credit stayed below {minimum} ms for {minutes} minutes"
    ),
    SendFailure.BUFFER_FULL: (
        "{free} bytes free, the message needs {needed} + {reserve} bytes reserve"
    ),
    SendFailure.NOT_QUEUED: "culfw printed EOB for {count} commands",
    SendFailure.BLOCKED: "The CUL transport does not allow the command",
    SendFailure.CUL_ERROR: "The CUL did not answer the command, its state is {state}",
}


def _fields(text: str) -> frozenset[str]:
    """Return the field names of a format string."""
    return frozenset(
        field for _, field, _, _ in string.Formatter().parse(text) if field is not None
    )


class FhtSendError(Exception):
    """A message for an FHT80b was not queued.

    The facts of the failure are separate values, so that the user gets a sentence of
    its own for each failure and not a technical detail glued to it. The text of the
    library error that caused the failure goes into `detail` for the log and never into
    the placeholders.
    """

    def __init__(
        self, failure: SendFailure, *, reason: str = "", **facts: str | int
    ) -> None:
        """Initialize the error with the failure and the facts that describe it.

        Raises:
            ValueError: The facts are not the ones that the failure is described by.
        """
        template = SEND_FAILURE_DETAILS[failure]
        if facts.keys() != _fields(template):
            raise ValueError(f"{failure} is described by {sorted(_fields(template))}")
        self.placeholders = {name: str(value) for name, value in facts.items()}
        self.detail = template.format_map(self.placeholders)
        if reason:
            self.detail = f"{self.detail}: {reason}"
        super().__init__(f"{failure}: {self.detail}")
        self.failure = failure


@dataclass(frozen=True, slots=True)
class CommandsDropped:
    """Commands that were accepted and that cannot be sent any more.

    The commands are in the state INVALIDATED. The owner tells the user, because the
    request returned long before.
    """

    device_id: str
    commands: tuple[PendingCommand, ...]
    failure: SendFailure
    detail: str


@dataclass(frozen=True, slots=True)
class ChannelState:
    """What the outbox knows about the command channel to one controller."""

    in_flight: bool
    staged: int
    trusted: bool
    broken: bool
    unechoed: int
    probes: int


@dataclass(slots=True)
class SendRecord:
    """The duty cycle credit around one message, for the diagnostics.

    The credit before is what the CUL reported when the message was queued, and the
    credit after is what it reported when the message was over. The radio spends the
    credit in between, in the time slot of the controller, so the two numbers and the
    seconds in flight (the credit grows by one unit per second) show what the message
    and everything else on the air cost. The values are units of 10 ms.
    """

    at: datetime
    device_id: str
    automatic: bool
    commands: int
    credit_before_10ms: int | None
    outcome: str | None = None
    seconds_in_flight: float | None = None
    credit_after_10ms: int | None = None
    synchronizing: bool = False


@dataclass(frozen=True, slots=True)
class Capacity:
    """What the CUL had room for when a message was checked.

    The credit is None when the check did not read it.
    """

    free_bytes: int
    credit_10ms: int | None


@dataclass(frozen=True, slots=True)
class ChannelBroken:
    """A controller did not echo the last messages, so nothing automatic goes to it."""

    device_id: str


@dataclass(frozen=True, slots=True)
class ChannelRecovered:
    """A controller that was cut off from automatic messages echoed a command."""

    device_id: str


@dataclass(frozen=True, slots=True)
class MessageSent:
    """A message for a controller went into the buffer of the CUL.

    Its commands are QUEUED from now on, so the owner can tell a request that still
    waits for its turn from one that waits for the echo.
    """

    device_id: str


type OutboxEvent = CommandsDropped | ChannelBroken | ChannelRecovered | MessageSent


@dataclass(frozen=True, slots=True)
class OutboxTiming:
    """The waiting times of the outbox, so that tests can shorten them."""

    coalesce_delay: timedelta = COALESCE_DELAY
    gate_timeout: timedelta = GATE_TIMEOUT
    gate_poll_interval: timedelta = GATE_POLL_INTERVAL
    defer_retry: timedelta = DEFER_RETRY


class _Kind(IntEnum):
    """What a staged message is for. A lower value is sent first."""

    URGENT = 0
    NORMAL = 1
    PROGRAM = 2
    REPORT = 3


class _Outcome(StrEnum):
    """How the wait for the end of a message in flight ended."""

    ECHOED = "echoed"
    SUPERSEDED = "superseded"
    DRAINED = "drained"
    TIMEOUT = "timeout"


@dataclass(eq=False, slots=True)
class _Staged:
    """The commands for one message that wait for their turn.

    Every command is a live PendingCommand of the controller, and `due` is the loop
    time at which the message may be sent.
    """

    message_id: int
    kind: _Kind
    automatic: bool
    due: float
    commands: dict[int, PendingCommand] = field(default_factory=dict)
    # The loop time at which the message first found the duty cycle credit too low, None
    # while it did not or since the credit was enough again.
    starved_since: float | None = None
    # Whether the message was held back because the controller counted down its
    # synchronization, so that it is counted once.
    held: bool = False


@dataclass(eq=False, slots=True)
class _InFlight:
    """A message that is in the buffer of the CUL and has not left it yet."""

    message_id: int
    last_code: int
    sent_at: float
    echoed: bool = False
    report: bool = False
    record: SendRecord | None = None


@dataclass(eq=False, slots=True)
class _Channel:
    """The command channel to one controller.

    A controller is trusted with automatic messages once it echoed a command (the
    device keeps that in `echoed_at`, so a restart does not forget it), once it echoed
    a time message, when the user added it, or when the user addressed it in this run.
    """

    device: FhtRoomController
    staged: list[_Staged] = field(default_factory=list)
    in_flight: _InFlight | None = None
    addressed: bool = False
    unechoed: int = 0
    broken: bool = False
    probes: int = 0

    @property
    def device_id(self) -> str:
        """Return the id of the controller."""
        return self.device.device_id

    @property
    def code(self) -> str:
        """Return the house code of the controller."""
        return self.device.code

    @property
    def label(self) -> str:
        """Return the name of the controller for the log."""
        return self.device.label

    @property
    def shown_code(self) -> str:
        """Return the house code of the controller as its display shows it."""
        return display_code(DeviceType.FHT80B, self.device.code)

    @property
    def queue(self) -> PendingQueue:
        """Return the commands in flight to the controller."""
        return self.device.pending

    @property
    def trusted(self) -> bool:
        """Return True if automatic messages may go to the controller."""
        return (
            self.addressed
            or self.device.confirmed
            or self.device.echoed_at is not None
            or self.device.time_ack is not None
        )


def find_controller(network: FhtNetwork, device_id: str) -> FhtRoomController:
    """Return the controller that may be sent a message, or raise FhtSendError.

    A controller that was never heard is no target, and neither is one that has been
    silent for SEND_MAX_SILENCE: it would never collect the message.
    """
    device = network.devices.get(device_id)
    code = display_code(DeviceType.FHT80B, device_id.partition("_")[2])
    if not isinstance(device, FhtRoomController):
        raise FhtSendError(SendFailure.UNKNOWN_DEVICE, code=code)
    silent = network.silent_for(device)
    if silent is None:
        raise FhtSendError(SendFailure.UNKNOWN_DEVICE, code=code)
    if silent > SEND_MAX_SILENCE:
        raise FhtSendError(
            SendFailure.DEVICE_SILENT,
            code=code,
            minutes=int(silent.total_seconds() // 60),
        )
    return device


async def check_capacity(
    transport: CulTransport, size: int, *, min_credit: int | None = MIN_CREDIT_10MS
) -> Capacity:
    """Return the room in the CUL if a message of `size` bytes fits.

    culfw keeps every message until the controller collects it, so the buffer has to
    keep BUFFER_RESERVE_BYTES free after the message, and the duty cycle credit has to
    be at least `min_credit` units unless that is None. A caller that can wait for the
    credit passes None, because a lack of credit heals by itself while a full buffer
    needs the controllers to collect their messages.
    """
    credit: int | None = None
    try:
        if min_credit is not None:
            credit = (await transport.get_credit()).credit_10ms
            if credit < min_credit:
                raise FhtSendError(
                    SendFailure.NO_CREDIT,
                    credit=credit * 10,
                    minimum=min_credit * 10,
                )
        free = await transport.get_fht_buffer_free()
    except CulCommandBlockedError as err:
        raise FhtSendError(SendFailure.BLOCKED, reason=str(err)) from err
    except CulError as err:
        raise FhtSendError(
            SendFailure.CUL_ERROR, reason=str(err), state=transport.state
        ) from err
    if free - size < BUFFER_RESERVE_BYTES:
        raise FhtSendError(
            SendFailure.BUFFER_FULL,
            free=free,
            needed=size,
            reserve=BUFFER_RESERVE_BYTES,
        )
    return Capacity(free, credit)


async def queue_message(
    transport: CulTransport,
    network: FhtNetwork,
    code: str,
    commands: Sequence[tuple[int, int]],
    free_before: int,
) -> None:
    """Queue a message in the CUL and judge whether it took.

    culfw prints EOB for a message that does not fit, and the line arrives before the
    answer to the T03 that follows, so the EOB counter of the network around the call
    tells. The buffer is only the second source: when the free space did not shrink
    and no EOB came, the controller may have collected the message in the meantime,
    which is no failure.

    Raises:
        FhtSendError: The transport refused the message, failed, or culfw printed EOB.
    """
    eob_before = network.eob_count
    try:
        with network.sending():
            await transport.send_fht(code, commands)
            free_after = await transport.get_fht_buffer_free()
    except CulCommandBlockedError as err:
        # The transport refused the line, so nothing went to the CUL and the stick is
        # not to blame.
        raise FhtSendError(SendFailure.BLOCKED, reason=str(err)) from err
    except CulError as err:
        raise FhtSendError(
            SendFailure.CUL_ERROR, reason=str(err), state=transport.state
        ) from err
    if network.eob_count != eob_before:
        raise FhtSendError(SendFailure.NOT_QUEUED, count=len(commands))
    if free_after >= free_before:
        _LOGGER.debug(
            "The buffer did not shrink after queuing FHT80b %s (%d -> %d bytes free)",
            display_code(DeviceType.FHT80B, code),
            free_before,
            free_after,
        )


def _check_request(commands: Mapping[int, int]) -> dict[int, int]:
    """Return the commands of a request or raise FhtValueError.

    The values are raw bytes, so they are quantized already, and the checks are those
    of the command builders. The holiday modes only work together with their end.
    """
    if not 1 <= len(commands) <= FHT_MAX_COMMANDS:
        raise FhtValueError(f"1 to {FHT_MAX_COMMANDS} commands, got {len(commands)}")
    for code, raw in commands.items():
        check_command(code, raw)
    if commands.keys() & _REPORT_CODES and len(commands) > 1:
        raise FhtValueError("A report request needs a message of its own")
    holiday = commands.get(FhtCode.MODE) in _HOLIDAY_MODES
    if holiday and _HOLIDAY_CODES - commands.keys():
        raise FhtValueError("The holiday modes need the end of the holiday")
    if commands.keys() & _HOLIDAY_CODES and not holiday:
        raise FhtValueError("The end of a holiday needs the holiday mode")
    return dict(commands)


def _kind_of(commands: Mapping[int, int], *, urgent: bool) -> _Kind:
    """Return what the message of a request is for."""
    if urgent:
        return _Kind.URGENT
    if commands.keys() & _REPORT_CODES:
        return _Kind.REPORT
    if all(map(is_week_program, commands)):
        return _Kind.PROGRAM
    return _Kind.NORMAL


def _in_message_order[T](commands: Mapping[int, T]) -> list[int]:
    """Return the codes in the order they travel in a message."""
    return sorted(commands, key=lambda code: _RANK.get(code, _DEFAULT_RANK))


class FhtOutbox:
    """Take commands for FHT80b controllers and queue them one message at a time.

    culfw keeps every message in a buffer of 174 bytes until the controller collects
    it in its next time slot, about every 2 minutes, and it delivers one message per
    slot. A controller that never talks again never collects, and a full buffer drops
    new messages for every controller. So commands do not go to the CUL as they come:

    1. `request()` checks at once what can be checked (the link, the target, the
       values and the room in the buffer, and for an automatic request the credit too,
       which has to be AUTOMATIC_MIN_CREDIT_10MS to keep a reserve for the user)
       and raises FhtSendError or FhtValueError. A request of the user is not refused
       for a lack of credit, because that heals by itself: the credit grows by 10 ms
       per second. Accepted commands are staged as pending, so an entity shows them as
       requested, and the call returns.
    2. Staged commands of a controller are merged: the last value of a command wins,
       the mode goes before the temperature, a new mode drops holiday values it does
       not carry, and the group of mode, holiday end and temperature is never split.
       Time messages (urgent), report requests and requests for nothing but week program
       times are messages of their own. The times go after the other commands of the
       user and before the report requests, one message for each request, so a week of
       seven days takes seven slots.
    3. A flusher task sends one message of up to 8 commands COALESCE_DELAY after the
       first command (at once when the message is full, or urgent), and only while
       no earlier message for that controller is in the CUL. Low credit, a full
       buffer or a controller that counts down its synchronization with its valves
       defer the message, and nothing is lost (during the countdown culfw answers the
       controller about every second and pays credit for it while a message waits in
       its buffer, so the message waits here instead). A message that finds the credit
       too low for CREDIT_WAIT_LIMIT in a row is dropped with the failure
       CREDIT_EXHAUSTED, so a radio that stays busy does not hold commands for ever.
    4. A message is in flight until the echo of its last command, until the buffer
       shows that it left, or until GATE_TIMEOUT. The echoes arrive through
       `handle_update()`.

    A controller that did not echo BREAKER_THRESHOLD messages in a row does not collect
    (it is silent but alive, or paired to another central). Anything automatic to it
    stops, a staged automatic message is dropped, and only commands that the user
    asked for go on. Any echo ends this. Automatic requests (`automatic=True`, for
    example the time sync and the read-back) go only to controllers that echoed a
    command or that the user addressed. An unknown controller gets one report2 as a
    probe until an echo arrives.

    A failure after the request cannot be raised to the caller any more. The listener
    gets a CommandsDropped event for it.
    """

    def __init__(
        self,
        transport: CulTransport,
        network: FhtNetwork,
        *,
        spawn: CreateTask = start_task,
        listener: Callable[[OutboxEvent], None] | None = None,
        timing: OutboxTiming | None = None,
        local_now: Callable[[], datetime] = _system_local_now,
    ) -> None:
        """Initialize the outbox.

        The `spawn` factory starts the flusher, so that the owner ties it to its own
        lifetime. The task ends when nothing is staged or in flight, and the next
        request starts it again. `local_now` returns the local time that a message
        with the date and the clock gets when it goes to the CUL.
        """
        self._transport = transport
        self._network = network
        self._spawn = spawn
        self._listener = listener
        self._timing = timing or OutboxTiming()
        self._local_now = local_now
        self._coalesce_seconds = self._timing.coalesce_delay.total_seconds()
        self._channels: dict[str, _Channel] = {}
        # Requests check and stage one after the other, because the check reads the CUL.
        self._request_lock = asyncio.Lock()
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        # The free bytes of the buffer before the oldest message in flight was queued.
        # When the buffer is that free again, every message of the outbox left it.
        self._idle_free: int | None = None
        self._next_poll = 0.0
        self._fht_queue: dict[str, list[tuple[int, int]]] | None = None
        self._fht_queue_at: datetime | None = None
        self._send_log: deque[SendRecord] = deque(maxlen=SEND_LOG_SIZE)
        # The records of messages that are over and wait for the credit after them.
        self._unmeasured: list[SendRecord] = []
        self._held_for_sync = 0

    @property
    def fht_queue(self) -> dict[str, list[tuple[int, int]]] | None:
        """Return the last dump of the FHT buffer that could be read, for diagnostics.

        It is read while a message is in flight. The format of the answer is not
        verified on hardware, so nothing decides on it unless USE_T02_GATE is set.
        """
        return self._fht_queue

    @property
    def fht_queue_at(self) -> datetime | None:
        """Return when the dump of the FHT buffer was read."""
        return self._fht_queue_at

    @property
    def send_log(self) -> list[SendRecord]:
        """Return the credit around the last messages, the oldest first."""
        return list(self._send_log)

    @property
    def held_for_sync(self) -> int:
        """Return how many messages were held back while a controller synchronized."""
        return self._held_for_sync

    def channel_states(self) -> dict[str, ChannelState]:
        """Return the state of every command channel by device id, for diagnostics."""
        return {
            device_id: ChannelState(
                in_flight=channel.in_flight is not None,
                staged=len(channel.staged),
                trusted=channel.trusted,
                broken=channel.broken,
                unechoed=channel.unechoed,
                probes=channel.probes,
            )
            for device_id, channel in self._channels.items()
        }

    def is_broken(self, device_id: str) -> bool:
        """Return True while no automatic message goes to the controller."""
        channel = self._channels.get(device_id)
        return channel is not None and channel.broken

    def in_flight(self, device_id: str) -> bool:
        """Return True while a message for the controller is in the CUL."""
        channel = self._channels.get(device_id)
        return channel is not None and channel.in_flight is not None

    def has_messages(self, device_id: str) -> bool:
        """Return True while a message for the controller is staged or in the CUL."""
        channel = self._channels.get(device_id)
        return channel is not None and (
            channel.in_flight is not None or bool(channel.staged)
        )

    def report_pending(self) -> bool:
        """Return True while a report request of any controller is staged or in the CUL."""
        return any(
            (channel.in_flight is not None and channel.in_flight.report)
            or any(staged.kind is _Kind.REPORT for staged in channel.staged)
            for channel in self._channels.values()
        )

    async def request(
        self,
        device_id: str,
        commands: Mapping[int, int],
        *,
        urgent: bool = False,
        automatic: bool = False,
    ) -> int:
        """Stage commands (code to raw value) for an FHT80b and return the message id.

        An urgent request is a message of its own that does not wait for more commands
        (it still waits for the message before it). A report request is a message of
        its own as well, and it goes after the commands of the user. A request that holds
        nothing but times of the week program is a message of its own, which the
        callers use for one day each. An automatic request comes from the integration
        itself, not from the user, and it is refused while the duty cycle credit is
        short, which a request of the user is not.

        Raises:
            FhtValueError: A command or value is not one that the controller takes.
            FhtSendError: A precondition failed.
        """
        checked = _check_request(commands)
        kind = _kind_of(checked, urgent=urgent)
        self._precheck(device_id, kind, checked, automatic)
        async with self._request_lock:
            channel = self._precheck(device_id, kind, checked, automatic)
            size = fht_send_size(self._message_length(channel, kind, checked))
            # The user's request waits for the credit in the flusher, and only an
            # automatic one is skipped, because its own schedule asks again.
            await check_capacity(
                self._transport,
                size,
                min_credit=AUTOMATIC_MIN_CREDIT_10MS if automatic else None,
            )
            # The link or the target may have gone while the CUL answered.
            channel = self._precheck(device_id, kind, checked, automatic)
            return self._stage(channel, kind, checked, automatic)

    def handle_update(self, update: NetworkUpdate | None) -> None:
        """Take the echoes of a telegram into account.

        The owner calls it with every update of the network. The echo of a command
        proves that the controller collected the message, so it ends the breaker, and
        the echo of the last command of the message in flight lets the next one go.

        Only a CONFIRMED command is such a proof. A controller reports values of its
        own as well (a program switch changes the desired temperature), and that report
        supersedes a command of ours without the controller having collected anything,
        so it settles the command and ends the wait for the message but proves nothing.
        The price is a controller that stores another value than the one sent (a limit
        of its own): its echo supersedes the command, and the message counts as
        unechoed. The ranges of the builders keep that case rare.
        """
        if not isinstance(update, DeviceUpdate) or not update.settled:
            return
        channel = self._channels.get(update.device.device_id)
        if channel is None:
            return
        flight = channel.in_flight
        if any(command.state is PendingState.CONFIRMED for command in update.settled):
            self._collected(channel)
            if flight is not None:
                flight.echoed = True
        if flight is None:
            return
        if any(
            command.message_id == flight.message_id and command.code == flight.last_code
            for command in update.settled
        ):
            self._release(
                channel,
                flight,
                _Outcome.ECHOED if flight.echoed else _Outcome.SUPERSEDED,
            )

    def _collected(self, channel: _Channel) -> None:
        """Note that the controller echoed a command, so it collects our messages."""
        channel.device.echoed_at = self._network.now()
        channel.unechoed = 0
        if channel.broken:
            channel.broken = False
            _LOGGER.info("%s echoed a command again", channel.label)
            self._emit(ChannelRecovered(channel.device_id))

    def reset(self, device_id: str | None = None) -> None:
        """Release the wait for the messages in flight of a controller, of all by default.

        The owner calls it when the messages are not in the buffer of the CUL any more
        (it was emptied or reset) or are not worth waiting for. Nothing is counted
        against the controller, because it has not failed to collect anything. The
        commands that were retired in the queue leave their staged messages by
        themselves.
        """
        for channel in self._channels.values():
            if device_id in (None, channel.device_id):
                channel.in_flight = None
        if all(channel.in_flight is None for channel in self._channels.values()):
            self._idle_free = None
        self._wake.set()

    def resume(self, free_bytes: int) -> int:
        """Take up the commands in flight that the queues hold and return the messages.

        After a restart the queues hold the commands that were sent before it. Their
        messages may still be in the buffer of the CUL, so the controller counts as
        busy until its echo, until the buffer shows them gone or until GATE_TIMEOUT
        from the request. `free_bytes` is the free space of the buffer now. The
        messages are not known to have gone unechoed, because the echo may have come
        while nobody listened, so they do not count against the controller.
        """
        now = asyncio.get_running_loop().time()
        sizes = 0
        resumed = 0
        for device in self._network.devices.values():
            if not isinstance(device, FhtRoomController):
                continue
            sent: dict[int, list[PendingCommand]] = {}
            for command in device.pending.commands():
                if command.state is PendingState.QUEUED and command.message_id:
                    sent.setdefault(command.message_id, []).append(command)
            if not sent:
                continue
            channel = self._channel(device)
            sizes += sum(fht_send_size(len(commands)) for commands in sent.values())
            resumed += len(sent)
            commands = sent[max(sent)]
            age = (self._network.now() - commands[0].clock_start).total_seconds()
            channel.in_flight = _InFlight(
                message_id=commands[0].message_id or 0,
                last_code=_in_message_order({c.code: c for c in commands})[-1],
                sent_at=now - max(age, 0.0),
                echoed=True,
                report=any(command.code in _REPORT_CODES for command in commands),
            )
        if resumed:
            if self._idle_free is None:
                self._idle_free = min(free_bytes + sizes, FHT_BUFFER_SIZE_BYTES)
                self._next_poll = now + self._timing.gate_poll_interval.total_seconds()
            self._ensure_running()
        return resumed

    async def async_stop(self) -> None:
        """Stop the flusher; the staged commands stay staged."""
        task, self._task = self._task, None
        if task is not None and not task.done():
            await cancel_task(task)

    def _channel(self, device: FhtRoomController) -> _Channel:
        """Return the channel of the controller, a new one for a forgotten device."""
        channel = self._channels.get(device.device_id)
        if channel is None or channel.device is not device:
            channel = _Channel(device)
            self._channels[device.device_id] = channel
        return channel

    def _precheck(
        self,
        device_id: str,
        kind: _Kind,
        commands: Mapping[int, int],
        automatic: bool,
    ) -> _Channel:
        """Raise unless the request may go on, and return the channel of the target."""
        state = self._transport.state
        if state is not TransportState.READY:
            raise FhtSendError(SendFailure.NOT_CONNECTED, state=state)
        device = find_controller(self._network, device_id)
        channel = self._channel(device)
        if automatic:
            self._check_automatic(channel, device, kind, commands)
        return channel

    @staticmethod
    def _check_automatic(
        channel: _Channel,
        device: FhtRoomController,
        kind: _Kind,
        commands: Mapping[int, int],
    ) -> None:
        if channel.broken:
            raise FhtSendError(SendFailure.DEVICE_UNRESPONSIVE, code=channel.shown_code)
        if channel.trusted:
            return
        if kind is _Kind.REPORT and FhtCode.REPORT2 in commands and channel.probes == 0:
            return
        raise FhtSendError(SendFailure.DEVICE_UNCONFIRMED, code=channel.shown_code)

    @staticmethod
    def _last(channel: _Channel, kind: _Kind) -> _Staged | None:
        """Return the newest staged message of the kind."""
        return next(
            (staged for staged in reversed(channel.staged) if staged.kind is kind),
            None,
        )

    @staticmethod
    def _joins(staged: _Staged, kind: _Kind, commands: Mapping[int, int]) -> bool:
        """Return True if the commands go into the staged message.

        A message holds 8 commands at most. A report request never shares a message.
        """
        if kind is _Kind.REPORT:
            return staged.commands.keys() == commands.keys()
        return len(staged.commands.keys() | commands.keys()) <= FHT_MAX_COMMANDS

    def _joinable(
        self, channel: _Channel, kind: _Kind, commands: Mapping[int, int]
    ) -> _Staged | None:
        """Return the staged message that takes the commands, None for a new one.

        A day of the week program is a message of its own, and the only message that it
        joins is one for the same day that waits still: the new times replace the old.
        """
        if kind is _Kind.PROGRAM:
            return next(
                (
                    staged
                    for staged in channel.staged
                    if staged.kind is kind and staged.commands.keys() == commands.keys()
                ),
                None,
            )
        last = self._last(channel, kind)
        return last if last is not None and self._joins(last, kind, commands) else None

    def _message_length(
        self, channel: _Channel, kind: _Kind, commands: Mapping[int, int]
    ) -> int:
        """Return the number of commands that the message of the request will hold."""
        joined = self._joinable(channel, kind, commands)
        if joined is not None:
            return len(joined.commands.keys() | commands.keys())
        return len(commands)

    def _stage(
        self,
        channel: _Channel,
        kind: _Kind,
        commands: Mapping[int, int],
        automatic: bool,
    ) -> int:
        """Add the commands to the staged messages of the channel."""
        loop = asyncio.get_running_loop()
        queue = channel.queue
        if FhtCode.MODE in commands:
            self._drop_holiday_leftovers(channel, commands)
        joined = self._joinable(channel, kind, commands)
        if joined is not None:
            staged = joined
            staged.automatic = staged.automatic and automatic
        else:
            last = self._last(channel, kind)
            if last is not None:
                # The commands do not fit, so the message in front goes now.
                last.due = loop.time()
            # Nothing joins a day of the week program, so there is nothing to wait for.
            wait = (
                0.0 if kind in (_Kind.URGENT, _Kind.PROGRAM) else self._coalesce_seconds
            )
            staged = _Staged(
                message_id=queue.new_message_id(),
                kind=kind,
                automatic=automatic,
                due=loop.time() + wait,
            )
            channel.staged.append(staged)
        queued_at = self._network.now()
        for code, raw in commands.items():
            if replaced := staged.commands.get(code):
                queue.retire([replaced], PendingState.SUPERSEDED)
            staged.commands[code] = queue.add(
                code,
                raw,
                queued_at,
                message_id=staged.message_id,
                waits_for_turn=kind is _Kind.PROGRAM,
            )
        if len(staged.commands) >= FHT_MAX_COMMANDS:
            staged.due = loop.time()
        if not automatic:
            channel.addressed = True
        elif not channel.trusted:
            channel.probes += 1
        self._ensure_running()
        return staged.message_id

    def _drop_holiday_leftovers(
        self, channel: _Channel, commands: Mapping[int, int]
    ) -> None:
        """Take the holiday values back that a new mode leaves behind.

        A staged holiday that the new mode does not carry is over, and so is the
        temperature that belonged to it, unless the new mode brings its own.
        """
        for staged in channel.staged:
            mode = staged.commands.get(FhtCode.MODE)
            was_holiday = mode is not None and mode.raw in _HOLIDAY_MODES
            gone = [
                code
                for code in _HOLIDAY_CODES
                if code in staged.commands and code not in commands
            ]
            if (
                was_holiday
                and FhtCode.DESIRED_TEMP in staged.commands
                and FhtCode.DESIRED_TEMP not in commands
            ):
                gone.append(FhtCode.DESIRED_TEMP)
            for code in gone:
                channel.queue.retire(
                    [staged.commands.pop(code)], PendingState.SUPERSEDED
                )

    def _ensure_running(self) -> None:
        self._wake.set()
        if self._task is None or self._task.done():
            self._task = self._spawn(self._run(), "culfw outbox")

    def _emit(self, event: OutboxEvent) -> None:
        if self._listener is not None:
            self._listener(event)

    async def _run(self) -> None:
        """Send what is due until nothing is staged or in flight any more."""
        while True:
            # Clear first, so that a request during the step wakes the next wait.
            self._wake.clear()
            delay = await self._step()
            if delay is None:
                return
            with suppress(TimeoutError):
                async with asyncio.timeout(delay):
                    await self._wake.wait()

    async def _step(self) -> float | None:
        """Do what is due and return the seconds until the next thing is, None if idle."""
        loop = asyncio.get_running_loop()
        await self._check_flights(loop.time())
        await self._measure_credit()
        delays: list[float] = []
        for channel in list(self._channels.values()):
            if channel.in_flight is None:
                delay = await self._flush(channel, loop.time())
                if delay is not None:
                    delays.append(delay)
        now = loop.time()
        if flying := self._flying():
            gate = self._timing.gate_timeout.total_seconds()
            delays.append(self._next_poll - now)
            delays.extend(flight.sent_at + gate - now for _, flight in flying)
        return max(min(delays), 0) if delays else None

    async def _measure_credit(self) -> None:
        """Read the credit once for the messages that are over, for the diagnostics."""
        if not self._unmeasured:
            return
        records, self._unmeasured = self._unmeasured, []
        try:
            credit = (await self._transport.get_credit()).credit_10ms
        except CulError as err:
            _LOGGER.debug("Cannot read the credit after a message: %s", err)
            return
        for record in records:
            record.credit_after_10ms = credit

    def _flying(self) -> list[tuple[_Channel, _InFlight]]:
        """Return the channels that have a message in flight with that message."""
        return [
            (channel, flight)
            for channel in self._channels.values()
            if (flight := channel.in_flight) is not None
        ]

    async def _check_flights(self, now: float) -> None:
        """End the wait for messages that timed out or that left the buffer."""
        gate = self._timing.gate_timeout.total_seconds()
        for channel, flight in self._flying():
            if now - flight.sent_at >= gate:
                self._release(channel, flight, _Outcome.TIMEOUT)
        if self._idle_free is None or now < self._next_poll:
            return
        self._next_poll = now + self._timing.gate_poll_interval.total_seconds()
        try:
            if USE_T02_GATE:
                self._release_unlisted(await self._dump_queue())
                return
            free = await self._transport.get_fht_buffer_free()
            if free >= self._idle_free:
                for channel, flight in self._flying():
                    self._release(channel, flight, _Outcome.DRAINED)
        except CulError as err:
            _LOGGER.debug("Cannot read the CUL buffer: %s", err)
        # The dump is for the diagnostics only, so its failure changes nothing above.
        with suppress(CulError):
            await self._dump_queue()

    async def _dump_queue(self) -> dict[str, list[tuple[int, int]]] | None:
        """Read the dump of the FHT buffer and keep the answer for the diagnostics."""
        queue = await self._transport.get_fht_queue()
        _LOGGER.debug("FHT buffer dump (T02): %s", queue)
        if queue is not None:
            self._fht_queue = queue
            self._fht_queue_at = self._network.now()
        return queue

    def _release_unlisted(self, queue: dict[str, list[tuple[int, int]]] | None) -> None:
        """End the wait for the controllers that the dump of the buffer no longer lists."""
        if queue is None:
            return
        for channel, flight in self._flying():
            if channel.code.upper() not in queue:
                self._release(channel, flight, _Outcome.DRAINED)

    def _release(self, channel: _Channel, flight: _InFlight, outcome: _Outcome) -> None:
        """End the wait for the message in flight and count a message nobody echoed.

        A message that nobody echoed while the link was down proves nothing about the
        controller, so it does not count. Neither does a report request: nobody has
        seen whether a controller repeats it, and the data telegrams that answer it are
        no proof either, as the controller sends them on its own as well. So a report
        that was not echoed is withdrawn quietly instead of expiring as a command that
        the user lost.
        """
        channel.in_flight = None
        if all(other.in_flight is None for other in self._channels.values()):
            self._idle_free = None
        _LOGGER.debug(
            "Message %d for %s: %s", flight.message_id, channel.label, outcome
        )
        if (record := flight.record) is not None:
            record.outcome = outcome.value
            record.seconds_in_flight = round(
                asyncio.get_running_loop().time() - flight.sent_at, 1
            )
            record.synchronizing = channel.device.synchronizing(self._network.now())
            self._unmeasured.append(record)
        if flight.report:
            channel.queue.retire(
                [
                    command
                    for command in channel.queue.commands()
                    if command.message_id == flight.message_id
                    and command.state is PendingState.QUEUED
                ],
                PendingState.SUPERSEDED,
            )
        elif not flight.echoed and self._transport.state is TransportState.READY:
            channel.unechoed += 1
            if channel.unechoed >= BREAKER_THRESHOLD and not channel.broken:
                self._break(channel)
        self._wake.set()

    def _break(self, channel: _Channel) -> None:
        """Cut the controller off from automatic messages."""
        channel.broken = True
        _LOGGER.warning(
            "%s did not echo %d messages in a row, so nothing automatic goes "
            "to it until it echoes a command",
            channel.label,
            channel.unechoed,
        )
        self._emit(ChannelBroken(channel.device_id))
        err = FhtSendError(SendFailure.DEVICE_UNRESPONSIVE, code=channel.shown_code)
        for staged in [staged for staged in channel.staged if staged.automatic]:
            channel.staged.remove(staged)
            self._drop(channel, staged, err.failure, err.detail)

    async def _flush(self, channel: _Channel, now: float) -> float | None:
        """Send the next staged message if it is due; return the seconds to wait."""
        for staged in list(channel.staged):
            if not any(
                command.state is PendingState.STAGED
                for command in staged.commands.values()
            ):
                # The owner took the commands back, for example after they expired.
                channel.staged.remove(staged)
        if not channel.staged:
            return None
        staged = min(channel.staged, key=lambda candidate: candidate.kind)
        if staged.due > now:
            return staged.due - now
        channel.staged.remove(staged)
        if not await self._send(channel, staged):
            channel.staged.insert(0, staged)
            return self._timing.defer_retry.total_seconds()
        # A message that was dropped leaves the next one to go at once.
        return 0.0 if channel.in_flight is None and channel.staged else None

    async def _send(self, channel: _Channel, staged: _Staged) -> bool:
        """Queue the message in the CUL; return False if it has to wait.

        A message that cannot be sent at all is dropped, which counts as handled.
        """
        if self._transport.state is not TransportState.READY:
            # An outage is no wait for credit, and the credit is unknown after it.
            staged.starved_since = None
            _LOGGER.debug("Message for %s waits for the CUL", channel.label)
            return False
        try:
            device = find_controller(self._network, channel.device_id)
        except FhtSendError as err:
            self._drop(channel, staged, err.failure, err.detail)
            return True
        if staged.automatic and device.synchronizing(self._network.now()):
            # While a controller counts down its synchronization it sends an actuator
            # telegram every second, and culfw may answer about every other one with a
            # packet if a message waits in its buffer. That is unproven, so only the
            # messages of the integration wait, and a request of the user is never
            # delayed by it. The record of the send log shows what such a message costs.
            if not staged.held:
                staged.held = True
                self._held_for_sync += 1
            _LOGGER.debug(
                "Message for %s waits for the end of its synchronization", channel.label
            )
            return False
        live = {
            code: command
            for code, command in staged.commands.items()
            if command.state is PendingState.STAGED
        }
        self._restamp(live)
        commands = [(code, live[code].raw) for code in _in_message_order(live)]
        try:
            capacity = await check_capacity(
                self._transport,
                fht_send_size(len(commands)),
                min_credit=(
                    AUTOMATIC_MIN_CREDIT_10MS if staged.automatic else MIN_CREDIT_10MS
                ),
            )
        except FhtSendError as err:
            if err.failure is not SendFailure.NO_CREDIT:
                staged.starved_since = None
            elif self._starved(channel, staged, err):
                return True
            _LOGGER.debug("Message for %s waits: %s", channel.label, err)
            return False
        staged.starved_since = None
        try:
            await queue_message(
                self._transport,
                self._network,
                device.code,
                commands,
                capacity.free_bytes,
            )
        except FhtSendError as err:
            self._drop(channel, staged, err.failure, err.detail)
            return True
        queued_at = self._network.now()
        channel.queue.mark_queued(staged.message_id, queued_at)
        self._emit(MessageSent(channel.device_id))
        record = SendRecord(
            at=queued_at,
            device_id=channel.device_id,
            automatic=staged.automatic,
            commands=len(commands),
            credit_before_10ms=capacity.credit_10ms,
        )
        self._send_log.append(record)
        now = asyncio.get_running_loop().time()
        if self._idle_free is None:
            self._idle_free = capacity.free_bytes
            self._next_poll = now + self._timing.gate_poll_interval.total_seconds()
        channel.in_flight = _InFlight(
            message_id=staged.message_id,
            last_code=commands[-1][0],
            sent_at=now,
            report=staged.kind is _Kind.REPORT,
            record=record,
        )
        return True

    def _restamp(self, live: Mapping[int, PendingCommand]) -> None:
        """Put the current local date and time into the commands that carry them.

        The message may have waited minutes for the credit or the end of a countdown,
        and the controller takes the hour and the date as they are (culfw replaces only
        the minute), so a stale value would set the clock wrong across an hour or a
        midnight.
        """
        if not _TIME_CODES.intersection(live):
            return
        fresh = dict(date_time_commands(self._local_now()))
        for code in _TIME_CODES.intersection(live):
            live[code].raw = fresh[code]

    def _starved(self, channel: _Channel, staged: _Staged, err: FhtSendError) -> bool:
        """Count the wait for credit and drop the message when it took too long.

        Return True if the message was dropped.
        """
        now = asyncio.get_running_loop().time()
        if staged.starved_since is None:
            staged.starved_since = now
        waited = now - staged.starved_since
        if waited < CREDIT_WAIT_LIMIT.total_seconds():
            return False
        exhausted = FhtSendError(
            SendFailure.CREDIT_EXHAUSTED,
            minimum=err.placeholders["minimum"],
            minutes=int(waited // 60),
        )
        _LOGGER.debug("Message for %s gives up waiting: %s", channel.label, err)
        self._drop(channel, staged, exhausted.failure, exhausted.detail)
        return True

    def _drop(
        self,
        channel: _Channel,
        staged: _Staged,
        failure: SendFailure,
        detail: str,
    ) -> None:
        """Take the commands of a message back that cannot be sent."""
        live = [
            command
            for command in staged.commands.values()
            if command.state is PendingState.STAGED
        ]
        channel.queue.retire(live, PendingState.INVALIDATED)
        _LOGGER.warning(
            "Dropped %d commands for %s: %s: %s",
            len(live),
            channel.label,
            failure,
            detail,
        )
        self._emit(CommandsDropped(channel.device_id, tuple(live), failure, detail))
