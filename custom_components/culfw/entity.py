"""Base classes for culfw entities."""

from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any, Final, override

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONNECTION_DEVICE_CODE,
    CUL_IDENTIFIER,
    CUL_UNREACHABLE_AFTER,
    DOMAIN,
    signal_command_update,
    signal_cul_update,
    signal_device_removed,
    signal_device_update,
    signal_new_device,
    signal_tick,
)
from .coordinator import CulCoordinator
from .pyculfw import (
    DEVICE_MODELS,
    PENDING_TIMEOUT,
    FhtDevice,
    FhtRoomController,
    FhtSendError,
    FhtValueError,
    FhtWindowContact,
    PendingCommand,
    SendFailure,
    code_to_display_pair,
    display_code,
    format_display_code,
)
from .runtime import ContactAssignment, FhtCulConfigEntry, firmware_version

# The translation key of the exception for each reason why a request was refused. The
# table is explicit, so that a key can be found by searching for it and a new reason
# fails the translation test instead of raising a missing key at run time.
SEND_FAILURE_KEYS: Final[Mapping[SendFailure, str]] = {
    SendFailure.UNKNOWN_DEVICE: "send_unknown_device",
    SendFailure.DEVICE_SILENT: "send_device_silent",
    SendFailure.DEVICE_UNCONFIRMED: "send_device_unconfirmed",
    SendFailure.DEVICE_UNRESPONSIVE: "send_device_unresponsive",
    SendFailure.NOT_CONNECTED: "send_not_connected",
    SendFailure.NO_CREDIT: "send_no_credit",
    SendFailure.CREDIT_EXHAUSTED: "send_credit_exhausted",
    SendFailure.BUFFER_FULL: "send_buffer_full",
    SendFailure.NOT_QUEUED: "send_not_queued",
    SendFailure.BLOCKED: "send_blocked",
    SendFailure.CUL_ERROR: "send_cul_error",
}


# The state attributes of an entity that waits for an echo. The recorder skips them.
PENDING_ATTRIBUTES: Final = frozenset({"pending", "pending_since"})


def invalid_value_error(err: FhtValueError) -> ServiceValidationError:
    """Return the translated validation error for a value the controller cannot take."""
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="invalid_value",
        translation_placeholders={"detail": str(err)},
    )


def send_error(err: FhtSendError) -> HomeAssistantError:
    """Return the translated error for a request that the outbox refused."""
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key=SEND_FAILURE_KEYS[err.failure],
        translation_placeholders=err.placeholders,
    )


def _iso(value: datetime | None) -> str | None:
    """Return a time as text for a state attribute, None while it is unknown."""
    return None if value is None else value.isoformat()


def _display_form(code: str) -> str | None:
    """Return a hex code as the numbers of a display, None if it has no such form."""
    # The codes of the network and the transport are four hex digits, which is all that
    # the conversion asks for.
    return None if code_to_display_pair(code) is None else format_display_code(code)


def controller_attributes(
    device: FhtRoomController,
    house_code: str,
    now: datetime,
    window_contacts: Sequence[str],
) -> dict[str, Any]:
    """Return everything the integration knows about an FHT80b as state attributes.

    The values are the ones the controller reported, never the pending ones that the
    climate entity shows until the echo. A value that the controller never reported is
    None. The codes come in both forms: the display code is what the thermostat shows
    on its display, and the device code and the house code are the hexadecimal digits on
    the radio. The house code is the central code of the CUL that the thermostat takes
    commands from, which is not the display code of the thermostat. A code that no
    display can show has no display form, so that one is None.
    """
    return {
        "display_code": _display_form(device.code),
        "device_code": device.code.upper(),
        "house_code_display": _display_form(house_code),
        "house_code": house_code.upper(),
        "last_seen": _iso(device.last_seen),
        "rssi_dbm": device.rssi_dbm,
        "valve_position": device.valve_percent,
        "measured_temperature": device.measured_temperature,
        "desired_temperature": device.desired_temperature,
        "mode": None if device.mode is None else device.mode.name.lower(),
        "day_temperature": device.day_temperature,
        "night_temperature": device.night_temperature,
        "windowopen_temperature": device.windowopen_temperature,
        "lowtemp_offset": device.lowtemp_offset,
        "battery_low": device.battery_low,
        "low_temperature_alarm": device.low_temperature,
        "window_open": device.window_open,
        "window_contacts": list(window_contacts),
        "window_sensor_fault": device.window_sensor_fault,
        "settings_read_at": _iso(device.settings_read_at),
        "week_program_read_at": _iso(device.week_program_read_at),
        "mode_read_at": _iso(device.mode_read_at),
        "time_acknowledged_at": _iso(device.time_ack),
        "holiday_end": _iso(device.holiday_end(now)),
        "confirmed": device.confirmed,
        "echoed_at": _iso(device.echoed_at),
    }


