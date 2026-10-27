"""Actions for the culfw integration."""

from datetime import datetime
from typing import Any

import probatio

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.helpers import config_validation as cv, service

from .climate import FhtClimate
from .const import (
    ATTR_UNTIL,
    DOMAIN,
    SERVICE_GET_SCHEDULE,
    SERVICE_SET_HOLIDAY,
    SERVICE_SET_SCHEDULE,
    WEEKDAYS,
)
from .pyculfw import CLIMATE_TEMP_MAX, CLIMATE_TEMP_MIN
from .schedule import ATTR_END, ATTR_START, RANGE_SCHEMA, format_time, parse_day


def _datetime(value: Any) -> datetime:
    """Return the value as a date and time, and refuse it without repeating it.

    The check of Home Assistant names the text it refuses, and the log of Home
    Assistant shows that message as it is, so a line break in the text of a user would
    start a line that looks like a log entry of its own.
    """
    try:
        return cv.datetime(value)
    except probatio.Invalid:
        raise probatio.Invalid("not a date and time like 2026-12-27 18:00:00") from None


async def _get_schedule(entity: FhtClimate, call: ServiceCall) -> ServiceResponse:
    """Return the week program that the thermostat reported, by weekday."""
    return {
        WEEKDAYS[weekday]: [
            {ATTR_START: format_time(start), ATTR_END: format_time(end)}
            for start, end in periods
        ]
        for weekday, periods in entity.get_schedule().items()
    }


async def _set_schedule(entity: FhtClimate, call: ServiceCall) -> None:
    """Write the time ranges of the given days to the thermostat."""
    await entity.async_set_schedule(
        {
            weekday: parse_day(day, call.data[day])
            for weekday, day in enumerate(WEEKDAYS)
            if day in call.data
        }
    )


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the entity actions."""
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_SET_HOLIDAY,
        entity_domain=CLIMATE_DOMAIN,
        schema={
            probatio.Required(ATTR_UNTIL): _datetime,
            probatio.Required(ATTR_TEMPERATURE): probatio.All(
                probatio.Coerce(float),
                probatio.Range(min=CLIMATE_TEMP_MIN, max=CLIMATE_TEMP_MAX),
            ),
        },
        func="async_set_holiday",
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_GET_SCHEDULE,
        entity_domain=CLIMATE_DOMAIN,
        schema=None,
        supports_response=SupportsResponse.ONLY,
        func=_get_schedule,
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_SET_SCHEDULE,
        entity_domain=CLIMATE_DOMAIN,
        schema=probatio.All(
            cv.make_entity_service_schema(
                {probatio.Optional(day): [RANGE_SCHEMA] for day in WEEKDAYS}
            ),
            probatio.AtLeastOne(*WEEKDAYS),
        ),
        func=_set_schedule,
    )
