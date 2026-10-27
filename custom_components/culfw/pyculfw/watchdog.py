"""Watchdog with reset escalation for a CUL."""

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from enum import StrEnum
import logging
import time

from .const import PURGE_CAP, PURGE_WINDOW
from .errors import CulCommandBlockedError, CulError
from .tasks import CreateTask, cancel_task, start_task
from .transport import CulTransport

_LOGGER = logging.getLogger(__name__)

# culfw prints this when it dropped an FHT command because the send buffer is full.
EOB_LINE = "EOB"
# Unsolicited lines that are no radio telegrams. LOVF means that the 1 % duty cycle
# limit is reached.
_NON_TELEGRAM_PREFIXES = (EOB_LINE, "LOVF", "? (")

# A rebooted CUL reports at most this much uptime on top of the reconnect time.
_REBOOT_UPTIME_MARGIN_SECONDS = 60.0


class WatchdogStep(StrEnum):
    """Rungs of the escalation ladder, in order."""

    PING = "ping"
    REOPEN = "reopen"
    CLEAR_BUFFER = "clear_buffer"
    REBOOT = "reboot"
    USB_RESET = "usb_reset"
    POWER_CYCLE = "power_cycle"


ESCALATION: tuple[WatchdogStep, ...] = tuple(WatchdogStep)


class WatchdogEventKind(StrEnum):
    """What a watchdog event reports.

    SILENCE means that no telegram arrived for the silence timeout and the escalation
    starts. SUCCEEDED and FAILED report a step that ran, and SKIPPED a step that did not
    run, where the reason says why. RECOVERED means that telegrams arrive again, and
    EXHAUSTED that every step was tried and the CUL is still silent. ABORTED means that
    the connection dropped or came back while the escalation was in progress, so it was
    given up and the silence counts afresh from the next connect.
    """

    SILENCE = "silence"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    RECOVERED = "recovered"
    EXHAUSTED = "exhausted"
    ABORTED = "aborted"


class WatchdogReason(StrEnum):
    """Why an event happened; for a skipped step, why it was not run."""

    NO_TELEGRAM = "no_telegram"
    NO_ANSWER = "no_answer"
    BUFFER_CRITICAL = "buffer_critical"
    EOB = "eob"
    STILL_SILENT = "still_silent"
    TELEGRAM = "telegram"
    CUL_ANSWERS = "cul_answers"
    BUFFER_OK = "buffer_ok"
    PURGE_LIMIT = "purge_limit"
    CONNECTION_CHANGED = "connection_changed"
    DISABLED = "disabled"
    NOT_CONFIGURED = "not_configured"
    ALL_STEPS_DONE = "all_steps_done"


@dataclass(frozen=True, slots=True)
class WatchdogEvent:
    """One observable watchdog action or state change."""

    kind: WatchdogEventKind
    reason: WatchdogReason
    step: WatchdogStep | None = None
    detail: str = ""


@dataclass(frozen=True, slots=True)
class WatchdogConfig:
    """Timing and thresholds of the watchdog."""

    silence_timeout_seconds: float = 600.0
    check_interval_seconds: float = 30.0
    # Time to wait for telegrams after a remedial step before trying the next one.
    step_grace_seconds: float = 120.0
    # Time for the transport to come back after a reopen, reboot or reset.
    reconnect_timeout_seconds: float = 60.0
    # Free bytes in the FHT send buffer (174 when empty) below which it is cleared.
    buffer_critical_bytes: int = 32
    # Minimum time between two buffer clears triggered by EOB lines.
    clear_cooldown_seconds: float = 600.0
    # A purge rewrites the house code in the EEPROM and drops every queued command, so
    # no more than `purge_cap` of them are made within `purge_window_seconds`.
    purge_cap: int = PURGE_CAP
    purge_window_seconds: float = PURGE_WINDOW.total_seconds()
    # Time after EXHAUSTED before the ladder starts over.
    retry_after_seconds: float = 3600.0
    # How often to look whether the transport is connected again.
    poll_interval_seconds: float = 0.5


type ResetHook = Callable[[], Awaitable[str | None]]
type EventCallback = Callable[[WatchdogEvent], None]


