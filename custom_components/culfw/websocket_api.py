"""Websocket API of the culfw integration for the week program card."""

from typing import Any, Final

import probatio

from homeassistant.auth.permissions.const import POLICY_CONTROL, POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.components.climate import DATA_COMPONENT as CLIMATE_DATA_COMPONENT
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from homeassistant.helpers import config_validation as cv

from .climate import FhtClimate
from .const import DOMAIN, WEEKDAYS
from .schedule import RANGE_SCHEMA, parse_day

ATTR_DAYS: Final = "days"
ATTR_ENTITY_ID: Final = "entity_id"


def _entity_id(value: Any) -> str:
    """Return the value as an entity ID, and refuse it without repeating it.

    The check of Home Assistant names the text it refuses, and Home Assistant writes
    that message to its log as it is, so a line break in the text of a user would start
    a line that looks like a log entry of its own.
    """
    try:
        return cv.entity_id(value)
    except probatio.Invalid:
        raise probatio.Invalid("not an entity ID like climate.living_room") from None


def _thermostat(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    entity_id: str,
    policy: str,
) -> FhtClimate:
    """Return the climate entity of a thermostat if the user may use it that way.

    The permission is checked first, so a user without it cannot tell whether the entity
    exists. Home Assistant checks the permission itself only for the actions, not for
    the commands of the websocket API.

    Raises:
        Unauthorized: The user has no permission of this kind for the entity.
        ServiceValidationError: The entity is not the climate entity of a thermostat.
    """
    if not connection.user.permissions.check_entity(entity_id, policy):
        raise Unauthorized(entity_id=entity_id)
    component = hass.data.get(CLIMATE_DATA_COMPONENT)
    entity = None if component is None else component.get_entity(entity_id)
    if not isinstance(entity, FhtClimate):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="schedule_entity_unknown",
            translation_placeholders={"entity_id": entity_id},
        )
    return entity


@websocket_api.websocket_command(
    {
        probatio.Required("type"): f"{DOMAIN}/schedule/get",
        probatio.Required(ATTR_ENTITY_ID): _entity_id,
    }
)
@callback
def websocket_get(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the week program of a thermostat with the status of every day."""
    entity = _thermostat(hass, connection, msg[ATTR_ENTITY_ID], POLICY_READ)
    connection.send_result(msg["id"], entity.schedule_state())


@websocket_api.websocket_command(
    {
        probatio.Required("type"): f"{DOMAIN}/schedule/subscribe",
        probatio.Required(ATTR_ENTITY_ID): _entity_id,
    }
)
@callback
def websocket_subscribe(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Send the week program now and again whenever it changes.

    The events have the data of the command `get`. The state is compared with the one
    that was sent last, so a trigger that changes nothing sends nothing. When the entity
    goes away, for example because the entry reloads, one last event `{"closed": true}`
    ends the subscription and the client subscribes again.
    """
    entity = _thermostat(hass, connection, msg[ATTR_ENTITY_ID], POLICY_READ)
    last: dict[str, Any] | None = None

    @callback
    def _send_if_changed() -> None:
        nonlocal last
        state = entity.schedule_state()
        if state != last:
            last = state
            connection.send_event(msg["id"], state)

    @callback
    def _closed() -> None:
        connection.send_event(msg["id"], {"closed": True})
        # The subscription is there: the entity only calls this for a listener that
        # was not stopped, and stopping removes the subscription from the connection.
        connection.subscriptions.pop(msg["id"])()

    connection.subscriptions[msg["id"]] = entity.async_listen_schedule(
        _send_if_changed, _closed
    )
    connection.send_result(msg["id"])
    _send_if_changed()


@websocket_api.websocket_command(
    {
        probatio.Required("type"): f"{DOMAIN}/schedule/set",
        probatio.Required(ATTR_ENTITY_ID): _entity_id,
        probatio.Required(ATTR_DAYS): probatio.All(
            {probatio.Optional(day): [RANGE_SCHEMA] for day in WEEKDAYS},
            probatio.AtLeastOne(*WEEKDAYS),
        ),
    }
)
@websocket_api.async_response
async def websocket_set(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Write the days of a week program that differ from what the thermostat holds.

    All days are checked before one is sent, with the checks of the action
    `set_schedule`. A day that the thermostat holds already, or that is on its way
    with the same times, is not sent again, and the result names it as unchanged. The
    command returns once the days are staged, like the action: the thermostat takes
    one day in each of its time slots, and the status of the day tells how far it is.
    """
    entity = _thermostat(hass, connection, msg[ATTR_ENTITY_ID], POLICY_CONTROL)
    requested = {
        weekday: parse_day(day, msg[ATTR_DAYS][day])
        for weekday, day in enumerate(WEEKDAYS)
        if day in msg[ATTR_DAYS]
    }
    changed = entity.changed_schedule_days(requested)
    await entity.async_set_schedule(changed)
    connection.send_result(
        msg["id"],
        {
            "sent": [WEEKDAYS[weekday] for weekday in sorted(changed)],
            "unchanged": [
                WEEKDAYS[weekday] for weekday in sorted(requested.keys() - changed)
            ],
        },
    )


@websocket_api.websocket_command(
    {
        probatio.Required("type"): f"{DOMAIN}/schedule/refresh",
        probatio.Required(ATTR_ENTITY_ID): _entity_id,
        probatio.Optional(ATTR_DAYS): probatio.All(
            [probatio.In(WEEKDAYS)], probatio.Length(min=1)
        ),
    }
)
@websocket_api.async_response
async def websocket_refresh(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Ask the thermostat to report its week program, all days or the given ones.

    The thermostat answers with one telegram for each switch time in its time slots, so
    a whole week takes about 35 minutes, and the days become known as they arrive. The
    command returns once the request is staged. It works whether the button Refresh
    schedule is enabled or not.
    """
    entity = _thermostat(hass, connection, msg[ATTR_ENTITY_ID], POLICY_CONTROL)
    names = msg.get(ATTR_DAYS)
    await entity.async_refresh_schedule(
        None if names is None else [WEEKDAYS.index(name) for name in names]
    )
    connection.send_result(
        msg["id"],
        {
            ATTR_DAYS: list(WEEKDAYS)
            if names is None
            else sorted(set(names), key=WEEKDAYS.index)
        },
    )


@callback
def async_setup_websocket_api(hass: HomeAssistant) -> None:
    """Register the websocket commands of the week program card."""
    websocket_api.async_register_command(hass, websocket_get)
    websocket_api.async_register_command(hass, websocket_subscribe)
    websocket_api.async_register_command(hass, websocket_set)
    websocket_api.async_register_command(hass, websocket_refresh)