def contact_attributes(
    device: FhtWindowContact, kind: str, assignment: ContactAssignment
) -> dict[str, Any]:
    """Return everything the integration knows about an FHT80 TF as state attributes.

    The address is the only code of a contact, because it has no display. The kind is
    what the options say the contact watches, a window or a door. The thermostat is the
    display code of the room controller that the contact belongs to, and its source says
    whether the user chose it (manual) or the radio traffic suggests it (suggested).
    Both are None while nothing is known. For a suggestion, the confidence (low, medium
    or high, from the votes of the learner) and the events (the changes of the contact
    that the thermostat answered) say why it is suggested. Both are None for a
    thermostat that the user chose.
    """
    thermostat = assignment.thermostat
    return {
        "address": device.code.upper(),
        "last_seen": _iso(device.last_seen),
        "rssi_dbm": device.rssi_dbm,
        "battery_low": device.battery_low,
        "contact_type": kind,
        "thermostat": (
            None
            if thermostat is None
            else display_code(thermostat.type, thermostat.code)
        ),
        "thermostat_source": assignment.source,
        "thermostat_confidence": assignment.confidence,
        "thermostat_events": assignment.events,
    }


def cul_attributes(version: str | None, house_code: str) -> dict[str, Any]:
    """Return the firmware and the house code of the CUL as state attributes."""
    return {
        "firmware": firmware_version(version),
        "house_code_display": _display_form(house_code),
        "house_code": house_code.upper(),
    }


def cul_device_info() -> DeviceInfo:
    """Return the device info of the CUL stick."""
    return DeviceInfo(identifiers={(DOMAIN, CUL_IDENTIFIER)})


@callback
def async_setup_device_platform(
    hass: HomeAssistant,
    entry: FhtCulConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[FhtDevice], Iterable[Entity]],
) -> None:
    """Add the entities of the devices of the network, now and as they appear.

    The factory returns the entities of one device, none for a device that the platform
    does not serve. A device gets its entities once. The user removing a device makes
    the platform forget it, so that its next telegram adds the entities again.
    """
    known: set[str] = set()

    @callback
    def _add(device: FhtDevice) -> None:
        if device.device_id in known:
            return
        known.add(device.device_id)
        async_add_entities(factory(device))

    @callback
    def _forget(device_id: str) -> None:
        known.discard(device_id)

    for device in list(entry.runtime_data.network.devices.values()):
        _add(device)
    entry.async_on_unload(
        async_dispatcher_connect(hass, signal_new_device(entry.entry_id), _add)
    )
    entry.async_on_unload(
        async_dispatcher_connect(hass, signal_device_removed(entry.entry_id), _forget)
    )


