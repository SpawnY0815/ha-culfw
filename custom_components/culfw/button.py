"""Support for culfw buttons."""

from dataclasses import dataclass
from typing import override

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import (
    CulPushEntity,
    FhtRoomControllerEntity,
    async_setup_device_platform,
    send_error,
)
from .pyculfw import (
    FULL_REFRESH,
    REPORT_ALL,
    FhtCommand,
    FhtDevice,
    FhtRoomController,
    FhtSendError,
    report1_command,
    report2_command,
)
from .runtime import FhtCulConfigEntry
from .timesync import TimeSync

# One press at a time for all buttons of the config entry. The outbox serializes the
# radio queue as well.
PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class FhtButtonDescription(ButtonEntityDescription):
    """Request of an FHT80b that a button sends to the controller."""

    command: FhtCommand


ROOM_CONTROLLER_BUTTONS: tuple[FhtButtonDescription, ...] = (
    FhtButtonDescription(
        key="refresh_settings",
        translation_key="refresh_settings",
        entity_category=EntityCategory.CONFIG,
        # The mode, the temperature settings, the setpoint and the warnings, which the
        # controller reports only when asked.
        command=report2_command(FULL_REFRESH),
    ),
    FhtButtonDescription(
        key="refresh_schedule",
        translation_key="refresh_schedule",
        entity_category=EntityCategory.CONFIG,
        # The week program is 28 telegrams of the controller, which keeps its radio busy
        # for minutes. The integration reads it on its own as well, so the button is for
        # the user who wants it now and is off by default.
        entity_registry_enabled_default=False,
        command=report1_command(REPORT_ALL),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FhtCulConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the button platform."""
    async_add_entities([SyncTimeButton(entry, entry.runtime_data.timesync)])

    def _create(device: FhtDevice) -> list[Entity]:
        if not isinstance(device, FhtRoomController):
            return []
        return [
            FhtRefreshButton(entry, device, description)
            for description in ROOM_CONTROLLER_BUTTONS
        ]

    async_setup_device_platform(hass, entry, async_add_entities, _create)


class SyncTimeButton(CulPushEntity, ButtonEntity):
    """Send date and time to every alive FHT80b (normally done daily at 04:05)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "sync_time"

    def __init__(self, entry: FhtCulConfigEntry, timesync: TimeSync) -> None:
        """Initialize the button."""
        super().__init__(entry, "sync_time")
        self._timesync = timesync
        self._transport = entry.runtime_data.transport

    @property
    @override
    def available(self) -> bool:
        """Return True while the CUL is connected, as the time goes out by radio."""
        return self._transport.connected

    @override
    async def async_press(self) -> None:
        """Send the time; fail if no FHT80b is known or none got it."""
        if not self._timesync.has_controllers:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_fht80b"
            )
        results = await self._timesync.async_sync_all("button", automatic=False)
        if results and all(failure is not None for failure in results.values()):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="time_sync_failed",
                translation_placeholders={"count": str(len(results))},
            )


class FhtRefreshButton(FhtRoomControllerEntity, ButtonEntity):
    """Ask an FHT80b to report values that it never sends on its own.

    The press returns once the outbox has taken the request. The controller answers
    with telegrams of its own in its next time slots, and the entities of the device
    update as they arrive.
    """

    entity_description: FhtButtonDescription

    def __init__(
        self,
        entry: FhtCulConfigEntry,
        device: FhtRoomController,
        description: FhtButtonDescription,
    ) -> None:
        """Initialize the button of a request."""
        super().__init__(entry, device, description.key)
        self.entity_description = description
        self._outbox = entry.runtime_data.outbox

    @override
    async def async_press(self) -> None:
        """Queue the request for the controller."""
        code, raw = self.entity_description.command
        try:
            await self._outbox.request(self._device.device_id, {code: raw})
        except FhtSendError as err:
            raise send_error(err) from err
