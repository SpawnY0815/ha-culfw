"""Parser for FHT80b and FHT80 TF telegrams reported by culfw."""

from dataclasses import dataclass
from enum import IntEnum, IntFlag, StrEnum
import re
from typing import Final

from .const import WEEK_PROGRAM_FIRST, WEEK_PROGRAM_LAST

# The number of bytes in front of the RSSI byte. culfw leaves the checksum out.
_FHT80B_BYTES: Final = 5
_FHT80TF_BYTES: Final = 4

# Explicit ASCII ranges, because int() and bytes.fromhex() also accept other digits and
# embedded whitespace.
_HEX_DIGITS: Final = re.compile(r"[0-9A-Fa-f]*")

# One queued message in the answer to `T02`: the house code, a colon and the commands as
# code and value, each two upper-case hex digits.
_QUEUED_MESSAGE: Final = re.compile(r"([0-9A-F]{4}):([0-9A-F]{4}(?:,[0-9A-F]{4})*)")
_QUEUE_EMPTY: Final = "N/A"

# The RSSI offset of the CC1101 radio chip at 868 MHz.
_RSSI_OFFSET_DBM: Final = 74

_WEEKDAYS: Final = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_SWITCH_TIMES: Final = ("from1", "to1", "from2", "to2")

# A switch time counts 10 minute steps since midnight. The step 144 is 24:00, which the
# device uses for a period that is not in use.
SWITCH_TIME_STEP_MINUTES: Final = 10
SWITCH_TIME_MAX_STEPS: Final = 144

# A status byte with the high nibble 7 marks a telegram of a central.
_FROM_CENTRAL_NIBBLE: Final = 0x7

# Bit 7 marks a repetition. FHEM maps only the codes 81, 82, 91 and 92 back to the base
# code, node-cul masks the bit for every code, so the codes 8c and 8f work too. The
# parser follows node-cul.
_TF_REPEAT_BIT: Final = 0x80


def rssi_to_dbm(raw: int) -> float:
    """Convert the RSSI byte of culfw (two's complement, half dB steps) to dBm."""
    signed = raw - 256 if raw >= 128 else raw
    return signed / 2 - _RSSI_OFFSET_DBM


class FhtCode(IntEnum):
    """FHT80b command codes, the week program excluded.

    The FHEM reading name is the member name in lower case with `-` for `_`.
    """

    ACTUATOR = 0x00
    ACTUATOR1 = 0x01
    ACTUATOR2 = 0x02
    ACTUATOR3 = 0x03
    ACTUATOR4 = 0x04
    ACTUATOR5 = 0x05
    ACTUATOR6 = 0x06
    ACTUATOR7 = 0x07
    ACTUATOR8 = 0x08
    MODE = 0x3E
    HOLIDAY1 = 0x3F
    HOLIDAY2 = 0x40
    DESIRED_TEMP = 0x41
    MEASURED_LOW = 0x42
    MEASURED_HIGH = 0x43
    WARNINGS = 0x44
    MANU_TEMP = 0x45
    ACK = 0x4B
    CAN_XMIT = 0x53
    CAN_RCV = 0x54
    YEAR = 0x60
    MONTH = 0x61
    DAY = 0x62
    HOUR = 0x63
    MINUTE = 0x64
    REPORT1 = 0x65
    REPORT2 = 0x66
    ACK2 = 0x69
    START_XMIT = 0x7D
    END_XMIT = 0x7E
    DAY_TEMP = 0x82
    NIGHT_TEMP = 0x84
    LOWTEMP_OFFSET = 0x85
    WINDOWOPEN_TEMP = 0x8A


# Every reading that ends in "-temp", except the measured temperature, is in half
# degrees.
_HALF_DEGREE_CODES: Final = frozenset(
    {
        FhtCode.DESIRED_TEMP,
        FhtCode.MANU_TEMP,
        FhtCode.DAY_TEMP,
        FhtCode.NIGHT_TEMP,
        FhtCode.WINDOWOPEN_TEMP,
    }
)


class FhtMode(IntEnum):
    """Value of the `mode` command."""

    AUTO = 0
    MANUAL = 1
    HOLIDAY = 2
    HOLIDAY_SHORT = 3


class FhtWarnings(IntFlag):
    """Bits of the `warnings` command. Unknown bits are kept."""

    BATTERY_LOW = 0x01
    LOW_TEMPERATURE = 0x02
    WINDOW_SENSOR_FAULT = 0x10
    WINDOW_OPEN = 0x20


class SetpointSwitch(StrEnum):
    """Special values of the `desired-temp` command.

    ON stands for 30.5 °C with the valve fully open, OFF for 5.5 °C with the valve
    closed.
    """

    ON = "on"
    OFF = "off"


