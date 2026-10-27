"""Climate platform for culfw."""

from collections.abc import Callable, Collection, Mapping, Sequence
from datetime import datetime
import logging
from typing import Any, override

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_TENTHS, UnitOfTemperature
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    HOLIDAY_MAX_DAYS,
    WEEKDAYS,
    signal_command_update,
    signal_cul_update,
    signal_device_update,
    signal_tick,
)
from .entity import (
    PENDING_ATTRIBUTES,
    FhtControlEntity,
    async_setup_device_platform,
    controller_attributes,
    invalid_value_error,
)
from .pyculfw import (
    CLIMATE_TEMP_MAX,
    CLIMATE_TEMP_MIN,
    DAYS_PER_WEEK,
    REPORT_ALL,
    TEMP_OFF,
    TEMP_ON,
    WEEK_PROGRAM_FIRST,
    WEEK_PROGRAM_LAST,
    FhtCode,
    FhtCommand,
    FhtDevice,
    FhtMode,
    FhtRoomController,
    FhtValueError,
    WeekDayStatus,
    desired_temperature_command,
    holiday_commands,
    mode_command,
    party_commands,
    report1_command,
    week_program_commands,
    week_program_periods,
)
from .runtime import FhtCulConfigEntry
from .schedule import Period, schedule_payload

_LOGGER = logging.getLogger(__name__)

# One action at a time for all climate entities of the config entry. The outbox
# serializes the radio queue as well.
PARALLEL_UPDATES = 1

