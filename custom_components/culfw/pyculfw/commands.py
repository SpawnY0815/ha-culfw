"""Build and check the commands that an FHT80b accepts."""

import calendar
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import IntFlag
import math
from typing import Final

from .const import (
    CLIMATE_TEMP_MAX,
    CLIMATE_TEMP_MIN,
    DAY_MAX,
    DAYS_PER_WEEK,
    FHT_SEND_CODES,
    HOUR_MAX,
    LOWTEMP_OFFSET_MAX,
    LOWTEMP_OFFSET_MIN,
    MINUTE_MAX,
    MINUTES_PER_DAY,
    MONTH_MAX,
    SETTING_TEMP_MAX,
    SETTING_TEMP_MIN,
    TEMP_STEP,
    WEEK_PROGRAM_FIRST,
    WEEK_PROGRAM_PERIODS,
    YEAR_MAX,
)
from .errors import FhtValueError
from .parser import (
    SWITCH_TIME_MAX_STEPS,
    SWITCH_TIME_STEP_MINUTES,
    FhtCode,
    FhtMode,
    is_week_program,
)

# A command is (command code, value). Every builder raises FhtValueError for a value
# that the controller cannot take, so a message that reaches the CUL is always one that
# the controller understands.
type FhtCommand = tuple[int, int]

# The request commands take the whole selection with all bits set.
REPORT_ALL: Final = 0xFF

# The first year that the two-digit year of the device stands for.
_YEAR_BASE: Final = 2000
_SWITCH_TIMES_PER_DAY: Final = 2 * WEEK_PROGRAM_PERIODS
# A leap year, because the year of a holiday end is not part of the command.
_LEAP_YEAR: Final = 2000

_SETTING_TEMPERATURE_CODES: Final = frozenset(
    {FhtCode.DAY_TEMP, FhtCode.NIGHT_TEMP, FhtCode.WINDOWOPEN_TEMP}
)
_SETTING_RAW: Final = (
    round(SETTING_TEMP_MIN / TEMP_STEP),
    round(SETTING_TEMP_MAX / TEMP_STEP),
)

# The range of the raw value of every command that is not a report or a week program
# time. The holiday registers hold a day, a month or a time in 10 minute steps,
# depending on the mode, so the range is the widest of them.
_RAW_RANGES: Final[Mapping[int, tuple[int, int]]] = {
    FhtCode.MODE: (min(FhtMode), max(FhtMode)),
    FhtCode.HOLIDAY1: (0, SWITCH_TIME_MAX_STEPS),
    FhtCode.HOLIDAY2: (1, DAY_MAX),
    FhtCode.DESIRED_TEMP: _SETTING_RAW,
    FhtCode.DAY_TEMP: _SETTING_RAW,
    FhtCode.NIGHT_TEMP: _SETTING_RAW,
    FhtCode.WINDOWOPEN_TEMP: _SETTING_RAW,
    FhtCode.LOWTEMP_OFFSET: (LOWTEMP_OFFSET_MIN, LOWTEMP_OFFSET_MAX),
    FhtCode.YEAR: (0, YEAR_MAX),
    FhtCode.MONTH: (1, MONTH_MAX),
    FhtCode.DAY: (1, DAY_MAX),
    FhtCode.HOUR: (0, HOUR_MAX),
    FhtCode.MINUTE: (0, MINUTE_MAX),
}


class Report1Days(IntFlag):
    """The days of the week program that report1 asks for, Monday first."""

    MONDAY = 0x01
    TUESDAY = 0x02
    WEDNESDAY = 0x04
    THURSDAY = 0x08
    FRIDAY = 0x10
    SATURDAY = 0x20
    SUNDAY = 0x40
    ALL = 0x7F


class Report2Settings(IntFlag):
    """The settings that report2 asks for. The bits 16 and 32 are undefined."""

    WARNINGS = 0x01
    MODE = 0x02
    DAY_NIGHT_WINDOWOPEN_TEMP = 0x04
    DESIRED_TEMP = 0x08
    LOWTEMP_OFFSET = 0x40
    ALL = 0x4F


