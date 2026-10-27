"""Hot-plug handling for the culfw integration."""

from functools import partial
import logging
from typing import cast

from homeassistant.components import usb
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICE
from homeassistant.core import HomeAssistant, callback
from homeassistant.loader import USBMatcher, async_get_integration

from .const import DOMAIN, LOCAL_DEVICE_DIR
from .runtime import FhtCulRuntime

_LOGGER = logging.getLogger(__name__)


async def async_setup_hotplug(hass: HomeAssistant) -> None:
    """Make the entry of the CUL try again as soon as the stick is plugged in.

    The USB integration reports a plugged in stick a few seconds after the host saw
    it. The callback is registered once for the domain, not per entry, so it also
    reaches an entry whose setup waits for its next retry. It selects the stick with
    the USB matchers of the manifest, which are read here once, so changing them
    needs a restart of Home Assistant.
    """
    integration = await async_get_integration(hass, DOMAIN)
    # The loader adds the domain to the matchers of a manifest in the same way.
    matchers = [
        cast(USBMatcher, {"domain": DOMAIN, **matcher})
        for matcher in integration.usb or []
    ]
    usb.async_register_port_event_callback(
        hass, partial(_async_port_event, hass, matchers)
    )


def _is_plugged_in(
    port: str, devices: set[usb.USBDevice], matchers: list[USBMatcher]
) -> bool:
    """Return whether one of the devices is the CUL behind the stored port.

    A URL points to a stick on another host, which no device of this host can be.
    The stored path of a stick is either its by-id link, which the USB integration
    reports as the device, or its tty node, which it reports as the resolved device.
    The matchers find a stick whose link was not there yet when the host scanned, and
    one that is stored under a name of the user, such as one of a udev rule.
    """
    if not port.startswith(LOCAL_DEVICE_DIR):
        return False
    return any(
        port in (device.device, device.resolved_device)
        or any(usb.usb_device_matches_matcher(device, matcher) for matcher in matchers)
        for device in devices
    )


@callback
def _async_port_event(
    hass: HomeAssistant,
    matchers: list[USBMatcher],
    added: set[usb.USBDevice],
    _removed: set[usb.USBDevice],
) -> None:
    """Wake up the entry whose CUL was just plugged in.

    The USB integration reports every device that is present as added when Home
    Assistant starts, so a connected CUL gets no more than a look here. A device that
    was removed needs nothing, because the transport learns about the loss from the
    port itself, and a setup that retries has nothing to learn from it.
    """
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.SETUP_RETRY:
            if _is_plugged_in(entry.data[CONF_DEVICE], added, matchers):
                _LOGGER.debug("The CUL appeared, setting up the entry again")
                hass.config_entries.async_schedule_reload(entry.entry_id)
        elif entry.state is ConfigEntryState.LOADED:
            runtime: FhtCulRuntime = entry.runtime_data
            if not runtime.transport.connected and _is_plugged_in(
                entry.data[CONF_DEVICE], added, matchers
            ):
                _LOGGER.debug("The CUL appeared, reconnecting without waiting")
                runtime.transport.reconnect_now()