class ActuatorState(StrEnum):
    """Meaning of an actuator telegram, from the status byte.

    VALVE carries the valve opening. ON and OFF stand for the desired temperatures 30.5
    and 5.5 °C, which FHEM reports as 99 and 0 percent. SYNCTIME is the countdown after
    Sond/Sync on the FHT80b, and TEST means that the FHT80b made the actuator beep.
    """

    VALVE = "valve"
    SYNC_NOW = "syncnow"
    ON = "on"
    OFF = "off"
    OFFSET = "offset"
    LIME_PROTECTION = "lime-protection"
    SYNCTIME = "synctime"
    TEST = "test"
    PAIR = "pair"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ActuatorValue:
    """Decoded value of an `actuator` telegram, from `actuator` to `actuator8`.

    The position is the valve opening. It is set for VALVE, ON, OFF and UNKNOWN, as FHEM
    does. The offset belongs to OFFSET and the countdown synctime to SYNCTIME.
    """

    state: ActuatorState
    position_percent: int | None = None
    offset: int | None = None
    synctime: int | None = None


class TfState(StrEnum):
    """State reported by an FHT80 TF."""

    OPEN = "open"
    CLOSED = "closed"
    SYNC = "sync"
    TEST = "test"
    UNKNOWN = "unknown"


# Maps a status code without the repeat bit to the state and whether the battery is low.
# Sync and test report the battery as ok. No source documents a sabotage code, so any
# other code is UNKNOWN and keeps the raw status, which lets live telegrams identify it.
_TF_STATES: Final[dict[int, tuple[TfState, bool]]] = {
    0x01: (TfState.OPEN, False),
    0x02: (TfState.CLOSED, False),
    0x11: (TfState.OPEN, True),
    0x12: (TfState.CLOSED, True),
    0x0C: (TfState.SYNC, False),
    0x0F: (TfState.TEST, False),
}


class NoticeKind(StrEnum):
    """Notices culfw prints on its own.

    EOB means that the FHT80b send buffer is full and the command was dropped. LOVF
    means that the 1 % duty cycle credit is used up and nothing was sent.
    """

    EOB = "EOB"
    LOVF = "LOVF"


class IgnoreReason(StrEnum):
    """Why a line was not decoded.

    NOT_FHT is another culfw message type or an answer, TRUNCATED an odd number of hex
    digits, and UNEXPECTED_LENGTH a size that is neither an FHT80b nor an FHT80 TF
    telegram.
    """

    EMPTY = "empty"
    NOT_FHT = "not_fht"
    NOT_HEX = "not_hex"
    TRUNCATED = "truncated"
    UNEXPECTED_LENGTH = "unexpected_length"


type FhtValue = (
    ActuatorValue | FhtWarnings | FhtMode | SetpointSwitch | float | int | str
)


@dataclass(frozen=True, slots=True, kw_only=True)
class FhtTelegram:
    """Telegram of an FHT80b room controller.

    The device is the house code as four lower-case hex digits. A telegram with a
    command that FHEM does not know is still returned, because the device is alive. Its
    code is then a plain int and its value the raw value byte.
    """

    device: str
    code: FhtCode | int
    status: int
    raw_value: int
    value: FhtValue
    rssi_dbm: float
    raw: str

    @property
    def known(self) -> bool:
        """Return True if the command is a known FHT80b command."""
        return isinstance(self.code, FhtCode) or is_week_program(self.code)

    @property
    def reading(self) -> str:
        """Return the FHEM reading name, `unknown_xx` for unknown commands."""
        if isinstance(self.code, FhtCode):
            return self.code.name.lower().replace("_", "-")
        if is_week_program(self.code):
            return week_program_reading(self.code)
        return f"unknown_{self.code:02x}"

    @property
    def from_central(self) -> bool:
        """Return True if the telegram was sent by a central, not by the FHT80b.

        FHEM stores these as `FHZ_<reading>`. With `X21` culfw already drops them.
        """
        return self.status >> 4 == _FROM_CENTRAL_NIBBLE


@dataclass(frozen=True, slots=True, kw_only=True)
class FhtTfTelegram:
    """Telegram of an FHT80 TF window contact.

    The contact sends its state on every change and otherwise as a heartbeat, so every
    telegram is a sign of life. It sends each telegram a second time with bit 7 of the
    status set (the repeat, for example 02 then 82). culfw only drops identical
    telegrams within 0.3 seconds, so both arrive.

    The sensor is the address as six lower-case hex digits. The status includes the
    repeat bit, and battery_low is None if the status code is unknown.
    """

    sensor: str
    status: int
    state: TfState
    battery_low: bool | None
    repeat: bool
    rssi_dbm: float
    raw: str

    @property
    def heartbeat_interval_seconds(self) -> int:
        """Return the nominal time between two heartbeats of this contact in seconds.

        It depends on the last 3 bits of the address: the FHT80 TF emulation of culfw
        uses 240 + 16 - 2 * (bits) seconds.
        """
        return 256 - 2 * (int(self.sensor[-2:], 16) & 0x07)


