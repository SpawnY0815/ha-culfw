"""Repairs for the culfw integration."""

from datetime import datetime, timedelta
import logging

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import (
    CUL_UNREACHABLE_AFTER,
    DOMAIN,
    FHT_BUFFER_CRITICAL_BYTES,
    FHT_BUFFER_WARNING_BYTES,
)
from .coordinator import CulStatus
from .pyculfw import (
    FhtDevice,
    FhtNetwork,
    WatchdogEvent,
    WatchdogEventKind,
    device_label,
)

_LOGGER = logging.getLogger(__name__)

ISSUE_CUL_UNREACHABLE = "cul_unreachable"
ISSUE_FHT_BUFFER_LOW = "fht_buffer_low"
ISSUE_WATCHDOG_EXHAUSTED = "watchdog_exhausted"

# The issues of one device have the id of the device after these prefixes.
_DEVICE_SILENT_PREFIX = "device_silent_"
_BATTERY_LOW_PREFIX = "battery_low_"
_TIME_SYNC_PREFIX = "time_sync_missing_"
_UNRESPONSIVE_PREFIX = "device_unresponsive_"
_DEVICE_ISSUE_PREFIXES = (
    _DEVICE_SILENT_PREFIX,
    _BATTERY_LOW_PREFIX,
    _TIME_SYNC_PREFIX,
    _UNRESPONSIVE_PREFIX,
)


def device_silent_issue(device_id: str) -> str:
    """Return the issue id for a silent device."""
    return f"{_DEVICE_SILENT_PREFIX}{device_id}"


def battery_low_issue(device_id: str) -> str:
    """Return the issue id for a device with a weak battery."""
    return f"{_BATTERY_LOW_PREFIX}{device_id}"


def device_unresponsive_issue(device_id: str) -> str:
    """Return the issue id for an FHT80b that stopped echoing our messages."""
    return f"{_UNRESPONSIVE_PREFIX}{device_id}"


def time_sync_issue(device_id: str) -> str:
    """Return the issue id for an FHT80b that does not take the time."""
    return f"{_TIME_SYNC_PREFIX}{device_id}"


