"""Coordinator for the culfw integration."""

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, override

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CUL_POLL_INTERVAL, DOMAIN
from .pyculfw import CulError, CulTransport

if TYPE_CHECKING:
    from .runtime import FhtCulConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CulStatus:
    """State of the CUL read with T03, X and t.

    The credit is the remaining 1 % duty cycle budget in units of 10 ms, and booted_at
    is the current time minus the uptime of the CUL. The sensor of the uptime device
    class ignores the jitter between two polls, so the time is not rounded here.
    """

    fht_buffer_free_bytes: int
    credit_10ms: int
    booted_at: datetime


class CulCoordinator(DataUpdateCoordinator[CulStatus]):
    """Poll the CUL's buffer, duty-cycle credit and uptime.

    A poll that fails because the link is down keeps the status of the last poll and
    does not count as a failure. The runtime reports the outage on its own and the
    entities follow the link, so a failed poll would only add an error line to the
    same outage. Only a poll that fails while the CUL is connected is the
    coordinator's own news.
    """

    config_entry: FhtCulConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: FhtCulConfigEntry, transport: CulTransport
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} CUL",
            update_interval=CUL_POLL_INTERVAL,
            # A poll that hands back the old status is no reason to write the listeners.
            always_update=False,
        )
        self._transport = transport

    @property
    def connected(self) -> bool:
        """Return True while the CUL is connected."""
        return self._transport.connected

    @override
    async def _async_update_data(self) -> CulStatus:
        """Fetch the status of the CUL, or keep the last one while the link is down."""
        try:
            free = await self._transport.get_fht_buffer_free()
            credit = await self._transport.get_credit()
            uptime = await self._transport.get_uptime()
        except CulError as err:
            if self._is_outage():
                return self.data
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cul_status_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        booted_at = dt_util.utcnow() - timedelta(seconds=uptime)
        return CulStatus(
            fht_buffer_free_bytes=free,
            credit_10ms=credit.credit_10ms,
            booted_at=booted_at,
        )

    def _is_outage(self) -> bool:
        """Return True if a failed poll is nothing but the lost link.

        A coordinator that fails already keeps failing, so that it does not report a
        recovery before the CUL is read again. The first poll has no status to keep.
        """
        return (
            not self._transport.connected
            and self.last_update_success
            and self.data is not None
        )