DEFAULT_ON_TEMPERATURE = 20.0
VALVE_SWITCHES = {TEMP_ON: "on", TEMP_OFF: "off"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FhtCulConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the climate platform."""

    def _create(device: FhtDevice) -> list[FhtClimate]:
        return (
            [FhtClimate(entry, device)] if isinstance(device, FhtRoomController) else []
        )

    async_setup_device_platform(hass, entry, async_add_entities, _create)


class FhtClimate(FhtControlEntity, ClimateEntity):
    """An FHT80b as a thermostat.

    The HVAC mode comes from the `mode` of the controller. The week program is auto,
    also at 5.5 °C, because the program switches the setpoint again at its next time.
    Off means manual or holiday mode with 5.5 °C, so the week program cannot switch it
    on again. The valve only gives the action. The setpoints 5.5 and 30.5 °C are the
    valve switches off and on, so they are no target temperature.

    The presets name what the setpoint is. Away is the holiday or party mode, and
    comfort and eco are the day and the night temperature of the controller. Comfort
    and eco can be selected, and they write the setpoint only. Away needs an end and is
    set with the action `culfw.set_holiday`, and the HVAC mode auto ends it, so away
    and none are shown but never selected. The device feature On (30.5 °C), which the
    manual calls the heating pause, keeps the valve open and is no preset, because a
    preset must not hold the valve open without an end. A temperature between two half
    degrees rounds half up, so 20.25 becomes 20.5 and 20.2 becomes 20.0.

    Commands go through the outbox, so they reach only controllers that are alive, with
    enough duty cycle credit and buffer space. culfw delivers them in the next time slot
    of the controller, which comes about every 2 minutes. Until the controller echoes a
    value, the entity shows the requested value as pending (see FhtControlEntity). While
    the holiday or party mode runs, `preset_end_time` tells when it ends, and
    `valve_switch` tells whether the device holds the valve open (`on`) or closed
    (`off`) with the setpoints 30.5 and 5.5 °C.

    The state attributes carry everything the integration knows about the thermostat,
    see `controller_attributes()`. They use English snake_case names, which are not
    translated, because a name of an attribute is a key for templates.

    The unrecorded attributes are left out of the stored attributes only. The values
    `last_seen` and `rssi_dbm` change with every telegram, about every 2 minutes, so
    Home Assistant still fires a state change and the recorder still writes a state
    row each time, which has the same state and the same stored attributes as the one
    before. The owner asked for these attributes, so the cost is accepted.
    """

    _pending_codes = (
        FhtCode.DESIRED_TEMP,
        FhtCode.MODE,
        FhtCode.HOLIDAY1,
        FhtCode.HOLIDAY2,
        *range(WEEK_PROGRAM_FIRST, WEEK_PROGRAM_LAST + 1),
    )
    # The history keeps the mode that the device reports and the two attributes that
    # explain the setpoint. Everything else is unrecorded, because it is either fixed
    # (the codes), noisy (the signal, the times of the last telegram) or the value of an
    # entity of the same device that has its own history, such as the valve position,
    # the warnings and the settings.
    _unrecorded_attributes = PENDING_ATTRIBUTES | frozenset(
        {
            "display_code",
            "device_code",
            "house_code_display",
            "house_code",
            "last_seen",
            "rssi_dbm",
            "valve_position",
            "measured_temperature",
            "desired_temperature",
            "day_temperature",
            "night_temperature",
            "windowopen_temperature",
            "lowtemp_offset",
            "battery_low",
            "low_temperature_alarm",
            "window_open",
            "window_contacts",
            "window_sensor_fault",
            "settings_read_at",
            "week_program_read_at",
            "mode_read_at",
            "time_acknowledged_at",
            "holiday_end",
            "confirmed",
            "echoed_at",
        }
    )
    _attr_name = None
    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
    _attr_max_temp = CLIMATE_TEMP_MAX
    _attr_min_temp = CLIMATE_TEMP_MIN
    _attr_precision = PRECISION_TENTHS
    _attr_preset_modes = [
        PRESET_COMFORT,
        PRESET_ECO,
        PRESET_AWAY,
        PRESET_NONE,
    ]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )
    _attr_target_temperature_step = 0.5
    # Home Assistant 2026.11 renames the temperature members to native_*, and 2026.10
    # knows only the old names. Both are set, so that neither version warns or breaks.
    # Remove the old names when the minimum version is 2026.11; they end in 2027.11.
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, entry: FhtCulConfigEntry, device: FhtRoomController) -> None:
        """Initialize the climate entity of an FHT80b."""
        super().__init__(entry, device)
        self._last_on_temperature = DEFAULT_ON_TEMPERATURE
        self._runtime = entry.runtime_data
        self._house_code = entry.runtime_data.transport.house_code
        # The callbacks of the views of the week program that end when the entity goes.
        self._schedule_removed: set[Callable[[], None]] = set()

    @property
    def native_current_temperature(self) -> float | None:
        """Return the measured temperature."""
        return self._device.measured_temperature

    @property
    def native_target_temperature(self) -> float | None:
        """Return the desired temperature, or the requested one while it is pending.

        The valve switches off (5.5 °C) and on (30.5 °C) give no temperature.
        """
        desired = self._desired()
        return None if desired in (None, TEMP_OFF, TEMP_ON) else desired

    current_temperature = native_current_temperature
    target_temperature = native_target_temperature

    @property
    @override
    def hvac_mode(self) -> HVACMode | None:
        """Return AUTO for the week program, else OFF at 5.5 °C and HEAT above.

        Every other mode holds a fixed setpoint, so a party mode at 5.5 °C is OFF too.
        """
        mode = self._mode()
        if mode is None:
            return None
        if mode == FhtMode.AUTO:
            return HVACMode.AUTO
        # Manual, holiday and holiday_short hold a fixed setpoint.
        return HVACMode.OFF if self._desired() == TEMP_OFF else HVACMode.HEAT

    @property
    @override
    def preset_mode(self) -> str | None:
        """Return what the setpoint stands for, or None while it is unknown.

        The holiday and the party mode are away, and a setpoint equal to the day or the
        night temperature is comfort or eco. When the day and the night temperature are
        equal, comfort wins. The valve switch on (30.5 °C) is the heating pause of the
        device and no preset, even when the day temperature is set to 30.5 °C.
        """
        if self._mode() in (FhtMode.HOLIDAY, FhtMode.HOLIDAY_SHORT):
            return PRESET_AWAY
        desired = self._desired()
        if desired is None:
            return None
        if desired == TEMP_ON:
            return PRESET_NONE
        if desired == self._device.day_temperature:
            return PRESET_COMFORT
        if desired == self._device.night_temperature:
            return PRESET_ECO
        return PRESET_NONE

    @property
    @override
    def hvac_action(self) -> HVACAction | None:
        """Return heating while the valve is open."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        valve_percent = self._device.valve_percent
        if valve_percent is None:
            return None
        return HVACAction.HEATING if valve_percent > 0 else HVACAction.IDLE

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the holiday end, the valve switch, the pending state and the device."""
        now = dt_util.now()
        holiday_end = self._device.holiday_end(now)
        valve_switch = VALVE_SWITCHES.get(self._desired() or 0)
        return {
            "preset_end_time": None if holiday_end is None else holiday_end.isoformat(),
            # The heating pause has no preset and no target temperature, so this is the
            # only sign that the valve is held open.
            "valve_switch": valve_switch,
            **super().extra_state_attributes,
            **controller_attributes(
                self._device,
                self._house_code,
                now,
                self._runtime.window_contacts(self._device.device_id),
            ),
        }

    def _desired(self) -> float | None:
        """Return the desired temperature with the switches, or the pending one."""
        return self._shown(
            FhtCode.DESIRED_TEMP, self._device.desired_temperature, lambda raw: raw / 2
        )

    def _mode(self) -> FhtMode | None:
        return self._shown(
            FhtCode.MODE,
            self._device.mode,
            lambda raw: FhtMode(raw) if raw in FhtMode else self._device.mode,
        )

    @callback
    @override
    def _handle_update(self) -> None:
        """Handle a telegram of the device."""
        temperature = self._device.desired_temperature
        if temperature not in (None, TEMP_OFF, TEMP_ON):
            self._last_on_temperature = temperature
        super()._handle_update()

    @override
    async def async_added_to_hass(self) -> None:
        """Remember the last setpoint that was not off."""
        await super().async_added_to_hass()
        temperature = self._device.desired_temperature
        if temperature not in (None, TEMP_OFF, TEMP_ON):
            self._last_on_temperature = temperature

    @override
    async def async_will_remove_from_hass(self) -> None:
        """Tell the views of the week program that the entity is gone."""
        removed, self._schedule_removed = self._schedule_removed, set()
        for callback_ in removed:
            callback_()
        await super().async_will_remove_from_hass()

    @callback
    @override
    def async_entity_id_changed(self, old_entity_id: str) -> None:
        """Opt in to in-place changes of the entity ID."""
        # This class implements async_added_to_hass, so it needs the opt-in itself.
        super().async_entity_id_changed(old_entity_id)

    @override
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the desired temperature, rounded half up to 0.5 °C.

        In auto mode the controller keeps it until the next switch time of its week
        program. With an HVAC mode, the mode goes first in the same message. Off holds
        5.5 °C, so a temperature with it is refused.
        """
        temperature = kwargs[ATTR_TEMPERATURE]
        commands: list[FhtCommand] = []
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            if hvac_mode == HVACMode.OFF:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="off_with_temperature"
                )
            commands += self._mode_commands(HVACMode(hvac_mode), set_temperature=False)
        try:
            commands.append(desired_temperature_command(temperature))
        except FhtValueError as err:
            raise invalid_value_error(err) from err
        await self.async_request(dict(commands))

    @override
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Write the setpoint that comfort or eco stands for."""
        if preset_mode in (PRESET_COMFORT, PRESET_ECO):
            device_temperature = (
                self._device.day_temperature
                if preset_mode == PRESET_COMFORT
                else self._device.night_temperature
            )
            if device_temperature is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="settings_unknown",
                    translation_placeholders={"preset": preset_mode},
                )
            if device_temperature == TEMP_ON:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="preset_heating_pause",
                    translation_placeholders={"preset": preset_mode},
                )
            temperature = device_temperature
        else:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="preset_not_settable",
                translation_placeholders={"preset": preset_mode},
            )
        # The day and night temperature may be 5.5 °C, and the controller then does what
        # its own program does with it.
        await self.async_request(
            dict([desired_temperature_command(temperature, allow_switch=True)])
        )

    @override
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Switch between the week program, manual and off."""
        await self.async_request(
            dict(self._mode_commands(hvac_mode, set_temperature=True))
        )

    @override
    async def async_turn_on(self) -> None:
        """Return to the week program."""
        await self.async_set_hvac_mode(HVACMode.AUTO)

    @override
    async def async_turn_off(self) -> None:
        """Close the valve: manual mode with 5.5 °C."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_holiday(self, until: datetime, temperature: float) -> None:
        """Hold `temperature` until `until` (entity action culfw.set_holiday).

        Today or tomorrow: party mode (holiday_short), ending at the given time
        rounded down to 10 minutes. From the day after tomorrow: holiday mode, ending
        at 00:00 of the given day. Afterwards the controller returns to auto.
        """
        local_until = dt_util.as_local(until)
        now = dt_util.now()
        days = (local_until.date() - now.date()).days
        if local_until <= now or days < 0:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="holiday_in_past"
            )
        if days > HOLIDAY_MAX_DAYS:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="holiday_too_far",
                translation_placeholders={"max_days": str(HOLIDAY_MAX_DAYS)},
            )
        try:
            if days <= 1:
                commands = party_commands(
                    local_until.hour * 60 + local_until.minute,
                    local_until.day,
                    temperature,
                )
            else:
                commands = holiday_commands(
                    local_until.day, local_until.month, temperature
                )
        except FhtValueError as err:
            raise invalid_value_error(err) from err
        await self.async_request(dict(commands))

    def get_schedule(self) -> dict[int, list[tuple[int, int]]]:
        """Return the periods of the days whose week program the controller reported.

        The key is the weekday counted from 0 for Monday, and a period is the start and
        the end in minutes after midnight. These are the times the controller holds,
        not the ones that still wait for their echo. The controller reports its week
        program only when asked (the automatic read or the button Refresh schedule), and
        a day is known when all four of its switch times are.

        Raises:
            ServiceValidationError: The controller has not reported any day yet.
        """
        week = self._device.week_program
        days = {
            weekday: periods
            for weekday in range(DAYS_PER_WEEK)
            if (periods := week_program_periods(week, weekday)) is not None
        }
        if not days:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="schedule_unknown"
            )
        return days

    async def async_set_schedule(
        self, days: Mapping[int, Sequence[tuple[int, int]]]
    ) -> None:
        """Write the periods of the given days, and leave the other days alone.

        The key is the weekday counted from 0 for Monday, and a period is the start and
        the end in minutes after midnight. Every day is a message of its own, which the
        controller collects in one of its time slots, so a week takes about 15 minutes.
        A day without periods runs at the night temperature all day.

        The days are requested one after the other and cannot be taken back, so a
        refusal in the middle of the week leaves the days before it on their way. The
        error names those days and the ones that were not sent.

        Raises:
            ServiceValidationError: A period is not one that the controller takes.
            HomeAssistantError: A day was refused, and the error names the days that
                went out and the ones that did not.
        """
        try:
            messages = [
                (weekday, week_program_commands(weekday, periods))
                for weekday, periods in sorted(days.items())
            ]
        except FhtValueError as err:
            raise invalid_value_error(err) from err
        sent: list[str] = []
        for weekday, commands in messages:
            try:
                await self.async_request(dict(commands))
            except HomeAssistantError as err:
                if not sent:
                    raise
                _LOGGER.warning(
                    "The week program of %s stopped after %s: %s",
                    self.entity_id,
                    ", ".join(sent),
                    err.__cause__ or err,
                )
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="schedule_partly_sent",
                    translation_placeholders={
                        "sent": ", ".join(sent),
                        "unsent": ", ".join(
                            WEEKDAYS[later] for later, _ in messages[len(sent) :]
                        ),
                    },
                ) from err
            sent.append(WEEKDAYS[weekday])

    def schedule_state(self) -> dict[str, Any]:
        """Return the week program for the card (see `schedule_payload()`)."""
        return schedule_payload(
            self._device,
            now=dt_util.utcnow(),
            link_up=self._runtime.transport.connected,
            available=self.available,
        )

    @callback
    def async_listen_schedule(
        self, changed: Callable[[], None], removed: Callable[[], None]
    ) -> CALLBACK_TYPE:
        """Call `changed` when the week program state may have changed.

        That is after a telegram of the controller, after a request was staged or
        sent, when the link of the CUL changes and with the clock of the entry (the
        end of the pending time, a controller that turns silent). The caller compares
        the state itself. `removed` is called once if the entity goes before the caller
        stops listening. Both have to be callbacks, so that the dispatcher runs them in
        the event loop at once. The result stops the listening and may be called more
        than once.
        """
        entry_id = self._entry_id
        device_id = self._device.device_id
        unsubscribers = [
            async_dispatcher_connect(self.hass, signal, changed)
            for signal in (
                signal_device_update(entry_id, device_id),
                signal_command_update(entry_id, device_id),
                signal_cul_update(entry_id),
                signal_tick(entry_id),
            )
        ]
        self._schedule_removed.add(removed)

        @callback
        def _stop() -> None:
            while unsubscribers:
                unsubscribers.pop()()
            self._schedule_removed.discard(removed)

        return _stop

    def changed_schedule_days(
        self, days: Mapping[int, Sequence[Period]]
    ) -> dict[int, list[Period]]:
        """Return the days whose periods differ from what the controller is going to hold.

        The key is the weekday counted from 0 for Monday, and the periods are the ones
        that the caller wants. A day is left out only when the controller reported it
        or has the same periods on their way. A day that is unknown, or whose last write
        was not confirmed or was lost, is always kept, because nothing tells what the
        controller holds.
        """
        now = dt_util.utcnow()
        shown = self._device.shown_week_program(now)
        known = (WeekDayStatus.SAVED, WeekDayStatus.QUEUED, WeekDayStatus.SENDING)
        return {
            weekday: list(periods)
            for weekday, periods in days.items()
            if self._device.week_day_status(weekday, now) not in known
            or sorted(week_program_periods(shown, weekday) or []) != sorted(periods)
        }

    async def async_refresh_schedule(self, weekdays: Collection[int] | None) -> None:
        """Ask the controller to report its week program (report1).

        The key is the weekday counted from 0 for Monday, and None asks for the whole
        week. The request is one of the user, not an automatic one. The controller
        answers with one telegram for each switch time in its time slots, so a week
        takes about 35 minutes.

        Raises:
            ServiceValidationError: A weekday is not one of the seven.
            HomeAssistantError: The request is refused, for example because the CUL is
                not connected or the controller is silent.
        """
        try:
            command = report1_command(
                REPORT_ALL
                if weekdays is None
                else sum(1 << weekday for weekday in set(weekdays))
            )
        except FhtValueError as err:
            raise invalid_value_error(err) from err
        await self.async_request(dict([command]))

    def _mode_commands(
        self, hvac_mode: HVACMode, *, set_temperature: bool
    ) -> list[FhtCommand]:
        """Return the commands for the HVAC mode.

        Heat restores a setpoint when `set_temperature` is set, which is not the case
        when the caller brings its own setpoint.
        """
        match hvac_mode:
            case HVACMode.AUTO:
                return [mode_command(FhtMode.AUTO)]
            case HVACMode.OFF:
                # Off is the manual mode at 5.5 °C, so the setpoint always goes along.
                return [
                    mode_command(FhtMode.MANUAL),
                    desired_temperature_command(TEMP_OFF, allow_switch=True),
                ]
            case HVACMode.HEAT:
                commands = [mode_command(FhtMode.MANUAL)]
                if set_temperature and self._desired() in (None, TEMP_OFF, TEMP_ON):
                    # Coming from off or the heating pause: restore the last setpoint
                    # instead of 5.5 or 30.5 °C.
                    commands.append(
                        desired_temperature_command(self._last_on_temperature)
                    )
                return commands
            case _:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="unsupported_hvac_mode",
                    translation_placeholders={"mode": str(hvac_mode)},
                )
