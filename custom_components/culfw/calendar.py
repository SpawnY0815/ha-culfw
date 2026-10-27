"""Support for the week program of the FHT80b thermostats as a calendar."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, override

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import WEEKDAYS
from .entity import FhtRoomControllerEntity, async_setup_device_platform
from .pyculfw import DAYS_PER_WEEK, FhtDevice, FhtRoomController, week_program_periods
from .runtime import FhtCulConfigEntry

PARALLEL_UPDATES = 0

# Every weekday comes round within a week, so this many days after today hold the next
# event of any program that has one.
_LOOKAHEAD = timedelta(days=DAYS_PER_WEEK)

# The recurrence of the periods, which the calendar views show as a repeating event.
_WEEKLY = "FREQ=WEEKLY"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FhtCulConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the calendar platform."""

    def _create(device: FhtDevice) -> list[Entity]:
        if not isinstance(device, FhtRoomController):
            return []
        return [FhtScheduleCalendar(entry, device)]

    async_setup_device_platform(hass, entry, async_add_entities, _create)


class FhtScheduleCalendar(FhtRoomControllerEntity, CalendarEntity):
    """The heating phases of the week program of an FHT80b, which the user can only read.

    The controller regulates to the day temperature inside a phase and to the night
    temperature outside of it. The calendar shows the phases that the controller
    reported, not the ones that still wait for their echo, and a day appears once the
    controller reported all four of its switch times. The times are the clock of the
    controller, which is the house time of Home Assistant.
    """

    _attr_translation_key = "heating_program"

    def __init__(self, entry: FhtCulConfigEntry, device: FhtRoomController) -> None:
        """Initialize the calendar of a controller."""
        super().__init__(entry, device, "heating_program")

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the weekdays whose phases the controller reported."""
        return {"known_days": [WEEKDAYS[weekday] for weekday in self._known_days()]}

    @property
    @override
    def event(self) -> CalendarEvent | None:
        """Return the current phase, or the next one when none is running."""
        now = dt_util.utcnow()
        today = dt_util.now().date()
        return next(
            (
                event
                for event in self._events(today, today + _LOOKAHEAD)
                if event.end > now
            ),
            None,
        )

    @override
    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return the phases that overlap the range, in the order of their start."""
        zone = dt_util.get_default_time_zone()
        return [
            event
            for event in self._events(
                start_date.astimezone(zone).date(), end_date.astimezone(zone).date()
            )
            if event.end > start_date and event.start < end_date
        ]

    def _known_days(self) -> dict[int, list[tuple[int, int]]]:
        """Return the phases of the weekdays that the controller reported completely."""
        week = self._device.week_program
        return {
            weekday: sorted(periods)
            for weekday in range(DAYS_PER_WEEK)
            if (periods := week_program_periods(week, weekday)) is not None
        }

    def _events(self, first_day: date, last_day: date) -> Iterator[CalendarEvent]:
        """Yield the phases of the days from the first to the last, oldest first."""
        days = self._known_days()
        temperature = self._device.day_temperature
        summary = "Comfort" if temperature is None else f"Comfort {temperature:g} °C"
        day = first_day
        while day <= last_day:
            for index, (start, end) in enumerate(days.get(day.weekday(), ())):
                begin = _local_time(day, start)
                finish = _local_time(day, end)
                # A phase that starts in the hour skipped by the change to summer time
                # can end where it starts.
                if finish.timestamp() > begin.timestamp():
                    yield CalendarEvent(
                        start=begin,
                        end=finish,
                        summary=summary,
                        uid=f"{self._device.device_id}_{day.weekday()}_{index}",
                        rrule=_WEEKLY,
                    )
            day += timedelta(days=1)


def _local_time(day: date, minutes: int) -> datetime:
    """Return the time of the clock on a day, where 1440 minutes are the next midnight.

    The minutes count on the wall clock, so a phase over the change of the time lasts
    an hour more or less. A time that the change skips moves to the hour after it.
    """
    zone = dt_util.get_default_time_zone()
    wall = datetime.combine(day, time.min) + timedelta(minutes=minutes)
    return wall.replace(tzinfo=zone).astimezone(UTC).astimezone(zone)