@dataclass(frozen=True, slots=True)
class CulNotice:
    """A notice line from culfw, EOB or LOVF."""

    kind: NoticeKind
    raw: str


@dataclass(frozen=True, slots=True)
class Ignored:
    """A line that is not an FHT telegram or could not be decoded."""

    reason: IgnoreReason
    raw: str


type ParseResult = FhtTelegram | FhtTfTelegram | CulNotice | Ignored


def parse_line(line: str) -> ParseResult:
    """Parse one line from culfw in report mode `X21`.

    The line is what the transport hands to its message callback, without the line
    ending. culfw reports a received telegram as the type letter, the decoded bytes in
    hex and one more byte with the RSSI. FHT telegrams use the letter T and have one of
    two sizes:

    - FHT80b room controller: T, house code (2 bytes), command, status and value, for
      example T5D1000B6BE00 (house code 5d10, actuator, status b6, value be, RSSI 00).
    - FHT80 TF window contact: T, address (3 bytes) and status, for example T895C978210
      (address 895c97, status 82, RSSI 10).

    This function never raises. A line it cannot decode comes back as Ignored with the
    reason. It keeps no state, and MeasuredTempAssembler puts together the two telegrams
    that carry the measured temperature.
    """
    text = line.strip()
    if not text:
        return Ignored(IgnoreReason.EMPTY, line)
    if text in NoticeKind:
        return CulNotice(NoticeKind(text), line)
    if text[0] != "T":
        return Ignored(IgnoreReason.NOT_FHT, line)

    digits = text[1:]
    if not _HEX_DIGITS.fullmatch(digits):
        return Ignored(IgnoreReason.NOT_HEX, line)
    if len(digits) % 2:
        return Ignored(IgnoreReason.TRUNCATED, line)

    data = bytes.fromhex(digits)
    # The last byte is the RSSI.
    payload_bytes = len(data) - 1
    if payload_bytes == _FHT80B_BYTES:
        return _parse_fht80b(data, line)
    if payload_bytes == _FHT80TF_BYTES:
        return _parse_fht80tf(data, line)
    return Ignored(IgnoreReason.UNEXPECTED_LENGTH, line)


def parse_fht_queue(line: str) -> dict[str, list[tuple[int, int]]] | None:
    """Parse the answer to `T02`, the messages in the FHT send buffer of the CUL.

    The CUL answers `N/A` for an empty buffer and otherwise one token per queued
    message, separated by single spaces. A token is the house code, a colon and the
    commands as code and value, for example `5D10:3E02,2C28`. The result maps each
    house code to its queued (code, value) commands in queue order, and is empty for
    `N/A`.

    The format follows the culfw source and has not been seen on hardware yet. The
    parser therefore accepts nothing but this exact shape in upper-case hex and
    returns None for everything else, including lower case, surrounding whitespace and
    a message without commands.
    """
    if line == _QUEUE_EMPTY:
        return {}
    queue: dict[str, list[tuple[int, int]]] = {}
    for token in line.split(" "):
        match = _QUEUED_MESSAGE.fullmatch(token)
        if match is None:
            return None
        data = bytes.fromhex(match.group(2).replace(",", ""))
        queue.setdefault(match.group(1), []).extend(
            zip(data[0::2], data[1::2], strict=True)
        )
    return queue


def measured_temperature(low: int, high: int) -> float:
    """Return the measured temperature in °C from its two bytes."""
    return (high * 256 + low) / 10


class MeasuredTempAssembler:
    """Combine `measured-low` and `measured-high` telegrams to `measured-temp`.

    The FHT80b sends the measured temperature as two telegrams, and the temperature is
    computed when the high byte arrives. A low byte is used only once. FHEM keeps it, so
    after a lost low byte it pairs a stale low byte with a new high byte: 25.5 °C is
    00/ff and 25.6 °C is 01/00, so 01 with the stale ff gives 51.1 °C.
    """

    def __init__(self) -> None:
        """Initialize the assembler without any low byte."""
        self._low: dict[str, int] = {}

    def feed(self, telegram: FhtTelegram) -> float | None:
        """Return the measured temperature once `telegram` completes it, else None."""
        if telegram.code == FhtCode.MEASURED_LOW:
            self._low[telegram.device] = telegram.raw_value
        elif telegram.code == FhtCode.MEASURED_HIGH:
            low = self._low.pop(telegram.device, None)
            if low is not None:
                return measured_temperature(low, telegram.raw_value)
        return None