class IssueTracker:
    """Raise and withdraw repair issues from the integration's state.

    The issues are raised in the issue registry (Settings > Repairs) and removed again
    when the cause is gone:

    - `device_silent_<id>`: no telegram for longer than the threshold of the device. It
      is an error from the first moment, because the entities of the device are
      unavailable then. The silence is counted from when the integration started
      listening and from when the link to the CUL came back, so restored devices do not
      raise false alarms right after a restart or an outage.
    - `battery_low_<id>`: the device reports a weak battery.
    - `fht_buffer_low`: few free bytes in the FHT send buffer of the CUL (a warning
      below 128 bytes twice in a row, an error below 32).
    - `cul_unreachable`: the CUL has been disconnected for 15 minutes. While it is
      raised, the device_silent issues are withdrawn, which gives one alarm instead of
      a dozen.
    - `watchdog_exhausted`: the watchdog tried every step and the CUL stays silent. It
      is withdrawn when telegrams arrive again, and when a change of the connection ends
      the ladder, because the watchdog starts over then.
    - `time_sync_missing_<id>`: an FHT80b did not acknowledge the last time syncs.
    - `device_unresponsive_<id>`: the outbox cut an FHT80b off from automatic messages
      because it did not echo the last messages. It is withdrawn when the controller
      echoes a command again.

    The tracker also logs one info line when a device becomes silent and one when it is
    heard again, at the same moments as the `device_silent` issue. That is one line per
    device however many entities it has, and none for repeated checks. A device is not
    judged while the link to the CUL is down, however short the outage is, because no
    telegram can arrive then and the outage explains the silence. The loss of the link
    is logged on its own, and every device gets a new silence window when it is back.

    The issues stay in the registry when the entry unloads, because Home Assistant keeps
    whether the user dismissed an issue only as long as the issue exists. The registry
    is therefore the truth about what is raised, not the tracker, and a new tracker
    withdraws what an earlier one raised: the two issues that only events can confirm,
    and the issues of devices that are no longer in the network.
    """

    def __init__(
        self, hass: HomeAssistant, entry_id: str, network: FhtNetwork, port: str
    ) -> None:
        """Initialize the tracker; the silence is counted from now on."""
        self._hass = hass
        self._entry_id = entry_id
        self._network = network
        self._port = port
        self._listening_since = dt_util.utcnow()
        self._link_down = False
        self._cul_unreachable = False
        self._unreachable_timer: CALLBACK_TYPE | None = None
        self._buffer_low_polls = 0
        # The devices whose silence was logged and who were not heard since.
        self._silent_logged: set[str] = set()

    @callback
    def async_start(self) -> None:
        """Withdraw the issues that this run cannot confirm.

        An outage of the CUL and a watchdog that gave up are known from events, and a
        new run starts without them, so it would never withdraw what the run before
        left behind, and so does a controller that the outbox cut off, because the
        outbox starts with every channel open. The same holds for the issues of a
        device that is not in the network any more, because it was ignored or removed or
        its stored state is gone: no check of this run reaches it, and the user cannot
        act on the issue.
        """
        self._delete(ISSUE_CUL_UNREACHABLE)
        self._delete(ISSUE_WATCHDOG_EXHAUSTED)
        for domain, issue_id in list(ir.async_get(self._hass).issues):
            if domain != DOMAIN:
                continue
            device_id = _device_of_issue(issue_id)
            if device_id is not None and (
                issue_id.startswith(_UNRESPONSIVE_PREFIX)
                or device_id not in self._network.devices
            ):
                self._delete(issue_id)

    @callback
    def async_check_device(self, device: FhtDevice) -> None:
        """Re-evaluate the issues of one device."""
        device_id = device.device_id
        now = dt_util.utcnow()
        silent_for = self._silent_for(device, now)
        threshold = self._network.stale_after[device.type]
        heard = not _silent_beyond(device, now, threshold)
        if silent_for > threshold and not self._link_down:
            name = self._device_name(device_id)
            hours = f"{threshold.total_seconds() / 3600:g}"
            last_seen = _format_time(device.last_seen)
            self._create(
                device_silent_issue(device_id),
                "device_silent",
                ir.IssueSeverity.ERROR,
                {"name": name, "last_seen": last_seen, "hours": hours},
            )
            if device_id not in self._silent_logged:
                self._silent_logged.add(device_id)
                _LOGGER.info(
                    "%s is unavailable: no telegram for more than %s h (last heard: %s)",
                    name,
                    hours,
                    last_seen,
                )
        elif self._cul_unreachable or heard:
            self._delete(device_silent_issue(device_id))
        # A device that is silent but still in the grace period after the start keeps
        # the issue of the run before, so that a dismissal of the user survives.
        if heard and device_id in self._silent_logged:
            self._silent_logged.remove(device_id)
            _LOGGER.info("%s is available again", self._device_name(device_id))

        if device.battery_low:
            self._create(
                battery_low_issue(device_id),
                "battery_low",
                ir.IssueSeverity.WARNING,
                {"name": self._device_name(device_id)},
            )
        else:
            self._delete(battery_low_issue(device_id))

    @callback
    def async_check_all(self) -> None:
        """Re-evaluate every device (called every minute)."""
        for device in self._network.devices.values():
            self.async_check_device(device)

    @callback
    def async_forget_device(self, device_id: str) -> None:
        """Withdraw the issues of a removed or ignored device."""
        self._silent_logged.discard(device_id)
        self._delete(device_silent_issue(device_id))
        self._delete(battery_low_issue(device_id))
        self._delete(time_sync_issue(device_id))
        self._delete(device_unresponsive_issue(device_id))

    @callback
    def async_channel_broken(self, device_id: str) -> None:
        """Raise an issue: the outbox stopped sending automatic messages to the FHT80b."""
        self._create(
            device_unresponsive_issue(device_id),
            "device_unresponsive",
            ir.IssueSeverity.WARNING,
            {"name": self._device_name(device_id)},
        )

    @callback
    def async_channel_recovered(self, device_id: str) -> None:
        """Withdraw the issue after the FHT80b echoed a command again."""
        self._delete(device_unresponsive_issue(device_id))

    @callback
    def async_time_sync_missing(self, device_id: str, missed: int) -> None:
        """Raise an issue: the FHT80b did not acknowledge `missed` syncs in a row."""
        self._create(
            time_sync_issue(device_id),
            "time_sync_missing",
            ir.IssueSeverity.WARNING,
            {"name": self._device_name(device_id), "missed": str(missed)},
        )

    @callback
    def async_time_sync_ok(self, device_id: str) -> None:
        """Withdraw the time sync issue after an acknowledged sync."""
        self._delete(time_sync_issue(device_id))

    @callback
    def async_cul_connection(self, connected: bool) -> None:
        """Track the serial connection; raise an issue after 15 minutes without it."""
        if connected:
            self._cancel_unreachable_timer()
            if self._link_down:
                self._link_down = False
                # Devices need a moment to be heard again after the outage.
                self._listening_since = dt_util.utcnow()
            if self._cul_unreachable:
                self._cul_unreachable = False
                self._delete(ISSUE_CUL_UNREACHABLE)
            return
        self._link_down = True
        if self._unreachable_timer is None and not self._cul_unreachable:
            self._unreachable_timer = async_call_later(
                self._hass, CUL_UNREACHABLE_AFTER, self._async_cul_unreachable
            )

    @callback
    def async_cul_status(self, status: CulStatus | None) -> None:
        """Check the free FHT buffer after each poll of the CUL."""
        if status is None:
            return
        free = status.fht_buffer_free_bytes
        placeholders = {"free": str(free)}
        if free < FHT_BUFFER_CRITICAL_BYTES:
            self._buffer_low_polls += 1
            self._create(
                ISSUE_FHT_BUFFER_LOW,
                "fht_buffer_low",
                ir.IssueSeverity.ERROR,
                placeholders,
            )
        elif free < FHT_BUFFER_WARNING_BYTES:
            self._buffer_low_polls += 1
            if self._buffer_low_polls >= 2:
                self._create(
                    ISSUE_FHT_BUFFER_LOW,
                    "fht_buffer_low",
                    ir.IssueSeverity.WARNING,
                    placeholders,
                )
        else:
            self._buffer_low_polls = 0
            self._delete(ISSUE_FHT_BUFFER_LOW)

    @callback
    def async_watchdog_event(self, event: WatchdogEvent) -> None:
        """Raise an issue when the watchdog gives up, withdraw it when that is over."""
        if event.kind == WatchdogEventKind.EXHAUSTED:
            self._create(
                ISSUE_WATCHDOG_EXHAUSTED,
                "watchdog_exhausted",
                ir.IssueSeverity.ERROR,
                {"port": self._port, "detail": event.detail or ""},
            )
        elif event.kind in (WatchdogEventKind.RECOVERED, WatchdogEventKind.ABORTED):
            self._delete(ISSUE_WATCHDOG_EXHAUSTED)

    @callback
    def async_stop(self) -> None:
        """Stop the timer of the outage check; the issues stay (entry unloaded)."""
        self._cancel_unreachable_timer()

    @callback
    def _async_cul_unreachable(self, _now: datetime) -> None:
        self._unreachable_timer = None
        self._cul_unreachable = True
        self._create(
            ISSUE_CUL_UNREACHABLE,
            "cul_unreachable",
            ir.IssueSeverity.ERROR,
            {
                "port": self._port,
                "minutes": f"{CUL_UNREACHABLE_AFTER.total_seconds() / 60:g}",
            },
        )
        for device_id in self._network.devices:
            self._delete(device_silent_issue(device_id))

    def _silent_for(self, device: FhtDevice, now: datetime) -> timedelta:
        heard = device.last_seen
        since = (
            self._listening_since
            if heard is None
            else max(heard, self._listening_since)
        )
        return now - since

    def _device_name(self, device_id: str) -> str:
        entry = dr.async_get(self._hass).async_get_device_by_identifier(
            (DOMAIN, device_id), self._entry_id
        )
        if entry is None:
            return device_label(device_id)
        return entry.name_by_user or entry.name or device_label(device_id)

    def _create(
        self,
        issue_id: str,
        translation_key: str,
        severity: ir.IssueSeverity,
        placeholders: dict[str, str],
    ) -> None:
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=severity,
            translation_key=translation_key,
            translation_placeholders=placeholders,
        )

    def _delete(self, issue_id: str) -> None:
        ir.async_delete_issue(self._hass, DOMAIN, issue_id)

    def _cancel_unreachable_timer(self) -> None:
        if self._unreachable_timer is not None:
            self._unreachable_timer()
            self._unreachable_timer = None


@callback
def async_delete_issues(hass: HomeAssistant) -> None:
    """Delete every repair issue of the integration, also the dismissed ones.

    No issue carries its config entry in this release, so nothing else removes the
    issues of an integration that is disabled or removed.
    """
    registry = ir.async_get(hass)
    for domain, issue_id in list(registry.issues):
        if domain == DOMAIN:
            registry.async_delete(domain, issue_id)


def _device_of_issue(issue_id: str) -> str | None:
    """Return the id of the device an issue is about, None for the other issues."""
    for prefix in _DEVICE_ISSUE_PREFIXES:
        if issue_id.startswith(prefix):
            return issue_id.removeprefix(prefix)
    return None


def _silent_beyond(device: FhtDevice, now: datetime, threshold: timedelta) -> bool:
    """Return True if the device was not heard for longer than the threshold."""
    return device.last_seen is None or now - device.last_seen > threshold


def _format_time(value: datetime | None) -> str:
    if value is None:
        return "-"
    return dt_util.as_local(value).strftime("%Y-%m-%d %H:%M")
