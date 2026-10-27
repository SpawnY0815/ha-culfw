"""Support for culfw sensors."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfInformation,
    UnitOfRatio,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .const import WEEKDAYS, signal_command_update
from .coordinator import CulCoordinator, CulStatus
from .entity import (
    CulPolledEntity,
    CulPushEntity,
    FhtControlEntity,
    FhtDeviceEntity,
    async_setup_device_platform,
)
from .pyculfw import (
    DAYS_PER_WEEK,
    WEEK_PROGRAM_FIRST,
    WEEK_PROGRAM_LAST,
    ActuatorState,
    FhtDevice,
    FhtNetwork,
    FhtRoomController,
    FhtWindowContact,
    WeekDayStatus,
    week_program_periods,
)
from .runtime import FhtCulConfigEntry

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class FhtSensorDescription[DeviceT: FhtDevice](SensorEntityDescription):
    """Sensor of an FHT device, with the value function typed for the device."""

    value_fn: Callable[[DeviceT], StateType | datetime]
    always_available: bool = False


def _rssi[DeviceT: FhtDevice]() -> FhtSensorDescription[DeviceT]:
    return FhtSensorDescription(
        key="rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.rssi_dbm,
    )


def _last_seen[DeviceT: FhtDevice]() -> FhtSensorDescription[DeviceT]:
    return FhtSensorDescription(
        key="last_seen",
        translation_key="last_seen",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        # It changes with every telegram, and the connectivity sensor and the repair
        # issues already tell when a device is gone.
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.last_seen,
        # The sensor shows how long a silent device has been gone.
        always_available=True,
    )


# The option of each state of the actuator, which is the key of its translation. UNKNOWN
# has none: a state called unknown would clash with the reserved state of the entity,
# so the sensor shows no state then.
ACTUATOR_STATE_OPTIONS: dict[ActuatorState, str] = {
    ActuatorState.VALVE: "regulating",
    ActuatorState.SYNC_NOW: "sync_now",
    ActuatorState.ON: "on",
    ActuatorState.OFF: "off",
    ActuatorState.OFFSET: "offset",
    ActuatorState.LIME_PROTECTION: "lime_protection",
    ActuatorState.SYNCTIME: "sync_time",
    ActuatorState.TEST: "test",
    ActuatorState.PAIR: "pair",
}


def _actuator_state(device: FhtRoomController) -> str | None:
    """Return the option of the last actuator state, None if there is none."""
    if device.actuator_state is None:
        return None
    return ACTUATOR_STATE_OPTIONS.get(device.actuator_state)


ROOM_CONTROLLER_SENSORS: tuple[FhtSensorDescription[FhtRoomController], ...] = (
    FhtSensorDescription(
        key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.measured_temperature,
    ),
    FhtSensorDescription(
        key="valve",
        translation_key="valve",
        native_unit_of_measurement=UnitOfRatio.PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.valve_percent,
    ),
    FhtSensorDescription(
        key="actuator_state",
        translation_key="actuator_state",
        device_class=SensorDeviceClass.ENUM,
        options=list(ACTUATOR_STATE_OPTIONS.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        # The valve position and the climate entity tell what matters, and this is for
        # chasing a device that syncs or beeps.
        entity_registry_enabled_default=False,
        value_fn=_actuator_state,
    ),
    FhtSensorDescription(
        key="holiday_end",
        translation_key="holiday_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        # The climate entity shows the same time as the end of its away preset.
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.holiday_end(dt_util.now()),
    ),
    _rssi(),
    _last_seen(),
    FhtSensorDescription(
        key="time_ack",
        translation_key="time_ack",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.time_ack,
        always_available=True,
    ),
)

WINDOW_CONTACT_SENSORS: tuple[FhtSensorDescription[FhtWindowContact], ...] = (
    _rssi(),
    _last_seen(),
)


@dataclass(frozen=True, kw_only=True)
class CulPolledSensorDescription(SensorEntityDescription):
    """Sensor of the CUL fed by the polling coordinator."""

    value_fn: Callable[[CulStatus], StateType | datetime]


CUL_POLLED_SENSORS: tuple[CulPolledSensorDescription, ...] = (
    CulPolledSensorDescription(
        key="fht_buffer_free",
        translation_key="fht_buffer_free",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda status: status.fht_buffer_free_bytes,
    ),
    CulPolledSensorDescription(
        key="duty_cycle_credit",
        translation_key="duty_cycle_credit",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda status: status.credit_10ms / 100,
    ),
    CulPolledSensorDescription(
        key="uptime",
        device_class=SensorDeviceClass.UPTIME,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda status: status.booted_at,
    ),
)


@dataclass(frozen=True, kw_only=True)
class CulCounterDescription(SensorEntityDescription):
    """Counter of culfw notices since the integration started."""

    value_fn: Callable[[FhtNetwork], int]


CUL_COUNTERS: tuple[CulCounterDescription, ...] = (
    CulCounterDescription(
        key="eob_count",
        translation_key="eob_count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda network: network.eob_count,
    ),
    CulCounterDescription(
        key="lovf_count",
        translation_key="lovf_count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        # The notice is rare, and the duty cycle credit sensor shows the budget itself.
        entity_registry_enabled_default=False,
        value_fn=lambda network: network.lovf_count,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FhtCulConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    runtime = entry.runtime_data
    async_add_entities(
        [
            *(
                CulPolledSensor(runtime.cul, description)
                for description in CUL_POLLED_SENSORS
            ),
            *(
                CulCounterSensor(entry, runtime.network, description)
                for description in CUL_COUNTERS
            ),
        ]
    )

    def _create(device: FhtDevice) -> list[Entity]:
        if isinstance(device, FhtRoomController):
            return [
                *(
                    FhtSensor(entry, device, description)
                    for description in ROOM_CONTROLLER_SENSORS
                ),
                FhtWeekProgramSensor(entry, device),
            ]
        return [
            FhtSensor(entry, device, description)
            for description in WINDOW_CONTACT_SENSORS
        ]

    async_setup_device_platform(hass, entry, async_add_entities, _create)


class FhtSensor[DeviceT: FhtDevice](FhtDeviceEntity[DeviceT], SensorEntity):
    """Sensor of an FHT device."""

    entity_description: FhtSensorDescription[DeviceT]

    def __init__(
        self,
        entry: FhtCulConfigEntry,
        device: DeviceT,
        description: FhtSensorDescription[DeviceT],
    ) -> None:
        """Initialize the sensor of a device."""
        super().__init__(entry, device, description.key)
        self.entity_description = description
        self._always_available = description.always_available

    @property
    @override
    def native_value(self) -> StateType | datetime:
        """Return the value from the device state."""
        return self.entity_description.value_fn(self._device)


# The states of the week program status. Unknown is the reserved state of Home Assistant
# on purpose: it is also what an entity shows while it knows nothing.
WEEK_PROGRAM_STATUS_OPTIONS: Final = ("unknown", "partial", "complete", "writing")


class FhtWeekProgramSensor(FhtControlEntity, SensorEntity):
    """How much of the week program of an FHT80b is known, and whether it is written.

    The status is writing while any day waits in the outbox or for the echo of the
    controller, complete when the controller reported all seven days, partial when it
    reported some and unknown when it reported none. A reported day is one whose four
    switch times the controller sent. The sensor is a control entity only because it
    follows the pending requests for the week program, and nothing writes through it.
    """

    _attr_translation_key = "week_program_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(WEEK_PROGRAM_STATUS_OPTIONS)
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _pending_codes = tuple(range(WEEK_PROGRAM_FIRST, WEEK_PROGRAM_LAST + 1))

    def __init__(self, entry: FhtCulConfigEntry, device: FhtRoomController) -> None:
        """Initialize the sensor of a thermostat."""
        super().__init__(entry, device, "week_program_status")

    @override
    async def async_added_to_hass(self) -> None:
        """Follow the requests of the other entities of the thermostat as well."""
        await super().async_added_to_hass()
        # The climate entity stages the week program, so only its signal reaches here
        # before the controller says anything.
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_command_update(self._entry_id, self._device.device_id),
                self._handle_update,
            )
        )

    @callback
    @override
    def async_entity_id_changed(self, old_entity_id: str) -> None:
        """Opt in to in-place changes of the entity ID."""
        # This class implements async_added_to_hass, so it needs the opt-in itself.
        super().async_entity_id_changed(old_entity_id)

    @property
    @override
    def native_value(self) -> str:
        """Return writing, complete, partial or unknown."""
        now = dt_util.utcnow()
        if any(
            self._device.week_day_status(weekday, now)
            in (WeekDayStatus.QUEUED, WeekDayStatus.SENDING)
            for weekday in range(DAYS_PER_WEEK)
        ):
            return "writing"
        known = len(self._known_days())
        if known == DAYS_PER_WEEK:
            return "complete"
        return "partial" if known else "unknown"

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the weekdays that were reported, the last full read and the pending state."""
        read_at = self._device.week_program_read_at
        return {
            "known_days": [WEEKDAYS[weekday] for weekday in self._known_days()],
            "week_program_read_at": None if read_at is None else read_at.isoformat(),
            **super().extra_state_attributes,
        }

    def _known_days(self) -> list[int]:
        """Return the weekdays whose four switch times the controller reported."""
        week = self._device.week_program
        return [
            weekday
            for weekday in range(DAYS_PER_WEEK)
            if week_program_periods(week, weekday) is not None
        ]


class CulPolledSensor(CulPolledEntity, SensorEntity):
    """Sensor of the CUL fed by the polling coordinator."""

    entity_description: CulPolledSensorDescription

    def __init__(
        self, coordinator: CulCoordinator, description: CulPolledSensorDescription
    ) -> None:
        """Initialize the sensor of the CUL with its coordinator."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    @override
    def native_value(self) -> StateType | datetime:
        """Return the value from the last poll."""
        return self.entity_description.value_fn(self.coordinator.data)


class CulCounterSensor(CulPushEntity, SensorEntity):
    """Counter of EOB or LOVF notices since the integration started."""

    entity_description: CulCounterDescription

    def __init__(
        self,
        entry: FhtCulConfigEntry,
        network: FhtNetwork,
        description: CulCounterDescription,
    ) -> None:
        """Initialize the counter sensor."""
        super().__init__(entry, description.key)
        self.entity_description = description
        self._network = network

    @property
    @override
    def native_value(self) -> int:
        """Return the current count."""
        return self.entity_description.value_fn(self._network)
