"""Support for culfw binary sensors."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import (
    CulPushEntity,
    FhtDeviceEntity,
    async_setup_device_platform,
    contact_attributes,
    cul_attributes,
)
from .pyculfw import CulTransport, FhtDevice, FhtRoomController, FhtWindowContact
from .runtime import FhtCulConfigEntry, contact_type

PARALLEL_UPDATES = 0

# The key of the state of a contact. It names a window although the contact may watch a
# door, because the unique ID is final.
CONTACT_KEY = "window"


@dataclass(frozen=True, kw_only=True)
class FhtBinarySensorDescription[DeviceT: FhtDevice](BinarySensorEntityDescription):
    """Binary sensor of an FHT device.

    The value function gets the device, typed for it, and whether it is stale.
    """

    value_fn: Callable[[DeviceT, bool], bool | None]
    always_available: bool = False


def _battery[DeviceT: FhtDevice]() -> FhtBinarySensorDescription[DeviceT]:
    return FhtBinarySensorDescription(
        key="battery",
        device_class=BinarySensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device, _stale: device.battery_low,
    )


def _connectivity[DeviceT: FhtDevice]() -> FhtBinarySensorDescription[DeviceT]:
    return FhtBinarySensorDescription(
        key="connectivity",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda _device, stale: not stale,
        # Off is the alarm for a missing sign of life, so it must stay available. It is
        # off too while the CUL has been out of reach for the grace period.
        always_available=True,
    )


ROOM_CONTROLLER_BINARY_SENSORS: tuple[
    FhtBinarySensorDescription[FhtRoomController], ...
] = (
    FhtBinarySensorDescription(
        key="window",
        device_class=BinarySensorDeviceClass.WINDOW,
        # The thermostat reports whether any of its paired contacts is open, which is
        # the only sign of a pairing that Home Assistant cannot see.
        value_fn=lambda device, _stale: device.window_open,
    ),
    FhtBinarySensorDescription(
        key="low_temperature",
        translation_key="low_temperature",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda device, _stale: device.low_temperature,
    ),
    FhtBinarySensorDescription(
        key="window_sensor_fault",
        translation_key="window_sensor_fault",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device, _stale: device.window_sensor_fault,
    ),
    _battery(),
    _connectivity(),
)

WINDOW_CONTACT_BINARY_SENSORS: tuple[
    FhtBinarySensorDescription[FhtWindowContact], ...
] = (
    FhtBinarySensorDescription(
        key=CONTACT_KEY,
        # The class is the default. The options can make the contact watch a door.
        device_class=BinarySensorDeviceClass.WINDOW,
        # Unavailable when the contact is silent: never claim "closed" from old data.
        value_fn=lambda device, _stale: device.window_open,
    ),
    _battery(),
    _connectivity(),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FhtCulConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    async_add_entities([CulConnectivity(entry, entry.runtime_data.transport)])

    def _create(device: FhtDevice) -> list[Entity]:
        if isinstance(device, FhtRoomController):
            return [
                FhtBinarySensor(entry, device, description)
                for description in ROOM_CONTROLLER_BINARY_SENSORS
            ]
        return [
            (
                FhtContactSensor(entry, device, description)
                if description.key == CONTACT_KEY
                else FhtBinarySensor(entry, device, description)
            )
            for description in WINDOW_CONTACT_BINARY_SENSORS
        ]

    async_setup_device_platform(hass, entry, async_add_entities, _create)


class FhtBinarySensor[DeviceT: FhtDevice](FhtDeviceEntity[DeviceT], BinarySensorEntity):
    """Binary sensor of an FHT device."""

    entity_description: FhtBinarySensorDescription[DeviceT]

    def __init__(
        self,
        entry: FhtCulConfigEntry,
        device: DeviceT,
        description: FhtBinarySensorDescription[DeviceT],
    ) -> None:
        """Initialize the binary sensor of a device."""
        super().__init__(entry, device, description.key)
        self.entity_description = description
        self._always_available = description.always_available

    @property
    @override
    def is_on(self) -> bool | None:
        """Return the value from the device state."""
        return self.entity_description.value_fn(self._device, self._is_stale())


class FhtContactSensor(FhtBinarySensor[FhtWindowContact]):
    """Whether an FHT80 TF contact is open, as a window or as a door.

    The user chooses in the options what the contact watches. The device class follows
    the choice, and an override in the entity settings of Home Assistant still wins
    over it.

    The state attributes carry everything the integration knows about the contact, see
    `contact_attributes()`. They are not translated, and the history skips them: the
    address and the thermostat change only when the user says so, the evidence for a
    suggestion only grows slowly, and the battery and the signal have entities of their
    own.
    """

    _unrecorded_attributes = frozenset(
        {
            "address",
            "last_seen",
            "rssi_dbm",
            "battery_low",
            "contact_type",
            "thermostat",
            "thermostat_source",
            "thermostat_confidence",
            "thermostat_events",
        }
    )

    def __init__(
        self,
        entry: FhtCulConfigEntry,
        device: FhtWindowContact,
        description: FhtBinarySensorDescription[FhtWindowContact],
    ) -> None:
        """Initialize the sensor with the device class that the options choose."""
        super().__init__(entry, device, description)
        self._runtime = entry.runtime_data
        self._contact_type = contact_type(entry.options, device.device_id)
        self._attr_device_class = BinarySensorDeviceClass(self._contact_type)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the address, the last telegram, the battery, type and thermostat."""
        return contact_attributes(
            self._device,
            self._contact_type,
            self._runtime.contact_assignment(self._device.device_id),
        )


class CulConnectivity(CulPushEntity, BinarySensorEntity):
    """Whether the CUL's serial port is open and initialized."""

    # The firmware and the house code stay as long as the entry is loaded.
    _unrecorded_attributes = frozenset({"firmware", "house_code_display", "house_code"})
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: FhtCulConfigEntry, transport: CulTransport) -> None:
        """Initialize the connectivity sensor of the CUL."""
        super().__init__(entry, "connectivity")
        self._transport = transport

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the firmware version and the house code of the CUL."""
        return cul_attributes(self._transport.version, self._transport.house_code)

    @property
    @override
    def is_on(self) -> bool:
        """Return True while the CUL is connected."""
        return self._transport.connected
