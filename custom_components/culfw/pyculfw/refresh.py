"""Decide when to ask an FHT80b for its settings and its week program, and ask."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import IntEnum
import logging
from typing import Final

from .commands import REPORT_ALL, Report2Settings
from .const import (
    REFRESH_INTERVAL,
    REFRESH_MIN_GAP,
    SEND_MAX_SILENCE,
    WEEK_PROGRAM_AFTER_CONNECT,
    WEEK_PROGRAM_BATCH_GAP,
    WEEK_PROGRAM_READ_WINDOW,
    WEEK_PROGRAM_RETRY_GAP,
    WEEK_PROGRAM_START_GAP,
)
from .devices import (
    DeviceUpdate,
    FhtNetwork,
    FhtRoomController,
    NetworkUpdate,
    device_label,
)
from .outbox import FhtOutbox, FhtSendError, SendFailure
from .parser import FhtCode
from .pending import PendingState
from .tasks import CreateTask, cancel_task, start_task

_LOGGER = logging.getLogger(__name__)

# Everything that a controller reports on request: the warnings, the mode, the three
# temperature settings, the desired temperature and the low temperature offset.
FULL_REFRESH: Final = int(Report2Settings.ALL)
# What our own mode or holiday command can have changed on the controller.
READ_BACK: Final = int(Report2Settings.MODE | Report2Settings.DESIRED_TEMP)

_OWN_COMMANDS: Final = frozenset({FhtCode.MODE, FhtCode.HOLIDAY1, FhtCode.HOLIDAY2})

# These refusals belong to the controller, so the next one in line may still be asked.
# Any other refusal (the link, the credit, the buffer) holds for all of them.
_CONTROLLER_REFUSALS: Final = frozenset(
    {
        SendFailure.UNKNOWN_DEVICE,
        SendFailure.DEVICE_SILENT,
        SendFailure.DEVICE_UNCONFIRMED,
        SendFailure.DEVICE_UNRESPONSIVE,
    }
)


class RefreshReason(IntEnum):
    """Why a controller is asked for its settings or program, the most urgent first."""

    READ_BACK = 0
    COMMANDS_LOST = 1
    CUL_RESET = 2
    FIRST_CONTACT = 3
    DAILY = 4


@dataclass(frozen=True, slots=True)
class RefreshRequest:
    """A report request for a controller.

    The `code` is REPORT2 for the settings or REPORT1 for the week program, and
    `settings` is the mask of what it asks for: the settings for a report2, the days
    for a report1.
    """

    device_id: str
    settings: int
    reason: RefreshReason
    code: int = FhtCode.REPORT2


class RefreshPlanner:
    """Ask the FHT80b controllers for their settings when there is a reason to.

    A controller reports its mode, its desired temperature and its settings only when
    asked (report2), so the integration asks. The reasons are:

    - First contact: the settings were never read (`settings_read_at` is empty).
    - A reset of the CUL, which emptied the send buffers, so commands may be gone.
    - Commands that were accepted and are gone, expired or dropped, so what the
      controller holds is unknown.
    - A mode or holiday command of ours that the controller echoed: it can change
      the desired temperature and the end of the holiday by itself, so these are read
      back (mode and desired temperature only).
    - The last read is 24 hours old.

    The policy is a function of the state of the network and of the notes that the owner
    passes in. `plan()` lists who is due, most urgent first, and `async_cycle()` asks
    the first one that the outbox takes. One controller is asked per cycle, and the owner
    calls the cycle once a minute, which staggers the requests. A controller gets at most
    one automatic request per `REFRESH_MIN_GAP`, only while it was heard within
    `SEND_MAX_SILENCE`, and nothing while the credit or the buffer reserve of the CUL
    does not allow it. The credit has to be `AUTOMATIC_MIN_CREDIT_10MS`, so that the
    account keeps a reserve for the commands of the user. A request for a controller
    that counts down its synchronization with the valves is staged, and the outbox
    holds it back until the countdown is over. The outbox refuses automatic requests to a controller that never
    echoed a command of this CUL (after one probe) and to one that stopped echoing, and
    the planner leaves them for later.

    A report2 is a message of its own in the outbox, so it never travels with a command
    of the user.

    The week program (report1) is read by the same cycle when the owner turns it on, but
    it is much dearer: the controller answers in its time slots, so the 28 times of a
    week take about 35 minutes. `plan_week_programs()` lists who is due:

    - Once after the first contact of a confirmed controller, as soon as its settings
      are known (a report2 comes first).
    - Again after a reset of the CUL, which emptied the buffers, or a rewrite of its
      house code (`note_cul_reset()`).
    - Every 24 hours counted from the last complete read (`week_program_read_at`, which
      the device stores). A read that was not complete counts as not done, and an
      unknown time of the last read is due.

    The reads are kept apart. Only a confirmed controller is asked, never one that
    the outbox cut off, and only one that has no message of the user in the way. Nothing
    is asked within `WEEK_PROGRAM_AFTER_CONNECT` of a connect, while a report request is
    in the outbox, while the read of any controller is running (until it is complete or
    `WEEK_PROGRAM_READ_WINDOW` is over) and within `WEEK_PROGRAM_START_GAP` of the start
    of the last read. A read that stayed incomplete is asked for again after
    `WEEK_PROGRAM_RETRY_GAP`. The request is the last message in the queue of a
    controller (the outbox sends the commands of the user first), and the settings go
    first in a cycle. The button of the entity asks for the week program whenever the
    user wants it, whatever the rules above say.
    """

    def __init__(
        self,
        network: FhtNetwork,
        outbox: FhtOutbox,
        *,
        spawn: CreateTask = start_task,
        read_week_programs: bool = True,
    ) -> None:
        """Initialize the planner.

        The `spawn` factory starts the task of a cycle, so that the owner ties it to its
        own lifetime. The week programs are read only with `read_week_programs`.
        """
        self._network = network
        self._outbox = outbox
        self._spawn = spawn
        self._read_week_programs = read_week_programs
        self._wanted: dict[str, RefreshRequest] = {}
        self._asked_at: dict[str, datetime] = {}
        self._week_wanted: set[str] = set()
        self._week_asked_at: dict[str, datetime] = {}
        self._week_started_at: datetime | None = None
        self._connected_at = network.now()
        # Counts the resets, so that a reset during a request is not mistaken for the
        # state that the request was made in.
        self._resets = 0
        self._task: asyncio.Task[None] | None = None

    def note_connected(self) -> None:
        """Note that the CUL is connected again, which starts the quiet time."""
        self._connected_at = self._network.now()

    def note_cul_reset(self) -> None:
        """Note that the buffers of the CUL are empty, so every controller is read again.

        This is a reset of the CUL and a rewrite of its house code. A request that was
        made before is gone, and the gap since the last request does not count any more.
        The week programs are read again too.
        """
        self._resets += 1
        self._asked_at.clear()
        self._week_asked_at.clear()
        self._week_started_at = None
        for device_id in self._controllers():
            self._want(device_id, FULL_REFRESH, RefreshReason.CUL_RESET)
            self._week_wanted.add(device_id)

    def note_commands_lost(self, device_id: str) -> None:
        """Note that commands for the controller expired or were dropped."""
        if device_id in self._controllers():
            self._want(device_id, FULL_REFRESH, RefreshReason.COMMANDS_LOST)

    def handle_update(self, update: NetworkUpdate | None) -> None:
        """Note the echo of a mode or holiday command that we sent.

        The owner calls it with every update of the network. The read-back is made at
        the next cycle.
        """
        if not isinstance(update, DeviceUpdate):
            return
        if any(
            command.state is PendingState.CONFIRMED and command.code in _OWN_COMMANDS
            for command in update.settled
        ):
            self._want(update.device.device_id, READ_BACK, RefreshReason.READ_BACK)

    def plan(self, now: datetime | None = None) -> list[RefreshRequest]:
        """Return the requests that are due now, the most urgent first.

        Nothing is changed. A controller that was not heard within SEND_MAX_SILENCE
        would not collect the request, and one that was asked less than REFRESH_MIN_GAP
        ago is not asked again, whatever the reason.
        """
        now = now or self._network.now()
        due: list[tuple[RefreshRequest, FhtRoomController]] = []
        for device_id, device in self._controllers().items():
            if request := self._due(device_id, device, now):
                due.append((request, device))
        due.sort(
            key=lambda item: (
                item[0].reason,
                item[1].settings_read_at.timestamp() if item[1].settings_read_at else 0,
                item[0].device_id,
            )
        )
        return [request for request, _ in due]

    def plan_week_programs(self, now: datetime | None = None) -> list[RefreshRequest]:
        """Return the reads of the week program that are due now, the most urgent first.

        Nothing is changed. There is at most one read at a time, so the list holds the
        controllers that may start one, and the cycle asks the first of them.
        """
        now = now or self._network.now()
        if not self._read_week_programs or self._week_blocked(now):
            return []
        due: list[tuple[RefreshReason, float, str]] = []
        for device_id, device in self._controllers().items():
            if (reason := self._week_due(device_id, device, now)) is not None:
                read_at = device.week_program_read_at
                due.append((reason, read_at.timestamp() if read_at else 0, device_id))
        return [
            RefreshRequest(device_id, REPORT_ALL, reason, FhtCode.REPORT1)
            for reason, _, device_id in sorted(due)
        ]

    def tick(self) -> None:
        """Start a cycle unless the last one is still running."""
        if self._task is None or self._task.done():
            self._task = self._spawn(self._run_cycle(), "culfw refresh")

    async def _run_cycle(self) -> None:
        await self.async_cycle()

    async def async_cycle(self) -> RefreshRequest | None:
        """Ask the first controller in line that the outbox takes; return the request."""
        self._forget_removed()
        for request in [*self.plan(), *self.plan_week_programs()]:
            wanted = self._wanted.get(request.device_id)
            resets = self._resets
            try:
                await self._outbox.request(
                    request.device_id,
                    {request.code: request.settings},
                    automatic=True,
                )
            except FhtSendError as err:
                if err.failure in _CONTROLLER_REFUSALS:
                    _LOGGER.debug(
                        "No refresh of %s for now: %s",
                        device_label(request.device_id),
                        err,
                    )
                    continue
                _LOGGER.debug("Refresh waits for the CUL: %s", err)
                return None
            self._record(request, wanted, resets)
            _LOGGER.debug(
                "Asked %s for its %s (%#04x): %s",
                device_label(request.device_id),
                "week program" if request.code == FhtCode.REPORT1 else "settings",
                request.settings,
                request.reason.name.lower(),
            )
            return request
        return None

    def _record(
        self, request: RefreshRequest, wanted: RefreshRequest | None, resets: int
    ) -> None:
        """Note that the outbox took the request, and clear the reason it was made for.

        A note that came in while the outbox checked the CUL stays for the next one. A
        reset during the request emptied the buffers, so the request may be gone and the
        read counts as not asked.
        """
        device_id = request.device_id
        now = self._network.now()
        if request.code == FhtCode.REPORT1:
            if resets == self._resets:
                self._week_asked_at[device_id] = now
                self._week_started_at = now
                self._week_wanted.discard(device_id)
            return
        self._asked_at[device_id] = now
        if self._wanted.get(device_id) is wanted:
            self._wanted.pop(device_id, None)

    async def async_stop(self) -> None:
        """Stop the cycle that is running."""
        task, self._task = self._task, None
        if task is not None and not task.done():
            await cancel_task(task)

    def _controllers(self) -> dict[str, FhtRoomController]:
        """Return the FHT80b controllers of the network by device id."""
        return {
            device_id: device
            for device_id, device in self._network.devices.items()
            if isinstance(device, FhtRoomController)
        }

    def _want(self, device_id: str, settings: int, reason: RefreshReason) -> None:
        """Remember a reason to read the controller, merged with an earlier one."""
        self._wanted[device_id] = _merge(
            self._wanted.get(device_id), device_id, settings, reason
        )

    def _forget_removed(self) -> None:
        """Forget what is known about controllers that left the network."""
        known = self._controllers()
        for book in (self._wanted, self._asked_at, self._week_asked_at):
            for device_id in [
                device_id for device_id in book if device_id not in known
            ]:
                del book[device_id]
        self._week_wanted &= known.keys()

    def _due(
        self, device_id: str, device: FhtRoomController, now: datetime
    ) -> RefreshRequest | None:
        """Return the request that is due for the controller, if any."""
        silent = self._network.silent_for(device, now)
        if silent is None or silent > SEND_MAX_SILENCE:
            return None
        asked_at = self._asked_at.get(device_id)
        if asked_at is not None and timedelta(0) <= now - asked_at < REFRESH_MIN_GAP:
            return None
        request = self._wanted.get(device_id)
        if (reason := _scheduled(device, now)) is not None:
            request = _merge(request, device_id, FULL_REFRESH, reason)
        return request

    def _week_blocked(self, now: datetime) -> bool:
        """Return True while no read of a week program may start, for any controller."""
        if timedelta(0) <= now - self._connected_at < WEEK_PROGRAM_AFTER_CONNECT:
            return True
        started = self._week_started_at
        if started is not None and timedelta(0) <= now - started < (
            WEEK_PROGRAM_START_GAP
        ):
            return True
        if self._outbox.report_pending():
            return True
        return any(
            self._week_running(device_id, device, now)
            for device_id, device in self._controllers().items()
        )

    def _week_asked(self, device_id: str, device: FhtRoomController) -> datetime | None:
        """Return when the read that is not complete was asked for, None without one."""
        asked_at = self._week_asked_at.get(device_id)
        if asked_at is None:
            return None
        read_at = device.week_program_read_at
        if read_at is not None and read_at >= asked_at:
            return None
        return asked_at

    def _week_running(
        self, device_id: str, device: FhtRoomController, now: datetime
    ) -> bool:
        """Return True while the controller is still answering a request for its times.

        That is the case when the request was asked for lately and the read is not
        complete, and when times of a read that someone else asked for (the button)
        arrive.
        """
        asked_at = self._week_asked(device_id, device)
        if asked_at is not None and timedelta(0) <= now - asked_at < (
            WEEK_PROGRAM_READ_WINDOW
        ):
            return True
        batch_at = device.week_program_batch_at
        return (
            bool(device.week_program_batch)
            and batch_at is not None
            and timedelta(0) <= now - batch_at < WEEK_PROGRAM_BATCH_GAP
        )

    def _week_due(
        self, device_id: str, device: FhtRoomController, now: datetime
    ) -> RefreshReason | None:
        """Return why the week program of the controller is read now, None if it is not."""
        silent = self._network.silent_for(device, now)
        if (
            not device.confirmed
            or device.settings_read_at is None
            or silent is None
            or silent > SEND_MAX_SILENCE
            or self._outbox.is_broken(device_id)
            or self._outbox.has_messages(device_id)
        ):
            return None
        asked_at = self._week_asked(device_id, device)
        if asked_at is not None and timedelta(0) <= now - asked_at < (
            WEEK_PROGRAM_RETRY_GAP
        ):
            return None
        if device_id in self._week_wanted:
            return RefreshReason.CUL_RESET
        read_at = device.week_program_read_at
        if read_at is None:
            return RefreshReason.FIRST_CONTACT
        age = now - read_at
        if age >= REFRESH_INTERVAL or age < timedelta(0):
            return RefreshReason.DAILY
        return None


def _merge(
    earlier: RefreshRequest | None,
    device_id: str,
    settings: int,
    reason: RefreshReason,
) -> RefreshRequest:
    """Return the request that asks for what both ask for, for the more urgent reason."""
    if earlier is not None:
        settings |= earlier.settings
        reason = min(reason, earlier.reason)
    return RefreshRequest(device_id, settings, reason)


def _scheduled(device: FhtRoomController, now: datetime) -> RefreshReason | None:
    """Return the reason the age of the settings gives, None while they are fresh.

    A read time in the future cannot be right, so it counts as stale.
    """
    if device.settings_read_at is None:
        return RefreshReason.FIRST_CONTACT
    age = now - device.settings_read_at
    if age >= REFRESH_INTERVAL or age < timedelta(0):
        return RefreshReason.DAILY
    return None