def is_week_program(code: int) -> bool:
    """Return True if the command code is one of the 28 switch times of the week."""
    return WEEK_PROGRAM_FIRST <= code <= WEEK_PROGRAM_LAST


def week_program_reading(code: int) -> str:
    """Return the reading name of a week program code, for example `mon-from1`."""
    offset = code - WEEK_PROGRAM_FIRST
    return f"{_WEEKDAYS[offset // 4]}-{_SWITCH_TIMES[offset % 4]}"


_WEEK_PROGRAM_CODES: Final = {
    week_program_reading(code): code
    for code in range(WEEK_PROGRAM_FIRST, WEEK_PROGRAM_LAST + 1)
}


def week_program_code(reading: object) -> int | None:
    """Return the command code of a week program reading name, None if unknown."""
    return _WEEK_PROGRAM_CODES.get(reading) if isinstance(reading, str) else None


def _parse_fht80b(data: bytes, line: str) -> FhtTelegram:
    command, status, value, rssi = data[2:]
    return FhtTelegram(
        device=data[:2].hex(),
        code=FhtCode(command) if command in FhtCode else command,
        status=status,
        raw_value=value,
        value=_decode_fht_value(command, status, value),
        rssi_dbm=rssi_to_dbm(rssi),
        raw=line,
    )


def _decode_fht_value(code: int, status: int, value: int) -> FhtValue:
    """Decode the value byte of a command."""
    if code <= FhtCode.ACTUATOR8:
        return _decode_actuator(status, value)
    if is_week_program(code):
        # Switch times count 10 minute steps since midnight, and 144 means unused.
        return f"{value // 6:02d}:{value % 6 * 10:02d}"
    if code == FhtCode.DESIRED_TEMP:
        # Only the desired temperature has the special values on and off.
        if value > 60:
            return SetpointSwitch.ON
        if value < 12:
            return SetpointSwitch.OFF
    if code in _HALF_DEGREE_CODES:
        return value / 2
    if code == FhtCode.MODE:
        # An unknown mode stays numeric.
        return FhtMode(value) if value in FhtMode else value
    if code == FhtCode.WARNINGS:
        return FhtWarnings(value)
    if code == FhtCode.LOWTEMP_OFFSET:
        # The offset is in whole degrees.
        return float(value)
    return value


def _decode_actuator(status: int, value: int) -> ActuatorValue:
    """Decode an actuator telegram.

    The low nibble of the status byte says what the value byte means. FHEM tests the
    patterns in a fixed order, so the order of the cases matters.
    """
    position = int(100 * value / 255 + 0.5)
    high, low = status >> 4, status & 0x0F
    match low:
        case 0x0 if high in (0xA, 0xB):
            # Sync in the summer, which is still a valve position.
            return ActuatorValue(ActuatorState.VALVE, position_percent=position)
        case 0x0:
            return ActuatorValue(ActuatorState.SYNC_NOW)
        case 0x1:
            return ActuatorValue(ActuatorState.ON, position_percent=99)
        case 0x2:
            return ActuatorValue(ActuatorState.OFF, position_percent=0)
        case 0x6:
            return ActuatorValue(ActuatorState.VALVE, position_percent=position)
        case 0x8:
            return ActuatorValue(
                ActuatorState.OFFSET, offset=128 - value if value > 128 else value
            )
        case 0xA if high in (0x2, 0x3):
            return ActuatorValue(ActuatorState.LIME_PROTECTION)
        case 0xA if high in (0xA, 0xB):
            # FHEM calls this the lime protection bug and reports a valve position.
            return ActuatorValue(ActuatorState.VALVE, position_percent=position)
        case 0xC:
            return ActuatorValue(ActuatorState.SYNCTIME, synctime=value // 2 - 1)
        case 0xE:
            return ActuatorValue(ActuatorState.TEST)
        case 0xF:
            return ActuatorValue(ActuatorState.PAIR)
        case _:
            return ActuatorValue(ActuatorState.UNKNOWN, position_percent=position)


def _parse_fht80tf(data: bytes, line: str) -> FhtTfTelegram:
    status, rssi = data[3:]
    state, battery_low = _TF_STATES.get(
        status & ~_TF_REPEAT_BIT, (TfState.UNKNOWN, None)
    )
    return FhtTfTelegram(
        sensor=data[:3].hex(),
        status=status,
        state=state,
        battery_low=battery_low,
        repeat=bool(status & _TF_REPEAT_BIT),
        rssi_dbm=rssi_to_dbm(rssi),
        raw=line,
    )
