"""Storage of the FHT device state."""

from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import DOMAIN

# Version of the file in .storage that holds the device state.
STORAGE_VERSION = 1


def create_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    """Return the store that holds the device state of a config entry."""
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")


class ThrottledSave:
    """Persist at most once per delay and surely within one delay of a change.

    Store.async_delay_save debounces: every call moves the write further out. With a
    telegram every few seconds it would only write on shutdown, so a crash would lose
    everything since the start.
    """

    def __init__(
        self,
        store: Store[dict[str, Any]],
        data_func: Callable[[], dict[str, Any]],
        delay_seconds: float,
    ) -> None:
        """Initialize the save with a store and the function that returns the data."""
        self._store = store
        self._data_func = data_func
        self._delay_seconds = delay_seconds
        self._pending = False

    @callback
    def schedule(self) -> None:
        """Save within `delay_seconds`; further calls until then are folded in."""
        if self._pending:
            return
        self._pending = True
        self._store.async_delay_save(self._data, self._delay_seconds)

    async def async_save_now(self) -> None:
        """Save immediately (on unload)."""
        self._pending = False
        await self._store.async_save(self._data_func())

    def _data(self) -> dict[str, Any]:
        # Called by the store right before writing: later changes schedule again.
        self._pending = False
        return self._data_func()
