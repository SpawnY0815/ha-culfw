"""Time ranges of the week program, shared by the actions and the websocket API."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from itertools import pairwise
import re
from typing import Any, Final

import probatio

from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, WEEKDAYS
from .pyculfw import (
    MINUTES_PER_DAY,
    SWITCH_TIME_STEP_MINUTES,
    WEEK_PROGRAM_PERIODS,
    FhtRoomController,
    WeekDayStatus,
    week_program_periods,
)

ATTR_START: Final = "start"
ATTR_END: Final = "end"

# One time range of a day, as the actions and the websocket API take it.
RANGE_SCHEMA: Final = {
    probatio.Required(ATTR_START): cv.string,
    probatio.Required(ATTR_END): cv.string,
}

# A time of day as the frontend and the users write it. The seconds are accepted
# because a time selector sends them, and they have to be zero. Only ASCII digits count,
# because `\d` alone also matches the digits of other scripts.
_TIME: Final = re.compile(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", re.ASCII)
_MINUTES_PER_HOUR: Final = 60
# The longest text of a user that an error message repeats.
_SHOWN_LENGTH: Final = 16

type Period = tuple[int, int]


def format_time(minutes: int) -> str:
    """Return minutes after midnight as HH:MM, where 24:00 is the end of the day."""
    return f"{minutes // _MINUTES_PER_HOUR:02d}:{minutes % _MINUTES_PER_HOUR:02d}"


def _shown(text: str) -> str:
    """Return a text of the user in a form that is safe for an error message.

    Home Assistant writes the message of an error to its log as it is, so a line break
    in the text would start a line that looks like a log entry of its own. Characters
    that are not printable are replaced, and a long text is cut.
    """
    shown = "".join(char if char.isprintable() else "?" for char in text)
    return shown if len(shown) <= _SHOWN_LENGTH else f"{shown[:_SHOWN_LENGTH]}…"


def _error(key: str, **placeholders: str) -> ServiceValidationError:
    """Return the translated error for a schedule that the controller cannot take."""
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders,
    )


def _parse_time(day: str, text: str) -> int:
    """Return the minutes after midnight of a time of day in steps of 10 minutes.

    The end of the day is 24:00.
    """
    match = _TIME.fullmatch(text.strip())
    if match is None:
        raise _error("schedule_time_invalid", day=day, value=_shown(text))
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    total = hours * _MINUTES_PER_HOUR + minutes
    if minutes >= _MINUTES_PER_HOUR or seconds or total > MINUTES_PER_DAY:
        raise _error("schedule_time_invalid", day=day, value=_shown(text))
    if total % SWITCH_TIME_STEP_MINUTES:
        raise _error(
            "schedule_time_step",
            day=day,
            value=_shown(text),
            step=str(SWITCH_TIME_STEP_MINUTES),
        )
    return total


def parse_day(day: str, ranges: Sequence[Mapping[str, str]]) -> list[Period]:
    """Return the periods of a day from the time ranges of the action, sorted.

    A range starts before it ends, and the ranges of a day do not overlap, but may touch.
    Raises a translated ServiceValidationError for anything else.
    """
    name = day.capitalize()
    if len(ranges) > WEEK_PROGRAM_PERIODS:
        raise _error(
            "schedule_too_many_ranges",
            day=name,
            count=str(len(ranges)),
            max_ranges=str(WEEK_PROGRAM_PERIODS),
        )
    periods = [
        (_parse_time(name, item[ATTR_START]), _parse_time(name, item[ATTR_END]))
        for item in ranges
    ]
    for start, end in periods:
        if start >= end:
            raise _error(
                "schedule_range_backwards",
                day=name,
                start=format_time(start),
                end=format_time(end),
            )
    periods.sort()
    for first, second in pairwise(periods):
        if second[0] < first[1]:
            raise _error(
                "schedule_ranges_overlap",
                day=name,
                first_start=format_time(first[0]),
                first_end=format_time(first[1]),
                second_start=format_time(second[0]),
                second_end=format_time(second[1]),
            )
    return periods


def _ranges(periods: Sequence[Period] | None) -> list[dict[str, str]] | None:
    """Return periods as the time ranges of the actions, None for an unknown day."""
    if periods is None:
        return None
    return [
        {ATTR_START: format_time(start), ATTR_END: format_time(end)}
        for start, end in periods
    ]


def schedule_payload(
    device: FhtRoomController, *, now: datetime, link_up: bool, available: bool
) -> dict[str, Any]:
    """Return the week program of a thermostat for the card, as JSON data.

    Every weekday has a status, the periods that the controller reported (None while
    the day is unknown), and, for a day with a write on its way, the periods that were
    requested and the time of the oldest request. A requested value is no confirmed
    one: the card shows it as pending. The thermostat is reachable when the CUL is
    connected and the thermostat is not silent for longer than its threshold. The
    limits tell the card what the controller takes, so it hard codes none of them.
    """
    shown = device.shown_week_program(now)
    days: dict[str, Any] = {}
    for weekday, name in enumerate(WEEKDAYS):
        status = device.week_day_status(weekday, now)
        requests = device.week_day_requests(weekday, now)
        waiting = status in (WeekDayStatus.QUEUED, WeekDayStatus.SENDING)
        days[name] = {
            "status": status.value,
            "periods": _ranges(week_program_periods(device.week_program, weekday)),
            "requested": _ranges(week_program_periods(shown, weekday))
            if waiting
            else None,
            "pending_since": min(c.queued_at for c in requests).isoformat()
            if waiting
            else None,
        }
    read_at = device.week_program_read_at
    return {
        "limits": {
            "step_minutes": SWITCH_TIME_STEP_MINUTES,
            "max_periods": WEEK_PROGRAM_PERIODS,
            "day_end": format_time(MINUTES_PER_DAY),
        },
        "days": days,
        "week_program_read_at": None if read_at is None else read_at.isoformat(),
        "day_temperature": device.day_temperature,
        "night_temperature": device.night_temperature,
        "link_up": link_up,
        "reachable": link_up and available,
    }
