"""Serial transport for a busware CUL running culfw."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
import errno
import logging
import re
from typing import Protocol

import serialx

from .codes import format_display_code
from .const import (
    DEFAULT_BAUDRATE,
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    DEFAULT_OPEN_TIMEOUT_SECONDS,
    FHT8V_SLOTS,
    FHT_CODE_PART_MAX,
    FHT_CODE_PART_MIN,
    FHT_MAX_COMMANDS,
    FHT_QUEUE_POLL_INTERVAL_SECONDS,
    FHT_SEND_CODES,
    PORT_LOST_AFTER_TIMEOUTS,
    REPORT_MODE,
    UPTIME_TICKS_PER_SECOND,
    VERSION_ATTEMPTS,
)
from .errors import (
    CulCommandBlockedError,
    CulConnectionError,
    CulError,
    CulPortBusyError,
    CulPortMissingError,
    CulPortPermissionError,
    CulProtocolError,
    CulTimeoutError,
)
from .parser import parse_fht_queue
from .tasks import CreateTask, cancel_task, start_task

_LOGGER = logging.getLogger(__name__)

_HOUSE_CODE_RE = re.compile(r"[0-9A-F]{4}")

# The commands this transport may ever send (full match, case-sensitive).
_ALLOWED_COMMANDS: tuple[re.Pattern[str], ...] = (
    # Read the firmware version.
    re.compile(r"V"),
    # Read the report mode and the 1 % duty cycle credit.
    re.compile(r"X"),
    # Set the report mode to all messages plus the RSSI, which lives in RAM only.
    re.compile(r"X21"),
    # Read the FHT house code.
    re.compile(r"T01"),
    # Set the FHT house code in the EEPROM, which clears the FHT buffers.
    re.compile(r"T01[0-9A-F]{4}"),
    # Read the free bytes in the FHT80b send buffer.
    re.compile(r"T03"),
    # Read the messages in the FHT80b send buffer, with their commands (T02) or only
    # their house codes (T0200).
    re.compile(r"T02(?:00)?"),
    # Read the uptime ticks.
    re.compile(r"t"),
)
_REBOOT_COMMAND = "B00"

_FHT_SEND_RE = re.compile(
    rf"T([0-9A-F]{{4}})((?:[0-9A-F]{{4}}){{1,{FHT_MAX_COMMANDS}}})"
)

_UNKNOWN_COMMAND_PREFIX = "? ("

_RESPONSE_VERSION = re.compile(r"V \S.*")
_RESPONSE_HOUSE_CODE = re.compile(r"[0-9A-Fa-f]{4}")
_RESPONSE_HEX2 = re.compile(r"[0-9A-Fa-f]{2}")
_RESPONSE_REPORT = re.compile(r"([0-9A-Fa-f]{2}) +(\d+)")
_RESPONSE_UPTIME = re.compile(r"[0-9A-Fa-f]{8}")
# The shape of the `T02` answer has not been seen on hardware, so this only has to tell
# it apart from the telegrams on the same stream (they start with a letter and have no
# separator after four hex digits). The parser does the strict check, because a line
# that nobody takes as the answer would count as a timeout.
_RESPONSE_FHT_QUEUE = re.compile(r"N/A|[0-9A-Fa-f]{4}(?:[: ,].*)?")

# Opening the node of a stick that is gone ends with one of these, depending on whether
# udev removed the node already.
_PORT_MISSING_ERRNOS = frozenset({errno.ENOENT, errno.ENODEV, errno.ENXIO})
_PORT_PERMISSION_ERRNOS = frozenset({errno.EACCES, errno.EPERM})


class LineReader(Protocol):
    """Minimal reader interface (satisfied by asyncio.StreamReader)."""

    async def readline(self) -> bytes:
        """Read one line including its terminator; empty bytes on EOF."""
        ...


class LineWriter(Protocol):
    """Minimal writer interface (satisfied by asyncio.StreamWriter)."""

    def write(self, data: bytes) -> None:
        """Queue data for writing."""

    async def drain(self) -> None:
        """Wait until the write buffer is flushed."""

    def close(self) -> None:
        """Close the underlying port."""

    async def wait_closed(self) -> None:
        """Wait until the port is closed."""


type OpenConnection = Callable[[str, int], Awaitable[tuple[LineReader, LineWriter]]]
type MessageCallback = Callable[[str], None]
type ConnectionCallback = Callable[[bool], None]


async def open_serialx_connection(
    port: str, baudrate: int
) -> tuple[LineReader, LineWriter]:
    """Open a serial port with serialx (exclusive access)."""
    return await serialx.open_serial_connection(port, baudrate=baudrate, exclusive=True)


def _open_error(
    port: str, err: Exception, open_timeout_seconds: float
) -> CulConnectionError:
    """Return the error for a port that cannot be opened, typed by its errno."""
    if isinstance(err, TimeoutError) and not err.args:
        # The expired timeout of the open call carries no text of its own.
        reason = f"no answer within {open_timeout_seconds:g} s"
    else:
        reason = str(err)
    message = f"Cannot open {port}: {reason}"
    code = err.errno if isinstance(err, OSError) else None
    if code in _PORT_MISSING_ERRNOS:
        return CulPortMissingError(message)
    if code == errno.EBUSY:
        return CulPortBusyError(message)
    if code in _PORT_PERMISSION_ERRNOS:
        return CulPortPermissionError(message)
    return CulConnectionError(message)


def normalize_house_code(house_code: str) -> str:
    """Return the house code as four upper-case hex digits or raise ValueError."""
    code = house_code.strip().upper()
    if not _HOUSE_CODE_RE.fullmatch(code):
        raise ValueError(f"FHT house code must be four hex digits, got {house_code!r}")
    return code


def _is_fht_code(parts: bytes) -> bool:
    """Return True if every part of a house code is one an FHT can be set to."""
    return all(FHT_CODE_PART_MIN <= part <= FHT_CODE_PART_MAX for part in parts)


def normalize_fht_house_code(house_code: str) -> str:
    """Return a house code that an FHT can have, or raise ValueError.

    The code is normalized by normalize_house_code(), and both of its parts have to be
    between 01 and 63, which are the numbers 1 to 99 that an FHT shows.
    """
    code = normalize_house_code(house_code)
    if not _is_fht_code(bytes.fromhex(code)):
        raise ValueError(f"FHT house code parts must be 01 to 63, got {house_code!r}")
    return code


def fht_send_size(commands: int) -> int:
    """Return the bytes a message with `commands` takes in culfw's FHT buffer.

    culfw stores a length byte, the 2-byte house code and 2 bytes per command.
    """
    return 3 + 2 * commands


def build_fht_send(device: str, commands: Sequence[tuple[int, int]]) -> str:
    """Return the culfw line that queues `commands` (code, value) for an FHT80b."""
    if not 1 <= len(commands) <= FHT_MAX_COMMANDS:
        raise CulCommandBlockedError(
            f"1-{FHT_MAX_COMMANDS} FHT commands, got {len(commands)}"
        )
    try:
        code = normalize_house_code(device)
    except ValueError as err:
        raise CulCommandBlockedError(str(err)) from err
    pairs = []
    for cmd, value in commands:
        if cmd not in FHT_SEND_CODES:
            raise CulCommandBlockedError(f"FHT command 0x{cmd:02X} is not allowed")
        if not 0 <= value <= 0xFF:
            raise CulCommandBlockedError(f"FHT value {value} is not a byte")
        pairs.append(f"{cmd:02X}{value:02X}")
    return f"T{code}{''.join(pairs)}"


def _check_fht_send(command: str, own_house_code: str) -> None:
    """Raise unless `command` queues allowed commands for a real FHT80b."""
    match = _FHT_SEND_RE.fullmatch(command)
    if match is None:
        raise CulCommandBlockedError(f"Command is not on the allow-list: {command!r}")
    target = bytes.fromhex(match.group(1))
    if not _is_fht_code(target):
        raise CulCommandBlockedError(f"Not an FHT80b house code: {match.group(1)}")
    own = bytes.fromhex(own_house_code)
    if target[1] == own[1] and own[0] <= target[0] < own[0] + FHT8V_SLOTS:
        raise CulCommandBlockedError(
            f"House code {match.group(1)} is the CUL's FHT8v range"
        )
    codes = bytes.fromhex(match.group(2))[0::2]
    if blocked := [code for code in codes if code not in FHT_SEND_CODES]:
        raise CulCommandBlockedError(f"FHT command 0x{blocked[0]:02X} is not allowed")


def ensure_command_allowed(
    command: str, *, allow_reboot: bool = False, house_code: str | None = None
) -> None:
    """Raise CulCommandBlockedError unless `command` may be sent to the CUL.

    culfw dispatches on the first character of a line, so the checks look at the
    prefix as well as at the full command. FHT80b messages are only accepted with the
    CUL's own `house_code` (needed to keep out of its FHT8v range).
    """
    if not command.isascii() or not command.isprintable():
        raise CulCommandBlockedError(
            f"Command contains control characters: {command!r}"
        )
    if command.startswith("e"):
        raise CulCommandBlockedError(f"Factory reset is blocked: {command!r}")
    if command.startswith("B"):
        if command == _REBOOT_COMMAND and allow_reboot:
            return
        raise CulCommandBlockedError(
            f"Bootloader/reboot command is blocked: {command!r}"
        )
    if any(pattern.fullmatch(command) for pattern in _ALLOWED_COMMANDS):
        return
    if (
        house_code is not None
        and command.startswith("T")
        and len(command) > len("T01XXXX")
    ):
        _check_fht_send(command, house_code)
        return
    raise CulCommandBlockedError(f"Command is not on the allow-list: {command!r}")


class TransportState(StrEnum):
    """Phase of the connection of a CulTransport.

    A transport starts IDLE and goes through CONNECTING (the port is being opened) and
    INITIALIZING (the init sequence runs) to READY, the only state that takes commands.
    A lost port is LOST until it is closed, then the supervisor waits in BACKOFF and
    starts over with CONNECTING. close() passes CLOSING and ends in CLOSED.
    """

    IDLE = "idle"
    CONNECTING = "connecting"
    INITIALIZING = "initializing"
    READY = "ready"
    LOST = "lost"
    BACKOFF = "backoff"
    CLOSING = "closing"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class ReconnectPolicy:
    """Exponential backoff for reconnecting after the port was lost."""

    initial_delay_seconds: float = 1.0
    maximum_delay_seconds: float = 60.0
    factor: float = 2.0
    # A connection that lasted at least this long resets the backoff.
    stable_after_seconds: float = 60.0
    # reconnect_now() ignores a call that comes sooner than this after the last one.
    wake_interval_seconds: float = 1.0

    def next_delay_seconds(self, delay_seconds: float) -> float:
        """Return the delay in seconds to use after `delay_seconds` failed."""
        return min(delay_seconds * self.factor, self.maximum_delay_seconds)


@dataclass(frozen=True, slots=True)
class CulInfo:
    """Identity of a CUL as read by probe()."""

    version: str
    house_code: str


@dataclass(frozen=True, slots=True)
class CulCredit:
    """Answer of the `X` command."""

    report_mode: int
    credit_10ms: int


@dataclass(frozen=True, slots=True)
class TransportStatistics:
    """Counters of a transport, for the diagnostics.

    `reconnect_count` is how often the supervisor brought the connection back after it
    was lost. `consecutive_timeouts` is the number of commands in a row that the CUL
    has not answered; any line from the CUL and every new attempt to connect set it
    back to zero. `last_error` tells what ended the latest connection or made the
    latest attempt fail, and it stays until the next error.
    """

    reconnect_count: int
    consecutive_timeouts: int
    last_error: str | None


@dataclass(slots=True)
class _PendingCommand:
    command: str
    response: re.Pattern[str]
    future: asyncio.Future[str]


class CulTransport:
    """Line-based connection to a CUL with init, serialized commands and reconnect.

    culfw speaks a line protocol. Commands are ASCII lines that end with a newline and
    are dispatched by their first character. Answers and received radio telegrams
    arrive as lines that end with CRLF on the same stream. Answers carry no request id,
    so only one command may be in flight at a time, and every answer is matched against
    the pattern that its command expects. Every other line is handed to the message
    callback.

    After a successful connect() the transport reconnects on its own with exponential
    backoff whenever the port is lost, and runs the init sequence again. A lost port
    and every attempt to get it back are logged at debug level only, and the first
    connect at info level: a CUL that stays away would otherwise fill the log with two
    lines per minute. The owner reports the loss and the recovery once, from the
    connection callback and the cause in `statistics`.

    There is no public method that sends a free-form command. Every line goes through
    ensure_command_allowed(), which lets only an explicit allow list through and blocks
    B01 to BFF (jump to the DFU bootloader), e (factory reset) and any other B or e
    variant. B00 (watchdog reboot) is reachable only through reboot() on a transport
    created with allow_reboot=True.

    Messages for FHT80b room controllers (send_fht()) are checked against the routing of
    culfw. Only targets that land in the FHT80b buffer pass, which leaves out the FHT80
    TF emulation and the FHT8v direct mode, and only the command codes in
    FHT_SEND_CODES.
    """

    def __init__(
        self,
        port: str,
        house_code: str,
        *,
        on_message: MessageCallback | None = None,
        on_connection_change: ConnectionCallback | None = None,
        baudrate: int = DEFAULT_BAUDRATE,
        command_timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
        open_timeout_seconds: float = DEFAULT_OPEN_TIMEOUT_SECONDS,
        reconnect_policy: ReconnectPolicy | None = None,
        allow_reboot: bool = False,
        open_connection: OpenConnection = open_serialx_connection,
        create_task: CreateTask = start_task,
        fht_queue_poll_interval_seconds: float = FHT_QUEUE_POLL_INTERVAL_SECONDS,
    ) -> None:
        """Initialize the transport; nothing is opened until connect().

        `create_task` starts the reader and the supervisor. The owner passes a
        factory that ties the tasks to its own lifetime, so that it can cancel them.
        """
        self._port = port
        self._house_code = normalize_house_code(house_code)
        self._on_message = on_message
        self._on_connection_change = on_connection_change
        self._baudrate = baudrate
        self._command_timeout_seconds = command_timeout_seconds
        self._open_timeout_seconds = open_timeout_seconds
        self._policy = reconnect_policy or ReconnectPolicy()
        self._allow_reboot = allow_reboot
        self._open_connection = open_connection
        self._create_task = create_task
        self._fht_queue_poll_interval_seconds = fht_queue_poll_interval_seconds

        self._lock = asyncio.Lock()
        self._writer: LineWriter | None = None
        self._read_task: asyncio.Task[None] | None = None
        self._supervisor_task: asyncio.Task[None] | None = None
        self._port_lost = asyncio.Event()
        self._wake = asyncio.Event()
        self._last_wake_at: float | None = None
        self._pending: _PendingCommand | None = None
        self._state = TransportState.IDLE
        self._closing = False
        self._connected_at: float | None = None
        self._reconnect_delay_seconds = self._policy.initial_delay_seconds
        self._reconnect_count = 0
        self._consecutive_timeouts = 0
        self._last_error: str | None = None
        self._reset_seen = False
        self._cul_was_reset = False
        self._unexpected_error_logged = False
        self._overlong_line_logged = False
        self._callback_error_logged = False
        self._fht_in_flight = True
        self._fht_queue: dict[str, list[tuple[int, int]]] | None = None
        self._fht_queue_stale = False
        self._fht_queue_polled_at: float | None = None
        self._fht_queue_format_logged = False

        self.version: str | None = None
        self.house_code_was_set = False
        # Every write of the house code clears the FHT buffers, so the owner compares
        # this with the number it knows to see a write that happened since.
        self.house_code_writes = 0

    @property
    def port(self) -> str:
        """Return the serial port path."""
        return self._port

    @property
    def house_code(self) -> str:
        """Return the configured FHT house code."""
        return self._house_code

    @property
    def state(self) -> TransportState:
        """Return the phase of the connection."""
        return self._state

    @property
    def connected(self) -> bool:
        """Return True while the port is open and the CUL is initialized."""
        return self._state is TransportState.READY

    @property
    def cul_was_reset(self) -> bool:
        """Return True when the CUL had lost its state before the latest connect.

        The init sequence reads the report mode before it sets it. Anything but the
        mode this transport sets means that the CUL started since, so everything it
        keeps in RAM is gone: the report mode, the uptime and the FHT send buffers. A
        reconnect over a port that was only closed and opened again leaves it False.
        The value belongs to the latest connect and covers the failed attempts before
        it.
        """
        return self._cul_was_reset

    @property
    def statistics(self) -> TransportStatistics:
        """Return the counters of the connection."""
        return TransportStatistics(
            reconnect_count=self._reconnect_count,
            consecutive_timeouts=self._consecutive_timeouts,
            last_error=self._last_error,
        )

    async def connect(self) -> None:
        """Open the port and initialize the CUL (single attempt).

        On success a background task keeps the connection alive until close().

        Raises:
            CulPortMissingError: The port does not exist.
            CulPortBusyError: Another process has the port open.
            CulPortPermissionError: The process may not open the port.
            CulConnectionError: The port cannot be opened for another reason.
            CulTimeoutError: The CUL does not answer.
            CulProtocolError: The device does not answer like a CUL with culfw.
        """
        if self._supervisor_task is not None:
            raise CulError("Transport is already running")
        self._closing = False
        resting_state = self._state
        try:
            await self._connect_once()
        except BaseException:
            self._set_state(resting_state)
            raise
        _LOGGER.info("Connected to CUL on %s (%s)", self._port, self.version)
        self._supervisor_task = self._create_task(
            self._supervise(), f"culfw supervisor {self._port}"
        )

    async def close(self) -> None:
        """Stop reconnecting and close the port."""
        was_ready = self.connected
        self._closing = True
        self._set_state(TransportState.CLOSING)
        self._port_lost.set()
        supervisor, self._supervisor_task = self._supervisor_task, None
        if supervisor is not None:
            await cancel_task(supervisor)
        await self._close_port()
        if was_ready:
            self._notify_connection(False)
        self._set_state(TransportState.CLOSED)

    def reconnect(self) -> None:
        """Drop the connection; the background task reopens it and re-runs the init.

        Used by the watchdog when the CUL stops answering on an open port. Does
        nothing while a reconnect is already in progress.
        """
        # The owner of the tasks cancels the supervisor to shut down, and then nothing
        # would reopen a port that is dropped.
        supervisor = self._supervisor_task
        if supervisor is None or supervisor.done() or self._closing:
            raise CulConnectionError("Transport is not running")
        if not self.connected:
            return
        _LOGGER.debug("Reopening CUL port %s", self._port)
        self._handle_port_lost("reopen requested")

    def reconnect_now(self) -> None:
        """Skip the wait before the next reconnect attempt.

        The owner calls this in the event loop when it learns that the stick is back,
        for example from a USB event. The attempt starts at once, and the delays start
        over with the initial one. The call does nothing while the connection is ready
        or the transport closes or does not run. It is also ignored when the last call
        that counted is less than `wake_interval_seconds` ago, so that a source of
        events that flaps cannot turn the backoff into a busy loop.
        """
        supervisor = self._supervisor_task
        # A transport that closes has let go of its supervisor already.
        if self.connected or supervisor is None or supervisor.done():
            return
        now = asyncio.get_running_loop().time()
        last = self._last_wake_at
        if last is not None and now - last < self._policy.wake_interval_seconds:
            return
        self._last_wake_at = now
        self._reconnect_delay_seconds = self._policy.initial_delay_seconds
        # Only the sleep can be woken. A port that is still being closed or an attempt
        # that is running reaches the next sleep with the delay that was reset above.
        if self._state is TransportState.BACKOFF:
            self._wake.set()

    async def probe(self) -> CulInfo:
        """Open the port, read version and house code, close it again.

        Changes nothing on the CUL (no house code, no report mode).
        """
        if self._writer is not None or self._supervisor_task is not None:
            raise CulError("Transport is already open")
        writer = await self._open_port()
        try:
            await self._flush_command_buffer(writer)
            version = await self._read_version()
            house_code = await self._execute(
                "T01", _RESPONSE_HOUSE_CODE, during_init=True
            )
        finally:
            await self._close_port()
        return CulInfo(version=version, house_code=house_code.upper())

    async def get_version(self) -> str:
        """Return the culfw version line, for example `V 1.66 CUL868`."""
        return await self._request("V", _RESPONSE_VERSION)

    async def get_house_code(self) -> str:
        """Return the FHT house code stored in the CUL."""
        return (await self._request("T01", _RESPONSE_HOUSE_CODE)).upper()

    async def get_fht_buffer_free(self) -> int:
        """Return the free bytes in the FHT80b send buffer (`T03`)."""
        return int(await self._request("T03", _RESPONSE_HEX2), 16)

    async def get_fht_queue(self) -> dict[str, list[tuple[int, int]]] | None:
        """Return the messages in the FHT send buffer as {house code: [(code, value)]}.

        This reads `T02`, which only talks to the CUL and sends nothing by radio. An
        entry disappears when its FHT80b has acknowledged the message, so a house code
        that is missing has no message in flight.

        The CUL is asked at most every `FHT_QUEUE_POLL_INTERVAL_SECONDS` and only
        while a message may be in flight: from the connect and after a send until an
        answer shows an empty buffer. Between two reads the last answer is returned,
        except that a call returns None for an answer that is older than the last send.
        None also means that the answer could not be parsed. That is logged once at
        debug level, and the buffer stays unknown.

        The format of the answer has not been verified on hardware, so callers use the
        result for diagnostics only unless USE_T02_GATE is set.
        """
        loop = asyncio.get_running_loop()
        if not self._fht_in_flight:
            return self._fht_queue_copy()
        now = loop.time()
        polled_at = self._fht_queue_polled_at
        if (
            polled_at is not None
            and now - polled_at < self._fht_queue_poll_interval_seconds
        ):
            return None if self._fht_queue_stale else self._fht_queue_copy()
        # A command that times out counts as a poll, so that a CUL that does not answer
        # is not asked again at once.
        self._fht_queue_polled_at = now
        answer = await self._request("T02", _RESPONSE_FHT_QUEUE)
        queue = parse_fht_queue(answer)
        self._fht_queue = queue
        self._fht_queue_stale = False
        if queue is None:
            if not self._fht_queue_format_logged:
                self._fht_queue_format_logged = True
                _LOGGER.debug("Cannot parse the FHT buffer dump of the CUL: %r", answer)
        else:
            self._fht_in_flight = bool(queue)
        return self._fht_queue_copy()

    async def get_credit(self) -> CulCredit:
        """Return report mode and remaining 1% duty-cycle credit (`X`)."""
        return _parse_report(await self._request("X", _RESPONSE_REPORT))

    async def get_uptime(self) -> float:
        """Return the CUL uptime in seconds (`t`, which wraps after about 397 days)."""
        ticks = int(await self._request("t", _RESPONSE_UPTIME), 16)
        return ticks / UPTIME_TICKS_PER_SECOND

    async def clear_fht_buffer(self) -> None:
        """Clear all FHT send buffers by re-writing the configured house code."""
        await self._send(f"T01{self._house_code}")
        self._fht_in_flight = False
        self._fht_queue = {}
        self._fht_queue_stale = False

    async def send_fht(self, device: str, commands: Sequence[tuple[int, int]]) -> None:
        """Queue (code, value) commands for an FHT80b in culfw's FHT buffer.

        culfw sends them in the controller's next time slot (every 115-118.5 s) and
        prints `EOB` if its buffer is full. A message for a controller that never
        talks stays in the buffer until it is cleared, so callers check that the
        device is alive and that there is room (`get_fht_buffer_free`) first.
        """
        line = build_fht_send(device, commands)
        try:
            await self._execute(line, None)
        finally:
            # Also after a failed write, which may have queued the message. The flags
            # change only after the command because it can wait for a read of the
            # buffer, whose answer then predates the message.
            self._fht_in_flight = True
            self._fht_queue_stale = True

    async def reboot(self) -> None:
        """Reboot the CUL via its watchdog (`B00`).

        The CUL re-enumerates on USB; the transport reconnects and re-runs the init
        sequence. Only safe when the whole USB device is passed through, for example
        to a VM by vendor and product ID. A device node that is bound into a container
        by path does not follow the re-enumeration.
        """
        if not self._allow_reboot:
            raise CulCommandBlockedError("Reboot (B00) is disabled for this transport")
        await self._execute(_REBOOT_COMMAND, None, allow_reboot=True)

    def _reset_fht_queue_knowledge(self) -> None:
        """Forget what the last `T02` showed; the next call reads the buffer."""
        self._fht_in_flight = True
        self._fht_queue = None
        self._fht_queue_stale = False
        self._fht_queue_polled_at = None

    def _fht_queue_copy(self) -> dict[str, list[tuple[int, int]]] | None:
        """Return a copy of the last answer, so that callers cannot change it."""
        if self._fht_queue is None:
            return None
        return {house: list(commands) for house, commands in self._fht_queue.items()}

    async def _request(self, command: str, response: re.Pattern[str]) -> str:
        return await self._execute(command, response)

    async def _send(self, command: str) -> None:
        await self._execute(command, None)

    async def _execute(
        self,
        command: str,
        response: re.Pattern[str] | None,
        *,
        allow_reboot: bool = False,
        during_init: bool = False,
    ) -> str:
        """Send one command and return its answer ("" if `response` is None)."""
        ensure_command_allowed(
            command, allow_reboot=allow_reboot, house_code=self._house_code
        )
        async with self._lock:
            writer = self._writer
            if writer is None or not (self.connected or during_init):
                raise CulConnectionError("CUL is not connected")
            future: asyncio.Future[str] | None = None
            if response is not None:
                future = asyncio.get_running_loop().create_future()
                self._pending = _PendingCommand(command, response, future)
            try:
                _LOGGER.debug("CUL <- %s", command)
                writer.write(command.encode("ascii") + b"\n")
                await writer.drain()
                if future is None:
                    return ""
                async with asyncio.timeout(self._command_timeout_seconds):
                    return await future
            except TimeoutError as err:
                self._count_timeout()
                raise CulTimeoutError(f"No answer from CUL to {command!r}") from err
            except (OSError, serialx.SerialException) as err:
                self._pending = None
                self._handle_port_lost(f"writing failed: {err}")
                raise CulConnectionError(
                    f"Writing {command!r} to CUL failed: {err}"
                ) from err
            finally:
                self._pending = None

    async def _open_port(self) -> LineWriter:
        """Open the serial port and start the reader task."""
        self._port_lost.clear()
        try:
            async with asyncio.timeout(self._open_timeout_seconds):
                reader, writer = await self._open_connection(self._port, self._baudrate)
        except (OSError, TimeoutError, ValueError, serialx.SerialException) as err:
            # serialx rejects a malformed port URL, for example socket:// without a
            # host, with a ValueError instead of a serial error.
            raise _open_error(self._port, err, self._open_timeout_seconds) from err

        self._writer = writer
        self._read_task = self._create_task(
            self._read_loop(reader), f"culfw reader {self._port}"
        )
        return writer

    async def _connect_once(self) -> None:
        """Open the port and run the init sequence; clean up on failure."""
        self._set_state(TransportState.CONNECTING)
        # What the commands of the connection before did not get answered says nothing
        # about this one.
        self._consecutive_timeouts = 0
        self._overlong_line_logged = False
        self._callback_error_logged = False
        # The RAM queue of the CUL outlives the connection, so what is in it is unknown.
        self._reset_fht_queue_knowledge()
        try:
            writer = await self._open_port()
            self._set_state(TransportState.INITIALIZING)
            await self._initialize(writer)
        except BaseException as err:
            await self._close_port()
            if isinstance(err, Exception):
                self._last_error = str(err) if isinstance(err, CulError) else repr(err)
            raise

        self._cul_was_reset, self._reset_seen = self._reset_seen, False
        self._set_state(TransportState.READY)
        self._connected_at = asyncio.get_running_loop().time()
        self._notify_connection(True)

    async def _initialize(self, writer: LineWriter) -> None:
        """Run the culfw init sequence.

        It reads the version, reads the house code and sets it only if it differs,
        reads the report mode to see whether the CUL was reset, sets the report mode
        and reads it again. It fails when the port was lost on the way.
        """
        await self._flush_command_buffer(writer)
        self.version = await self._read_version()

        current = (
            await self._execute("T01", _RESPONSE_HOUSE_CODE, during_init=True)
        ).upper()
        if current != self._house_code:
            _LOGGER.warning(
                "CUL FHT house code is %s, setting it to %s (this clears the FHT buffers)",
                format_display_code(current),
                format_display_code(self._house_code),
            )
            await self._execute(f"T01{self._house_code}", None, during_init=True)
            self.house_code_writes += 1
            confirmed = await self._execute(
                "T01", _RESPONSE_HOUSE_CODE, during_init=True
            )
            if confirmed.upper() != self._house_code:
                raise CulProtocolError(
                    f"CUL kept FHT house code {format_display_code(confirmed)}"
                    f" instead of {format_display_code(self._house_code)}"
                )
            self.house_code_was_set = True

        before = _parse_report(
            await self._execute("X", _RESPONSE_REPORT, during_init=True)
        )
        if before.report_mode != REPORT_MODE:
            _LOGGER.debug(
                "CUL on %s had report mode %02X instead of %02X",
                self._port,
                before.report_mode,
                REPORT_MODE,
            )
            # A failed attempt may already have set the mode, so the next one would
            # not see the reset any more.
            self._reset_seen = True

        await self._execute(f"X{REPORT_MODE:02X}", None, during_init=True)
        credit = _parse_report(
            await self._execute("X", _RESPONSE_REPORT, during_init=True)
        )
        if credit.report_mode != REPORT_MODE:
            raise CulProtocolError(
                f"CUL report mode is {credit.report_mode:02X}, expected {REPORT_MODE:02X}"
            )
        if self._port_lost.is_set():
            # The port can end right behind the last answer. Nobody reports a loss
            # before the connection is ready, and a flag that stayed set would make the
            # supervisor drop the port as soon as it is.
            raise CulConnectionError("CUL port was lost during the init sequence")

    async def _flush_command_buffer(self, writer: LineWriter) -> None:
        """Terminate whatever a previous user left in culfw's command buffer.

        culfw ignores empty lines, so a bare newline is harmless otherwise.
        """
        try:
            writer.write(b"\n")
            await writer.drain()
        except (OSError, serialx.SerialException) as err:
            raise CulConnectionError(f"Writing to CUL failed: {err}") from err

    async def _read_version(self) -> str:
        """Ask for the version; retry because the first answer may get lost."""
        for attempt in range(1, VERSION_ATTEMPTS):
            try:
                return await self._execute("V", _RESPONSE_VERSION, during_init=True)
            except CulTimeoutError:
                _LOGGER.debug(
                    "No version answer from CUL (attempt %d), retrying", attempt
                )
        return await self._execute("V", _RESPONSE_VERSION, during_init=True)

    async def _read_loop(self, reader: LineReader) -> None:
        """Read lines until EOF or error, then flag the port as lost."""
        try:
            while True:
                try:
                    raw = await reader.readline()
                except ValueError:
                    # A line longer than the stream limit is garbage, so keep reading.
                    # One report is enough, because noise on the line repeats itself.
                    _LOGGER.log(
                        logging.DEBUG
                        if self._overlong_line_logged
                        else logging.WARNING,
                        "Discarding overlong line from CUL",
                    )
                    self._overlong_line_logged = True
                    continue
                if not raw:
                    _LOGGER.debug("CUL port %s closed (EOF)", self._port)
                    cause = "port closed (EOF)"
                    break
                if not raw.endswith(b"\n"):
                    # The stream ended in the middle of a line. What is there could be
                    # the front of a telegram that reads as the telegram of another
                    # device, for example an FHT80b line cut to the size of an FHT80 TF.
                    _LOGGER.debug("Dropping the unfinished line %r", raw)
                    continue
                line = raw.decode("ascii", errors="replace").strip()
                if line:
                    self._handle_line(line)
        except (OSError, serialx.SerialException) as err:
            _LOGGER.debug("Reading from CUL on %s failed: %s", self._port, err)
            cause = f"reading failed: {err}"
        except Exception as err:
            # A reader that ended silently would leave a port that nobody reads open.
            _LOGGER.exception("Reading from CUL on %s failed unexpectedly", self._port)
            cause = f"reading failed unexpectedly: {err!r}"
        self._handle_port_lost(cause)

    def _handle_line(self, line: str) -> None:
        _LOGGER.debug("CUL -> %s", line)
        self._consecutive_timeouts = 0
        pending = self._pending
        if pending is not None and not pending.future.done():
            if pending.response.fullmatch(line):
                pending.future.set_result(line)
                return
            if line.startswith(_UNKNOWN_COMMAND_PREFIX):
                pending.future.set_exception(
                    CulProtocolError(f"CUL rejected {pending.command!r}: {line}")
                )
                return
        if self._on_message is not None:
            try:
                self._on_message(line)
            except Exception:
                # A bug in the owner would fail for every telegram that follows, so
                # the first one is an error and the rest stay at debug.
                _LOGGER.log(
                    logging.DEBUG if self._callback_error_logged else logging.ERROR,
                    "Error in CUL message callback for %r",
                    line,
                    exc_info=True,
                )
                self._callback_error_logged = True

    def _handle_port_lost(self, cause: str) -> None:
        was_ready = self.connected
        if was_ready:
            self._set_state(TransportState.LOST)
            self._last_error = cause
        self._fail_pending(CulConnectionError(f"Connection to CUL lost: {cause}"))
        self._port_lost.set()
        if was_ready:
            self._notify_connection(False)

    async def _close_port(self) -> None:
        read_task, self._read_task = self._read_task, None
        if read_task is not None:
            await cancel_task(read_task)
        self._fail_pending(CulConnectionError("CUL connection closed"))
        writer, self._writer = self._writer, None
        if writer is not None:
            writer.close()
            with suppress(OSError, serialx.SerialException):
                await writer.wait_closed()

    def _count_timeout(self) -> None:
        """Count a command that nobody answered, and give up on a port that stays mute."""
        self._consecutive_timeouts += 1
        if self._consecutive_timeouts >= PORT_LOST_AFTER_TIMEOUTS:
            _LOGGER.debug(
                "CUL on %s did not answer %d commands in a row",
                self._port,
                self._consecutive_timeouts,
            )
            self._handle_port_lost(
                f"no answer to {self._consecutive_timeouts} commands in a row"
            )

    def _fail_pending(self, error: CulError) -> None:
        pending = self._pending
        if pending is not None and not pending.future.done():
            pending.future.set_exception(error)

    async def _supervise(self) -> None:
        """Reconnect with exponential backoff whenever the port is lost.

        The supervisor has to outlive every failure, because a CUL that nothing
        reconnects stays gone until Home Assistant restarts.
        """
        while not self._closing:
            await self._port_lost.wait()
            await self._recover()

    async def _recover(self) -> None:
        """Close the lost port and reopen it, backing off between the attempts."""
        loop = asyncio.get_running_loop()
        try:
            await self._close_port()
        except Exception:
            _LOGGER.log(
                self._unexpected_error_level(),
                "Unexpected error while closing the lost port of the CUL on %s",
                self._port,
                exc_info=True,
            )
        if (
            self._connected_at is not None
            and loop.time() - self._connected_at >= self._policy.stable_after_seconds
        ):
            self._reconnect_delay_seconds = self._policy.initial_delay_seconds
        while not self._closing:
            delay_seconds = self._reconnect_delay_seconds
            self._reconnect_delay_seconds = self._policy.next_delay_seconds(
                delay_seconds
            )
            self._set_state(TransportState.BACKOFF)
            _LOGGER.debug(
                "Reconnecting to CUL on %s in %.3g s", self._port, delay_seconds
            )
            await self._sleep_until_woken(delay_seconds)
            try:
                await self._connect_once()
            except CulError as err:
                _LOGGER.debug("Reconnect to CUL on %s failed: %s", self._port, err)
            except Exception:
                _LOGGER.log(
                    self._unexpected_error_level(),
                    "Unexpected error while reconnecting to the CUL on %s",
                    self._port,
                    exc_info=True,
                )
            else:
                self._reconnect_count += 1
                self._unexpected_error_logged = False
                _LOGGER.debug("Reconnected to CUL on %s (%s)", self._port, self.version)
                break

    async def _sleep_until_woken(self, delay_seconds: float) -> None:
        """Wait for the delay to pass, or until reconnect_now() ends it early."""
        self._wake.clear()
        with suppress(TimeoutError):
            async with asyncio.timeout(delay_seconds):
                await self._wake.wait()

    def _set_state(self, state: TransportState) -> None:
        if state is not self._state:
            _LOGGER.debug("CUL on %s: %s -> %s", self._port, self._state, state)
            self._state = state

    def _unexpected_error_level(self) -> int:
        """Return the log level of an unexpected error: error once, then debug.

        The attempts repeat with the backoff, and the same bug would fill the log.
        A successful reconnect starts over.
        """
        if self._unexpected_error_logged:
            return logging.DEBUG
        self._unexpected_error_logged = True
        return logging.ERROR

    def _notify_connection(self, connected: bool) -> None:
        if self._on_connection_change is None:
            return
        try:
            self._on_connection_change(connected)
        except Exception:
            _LOGGER.exception("Error in CUL connection callback")


def _parse_report(line: str) -> CulCredit:
    match = _RESPONSE_REPORT.fullmatch(line)
    if match is None:
        raise CulProtocolError(f"Unexpected answer to X: {line!r}")
    return CulCredit(
        report_mode=int(match.group(1), 16), credit_10ms=int(match.group(2))
    )
