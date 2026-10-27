"""Last known state of the FHT devices heard by the CUL."""

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
import logging
import math
import re
from typing import Any, ClassVar, Final

from .codes import format_display_code
from .commands import week_program_day_codes, week_program_periods
from .const import (
    BOOT_TOLERANCE,
    FHT_SEND_CODES,
    LOWTEMP_OFFSET_MAX,
    LOWTEMP_OFFSET_MIN,
    PENDING_TIMEOUT,
    SYNC_MARGIN,
    SYNC_SECONDS,
    TEMP_OFF,
    TEMP_ON,
    WEEK_PROGRAM_BATCH_GAP,
    WEEK_PROGRAM_FIRST,
    WEEK_PROGRAM_LAST,
    WEEK_PROGRAM_SIZE,
)
from .pairing import WindowPairing
from .parser import (
    SWITCH_TIME_MAX_STEPS,
    SWITCH_TIME_STEP_MINUTES,
    ActuatorState,
    ActuatorValue,
    CulNotice,
    FhtCode,
    FhtMode,
    FhtTelegram,
    FhtTfTelegram,
    FhtWarnings,
    MeasuredTempAssembler,
    NoticeKind,
    ParseResult,
    SetpointSwitch,
    TfState,
    is_week_program,
    week_program_code,
    week_program_reading,
)
from .pending import PendingCommand, PendingQueue, PendingState

_LOGGER = logging.getLogger(__name__)

# The settings that an FHT80b sends only when asked. Their telegrams mark the time of the
# last read-back.
_SETTINGS_CODES: Final = frozenset(
    {
        FhtCode.DAY_TEMP,
        FhtCode.NIGHT_TEMP,
        FhtCode.WINDOWOPEN_TEMP,
        FhtCode.LOWTEMP_OFFSET,
    }
)

# The years that holiday_end() looks ahead. A leap day needs up to eight.
_HOLIDAY_YEARS_AHEAD: Final = 8
# The measured temperature has 16 bits in steps of 0.1 °C.
_MEASURED_RANGE_CELSIUS: Final = (0.0, 6553.5)
# The CC1101 radio chip reports between -138 and -10 dBm.
_RSSI_RANGE_DBM: Final = (-150.0, 0.0)
# The most commands of a controller that the store keeps. A message holds 8 commands, so
# this is far more than can be in flight, and damaged data cannot make the load grow.
_PENDING_STORE_LIMIT: Final = 32
_MESSAGE_ID_MAX: Final = 2**31

# The devices that wait for the user to add or ignore them. A neighbor's heating can
# be heard all day, so the oldest candidate makes room for a new one.
MAX_CANDIDATES: Final = 20


class DeviceType(StrEnum):
    """Kinds of FHT devices."""

    FHT80B = "fht80b"
    FHT80TF = "fht80tf"


# The model names of the FHT devices, as the device registry, the options form and the
# log show them.
DEVICE_MODELS: Final = {DeviceType.FHT80B: "FHT80b", DeviceType.FHT80TF: "FHT80 TF"}


def display_code(device_type: DeviceType, code: str) -> str:
    """Return the code of a device the way the user knows it.

    An FHT80b shows its code as two numbers of three digits on its display, Code 1 and
    Code 2, so that is what the user reads, and "3f48" becomes "063 072". An FHT80 TF shows nothing on any
    display, so its address stays in upper-case hex digits, as does a thermostat code
    that has no display form.
    """
    if device_type is DeviceType.FHT80B:
        with suppress(ValueError):
            return format_display_code(code)
    return code.upper()


def device_label(device_id: str) -> str:
    """Return the name of a device from its ID, such as "FHT80b 063 072".

    This is what the user sees in the device registry, in the options and in the log.
    An ID that does not belong to an FHT device comes back as it is.
    """
    kind, _, code = device_id.partition("_")
    try:
        device_type = DeviceType(kind)
    except ValueError:
        return device_id
    return f"{DEVICE_MODELS[device_type]} {display_code(device_type, code)}"


class WeekDayStatus(StrEnum):
    """Where the week program of one weekday stands.

    UNKNOWN: the controller never reported all four switch times of the day, and no
    write is on its way. SAVED: the controller reported the day and nothing is on its
    way. QUEUED: a write waits in the outbox for its turn. SENDING: the message is in
    the CUL and waits for the echo of the controller. UNCONFIRMED: the controller did
    not echo the write in time, so it may or may not hold it. ERROR: the write was lost
    before the controller could take it, for example because the credit ran out or the
    CUL lost its buffers.
    """

    UNKNOWN = "unknown"
    SAVED = "saved"
    QUEUED = "queued"
    SENDING = "sending"
    UNCONFIRMED = "unconfirmed"
    ERROR = "error"