class FhtDeviceEntity[DeviceT: FhtDevice](Entity):
    """Entity of one FHT device, pushed by its telegrams.

    It is unavailable once the device has been silent for longer than its threshold
    (set in the options, by default 2 hours for an FHT80b and 4 hours for an FHT80 TF),
    and once the CUL has been out of reach for 15 minutes, because the device may have
    sent anything since. A shorter outage keeps the last values, so that a stick that
    enumerates again does not make every entity flap. A change of the link is checked at
    once, the end of the grace period with the clock. An entity that reports the
    silence or the outage itself sets `_always_available`.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _always_available = False

    _device: DeviceT

    def __init__(
        self, entry: FhtCulConfigEntry, device: DeviceT, key: str | None = None
    ) -> None:
        """Initialize the entity of a device of the network.

        The main entity of a device, the thermostat, has no key and takes the ID of the
        device as its unique ID.
        """
        self._entry_id = entry.entry_id
        self._device = device
        self._network = entry.runtime_data.network
        self._stale: bool | None = None
        self._attr_unique_id = (
            device.device_id if key is None else f"{device.device_id}_{key}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.device_id)},
            connections={(CONNECTION_DEVICE_CODE, device.code.upper())},
            name=device.label,
            manufacturer="ELV",
            model=DEVICE_MODELS[device.type],
            model_id=device.type.value,
            serial_number=display_code(device.type, device.code),
            via_device_id=entry.runtime_data.cul_device_id,
        )

    @property
    @override
    def available(self) -> bool:
        """Return False while the values of the device cannot be current."""
        return self._always_available or not self._is_stale()

    @override
    async def async_added_to_hass(self) -> None:
        """Follow telegrams of the device, the link to the CUL and the clock."""
        await super().async_added_to_hass()
        self._stale = self._is_stale()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_device_update(self._entry_id, self._device.device_id),
                self._handle_update,
            )
        )
        # The end of the grace period is a matter of the clock, but a connection that
        # came back should not wait for the next tick.
        for signal in (signal_tick(self._entry_id), signal_cul_update(self._entry_id)):
            self.async_on_remove(
                async_dispatcher_connect(self.hass, signal, self._handle_tick)
            )

    @callback
    def async_entity_id_changed(self, old_entity_id: str) -> None:
        """Opt in to in-place changes of the entity ID."""
        # Home Assistant 2026.11 requires the call to the base class, which 2026.10 does
        # not have yet.
        if (parent := getattr(super(), "async_entity_id_changed", None)) is not None:
            parent(old_entity_id)

    def _is_stale(self) -> bool:
        """Return True if the values of the device cannot be current.

        That is so when the device was silent for longer than its threshold, and when
        the link to the CUL has been down for the grace period.
        """
        now = dt_util.utcnow()
        outage = self._network.link_down_for(now)
        return self._network.is_stale(self._device, now) or (
            outage is not None and outage >= CUL_UNREACHABLE_AFTER
        )

    @callback
    def _handle_update(self) -> None:
        """Handle a telegram of the device."""
        self._stale = self._is_stale()
        self.async_write_ha_state()

    @callback
    def _handle_tick(self) -> None:
        """Write the state when the device became stale or came back.

        The clock calls it every minute, and a change of the connection or a notice of
        the CUL calls it too.
        """
        stale = self._is_stale()
        if stale != self._stale:
            self._stale = stale
            self.async_write_ha_state()


class FhtRoomControllerEntity(FhtDeviceEntity[FhtRoomController]):
    """Entity of an FHT80b, which knows its device as a room controller."""


class FhtControlEntity(FhtRoomControllerEntity):
    """Entity that writes values to an FHT80b through the outbox.

    A request returns once the outbox has staged the commands, because the controller
    collects them in its next time slot, minutes later. Until the controller echoes a
    value, the entity shows the requested one as pending (the state attributes
    `pending` and `pending_since`, which the recorder skips) for up to
    `PENDING_TIMEOUT` (counted from the request, or from the sending for a day of the
    week program), instead of jumping back to the old value. A value that nothing
    confirms leaves the pending state on the next tick after the timeout, and the
    runtime then tells the user through the log, the event `culfw_command_expired`
    and the logbook.

    A subclass lists the commands it shows in `_pending_codes` and reads the value to
    show through `_shown()`.
    """

    _unrecorded_attributes = PENDING_ATTRIBUTES
    _pending_codes: tuple[int, ...] = ()

    def __init__(
        self,
        entry: FhtCulConfigEntry,
        device: FhtRoomController,
        key: str | None = None,
    ) -> None:
        """Initialize the entity of a controller that takes values."""
        super().__init__(entry, device, key)
        self._outbox = entry.runtime_data.outbox
        self._pending_shown = False

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return whether a requested value waits for its echo, and since when."""
        pending_since = [
            command.queued_at
            for code in self._pending_codes
            if (command := self._pending(code)) is not None
        ]
        return {
            "pending": bool(pending_since),
            "pending_since": min(pending_since).isoformat() if pending_since else None,
        }

    def _pending(self, code: int) -> PendingCommand | None:
        """Return the newest requested command of a code that waits for its echo."""
        return self._device.pending.newest(code, dt_util.utcnow(), PENDING_TIMEOUT)

    def _has_pending(self) -> bool:
        return any(self._pending(code) is not None for code in self._pending_codes)

    def _shown[T](self, code: int, device_value: T, convert: Callable[[int], T]) -> T:
        """Return the newest requested value of a code, or the value of the device.

        The requested value counts until the controller echoes it or the timeout is
        over. The convert callable turns the raw value into the type of the device value.
        """
        return self._device.pending.display_value(
            code, device_value, dt_util.utcnow(), PENDING_TIMEOUT, convert
        )

    async def async_request(
        self, commands: Mapping[int, int], *, urgent: bool = False
    ) -> None:
        """Hand commands (code to raw value) to the outbox and show them as pending.

        Raises:
            ServiceValidationError: The controller cannot take a value.
            HomeAssistantError: The request is refused, for example because the CUL is
                not connected or the controller is silent.
        """
        try:
            await self._outbox.request(self._device.device_id, commands, urgent=urgent)
        except FhtValueError as err:
            raise invalid_value_error(err) from err
        except FhtSendError as err:
            raise send_error(err) from err
        self._pending_shown = self._has_pending()
        self.async_write_ha_state()
        # Other views of the pending requests, such as the week program card, follow it.
        async_dispatcher_send(
            self.hass, signal_command_update(self._entry_id, self._device.device_id)
        )

    @callback
    @override
    def _handle_update(self) -> None:
        """Handle a telegram of the device, which may have settled a command."""
        self._pending_shown = self._has_pending()
        super()._handle_update()

    @callback
    @override
    def _handle_tick(self) -> None:
        """Write the state when a pending value expired or the availability changed."""
        # A pending value that expires changes the state without a telegram.
        if self._pending_shown != self._has_pending():
            self._pending_shown = not self._pending_shown
            self.async_write_ha_state()
            return
        super()._handle_tick()


