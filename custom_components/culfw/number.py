"""Number platform for culfw."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
import math
from typing import override

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import FhtControlEntity, async_setup_device_platform, invalid_value_error
from .pyculfw import (
    LOWTEMP_OFFSET_MAX,
    LOWTEMP_OFFSET_MIN,
    SETTING_TEMP_MAX,
    SETTING_TEMP_MIN,
    TEMP_STEP,
    FhtCode,
    FhtCommand,
    FhtDevice,
    FhtRoomController,
    FhtValueError,
    lowtemp_offset_command,
    setting_temperature_command,
)
from .runtime import FhtCulConfigEntry

# One action at a time for all number entities of the config entry. The outbox
# serializes the radio queue as well.
PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class FhtNumberDescription(NumberEntityDescription):
    """Setting of an FHT80b, with the code that carries it to the controller."""

    code: FhtCode
    value_fn: Callable[[FhtRoomController], float | None]
    # The value that a raw byte of the code stands for.
    from_raw: Callable[[int], float]
    # The command for a value, which quantizes it and raises FhtValueError if the
    # controller cannot take it.
    command_fn: Callable[[float], FhtCommand]


def _half_degrees(raw: int) -> float:
    """Return the temperature of a byte that counts half degrees."""
    return raw * TEMP_STEP


def _whole_degrees(raw: int) -> float:
    """Return the offset of a byte that counts whole degrees."""
    return float(raw)


def _offset_command(value: float) -> FhtCommand:
    """Return the command for an offset, rounded half up like the temperatures.

    Home Assistant checks the range of a value but not its step. Anything that is not a
    finite number goes on unchanged, so that the builder refuses it.
    """
    return lowtemp_offset_command(
        math.floor(value + 0.5) if math.isfinite(value) else value
    )


def _temperature_setting(
    key: str, code: FhtCode, value_fn: Callable[[FhtRoomController], float | None]
) -> FhtNumberDescription:
    """Return the description of a temperature that the controller keeps."""
    return FhtNumberDescription(
        key=key,
        translation_key=key,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=SETTING_TEMP_MIN,
        native_max_value=SETTING_TEMP_MAX,
        native_step=TEMP_STEP,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        code=code,
        value_fn=value_fn,
        from_raw=_half_degrees,
        command_fn=partial(setting_temperature_command, code),
    )


ROOM_CONTROLLER_NUMBERS: tuple[FhtNumberDescription, ...] = (
    _temperature_setting(
        "day_temperature", FhtCode.DAY_TEMP, lambda device: device.day_temperature
    ),
    _temperature_setting(
        "night_temperature", FhtCode.NIGHT_TEMP, lambda device: device.night_temperature
    ),
    _temperature_setting(
        "windowopen_temperature",
        FhtCode.WINDOWOPEN_TEMP,
        lambda device: device.windowopen_temperature,
    ),
    FhtNumberDescription(
        key="lowtemp_offset",
        translation_key="lowtemp_offset",
        device_class=NumberDeviceClass.TEMPERATURE_DELTA,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=LOWTEMP_OFFSET_MIN,
        native_max_value=LOWTEMP_OFFSET_MAX,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        # The alarm offset is set once at installation, so it is clutter for most users.
        entity_registry_enabled_default=False,
        code=FhtCode.LOWTEMP_OFFSET,
        value_fn=lambda device: device.lowtemp_offset,
        from_raw=_whole_degrees,
        command_fn=_offset_command,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FhtCulConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the number platform."""

    def _create(device: FhtDevice) -> list[Entity]:
        if not isinstance(device, FhtRoomController):
            return []
        return [
            FhtNumber(entry, device, description)
            for description in ROOM_CONTROLLER_NUMBERS
        ]

    async_setup_device_platform(hass, entry, async_add_entities, _create)


class FhtNumber(FhtControlEntity, NumberEntity):
    """A setting of an FHT80b that the user can change.

    The value is unknown until the controller has reported its settings. A new value
    shows as pending until the controller echoes it (see FhtControlEntity), and a
    controller that echoes another value wins.
    """

    entity_description: FhtNumberDescription

    def __init__(
        self,
        entry: FhtCulConfigEntry,
        device: FhtRoomController,
        description: FhtNumberDescription,
    ) -> None:
        """Initialize the number of a setting."""
        super().__init__(entry, device, description.key)
        self.entity_description = description
        self._pending_codes = (description.code,)

    @property
    @override
    def native_value(self) -> float | None:
        """Return the requested value while it waits for its echo, else the setting."""
        return self._shown(
            self.entity_description.code,
            self.entity_description.value_fn(self._device),
            self.entity_description.from_raw,
        )

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Send the value, rounded half up to the step of the controller."""
        try:
            command = self.entity_description.command_fn(value)
        except FhtValueError as err:
            raise invalid_value_error(err) from err
        await self.async_request(dict([command]))
