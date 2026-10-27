"""Commands for an FHT80b that no echo has settled yet."""

from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from .parser import FhtCode


class PendingState(StrEnum):
    """Where a command is on its way to the device."""

    STAGED = "staged"
    QUEUED = "queued"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


_LIVE_STATES = frozenset({PendingState.STAGED, PendingState.QUEUED})
_FAILED_STATES = frozenset({PendingState.EXPIRED, PendingState.INVALIDATED})


@dataclass(slots=True, kw_only=True)
class PendingCommand:
    """A command that was requested and that the device has not echoed yet.

    The queued_at time is when the command was requested, and the timeout of the display
    counts from the request. The exception is a command that waits for its turn, one of
    several messages that go one after the other, such as the days of a week program.
    Its message may wait behind the days before it, which is not the fault of the
    device, so its timeout counts from sent_at, the time its message went to the CUL,
    and it gets twice the timeout while it is still staged. The message_id ties the
    command to the message that carries it, and it is None for a command without one.
    The state changes only through the PendingQueue.

    A command is live while it is STAGED (waiting for its message to be sent) or QUEUED
    (sent to the CUL, waiting for the device to collect it and echo it). The other
    states are final, and the queue hands a command out in its final state exactly once.
    """

    code: int
    raw: int
    queued_at: datetime
    sent_at: datetime | None = None
    message_id: int | None = None
    state: PendingState = PendingState.STAGED
    waits_for_turn: bool = False

    @property
    def clock_start(self) -> datetime:
        """Return the time from which the timeout counts."""
        if self.waits_for_turn and self.sent_at is not None:
            return self.sent_at
        return self.queued_at

    def is_stale(self, now: datetime, timeout: timedelta) -> bool:
        """Return True when the command waited for its echo for longer than `timeout`."""
        if self.waits_for_turn and self.state is PendingState.STAGED:
            timeout *= 2
        return now - self.clock_start > timeout


def _echoes_by_code_only(code: int) -> bool:
    """Return True for the date and time codes, whose echo shows another value.

    culfw replaces the minute of a time sync with its own running minute, so the echo
    of that command says nothing about the value that was requested.
    """
    return FhtCode.YEAR <= code <= FhtCode.MINUTE