@dataclass(slots=True, kw_only=True)
class FhtRoomController:
    """Last known state of an FHT80b room controller.

    The code is the house code as four lower-case hex digits. The desired temperature is
    5.5 for off and 30.5 for on. The device mirrors what the controller reported, so a
    value it never reported is None and means unknown.

    The battery_low, low_temperature, window_open and window_sensor_fault flags are the
    bits of its warnings telegram. The window_open flag is the aggregate of the window
    contacts that are paired with the controller itself.

    The day, night and window open temperatures and the low temperature offset are
    settings. The controller reports them only when asked, and settings_read_at is the
    time of the last such report. A value outside the range that the device accepts is
    unknown, not a setting.

    The holiday1 and holiday2 values are the raw registers that hold the end of the
    holiday or party mode, and holiday_end() turns them into a time. The mode_read_at is
    the time of the last mode telegram, which the end counts from. The week_program
    maps the command code of each of the 28 switch times to its time in 10 minute steps
    since midnight, and 144 means a period that is not in use. The manu_temp_raw is the
    raw value of a register of unknown meaning, kept for the diagnostics.

    The confirmed flag tells whether the controller is known to be one of ours. A device
    that was only heard is not confirmed, and the outbox and the refresh planner must
    keep automatic radio traffic away from it until an echo of a command or an explicit
    action of the user confirms it. A controller restored from a store that has no such
    flag was heard before, so it counts as confirmed.

    The time_ack is the time of the last echo of the minute command. The controller
    echoes every command it receives, and the minute is the last command of a time sync
    message, so only its echo proves that the whole message arrived. A controller can
    echo year to hour and then break off the radio dialog before the minute.

    The echoed_at is the time of the last echo of any command of this CUL. It is what
    makes the controller known to the outbox, so it is stored, and a restart does not
    send the controller back to the first contact.

    The pending queue holds the commands that were requested and that the controller
    has not echoed yet, a FIFO for each command code. Its newest entry of a code is what
    an entity shows until the echo settles it. The store keeps the commands that were
    sent to the CUL (the ones in flight), so a restart does not forget them. A command
    that is still staged was never sent and is not kept.

    The sync_until is the time until which the controller counts down its
    synchronization with the valves (see `note_actuator()`). It is not stored: the next
    telegram of the countdown sets it again.
    """

    type: ClassVar[DeviceType] = DeviceType.FHT80B
    # An FHT80b sends its actuator telegram about every 2 minutes (115 to 118.5
    # seconds), so 2 hours of silence mean that it is gone.
    stale_after: ClassVar[timedelta] = timedelta(hours=2)

    code: str
    last_seen: datetime | None = None
    rssi_dbm: float | None = None
    measured_temperature: float | None = None
    desired_temperature: float | None = None
    mode: FhtMode | None = None
    mode_read_at: datetime | None = None
    valve_percent: int | None = None
    actuator_state: ActuatorState | None = None
    battery_low: bool | None = None
    low_temperature: bool | None = None
    window_open: bool | None = None
    window_sensor_fault: bool | None = None
    day_temperature: float | None = None
    night_temperature: float | None = None
    windowopen_temperature: float | None = None
    lowtemp_offset: float | None = None
    settings_read_at: datetime | None = None
    holiday1: int | None = None
    holiday2: int | None = None
    week_program: dict[int, int] = field(default_factory=dict)
    week_program_read_at: datetime | None = None
    manu_temp_raw: int | None = None
    time_ack: datetime | None = None
    echoed_at: datetime | None = None
    confirmed: bool = False
    pending: PendingQueue = field(default_factory=PendingQueue, compare=False)
    # The switch times of the read that is going on and when the last one arrived. They
    # are not stored: a restart in the middle of a read starts the next one.
    week_program_batch: set[int] = field(default_factory=set, compare=False, repr=False)
    week_program_batch_at: datetime | None = field(
        default=None, compare=False, repr=False
    )
    sync_until: datetime | None = field(default=None, compare=False, repr=False)

    @property
    def device_id(self) -> str:
        """Return the stable id used for unique IDs and the device registry."""
        return f"{self.type}_{self.code}"

    @property
    def label(self) -> str:
        """Return the name the user knows the device by."""
        return device_label(self.device_id)

    def synchronizing(self, now: datetime) -> bool:
        """Return True while the controller counts down its synchronization."""
        return self.sync_until is not None and now < self.sync_until

    def note_actuator(self, value: ActuatorValue, now: datetime) -> None:
        """Note what an actuator telegram says about the synchronization.

        After a battery change the controller announces the first valve (pair) and then
        counts down 120 seconds with a telegram every second (the status of the
        countdown), which also happens when the user starts SYnC in its menu. It is back
        to its normal pace with the first telegram that regulates the valve. A countdown
        telegram says how many seconds are left, and a pair telegram says that the
        whole countdown follows.
        """
        if value.state is ActuatorState.SYNCTIME:
            left = max(value.synctime or 0, 0)
        elif value.state is ActuatorState.PAIR:
            left = SYNC_SECONDS
        elif value.state is ActuatorState.VALVE:
            self.sync_until = None
            return
        else:
            return
        self.sync_until = now + timedelta(seconds=left) + SYNC_MARGIN

    def note_week_program_time(self, code: int, now: datetime) -> None:
        """Count a switch time that arrived towards the read of the week program.

        The read is complete, and `week_program_read_at` is set, when all 28 different
        times arrived in it and the controller holds all of them. A time that arrives a
        second time inside the read, such as a repeated telegram, is counted once, and
        only a pause longer than the gap starts a read of its own.
        """
        last = self.week_program_batch_at
        if last is None or not timedelta(0) <= now - last <= WEEK_PROGRAM_BATCH_GAP:
            self.week_program_batch = set()
        self.week_program_batch.add(code)
        self.week_program_batch_at = now
        if (
            len(self.week_program_batch) == WEEK_PROGRAM_SIZE
            and len(self.week_program) == WEEK_PROGRAM_SIZE
        ):
            self.week_program_read_at = now
            self.week_program_batch = set()

    def apply(self, telegram: FhtTelegram, measured: float | None) -> None:
        """Update the state from a telegram of this controller."""
        if measured is not None:
            self.measured_temperature = measured
        code = telegram.code
        value = telegram.value
        if code == FhtCode.ACTUATOR and isinstance(value, ActuatorValue):
            self.actuator_state = value.state
            if value.position_percent is not None:
                self.valve_percent = value.position_percent
        elif code == FhtCode.DESIRED_TEMP:
            if value == SetpointSwitch.OFF:
                self.desired_temperature = TEMP_OFF
            elif value == SetpointSwitch.ON:
                self.desired_temperature = TEMP_ON
            elif isinstance(value, float):
                self.desired_temperature = value
        elif code == FhtCode.MODE and isinstance(value, FhtMode):
            self.mode = value
        elif code == FhtCode.WARNINGS and isinstance(value, FhtWarnings):
            self.battery_low = FhtWarnings.BATTERY_LOW in value
            self.low_temperature = FhtWarnings.LOW_TEMPERATURE in value
            self.window_open = FhtWarnings.WINDOW_OPEN in value
            self.window_sensor_fault = FhtWarnings.WINDOW_SENSOR_FAULT in value
        elif code == FhtCode.DAY_TEMP:
            self.day_temperature = _setting_temperature(value)
        elif code == FhtCode.NIGHT_TEMP:
            self.night_temperature = _setting_temperature(value)
        elif code == FhtCode.WINDOWOPEN_TEMP:
            self.windowopen_temperature = _setting_temperature(value)
        elif code == FhtCode.LOWTEMP_OFFSET:
            self.lowtemp_offset = _lowtemp_offset(value)
        elif code == FhtCode.HOLIDAY1:
            self.holiday1 = telegram.raw_value
        elif code == FhtCode.HOLIDAY2:
            self.holiday2 = telegram.raw_value
        elif code == FhtCode.MANU_TEMP:
            self.manu_temp_raw = telegram.raw_value
        elif is_week_program(code):
            if telegram.raw_value <= SWITCH_TIME_MAX_STEPS:
                self.week_program[code] = telegram.raw_value
            else:
                self.week_program.pop(code, None)

    def week_day_status(
        self, weekday: int, now: datetime, timeout: timedelta = PENDING_TIMEOUT
    ) -> WeekDayStatus:
        """Return where the week program of a weekday stands.

        `weekday` counts from 0 for Monday. A write that is on its way beats the failure
        of an earlier one, and a failure beats the reported day. A write that outlived
        the timeout but is not retired yet counts as unconfirmed, because the next tick
        retires it.
        """
        codes = week_program_day_codes(weekday)
        live = self.pending.live(codes)
        fresh = self.week_day_requests(weekday, now, timeout)
        if any(command.state is PendingState.STAGED for command in fresh):
            return WeekDayStatus.QUEUED
        if fresh:
            return WeekDayStatus.SENDING
        failures = {self.pending.failure(code) for code in codes}
        if PendingState.INVALIDATED in failures:
            return WeekDayStatus.ERROR
        if live or PendingState.EXPIRED in failures:
            return WeekDayStatus.UNCONFIRMED
        if week_program_periods(self.week_program, weekday) is None:
            return WeekDayStatus.UNKNOWN
        return WeekDayStatus.SAVED

    def week_day_requests(
        self, weekday: int, now: datetime, timeout: timedelta = PENDING_TIMEOUT
    ) -> list[PendingCommand]:
        """Return the live requests for the switch times of a weekday, the oldest first.

        A request that outlived the timeout is left out, as the entities leave it out.
        """
        return [
            command
            for command in self.pending.live(week_program_day_codes(weekday))
            if not command.is_stale(now, timeout)
        ]

    def shown_week_program(
        self, now: datetime, timeout: timedelta = PENDING_TIMEOUT
    ) -> dict[int, int]:
        """Return the week program with the newest requested time of each code.

        This is what the controller is going to hold, so a caller that shows it must
        say that it is pending. A code without a request keeps the reported time.
        """
        shown = dict(self.week_program)
        for code in range(WEEK_PROGRAM_FIRST, WEEK_PROGRAM_LAST + 1):
            if (command := self.pending.newest(code, now, timeout)) is not None:
                shown[code] = command.raw
        return shown

    def holiday_end(self, now: datetime) -> datetime | None:
        """Return when the holiday or party mode ends, None if it does not apply.

        The result is None outside the two modes, while a register or the time of the
        mode reading is unknown and when the end has passed. The device leaves the mode
        then without a telegram, so a mode that was read before the end is stale, and
        the end must not move to the next year. The time zone of `now` is the one of the
        device clock.

        The holiday mode ends at 00:00 of the day in holiday1 and the month in holiday2,
        which is the first such date after the mode was read. The party mode ends today or tomorrow, as the day
        in holiday2 says, at the time in holiday1 in 10 minute steps since midnight.
        """
        if self.holiday1 is None or self.holiday2 is None:
            return None
        if self.mode == FhtMode.HOLIDAY:
            if self.mode_read_at is None:
                return None
            return _holiday_end(
                self.holiday1,
                self.holiday2,
                self.mode_read_at.astimezone(now.tzinfo),
                now,
            )
        if self.mode == FhtMode.HOLIDAY_SHORT:
            return _party_end(self.holiday1, self.holiday2, now)
        return None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict."""
        return {
            "type": self.type.value,
            "code": self.code,
            "last_seen": _datetime_to_str(self.last_seen),
            "rssi": self.rssi_dbm,
            "measured_temperature": self.measured_temperature,
            "desired_temperature": self.desired_temperature,
            "mode": None if self.mode is None else self.mode.name.lower(),
            "mode_read_at": _datetime_to_str(self.mode_read_at),
            "valve": self.valve_percent,
            "actuator_state": None
            if self.actuator_state is None
            else self.actuator_state.value,
            "battery_low": self.battery_low,
            "low_temperature": self.low_temperature,
            "window_open": self.window_open,
            "window_sensor_fault": self.window_sensor_fault,
            "day_temperature": self.day_temperature,
            "night_temperature": self.night_temperature,
            "windowopen_temperature": self.windowopen_temperature,
            "lowtemp_offset": self.lowtemp_offset,
            "settings_read_at": _datetime_to_str(self.settings_read_at),
            "holiday1": self.holiday1,
            "holiday2": self.holiday2,
            "week_program": {
                week_program_reading(code): steps
                for code, steps in sorted(self.week_program.items())
            },
            "week_program_read_at": _datetime_to_str(self.week_program_read_at),
            "manu_temp_raw": self.manu_temp_raw,
            "time_ack": _datetime_to_str(self.time_ack),
            "echoed_at": _datetime_to_str(self.echoed_at),
            "pending": [
                {
                    "code": command.code,
                    "raw": command.raw,
                    "queued_at": command.queued_at.isoformat(),
                    "sent_at": _datetime_to_str(command.sent_at),
                    "message_id": command.message_id,
                }
                for command in self.pending.commands()
                if command.state == PendingState.QUEUED
            ],
            "confirmed": self.confirmed,
        }

    @classmethod
    def from_dict(cls, code: str, data: Mapping[str, Any]) -> FhtRoomController:
        """Rebuild the controller from to_dict().

        A missing value, one of the wrong type and one outside its range become None,
        so data stored by an earlier version or damaged data never fails the load. The
        exception is the confirmed flag: a controller that was heard before and has no
        flag in the store is confirmed.
        """
        last_seen = _str_to_datetime(data.get("last_seen"))
        confirmed = _boolean(data.get("confirmed"))
        return cls(
            code=code,
            last_seen=last_seen,
            confirmed=last_seen is not None if confirmed is None else confirmed,
            rssi_dbm=_number(data.get("rssi"), *_RSSI_RANGE_DBM),
            measured_temperature=_number(
                data.get("measured_temperature"), *_MEASURED_RANGE_CELSIUS
            ),
            desired_temperature=_number(
                data.get("desired_temperature"), TEMP_OFF, TEMP_ON
            ),
            mode=_enum_by_name(FhtMode, data.get("mode")),
            mode_read_at=_str_to_datetime(data.get("mode_read_at")),
            valve_percent=_integer(data.get("valve"), 0, 100),
            actuator_state=_enum_by_value(ActuatorState, data.get("actuator_state")),
            battery_low=_boolean(data.get("battery_low")),
            low_temperature=_boolean(data.get("low_temperature")),
            window_open=_boolean(data.get("window_open")),
            window_sensor_fault=_boolean(data.get("window_sensor_fault")),
            day_temperature=_number(data.get("day_temperature"), TEMP_OFF, TEMP_ON),
            night_temperature=_number(data.get("night_temperature"), TEMP_OFF, TEMP_ON),
            windowopen_temperature=_number(
                data.get("windowopen_temperature"), TEMP_OFF, TEMP_ON
            ),
            lowtemp_offset=_number(
                data.get("lowtemp_offset"), LOWTEMP_OFFSET_MIN, LOWTEMP_OFFSET_MAX
            ),
            settings_read_at=_str_to_datetime(data.get("settings_read_at")),
            holiday1=_integer(data.get("holiday1"), 0, 255),
            holiday2=_integer(data.get("holiday2"), 0, 255),
            week_program=_week_program(data.get("week_program")),
            week_program_read_at=_str_to_datetime(data.get("week_program_read_at")),
            manu_temp_raw=_integer(data.get("manu_temp_raw"), 0, 255),
            time_ack=_str_to_datetime(data.get("time_ack")),
            echoed_at=_str_to_datetime(data.get("echoed_at")),
            pending=_pending_queue(data.get("pending")),
        )


@dataclass(slots=True, kw_only=True)
class FhtWindowContact:
    """Last known state of an FHT80 TF window contact.

    The code is the address as six lower-case hex digits.
    """

    type: ClassVar[DeviceType] = DeviceType.FHT80TF
    # A contact sends a heartbeat every 242 to 256 seconds, so 4 hours without one mean
    # that it is gone.
    stale_after: ClassVar[timedelta] = timedelta(hours=4)

    code: str
    last_seen: datetime | None = None
    rssi_dbm: float | None = None
    window_open: bool | None = None
    battery_low: bool | None = None

    @property
    def device_id(self) -> str:
        """Return the stable id used for unique IDs and the device registry."""
        return f"{self.type}_{self.code}"

    @property
    def label(self) -> str:
        """Return the name the user knows the device by."""
        return device_label(self.device_id)

    def apply(self, telegram: FhtTfTelegram) -> None:
        """Update the state from a telegram of this contact."""
        # Sync and test telegrams carry no window state; they only prove it is alive.
        if telegram.state in (TfState.OPEN, TfState.CLOSED):
            self.window_open = telegram.state == TfState.OPEN
        if telegram.battery_low is not None:
            self.battery_low = telegram.battery_low

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict."""
        return {
            "type": self.type.value,
            "code": self.code,
            "last_seen": _datetime_to_str(self.last_seen),
            "rssi": self.rssi_dbm,
            "window_open": self.window_open,
            "battery_low": self.battery_low,
        }

    @classmethod
    def from_dict(cls, code: str, data: Mapping[str, Any]) -> FhtWindowContact:
        """Rebuild the contact from to_dict(); wrong types become None."""
        return cls(
            code=code,
            last_seen=_str_to_datetime(data.get("last_seen")),
            rssi_dbm=_number(data.get("rssi")),
            window_open=_boolean(data.get("window_open")),
            battery_low=_boolean(data.get("battery_low")),
        )


