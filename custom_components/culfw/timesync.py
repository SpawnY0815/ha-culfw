"""Date and time for the FHT80b controllers."""

from collections.abc import Callable
from datetime import datetime, timedelta
from functools import partial
import logging
from typing import Final

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_time_change
from homeassistant.util import dt as dt_util

from .issues import IssueTracker
from .pyculfw import (
    FhtNetwork,
    FhtOutbox,
    FhtRoomController,
    FhtSendError,
    SendFailure,
    date_time_commands,
    device_label,
)

_LOGGER = logging.getLogger(__name__)

SYNC_HOUR: Final = 4
SYNC_MINUTE: Final = 5
ACK_TIMEOUT: Final = timedelta(minutes=30)
MISSED_SYNCS_FOR_ISSUE: Final = 2

# A controller that is silent, unknown to us or cut off from automatic messages is the
# normal state of a dead or foreign thermostat, so the daily sync stays quiet about it.
_QUIET_FAILURES: Final = frozenset(
    {
        SendFailure.DEVICE_SILENT,
        SendFailure.DEVICE_UNCONFIRMED,
        SendFailure.DEVICE_UNRESPONSIVE,
    }
)


class TimeSync:
    """Send date and time to every alive FHT80b and watch the acknowledgements.

    Without a central the clock of an FHT80b drifts, its day and night program runs at
    the wrong time, and after 5 to 10 days without any traffic it stops sending,
    according to the FHEM wiki. FHEM sets time and date every night. This does the same
    once a day at 04:05 local time, which is after both daylight saving switches, and
    right after the UTC offset changed, so the clocks are not an hour off for a day.

    The message goes through the outbox, as an urgent message of its own with the
    minute last, so it does not wait for more commands but still waits for the message
    that is in the CUL for the same controller. Only controllers that are alive and that
    are not cut off from automatic messages get it (see FhtOutbox). The controller
    echoes the hour and the minute it received, and the minute is the acknowledgement.
    No echo within 30 minutes counts as a missed sync, and two missed syncs in a row
    raise a repair issue.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        network: FhtNetwork,
        outbox: FhtOutbox,
        issues: IssueTracker,
    ) -> None:
        """Initialize the time sync."""
        self._hass = hass
        self._network = network
        self._outbox = outbox
        self._issues = issues
        self._offset = dt_util.now().utcoffset()
        self._missed: dict[str, int] = {}
        self._unsubscribe: list[CALLBACK_TYPE] = []

    @callback
    def start(self) -> None:
        """Schedule the daily sync and the hourly check for a new UTC offset."""
        self._unsubscribe.append(
            async_track_time_change(
                self._hass,
                self._async_daily,
                hour=SYNC_HOUR,
                minute=SYNC_MINUTE,
                second=0,
            )
        )
        self._unsubscribe.append(
            async_track_time_change(
                self._hass, self._async_check_offset, minute=0, second=30
            )
        )

    @callback
    def stop(self) -> None:
        """Cancel every schedule, including pending acknowledgement checks."""
        while self._unsubscribe:
            self._unsubscribe.pop()()

    @property
    def has_controllers(self) -> bool:
        """Return True once an FHT80b is known, which is the only one that takes time."""
        return any(
            isinstance(device, FhtRoomController)
            for device in self._network.devices.values()
        )

    @callback
    def async_forget_device(self, device_id: str) -> None:
        """Forget the missed syncs of a device that left the network."""
        self._missed.pop(device_id, None)

    async def async_sync_all(
        self, reason: str, *, automatic: bool = True
    ) -> dict[str, SendFailure | None]:
        """Stage date and time for every alive FHT80b; return the result per device.

        A sync that the user asked for (`automatic=False`) also goes to a controller
        that never echoed a command of ours, which is how it becomes known, and it is
        not refused for a lack of radio budget: the message is staged and goes out as
        soon as the duty cycle credit allows. The result says whether the message was
        accepted, not whether the controller got it.
        """
        local = dt_util.now()
        sent_at = dt_util.utcnow()
        results: dict[str, SendFailure | None] = {}
        sent: list[str] = []
        for device in list(self._network.devices.values()):
            if not isinstance(device, FhtRoomController):
                continue
            try:
                await self._outbox.request(
                    device.device_id,
                    dict(date_time_commands(local)),
                    urgent=True,
                    automatic=automatic,
                )
            except FhtSendError as err:
                results[device.device_id] = err.failure
                level = (
                    logging.DEBUG if err.failure in _QUIET_FAILURES else logging.WARNING
                )
                _LOGGER.log(
                    level,
                    "Time sync (%s) for %s not sent: %s",
                    reason,
                    device.label,
                    err,
                )
                continue
            results[device.device_id] = None
            sent.append(device.device_id)
        _LOGGER.info(
            "Time sync (%s) queued for %s%s",
            reason,
            ", ".join(device_label(device_id) for device_id in sent) or "no FHT80b",
            # The message waits for the radio budget, so queued is not yet sent.
            "; it goes out when the radio budget allows" if sent else "",
        )
        if sent:
            self._schedule(
                ACK_TIMEOUT, partial(self._async_check_acks, tuple(sent), sent_at)
            )
        return results

    def _schedule(self, delay: timedelta, action: Callable[[datetime], None]) -> None:
        unsubscribe: CALLBACK_TYPE | None = None

        @callback
        def _run(now: datetime) -> None:
            if unsubscribe in self._unsubscribe:
                self._unsubscribe.remove(unsubscribe)
            action(now)

        unsubscribe = async_call_later(self._hass, delay, _run)
        self._unsubscribe.append(unsubscribe)

    async def _async_daily(self, _now: datetime) -> None:
        await self.async_sync_all("daily")

    async def _async_check_offset(self, _now: datetime) -> None:
        offset = dt_util.now().utcoffset()
        if offset == self._offset:
            return
        _LOGGER.info("UTC offset changed from %s to %s", self._offset, offset)
        self._offset = offset
        await self.async_sync_all("utc_offset_changed")

    @callback
    def _async_check_acks(
        self, device_ids: tuple[str, ...], sent_at: datetime, _now: datetime
    ) -> None:
        for device_id in device_ids:
            device = self._network.devices.get(device_id)
            if not isinstance(device, FhtRoomController):
                continue
            if device.time_ack is not None and device.time_ack >= sent_at:
                self._missed[device_id] = 0
                self._issues.async_time_sync_ok(device_id)
                continue
            missed = self._missed.get(device_id, 0) + 1
            self._missed[device_id] = missed
            _LOGGER.warning(
                "%s did not acknowledge the time sync (%d)", device.label, missed
            )
            if missed >= MISSED_SYNCS_FOR_ISSUE:
                self._issues.async_time_sync_missing(device_id, missed)