def _check_integer(name: str, value: object, minimum: int, maximum: int) -> int:
    """Return `value` if it is an integer from `minimum` to `maximum`."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise FhtValueError(f"{name} must be a whole number, got {value!r}")
    if not minimum <= value <= maximum:
        raise FhtValueError(f"{name} must be {minimum} to {maximum}, got {value}")
    return value


def temperature_to_raw(
    temperature: float,
    minimum: float = SETTING_TEMP_MIN,
    maximum: float = SETTING_TEMP_MAX,
) -> int:
    """Return the byte for `temperature`, which the device counts in half degrees.

    A temperature between two steps rounds half up, so 20.25 becomes 20.5. The range
    applies to the rounded temperature.
    """
    if (
        isinstance(temperature, bool)
        or not isinstance(temperature, int | float)
        or not minimum - TEMP_STEP <= temperature <= maximum + TEMP_STEP
    ):
        raise FhtValueError(
            f"Temperature must be {minimum} to {maximum} °C, got {temperature!r}"
        )
    raw = math.floor(temperature / TEMP_STEP + 0.5)
    if not minimum <= raw * TEMP_STEP <= maximum:
        raise FhtValueError(
            f"Temperature must be {minimum} to {maximum} °C, got {temperature!r}"
        )
    return raw


def desired_temperature_command(
    temperature: float, *, allow_switch: bool = False
) -> FhtCommand:
    """Return the command for the desired temperature.

    A thermostat asks for 6.0 to 30.0 °C. The setpoints 5.5 °C (valve closed) and
    30.5 °C (valve fully open) are only for the switches off and on, and `allow_switch`
    lets them pass.
    """
    if allow_switch:
        raw = temperature_to_raw(temperature)
    else:
        raw = temperature_to_raw(temperature, CLIMATE_TEMP_MIN, CLIMATE_TEMP_MAX)
    return (FhtCode.DESIRED_TEMP, raw)


def mode_command(mode: int) -> FhtCommand:
    """Return the command for the auto or manual mode.

    The holiday modes only work together with their end, so they have their own
    builders.
    """
    if isinstance(mode, bool) or mode not in (FhtMode.AUTO, FhtMode.MANUAL):
        raise FhtValueError(
            f"Mode must be auto ({FhtMode.AUTO}) or manual ({FhtMode.MANUAL}), "
            f"got {mode!r}; the holiday modes need an end"
        )
    return (FhtCode.MODE, FhtMode(mode))


def _holiday_group(
    mode: FhtMode, holiday1: int, holiday2: int, temperature: float
) -> list[FhtCommand]:
    """Return the four commands of a holiday, which have to go in one message.

    The controller only takes the end of a holiday in the message that sets the mode,
    and the mode comes first.
    """
    return [
        (FhtCode.MODE, mode),
        (FhtCode.HOLIDAY1, holiday1),
        (FhtCode.HOLIDAY2, holiday2),
        desired_temperature_command(temperature),
    ]


def holiday_commands(day: int, month: int, temperature: float) -> list[FhtCommand]:
    """Return the commands for a holiday that ends at 00:00 of `day` and `month`."""
    _check_integer("Month", month, 1, MONTH_MAX)
    _check_integer("Day", day, 1, calendar.monthrange(_LEAP_YEAR, month)[1])
    return _holiday_group(FhtMode.HOLIDAY, day, month, temperature)


def party_commands(minutes: int, day: int, temperature: float) -> list[FhtCommand]:
    """Return the commands for a holiday that ends today or tomorrow.

    The end is `minutes` after midnight of the day of the month `day`, rounded down to
    the 10 minute steps of the device.
    """
    _check_integer("Minutes", minutes, 0, MINUTES_PER_DAY)
    _check_integer("Day", day, 1, DAY_MAX)
    return _holiday_group(
        FhtMode.HOLIDAY_SHORT,
        minutes // SWITCH_TIME_STEP_MINUTES,
        day,
        temperature,
    )


def setting_temperature_command(code: int, temperature: float) -> FhtCommand:
    """Return the command for the day, night or window open temperature."""
    if code not in _SETTING_TEMPERATURE_CODES:
        raise FhtValueError(f"0x{code:02X} is not a temperature setting")
    return (code, temperature_to_raw(temperature))


def lowtemp_offset_command(offset: float) -> FhtCommand:
    """Return the command for the low temperature alarm offset in whole degrees."""
    if isinstance(offset, float) and offset.is_integer():
        offset = int(offset)
    return (
        FhtCode.LOWTEMP_OFFSET,
        _check_integer(
            "Low temperature offset", offset, LOWTEMP_OFFSET_MIN, LOWTEMP_OFFSET_MAX
        ),
    )


def report1_command(days: int) -> FhtCommand:
    """Return the request for the week program of the days in the `Report1Days` mask.

    The controller answers with its 4 switch times per day as telegrams of their own
    in its next time slots. `REPORT_ALL` asks for the whole week.
    """
    _check_integer("Report1 days", days, 1, REPORT_ALL)
    if days != REPORT_ALL and days & ~int(Report1Days.ALL):
        raise FhtValueError(f"Report1 days has undefined bits: {days:#04x}")
    return (FhtCode.REPORT1, days)


def report2_command(settings: int) -> FhtCommand:
    """Return the request for the settings in the `Report2Settings` mask.

    The controller answers with the settings as telegrams of their own in its next
    time slots. `REPORT_ALL` asks for everything.
    """
    _check_integer("Report2 settings", settings, 1, REPORT_ALL)
    if settings != REPORT_ALL and settings & ~int(Report2Settings.ALL):
        raise FhtValueError(f"Report2 settings has undefined bits: {settings:#04x}")
    return (FhtCode.REPORT2, settings)


def date_commands(local: datetime) -> list[FhtCommand]:
    """Return the commands that set the date of an FHT80b to the local date."""
    if not _YEAR_BASE <= local.year <= _YEAR_BASE + YEAR_MAX:
        raise FhtValueError(
            f"The year must be {_YEAR_BASE} to {_YEAR_BASE + YEAR_MAX}, got {local.year}"
        )
    return [
        (FhtCode.YEAR, local.year - _YEAR_BASE),
        (FhtCode.MONTH, local.month),
        (FhtCode.DAY, local.day),
    ]


def time_commands(local: datetime) -> list[FhtCommand]:
    """Return the commands that set the clock of an FHT80b.

    culfw replaces the minute with its own running minute when it finally sends the
    message, so the time is right even after waiting for the time slot. The minute
    comes last, because its echo is the proof that the whole message arrived.
    """
    return [(FhtCode.HOUR, local.hour), (FhtCode.MINUTE, local.minute)]


def date_time_commands(local: datetime) -> list[FhtCommand]:
    """Return the commands that set the date and the clock of an FHT80b."""
    return [*date_commands(local), *time_commands(local)]


def week_program_commands(
    weekday: int, periods: Sequence[tuple[int, int]]
) -> list[FhtCommand]:
    """Return the commands for the week program of one day.

    `weekday` counts from 0 for Monday. Every period is the start and the end in
    minutes after midnight, rounded down to 10 minutes. The day has two periods, and
    a period that is left out stays unused (24:00 to 24:00), so a day without periods
    runs at the night temperature all day. Inside a period the controller regulates to
    the day temperature, outside to the night temperature.
    """
    _check_integer("Weekday", weekday, 0, DAYS_PER_WEEK - 1)
    if len(periods) > WEEK_PROGRAM_PERIODS:
        raise FhtValueError(
            f"A day has at most {WEEK_PROGRAM_PERIODS} periods, got {len(periods)}"
        )
    steps: list[int] = []
    for start, end in periods:
        _check_integer("Start", start, 0, MINUTES_PER_DAY)
        _check_integer("End", end, start, MINUTES_PER_DAY)
        steps += [
            start // SWITCH_TIME_STEP_MINUTES,
            end // SWITCH_TIME_STEP_MINUTES,
        ]
    steps += [SWITCH_TIME_MAX_STEPS] * (_SWITCH_TIMES_PER_DAY - len(steps))
    first = WEEK_PROGRAM_FIRST + weekday * _SWITCH_TIMES_PER_DAY
    return [(first + index, step) for index, step in enumerate(steps)]


def week_program_day_codes(weekday: int) -> range:
    """Return the command codes of the four switch times of a weekday.

    `weekday` counts from 0 for Monday. The codes are the ones that
    `week_program_commands()` builds and that the controller reports.
    """
    _check_integer("Weekday", weekday, 0, DAYS_PER_WEEK - 1)
    first = WEEK_PROGRAM_FIRST + weekday * _SWITCH_TIMES_PER_DAY
    return range(first, first + _SWITCH_TIMES_PER_DAY)


def week_program_periods(
    week_program: Mapping[int, int], weekday: int
) -> list[tuple[int, int]] | None:
    """Return the periods of one day from the switch times that the device reported.

    `week_program` maps the command code of a switch time to its time in 10 minute
    steps. The result is what `week_program_commands()` takes: the start and the end of
    every period in minutes after midnight. A period that is not in use, or that ends
    where it starts, is left out. The result is None while one of the four switch times
    of the day is unknown.
    """
    times: list[int] = []
    for code in week_program_day_codes(weekday):
        if (step := week_program.get(code)) is None:
            return None
        times.append(step * SWITCH_TIME_STEP_MINUTES)
    return [
        (start, end)
        for start, end in zip(times[::2], times[1::2], strict=True)
        if start < end
    ]


def check_command(code: int, raw: int) -> None:
    """Raise FhtValueError unless `raw` is a value that the command takes.

    This is the check for a value that is a byte already, which the outbox applies to
    every request. The builders above quantize and check a physical value first.
    """
    if code not in FHT_SEND_CODES:
        raise FhtValueError(f"Command 0x{code:02X} cannot be sent to an FHT80b")
    if isinstance(raw, bool) or not isinstance(raw, int) or not 0 <= raw <= 0xFF:
        raise FhtValueError(f"Value of command 0x{code:02X} is not a byte: {raw!r}")
    if code == FhtCode.REPORT1:
        report1_command(raw)
    elif code == FhtCode.REPORT2:
        report2_command(raw)
    else:
        low, high = (
            (0, SWITCH_TIME_MAX_STEPS) if is_week_program(code) else _RAW_RANGES[code]
        )
        if not low <= raw <= high:
            raise FhtValueError(
                f"Value of command 0x{code:02X} must be {low} to {high}, got {raw}"
            )