type FhtDevice = FhtRoomController | FhtWindowContact

_CODE_PATTERNS: Final = {
    DeviceType.FHT80B: re.compile(r"[0-9a-f]{4}"),
    DeviceType.FHT80TF: re.compile(r"[0-9a-f]{6}"),
}


@dataclass(slots=True, kw_only=True)
class FhtCandidate:
    """A device that was heard while new devices are not added automatically.

    The candidate keeps no state of the device, only when it was first and last heard
    and how strong the signal was, which tells a device of the house from a neighbor's.
    """

    type: DeviceType
    code: str
    first_heard: datetime
    last_heard: datetime
    rssi_dbm: float

    @property
    def device_id(self) -> str:
        """Return the id that the device gets when the user adds it."""
        return f"{self.type}_{self.code}"

    @property
    def label(self) -> str:
        """Return the name the user knows the device by."""
        return device_label(self.device_id)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict."""
        return {
            "type": self.type.value,
            "code": self.code,
            "first_heard": self.first_heard.isoformat(),
            "last_heard": self.last_heard.isoformat(),
            "rssi": self.rssi_dbm,
        }

    @classmethod
    def from_dict(cls, data: Any) -> FhtCandidate | None:
        """Rebuild the candidate from to_dict(), None if the data is unusable."""
        if not isinstance(data, Mapping):
            return None
        code = data.get("code")
        raw_type = data.get("type")
        if not isinstance(raw_type, str):
            return None
        try:
            device_type = DeviceType(raw_type)
        except ValueError:
            return None
        first_heard = _str_to_datetime(data.get("first_heard"))
        last_heard = _str_to_datetime(data.get("last_heard"))
        rssi_dbm = _number(data.get("rssi"), *_RSSI_RANGE_DBM)
        if (
            not isinstance(code, str)
            or not _CODE_PATTERNS[device_type].fullmatch(code)
            or first_heard is None
            or last_heard is None
            or rssi_dbm is None
        ):
            return None
        return cls(
            type=device_type,
            code=code,
            first_heard=first_heard,
            last_heard=last_heard,
            rssi_dbm=rssi_dbm,
        )


@dataclass(frozen=True, slots=True)
class DeviceUpdate:
    """A telegram changed a device; `new` is True if it was heard for the first time.

    The settled commands are the pending commands of the device that the telegram
    confirmed or superseded.
    """

    device: FhtDevice
    new: bool
    settled: tuple[PendingCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class CandidateUpdate:
    """A telegram of a device that waits to be added; `new` is True on the first one."""

    candidate: FhtCandidate
    new: bool


@dataclass(frozen=True, slots=True)
class NoticeUpdate:
    """culfw reported EOB or LOVF.

    An EOB is claimed when a message of ours was waiting for the answer of the CUL
    (see FhtNetwork.sending()), so it belongs to that message. An EOB that nobody
    claims says that some message did not fit that we do not know about.
    """

    kind: NoticeKind
    claimed: bool = False


type NetworkUpdate = CandidateUpdate | DeviceUpdate | NoticeUpdate


class InvalidationReason(StrEnum):
    """Why pending commands left the queue without an echo."""

    EXPIRED = "expired"
    UNCLAIMED_EOB = "unclaimed_eob"
    BUFFER_PURGE = "buffer_purge"
    CUL_RESET = "cul_reset"
    LINK_OUTAGE = "link_outage"
    HOUSE_CODE_REWRITE = "house_code_rewrite"


@dataclass(frozen=True, slots=True)
class PendingRetired:
    """Pending commands that were retired without an echo, and why.

    Every entry is the id of the controller and the command, which is in the state
    EXPIRED or INVALIDATED.
    """

    reason: InvalidationReason
    commands: tuple[tuple[str, PendingCommand], ...]


@dataclass(slots=True)
class FhtNetwork:
    """All FHT devices heard so far, plus counters for culfw notices.

    The network is fed every parse result. It creates a device on its first telegram,
    keeps the last decoded values and the time of the last telegram, and counts the
    culfw notices. Whether a device is alive is decided from that time alone: every
    telegram counts, including repetitions and commands the parser does not know.

    The stale_after thresholds are the silence after which a device of each type counts
    as gone. The ignored set holds the ids of devices whose telegrams are dropped, for
    example the FHT80b of a neighbor. The notice counters count since the start and are
    not persisted, because their sensors use the state class total_increasing. The same
    goes for the counters of the telegrams that the network sets aside (sent by another
    central, from an ignored device, with a command code it does not know, which still
    counts as a sign of life) and for the commands retired per reason, which the
    diagnostics show.

    With auto_add off, a device that is heard for the first time becomes a candidate
    instead of a device, and the user decides with adopt() or ignore(). At most
    MAX_CANDIDATES wait, and a new one pushes out the one that was heard longest ago.

    The owner tells the network whether the link to the CUL is up with set_link(). While
    the link is down no telegram can arrive, so the silence of a device says nothing
    about the device. link_down_since is the start of the outage, and the owner decides
    after how long the values of the devices are too old to show.

    The commands in flight can be retired in one go with invalidate_pending(), for the
    events that make them uncertain: the buffers of the CUL were emptied, or the CUL or
    the link were away for too long. The owner sets `on_pending_retired` to learn which
    commands went and why, because it tells the user.

    The state survives restarts through to_dict() and load(). It holds the commands in
    flight of the controllers and the boot time of the CUL, which tells after a restart
    whether the CUL still holds the messages. Loading is lenient: unknown keys and
    values of the wrong type are dropped instead of failing the setup.
    """

    now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    devices: dict[str, FhtDevice] = field(default_factory=dict)
    stale_after: dict[DeviceType, timedelta] = field(
        default_factory=lambda: {
            DeviceType.FHT80B: FhtRoomController.stale_after,
            DeviceType.FHT80TF: FhtWindowContact.stale_after,
        }
    )
    ignored: frozenset[str] = frozenset()
    auto_add: bool = True
    candidates: dict[str, FhtCandidate] = field(default_factory=dict)
    eob_count: int = 0
    lovf_count: int = 0
    central_telegram_count: int = 0
    ignored_telegram_count: int = 0
    unknown_code_count: int = 0
    retired_counts: dict[InvalidationReason, int] = field(default_factory=dict)
    link_down_since: datetime | None = None
    cul_booted_at: datetime | None = None
    on_pending_retired: Callable[[PendingRetired], None] | None = None
    pairing: WindowPairing = field(default_factory=WindowPairing)
    on_pairing_changed: Callable[[str], None] | None = None
    _assembler: MeasuredTempAssembler = field(default_factory=MeasuredTempAssembler)
    _sending: int = field(default=0, init=False, repr=False)

    def process(self, result: ParseResult) -> NetworkUpdate | None:
        """Apply one parse result; return what changed, None for ignored lines."""
        if isinstance(result, CulNotice):
            if result.kind == NoticeKind.EOB:
                self.eob_count += 1
                return NoticeUpdate(result.kind, claimed=self._sending > 0)
            self.lovf_count += 1
            return NoticeUpdate(result.kind)
        if isinstance(result, FhtTelegram):
            if result.from_central:
                # This is another central talking to the FHT80b, not the device itself.
                self.central_telegram_count += 1
                return None
            if held := self._hold(DeviceType.FHT80B, result.device, result.rssi_dbm):
                return held
            found = self._get(FhtRoomController, result.device)
            if found is None:
                return None
            controller, new = found
            if not result.known:
                self.unknown_code_count += 1
            self._report_pairing(
                self.pairing.note_telegram(
                    controller.device_id, result.code, self.now()
                )
            )
            was_open = controller.window_open
            controller.apply(result, self._assembler.feed(result))
            if isinstance(result.value, ActuatorValue) and (
                result.code == FhtCode.ACTUATOR
                or result.value.state is ActuatorState.PAIR
            ):
                controller.note_actuator(result.value, self.now())
            if was_open is not None and controller.window_open is not was_open:
                self._note_window_flag(controller.device_id, not was_open)
            settled = _reconcile(controller, result)
            if settled:
                controller.confirmed = True
            if result.code == FhtCode.MINUTE:
                controller.time_ack = self.now()
            elif result.code == FhtCode.MODE:
                controller.mode_read_at = self.now()
            elif result.code in _SETTINGS_CODES:
                controller.settings_read_at = self.now()
            elif is_week_program(result.code):
                controller.note_week_program_time(result.code, self.now())
            return self._seen(controller, result.rssi_dbm, new, settled)
        if isinstance(result, FhtTfTelegram):
            if held := self._hold(DeviceType.FHT80TF, result.sensor, result.rssi_dbm):
                return held
            found_tf = self._get(FhtWindowContact, result.sensor)
            if found_tf is None:
                return None
            contact, new = found_tf
            was_open = contact.window_open
            contact.apply(result)
            # A contact that repeats its state is no change and no event.
            if was_open is not None and contact.window_open is not was_open:
                self._report_pairing(
                    self.pairing.note_contact(
                        contact.device_id, not was_open, self.now()
                    )
                )
            else:
                self._report_pairing(self.pairing.settle(self.now()))
            return self._seen(contact, result.rssi_dbm, new)
        return None

    def is_stale(self, device: FhtDevice, now: datetime | None = None) -> bool:
        """Return True if the device was silent for longer than its threshold."""
        if device.last_seen is None:
            return True
        return (now or self.now()) - device.last_seen > self.stale_after[device.type]

    def silent_for(
        self, device: FhtDevice, now: datetime | None = None
    ) -> timedelta | None:
        """Return how long the device has been silent, None if never heard."""
        if device.last_seen is None:
            return None
        return (now or self.now()) - device.last_seen

    def set_link(self, connected: bool) -> None:
        """Record that the link to the CUL came back or went down.

        The outage counts from the first report of the loss, so a second report of the
        same loss does not move it.
        """
        if connected:
            self.link_down_since = None
        elif self.link_down_since is None:
            self.link_down_since = self.now()

    def link_down_for(self, now: datetime | None = None) -> timedelta | None:
        """Return how long the link has been down, None while it is up."""
        if self.link_down_since is None:
            return None
        return (now or self.now()) - self.link_down_since

    @contextmanager
    def sending(self) -> Iterator[None]:
        """Mark the time in which a message of ours waits for the answer of the CUL.

        culfw prints EOB before it answers the read of the buffer that follows the
        message, so an EOB inside the block belongs to the message. Blocks may overlap.
        """
        self._sending += 1
        try:
            yield
        finally:
            self._sending -= 1

    def invalidate_pending(
        self, reason: InvalidationReason, *, include_staged: bool = False
    ) -> int:
        """Retire the commands in flight as INVALIDATED and return how many went.

        Call it when the commands cannot be trusted any more: the buffers of the CUL
        were emptied (a reset, a purge, a new house code), a message did not fit that
        nobody waited for, or the link was away for so long that the requests are old.
        Staged commands were not sent yet, so only `include_staged` takes them back
        too. The owner of `on_pending_retired` learns what went. Nothing is reported
        when there was nothing in flight.
        """
        retired: list[tuple[str, PendingCommand]] = []
        for device in self._controllers():
            live = [
                command
                for command in device.pending.commands()
                if include_staged or command.state == PendingState.QUEUED
            ]
            retired.extend(
                (device.device_id, command)
                for command in device.pending.retire(live, PendingState.INVALIDATED)
            )
        self._report_retired(reason, retired)
        return len(retired)

    def expire_pending(self, timeout: timedelta = PENDING_TIMEOUT) -> int:
        """Retire the live commands older than `timeout` as EXPIRED; return how many."""
        now = self.now()
        retired: list[tuple[str, PendingCommand]] = []
        for device in self._controllers():
            retired.extend(
                (device.device_id, command)
                for command in device.pending.expire(now, timeout)
            )
        self._report_retired(InvalidationReason.EXPIRED, retired)
        return len(retired)

    def note_cul_boot(self, booted_at: datetime) -> bool:
        """Record when the CUL booted; return True unless it is the boot known before.

        The boot time is the time of a reading minus the uptime. The commands in flight
        that the store kept are still in the buffers of the CUL only if it did not boot
        since. A boot time that was never recorded cannot show that, so it counts as a
        different boot.
        """
        known, self.cul_booted_at = self.cul_booted_at, booted_at
        return known is None or abs(booted_at - known) > BOOT_TOLERANCE

    def remove(self, device_id: str) -> FhtDevice | None:
        """Forget a device (it comes back with its next telegram)."""
        self.pairing.forget(device_id)
        return self.devices.pop(device_id, None)

    def ignore(self, device_id: str) -> None:
        """Drop the device and its candidate, and ignore its telegrams from now on."""
        self.pairing.forget(device_id)
        self.ignored = self.ignored | {device_id}
        self.devices.pop(device_id, None)
        self.candidates.pop(device_id, None)

    def adopt(self, device_id: str) -> FhtDevice | None:
        """Turn a candidate into a device; return it, None if there is no candidate.

        The user added the device, which is an explicit action, so it is confirmed. It
        has no values yet and counts as silent until its next telegram.
        """
        candidate = self.candidates.pop(device_id, None)
        if candidate is None or device_id in self.devices:
            return None
        device: FhtDevice
        if candidate.type == DeviceType.FHT80B:
            device = FhtRoomController(code=candidate.code, confirmed=True)
        else:
            device = FhtWindowContact(code=candidate.code)
        self.devices[device_id] = device
        return device

    def to_dict(self) -> dict[str, Any]:
        """Return the persistent state as a JSON-serializable dict."""
        data: dict[str, Any] = {
            "devices": {key: device.to_dict() for key, device in self.devices.items()},
            "candidates": {
                key: candidate.to_dict() for key, candidate in self.candidates.items()
            },
        }
        if self.cul_booted_at is not None:
            data["cul_booted_at"] = self.cul_booted_at.isoformat()
        if votes := self.pairing.to_dict():
            data["pairing"] = votes
        return data

    def load(self, data: Mapping[str, Any] | None) -> None:
        """Restore devices saved by to_dict(), skipping broken entries."""
        if not isinstance(data, Mapping) or not isinstance(
            data.get("devices"), Mapping
        ):
            return
        self.cul_booted_at = _str_to_datetime(data.get("cul_booted_at"))
        for key, entry in data["devices"].items():
            device = _device_from_dict(entry)
            if device is None or device.device_id != key:
                _LOGGER.warning("Ignoring stored FHT device %r: %r", key, entry)
                continue
            if key in self.ignored:
                continue
            self.devices[key] = device
        self._load_candidates(data.get("candidates"))
        self.pairing.load(data.get("pairing"))

    def _load_candidates(self, stored: Any) -> None:
        """Restore the candidates, newest heard first when there are too many."""
        if not isinstance(stored, Mapping):
            return
        restored = [FhtCandidate.from_dict(entry) for entry in stored.values()]
        for candidate in sorted(
            (candidate for candidate in restored if candidate is not None),
            key=lambda candidate: candidate.last_heard,
            reverse=True,
        ):
            if (
                candidate.device_id not in self.ignored
                and candidate.device_id not in self.devices
                and len(self.candidates) < MAX_CANDIDATES
            ):
                self.candidates[candidate.device_id] = candidate

    def _hold(
        self, device_type: DeviceType, code: str, rssi_dbm: float
    ) -> CandidateUpdate | None:
        """Keep a device that is not added automatically as a candidate.

        Returns None for a telegram that needs no candidate: the device is known or
        ignored, or new devices are added automatically.
        """
        device_id = f"{device_type}_{code}"
        if self.auto_add or device_id in self.ignored or device_id in self.devices:
            return None
        now = self.now()
        if candidate := self.candidates.get(device_id):
            candidate.last_heard = now
            candidate.rssi_dbm = rssi_dbm
            return CandidateUpdate(candidate, new=False)
        if len(self.candidates) >= MAX_CANDIDATES:
            oldest = min(self.candidates.values(), key=lambda c: c.last_heard)
            del self.candidates[oldest.device_id]
        candidate = FhtCandidate(
            type=device_type,
            code=code,
            first_heard=now,
            last_heard=now,
            rssi_dbm=rssi_dbm,
        )
        self.candidates[device_id] = candidate
        return CandidateUpdate(candidate, new=True)

    def _note_window_flag(self, thermostat: str, window_open: bool) -> None:
        """Hand a change of the window flag of a thermostat to the learner."""
        self._report_pairing(
            self.pairing.note_thermostat(thermostat, window_open, self.now())
        )

    def _report_pairing(self, changed: tuple[str, ...]) -> None:
        """Tell the owner which contacts have another proposal or evidence now."""
        if self.on_pairing_changed is not None:
            for contact in changed:
                self.on_pairing_changed(contact)

    def _controllers(self) -> list[FhtRoomController]:
        """Return the room controllers."""
        return [
            device
            for device in self.devices.values()
            if isinstance(device, FhtRoomController)
        ]

    def _report_retired(
        self, reason: InvalidationReason, retired: list[tuple[str, PendingCommand]]
    ) -> None:
        if not retired:
            return
        self.retired_counts[reason] = self.retired_counts.get(reason, 0) + len(retired)
        if self.on_pending_retired is not None:
            self.on_pending_retired(PendingRetired(reason, tuple(retired)))

    def _get[T: (FhtRoomController, FhtWindowContact)](
        self, cls: type[T], code: str
    ) -> tuple[T, bool] | None:
        device_id = f"{cls.type}_{code}"
        if device_id in self.ignored:
            self.ignored_telegram_count += 1
            return None
        device = self.devices.get(device_id)
        if isinstance(device, cls):
            return device, False
        created = cls(code=code)
        self.devices[device_id] = created
        # A candidate that is heard while adding is on has found its way in.
        self.candidates.pop(device_id, None)
        return created, True

    def _seen(
        self,
        device: FhtDevice,
        rssi_dbm: float,
        new: bool,
        settled: tuple[PendingCommand, ...] = (),
    ) -> DeviceUpdate:
        device.last_seen = self.now()
        device.rssi_dbm = rssi_dbm
        return DeviceUpdate(device, new, settled)


def _reconcile(
    controller: FhtRoomController, telegram: FhtTelegram
) -> tuple[PendingCommand, ...]:
    """Settle the pending commands with a telegram and log those that lost."""
    settled = tuple(controller.pending.reconcile(telegram.code, telegram.raw_value))
    for command in settled:
        if command.state == PendingState.SUPERSEDED:
            _LOGGER.debug(
                "%s reported %#04x for command %#04x, which supersedes the"
                " requested %#04x",
                controller.label,
                telegram.raw_value,
                telegram.code,
                command.raw,
            )
    return settled


def _device_from_dict(data: Any) -> FhtDevice | None:
    if not isinstance(data, Mapping):
        return None
    code = data.get("code")
    raw_type = data.get("type")
    if not isinstance(raw_type, str):
        return None
    try:
        device_type = DeviceType(raw_type)
    except ValueError:
        return None
    if not isinstance(code, str) or not _CODE_PATTERNS[device_type].fullmatch(code):
        return None
    if device_type == DeviceType.FHT80B:
        return FhtRoomController.from_dict(code, data)
    return FhtWindowContact.from_dict(code, data)


def _datetime_to_str(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _str_to_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    # Naive timestamps cannot be compared with aware ones; drop them.
    return parsed if parsed.tzinfo is not None else None


def _number(value: Any, low: float = -math.inf, high: float = math.inf) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    # NaN and infinity are valid JSON for Python and fail every comparison.
    return number if low <= number <= high else None


def _integer(value: Any, low: int, high: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if low <= value <= high else None


def _boolean(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _setting_temperature(value: Any) -> float | None:
    """Return a reported setting temperature, None if the device cannot hold it."""
    if isinstance(value, float) and TEMP_OFF <= value <= TEMP_ON:
        return value
    _LOGGER.debug("Ignoring setting temperature %r outside the device range", value)
    return None


def _lowtemp_offset(value: Any) -> float | None:
    """Return a reported low temperature offset, None if the device cannot hold it."""
    if isinstance(value, float) and LOWTEMP_OFFSET_MIN <= value <= LOWTEMP_OFFSET_MAX:
        return value
    _LOGGER.debug("Ignoring low temperature offset %r outside the device range", value)
    return None


def _pending_queue(value: Any) -> PendingQueue:
    """Return the queue of the commands in flight that the store holds."""
    queue = PendingQueue()
    if not isinstance(value, list):
        return queue
    for entry in value[:_PENDING_STORE_LIMIT]:
        if not isinstance(entry, Mapping):
            continue
        code = _integer(entry.get("code"), 0, 0xFF)
        raw = _integer(entry.get("raw"), 0, 0xFF)
        queued_at = _str_to_datetime(entry.get("queued_at"))
        sent_at = _str_to_datetime(entry.get("sent_at"))
        if code not in FHT_SEND_CODES or raw is None or queued_at is None:
            continue
        queue.add(
            code,
            raw,
            queued_at,
            message_id=_integer(entry.get("message_id"), 1, _MESSAGE_ID_MAX),
            state=PendingState.QUEUED,
            sent_at=sent_at,
            waits_for_turn=sent_at is not None,
        )
    return queue


def _week_program(value: Any) -> dict[int, int]:
    if not isinstance(value, Mapping):
        return {}
    program: dict[int, int] = {}
    for reading, steps in value.items():
        code = week_program_code(reading)
        step = _integer(steps, 0, SWITCH_TIME_MAX_STEPS)
        if code is not None and step is not None:
            program[code] = step
    return program


def _holiday_end(
    day: int, month: int, read_at: datetime, now: datetime
) -> datetime | None:
    for year in range(read_at.year, read_at.year + _HOLIDAY_YEARS_AHEAD + 1):
        try:
            end = datetime(year, month, day, tzinfo=read_at.tzinfo)
        except ValueError:
            # The register holds no date in this year (the 29th of February) or none.
            continue
        if end > read_at:
            return end if end > now else None
    return None


def _party_end(steps: int, day: int, now: datetime) -> datetime | None:
    if steps > SWITCH_TIME_MAX_STEPS:
        return None
    today = now.date()
    for offset in (0, 1):
        candidate = today + timedelta(days=offset)
        if candidate.day == day:
            end = _midnight(candidate, now) + timedelta(
                minutes=steps * SWITCH_TIME_STEP_MINUTES
            )
            return end if end > now else None
    return None


def _midnight(day: date, now: datetime) -> datetime:
    return datetime.combine(day, time(), tzinfo=now.tzinfo)


def _enum_by_name(enum: type[FhtMode], value: Any) -> FhtMode | None:
    if not isinstance(value, str):
        return None
    return enum.__members__.get(value.upper())


def _enum_by_value(enum: type[ActuatorState], value: Any) -> ActuatorState | None:
    try:
        return enum(value)
    except ValueError, TypeError:
        return None