class CulWatchdog:
    """Watches the telegram flow of a CUL and escalates resets when it stops.

    The owner forwards every unsolicited line of the transport to handle_line(). When no
    radio telegram arrives for `silence_timeout_seconds`, the watchdog walks this
    ladder, one rung at a time, until telegrams come back:

    1. PING: send V. An answer means that the CUL itself is alive.
    2. REOPEN: only if the ping failed. Close and reopen the port, which runs the init
       sequence again.
    3. CLEAR_BUFFER: only if the FHT send buffer is critical. Send T01 with the house
       code.
    4. REBOOT: B00, only if the transport was created with allow_reboot=True. The init
       sequence after the re-enumeration checks the house code and sets X21 again.
    5. USB_RESET: the USB reset hook, if configured.
    6. POWER_CYCLE: the hook for a real power reset, if configured.

    After each remedial step it waits `step_grace_seconds` for telegrams before the next
    one. If nothing helped it reports EXHAUSTED and starts over after
    `retry_after_seconds`. An EOB line (FHT buffer full) clears the buffer right away,
    independent of the ladder, but only if the buffer reads critical. Every purge of
    the buffer drops all queued commands, so there are at most `purge_cap` within
    `purge_window_seconds`, and the owner treats a successful clear step as the loss of
    every command in flight. Every step and state change is reported as a
    WatchdogEvent.

    The silence only counts while the transport is connected. A CUL that is unplugged
    is the business of the transport, which reconnects on its own, so the owner
    forwards every change of the connection to handle_connection(). A lost connection
    gives up a ladder in progress, nothing runs while the transport is down, and the
    silence counts from the moment the connection is back. Otherwise a stick that
    returns late would be rebooted for a silence that happened while it was away. The
    reconnects that the ladder causes itself with the steps REOPEN, REBOOT, USB_RESET
    and POWER_CYCLE are not changes in this sense and leave the ladder alone.
    """

    def __init__(
        self,
        transport: CulTransport,
        *,
        on_event: EventCallback | None = None,
        config: WatchdogConfig | None = None,
        usb_reset: ResetHook | None = None,
        power_cycle: ResetHook | None = None,
        create_task: CreateTask = start_task,
    ) -> None:
        """Initialize the watchdog; nothing runs until start().

        `create_task` starts the task of the watchdog. The owner passes a factory
        that ties the task to its own lifetime, so that it can cancel it.
        """
        self._transport = transport
        self._on_event = on_event
        self._config = config or WatchdogConfig()
        self._usb_reset = usb_reset
        self._power_cycle = power_cycle
        self._create_task = create_task

        self._task: asyncio.Task[None] | None = None
        self._wakeup = asyncio.Event()
        self._last_telegram = time.monotonic()
        self._eob_received = False
        self._last_clear: float | None = None
        self._purges: deque[float] = deque()
        self._purge_count = 0

        self._escalating = False
        self._exhausted = False
        self._next_step = 0
        self._next_step_at = 0.0
        self._last_step: WatchdogStep | None = None
        self._cul_answers = False
        self._own_reconnect = False

    @property
    def purge_count(self) -> int:
        """Return how many times the watchdog purged the FHT buffer since it started."""
        return self._purge_count

    @property
    def escalating(self) -> bool:
        """Return True while the CUL is silent and the ladder is in progress."""
        return self._escalating

    def handle_line(self, line: str) -> None:
        """Take one unsolicited line from the transport (its on_message callback)."""
        if line == EOB_LINE:
            self._eob_received = True
            self._wakeup.set()
            return
        if line.startswith(_NON_TELEGRAM_PREFIXES):
            return
        self._last_telegram = time.monotonic()
        if self._escalating:
            self._wakeup.set()

    def handle_connection(self, connected: bool) -> None:
        """Take a change of the connection (the on_connection_change callback).

        A lost connection gives up a ladder in progress and drops an EOB that is not
        handled yet, and a connect starts the silence timer over. The changes that a
        step of the ladder causes itself are ignored, because the ladder goes on when
        the CUL is back.
        """
        if self._own_reconnect:
            return
        self._eob_received = False
        if self._escalating:
            self._reset_ladder()
            self._emit(
                WatchdogEventKind.ABORTED,
                WatchdogReason.CONNECTION_CHANGED,
                detail="connection restored" if connected else "connection lost",
            )
        if connected:
            self._last_telegram = time.monotonic()

    def start(self) -> None:
        """Start watching; the silence timer starts now."""
        if self._task is not None:
            raise RuntimeError("Watchdog is already running")
        self._last_telegram = time.monotonic()
        self._task = self._create_task(self._run(), "culfw watchdog")

    async def stop(self) -> None:
        """Stop watching (cancels a step in progress)."""
        task, self._task = self._task, None
        if task is not None:
            await cancel_task(task)

    async def _run(self) -> None:
        while True:
            with suppress(TimeoutError):
                async with asyncio.timeout(self._config.check_interval_seconds):
                    await self._wakeup.wait()
            self._wakeup.clear()
            try:
                await self._check()
            except Exception:
                _LOGGER.exception("CUL watchdog check failed")

    async def _check(self) -> None:
        if not self._transport.connected:
            # The transport reconnects on its own, and the silence counts again from
            # the connect.
            return
        if self._eob_received:
            self._eob_received = False
            await self._clear_after_eob()

        now = time.monotonic()
        silent_for = now - self._last_telegram
        if silent_for < self._config.silence_timeout_seconds:
            if self._escalating:
                self._recovered()
            return
        if not self._escalating or (self._exhausted and now >= self._next_step_at):
            self._start_escalation(silent_for)
        elif now < self._next_step_at:
            return
        await self._escalate()

    def _reset_ladder(self) -> None:
        """Put the ladder back to the state of a CUL that is not silent."""
        self._escalating = False
        self._exhausted = False
        self._next_step = 0
        self._last_step = None
        self._cul_answers = False

    def _start_escalation(self, silent_for: float) -> None:
        self._reset_ladder()
        self._escalating = True
        self._emit(
            WatchdogEventKind.SILENCE,
            WatchdogReason.NO_TELEGRAM,
            detail=f"no telegram for {silent_for:.0f} s",
        )

    async def _escalate(self) -> None:
        """Run steps until one needs a grace period or the ladder ends."""
        while self._next_step < len(ESCALATION):
            if (
                time.monotonic() - self._last_telegram
                < self._config.silence_timeout_seconds
            ):
                # A telegram arrived, and the next check reports the recovery.
                return
            step = ESCALATION[self._next_step]
            self._next_step += 1
            needs_grace = await self._run_step(step)
            if not self._escalating:
                # The connection changed during the step and ended the ladder.
                return
            if needs_grace:
                self._last_step = step
                self._next_step_at = time.monotonic() + self._config.step_grace_seconds
                return
        self._exhausted = True
        self._next_step_at = time.monotonic() + self._config.retry_after_seconds
        self._emit(
            WatchdogEventKind.EXHAUSTED,
            WatchdogReason.ALL_STEPS_DONE,
            detail=(
                "still no telegram, next attempt in "
                f"{self._config.retry_after_seconds:.0f} s"
            ),
        )

    def _recovered(self) -> None:
        last_step = self._last_step
        self._reset_ladder()
        self._emit(
            WatchdogEventKind.RECOVERED,
            WatchdogReason.TELEGRAM,
            step=last_step,
            detail=f"telegram received after {last_step}"
            if last_step
            else "telegram received",
        )

    async def _run_step(self, step: WatchdogStep) -> bool:
        """Run one rung; return True if a remedial step ran and needs a grace period."""
        if step is WatchdogStep.PING:
            # This step only diagnoses, so no grace period follows.
            await self._ping()
            return False
        if step is WatchdogStep.CLEAR_BUFFER:
            return await self._check_buffer()
        # The other steps drop the port on purpose and wait for it to come back.
        with self._own_reconnects():
            if step is WatchdogStep.REOPEN:
                return await self._reopen()
            if step is WatchdogStep.REBOOT:
                return await self._reboot()
            if step is WatchdogStep.USB_RESET:
                return await self._run_hook(step, self._usb_reset)
            return await self._run_hook(step, self._power_cycle)

    @contextmanager
    def _own_reconnects(self) -> Iterator[None]:
        """Mark the changes of the connection in the block as caused by the ladder."""
        self._own_reconnect = True
        try:
            yield
        finally:
            self._own_reconnect = False

    async def _ping(self) -> None:
        step = WatchdogStep.PING
        try:
            version = await self._transport.get_version()
        except CulError as err:
            self._cul_answers = False
            self._emit(
                WatchdogEventKind.FAILED, WatchdogReason.NO_TELEGRAM, step, str(err)
            )
        else:
            self._cul_answers = True
            self._emit(
                WatchdogEventKind.SUCCEEDED, WatchdogReason.NO_TELEGRAM, step, version
            )

    async def _reopen(self) -> bool:
        step = WatchdogStep.REOPEN
        if self._cul_answers:
            self._emit(WatchdogEventKind.SKIPPED, WatchdogReason.CUL_ANSWERS, step)
            return False
        try:
            self._transport.reconnect()
        except CulError as err:
            self._emit(
                WatchdogEventKind.FAILED, WatchdogReason.NO_ANSWER, step, str(err)
            )
            return False
        if await self._wait_connected():
            self._emit(
                WatchdogEventKind.SUCCEEDED,
                WatchdogReason.NO_ANSWER,
                step,
                f"port reopened, CUL initialized ({self._transport.version})",
            )
        else:
            self._emit(
                WatchdogEventKind.FAILED,
                WatchdogReason.NO_ANSWER,
                step,
                f"CUL not back after {self._config.reconnect_timeout_seconds:g} s",
            )
        return True

    async def _check_buffer(self) -> bool:
        step = WatchdogStep.CLEAR_BUFFER
        try:
            free = await self._transport.get_fht_buffer_free()
        except CulError as err:
            self._emit(
                WatchdogEventKind.FAILED, WatchdogReason.STILL_SILENT, step, str(err)
            )
            return False
        if free >= self._config.buffer_critical_bytes:
            self._emit(
                WatchdogEventKind.SKIPPED,
                WatchdogReason.BUFFER_OK,
                step,
                f"{free} bytes free",
            )
            return False
        return await self._clear_buffer(WatchdogReason.BUFFER_CRITICAL, free)

    async def _clear_after_eob(self) -> None:
        now = time.monotonic()
        if (
            self._last_clear is not None
            and now - self._last_clear < self._config.clear_cooldown_seconds
        ):
            _LOGGER.debug("EOB from CUL, FHT buffer was cleared recently")
            return
        try:
            free = await self._transport.get_fht_buffer_free()
        except CulError as err:
            # Like a failed clear, it counts for the cooldown.
            self._last_clear = now
            self._emit(
                WatchdogEventKind.FAILED,
                WatchdogReason.EOB,
                WatchdogStep.CLEAR_BUFFER,
                str(err),
            )
            return
        if free >= self._config.buffer_critical_bytes:
            # A message that did not fit is not a full buffer, and a purge would drop
            # the commands of every controller.
            self._emit(
                WatchdogEventKind.SKIPPED,
                WatchdogReason.BUFFER_OK,
                WatchdogStep.CLEAR_BUFFER,
                f"{free} bytes free",
            )
            return
        await self._clear_buffer(WatchdogReason.EOB, free)

    async def _clear_buffer(
        self, reason: WatchdogReason, free_before: int | None
    ) -> bool:
        """Purge the FHT buffer unless the cap is reached; return True if it ran."""
        step = WatchdogStep.CLEAR_BUFFER
        now = time.monotonic()
        while (
            self._purges and now - self._purges[0] >= self._config.purge_window_seconds
        ):
            self._purges.popleft()
        if len(self._purges) >= self._config.purge_cap:
            self._emit(
                WatchdogEventKind.SKIPPED,
                WatchdogReason.PURGE_LIMIT,
                step,
                f"{len(self._purges)} purges in the last "
                f"{self._config.purge_window_seconds / 3600:g} h",
            )
            return False
        self._last_clear = now
        try:
            await self._transport.clear_fht_buffer()
        except CulError as err:
            self._emit(WatchdogEventKind.FAILED, reason, step, str(err))
            return True
        self._purges.append(now)
        self._purge_count += 1
        try:
            free = await self._transport.get_fht_buffer_free()
        except CulError as err:
            # The line went out, so the commands are gone however the read ended.
            self._emit(
                WatchdogEventKind.SUCCEEDED, reason, step, f"buffer not read: {err}"
            )
            return True
        before = "" if free_before is None else f"{free_before} -> "
        self._emit(
            WatchdogEventKind.SUCCEEDED, reason, step, f"{before}{free} bytes free"
        )
        return True

    async def _reboot(self) -> bool:
        step = WatchdogStep.REBOOT
        started = time.monotonic()
        try:
            await self._transport.reboot()
        except CulCommandBlockedError as err:
            self._emit(
                WatchdogEventKind.SKIPPED, WatchdogReason.DISABLED, step, str(err)
            )
            return False
        except CulError as err:
            self._emit(
                WatchdogEventKind.FAILED, WatchdogReason.STILL_SILENT, step, str(err)
            )
            return True
        # The CUL drops off USB anyway; release the port now so the reconnect starts.
        with suppress(CulError):
            self._transport.reconnect()
        if not await self._wait_connected():
            self._emit(
                WatchdogEventKind.FAILED,
                WatchdogReason.STILL_SILENT,
                step,
                f"CUL not back after {self._config.reconnect_timeout_seconds:g} s",
            )
            return True
        try:
            uptime = await self._transport.get_uptime()
        except CulError as err:
            self._emit(
                WatchdogEventKind.FAILED, WatchdogReason.STILL_SILENT, step, str(err)
            )
            return True
        if uptime > time.monotonic() - started + _REBOOT_UPTIME_MARGIN_SECONDS:
            self._emit(
                WatchdogEventKind.FAILED,
                WatchdogReason.STILL_SILENT,
                step,
                f"CUL did not reboot (uptime {uptime:.0f} s)",
            )
        else:
            self._emit(
                WatchdogEventKind.SUCCEEDED,
                WatchdogReason.STILL_SILENT,
                step,
                f"CUL rebooted and initialized ({self._transport.version}, "
                f"uptime {uptime:.0f} s)",
            )
        return True

    async def _run_hook(self, step: WatchdogStep, hook: ResetHook | None) -> bool:
        if hook is None:
            self._emit(WatchdogEventKind.SKIPPED, WatchdogReason.NOT_CONFIGURED, step)
            return False
        try:
            detail = await hook()
        except Exception as err:  # noqa: BLE001 - reset hooks may fail in any way
            self._emit(
                WatchdogEventKind.FAILED, WatchdogReason.STILL_SILENT, step, repr(err)
            )
            return True
        # Re-run the init on a fresh port, whatever the reset did to the old one.
        with suppress(CulError):
            self._transport.reconnect()
        if await self._wait_connected():
            self._emit(
                WatchdogEventKind.SUCCEEDED,
                WatchdogReason.STILL_SILENT,
                step,
                detail or "",
            )
        else:
            self._emit(
                WatchdogEventKind.FAILED,
                WatchdogReason.STILL_SILENT,
                step,
                f"{detail or 'reset done'}, CUL not back after "
                f"{self._config.reconnect_timeout_seconds:g} s",
            )
        return True

    async def _wait_connected(self) -> bool:
        deadline = time.monotonic() + self._config.reconnect_timeout_seconds
        while not self._transport.connected:
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(self._config.poll_interval_seconds)
        return True

    def _emit(
        self,
        kind: WatchdogEventKind,
        reason: WatchdogReason,
        step: WatchdogStep | None = None,
        detail: str = "",
    ) -> None:
        event = WatchdogEvent(kind=kind, reason=reason, step=step, detail=detail)
        level = (
            logging.WARNING
            if kind
            in (
                WatchdogEventKind.SILENCE,
                WatchdogEventKind.FAILED,
                WatchdogEventKind.EXHAUSTED,
            )
            else logging.INFO
        )
        _LOGGER.log(
            level, "CUL watchdog: %s %s (%s) %s", kind, step or "", reason, detail
        )
        if self._on_event is None:
            return
        try:
            self._on_event(event)
        except Exception:
            _LOGGER.exception("Error in CUL watchdog event callback")