class PendingQueue:
    """The commands in flight to one FHT80b, as a FIFO for each command code.

    The device collects the messages of the CUL in order and echoes every command with
    the value it stored. So the echo of a code belongs to the oldest command of that
    code that was sent:

    - An echo with the value of a sent command confirms that command. A sent command
      that is older was never echoed, so it is superseded: the device took a later
      value.
    - An echo that matches none of the sent commands was not caused by them, either
      because the device kept another value (a limit, a change at the device) or because
      it is a report the device sends on its own. The device wins: every sent command of
      that code is superseded.
    - The codes of date and time (YEAR to MINUTE) are matched by code only. The oldest
      sent command of the code is confirmed whatever value the echo has.

    A command that is still staged is not touched by an echo, because the device cannot
    have echoed what was not sent yet.

    The newest live command of a code is what the device is going to hold, so that is
    what an entity shows while it waits, as pending and never as confirmed. The queue
    holds nothing but live commands. A command leaves it as CONFIRMED, SUPERSEDED,
    EXPIRED or INVALIDATED, and the method that retires it returns it, so the owner can
    tell why a command is gone.

    The queue also remembers, for each code, that its last command ended as EXPIRED or
    INVALIDATED, which `failure()` tells. The memory ends with a new command of the code
    and with any report of the device for the code, because the device then says what
    it holds. It is not stored: a restart forgets it, and the device is read again.
    """

    def __init__(self) -> None:
        """Initialize an empty queue."""
        self._commands: dict[int, deque[PendingCommand]] = {}
        self._failed: dict[int, PendingState] = {}
        self._last_message_id = 0

    def new_message_id(self) -> int:
        """Return an id for a message that is not used before."""
        self._last_message_id += 1
        return self._last_message_id

    def add(
        self,
        code: int,
        raw: int,
        queued_at: datetime,
        *,
        message_id: int | None = None,
        state: PendingState = PendingState.STAGED,
        sent_at: datetime | None = None,
        waits_for_turn: bool = False,
    ) -> PendingCommand:
        """Append a live command to the FIFO of its code and return it.

        A message id that the queue did not hand out itself (a command restored from
        the store) moves the counter on, so that new_message_id() never repeats it.
        """
        if state not in _LIVE_STATES:
            raise ValueError(f"A new pending command cannot be {state}")
        if message_id is not None:
            self._last_message_id = max(self._last_message_id, message_id)
        command = PendingCommand(
            code=code,
            raw=raw,
            queued_at=queued_at,
            sent_at=sent_at,
            message_id=message_id,
            state=state,
            waits_for_turn=waits_for_turn,
        )
        self._failed.pop(code, None)
        self._commands.setdefault(code, deque()).append(command)
        return command

    def mark_queued(self, message_id: int, sent_at: datetime) -> list[PendingCommand]:
        """Mark the staged commands of a message as sent to the CUL at `sent_at`.

        Only the commands that wait for their turn record the time, because only their
        timeout counts from the sending.
        """
        queued = [
            command
            for fifo in self._commands.values()
            for command in fifo
            if command.message_id == message_id and command.state == PendingState.STAGED
        ]
        for command in queued:
            command.state = PendingState.QUEUED
            if command.waits_for_turn:
                command.sent_at = sent_at
        return queued

    def commands(self) -> list[PendingCommand]:
        """Return every live command, the oldest first."""
        return sorted(
            (command for fifo in self._commands.values() for command in fifo),
            key=lambda command: command.queued_at,
        )

    def live(self, codes: Iterable[int]) -> list[PendingCommand]:
        """Return the live commands of the codes, the oldest first."""
        wanted = set(codes)
        return [command for command in self.commands() if command.code in wanted]

    def failure(self, code: int) -> PendingState | None:
        """Return EXPIRED or INVALIDATED if the last command of `code` ended so.

        The result is None when no command of the code failed since the device reported
        the code or a new command of the code was added.
        """
        return self._failed.get(code)

    def newest(
        self, code: int, now: datetime, timeout: timedelta
    ) -> PendingCommand | None:
        """Return the newest live command of `code` that is not stale."""
        for command in reversed(self._commands.get(code, ())):
            if not command.is_stale(now, timeout):
                return command
        return None

    def display_value[T](
        self,
        code: int,
        device_value: T,
        now: datetime,
        timeout: timedelta,
        convert: Callable[[int], T],
    ) -> T:
        """Return the newest live value of `code`, or the device value without one.

        The convert callable turns the raw value into the type of the device value.
        """
        command = self.newest(code, now, timeout)
        return device_value if command is None else convert(command.raw)

    def reconcile(self, code: int, raw: int) -> list[PendingCommand]:
        """Settle the sent commands of `code` with a value that the device reported.

        Returns the commands that left the queue, the oldest first, as CONFIRMED or
        SUPERSEDED.
        """
        self._failed.pop(code, None)
        fifo = self._commands.get(code)
        if not fifo:
            return []
        sent = [command for command in fifo if command.state == PendingState.QUEUED]
        if not sent:
            return []
        if _echoes_by_code_only(code):
            confirmed: int | None = 0
        else:
            confirmed = next(
                (index for index, command in enumerate(sent) if command.raw == raw),
                None,
            )
        settled = sent if confirmed is None else sent[: confirmed + 1]
        for command in settled:
            command.state = PendingState.SUPERSEDED
        if confirmed is not None:
            settled[confirmed].state = PendingState.CONFIRMED
        self._remove(code, settled)
        return settled

    def expire(self, now: datetime, timeout: timedelta) -> list[PendingCommand]:
        """Retire the live commands that waited for longer than `timeout` as EXPIRED."""
        expired = [
            command for command in self.commands() if command.is_stale(now, timeout)
        ]
        return self.retire(expired, PendingState.EXPIRED)

    def invalidate(self) -> list[PendingCommand]:
        """Retire every live command as INVALIDATED.

        The owner calls it when the commands cannot be on their way any more, for
        example after the CUL lost its buffer.
        """
        return self.retire(self.commands(), PendingState.INVALIDATED)

    def retire(
        self, commands: Iterable[PendingCommand], state: PendingState
    ) -> list[PendingCommand]:
        """Retire live commands of this queue in a final state and return them.

        The owner uses it for a command that it takes back itself, for example a staged
        command that a newer value replaced (SUPERSEDED) or one that cannot be sent
        (INVALIDATED).
        """
        if state in _LIVE_STATES:
            raise ValueError(f"A retired pending command cannot be {state}")
        retired = list(commands)
        for command in retired:
            command.state = state
            self._remove(command.code, [command])
            if state in _FAILED_STATES:
                self._failed[command.code] = state
        return retired

    def _remove(self, code: int, commands: list[PendingCommand]) -> None:
        fifo = self._commands[code]
        for command in commands:
            fifo.remove(command)
        if not fifo:
            del self._commands[code]