class FhtWindowContactEntity(FhtDeviceEntity[FhtWindowContact]):
    """Entity of an FHT80 TF, which knows its device as a window contact."""


class CulPushEntity(Entity):
    """Entity of the CUL stick updated on connection changes and notices."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: FhtCulConfigEntry, key: str) -> None:
        """Initialize the entity of the CUL device."""
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{CUL_IDENTIFIER}_{key}"
        self._attr_device_info = cul_device_info()

    @override
    async def async_added_to_hass(self) -> None:
        """Follow connection changes and notices."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_cul_update(self._entry_id), self.async_write_ha_state
            )
        )

    @callback
    def async_entity_id_changed(self, old_entity_id: str) -> None:
        """Opt in to in-place changes of the entity ID."""
        # Home Assistant 2026.11 requires the call to the base class, which 2026.10 does
        # not have yet.
        if (parent := getattr(super(), "async_entity_id_changed", None)) is not None:
            parent(old_entity_id)


class CulPolledEntity(CoordinatorEntity[CulCoordinator]):
    """Entity of the CUL stick fed by the polling coordinator.

    Besides a failed poll, a lost connection makes it unavailable at once, so it does
    not show the numbers of the last poll for up to five minutes while the stick is
    away.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: CulCoordinator, key: str) -> None:
        """Initialize the entity of the CUL device with its coordinator."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{CUL_IDENTIFIER}_{key}"
        self._attr_device_info = cul_device_info()

    @property
    @override
    def available(self) -> bool:
        """Return False while the CUL is disconnected or the last poll failed."""
        return self.coordinator.connected and super().available

    @override
    async def async_added_to_hass(self) -> None:
        """Follow the polls and the connection."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_cul_update(self.coordinator.config_entry.entry_id),
                self.async_write_ha_state,
            )
        )

    @callback
    def async_entity_id_changed(self, old_entity_id: str) -> None:
        """Opt in to in-place changes of the entity ID."""
        # Home Assistant 2026.11 requires the call to the base class, which 2026.10 does
        # not have yet.
        if (parent := getattr(super(), "async_entity_id_changed", None)) is not None:
            parent(old_entity_id)
