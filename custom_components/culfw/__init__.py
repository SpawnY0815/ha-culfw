"""The culfw integration."""

import logging

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICE, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import CONF_ADD_CARD, CUL_IDENTIFIER, DEFAULT_ADD_CARD, DOMAIN
from .frontend_registration import (
    async_add_card,
    async_remove_card,
    async_setup_frontend,
)
from .hotplug import async_setup_hotplug
from .issues import async_delete_issues
from .pyculfw import (
    CulError,
    CulPortBusyError,
    CulPortMissingError,
    CulPortPermissionError,
    CulProtocolError,
    CulTimeoutError,
)
from .runtime import FhtCulConfigEntry, FhtCulRuntime, async_stable_port
from .services import async_setup_services
from .store import create_store
from .websocket_api import async_setup_websocket_api

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CALENDAR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SENSOR,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the culfw integration."""
    async_setup_services(hass)
    async_setup_websocket_api(hass)
    await async_setup_frontend(hass)
    await async_setup_hotplug(hass)
    return True


async def _async_migrate_port(hass: HomeAssistant, entry: FhtCulConfigEntry) -> None:
    """Store the by-id path of the CUL in an entry that holds a tty node."""
    port: str = entry.data[CONF_DEVICE]
    stable_port = await async_stable_port(hass, port)
    if stable_port != port:
        _LOGGER.info(
            "Replacing the port %s of the CUL with its stable path %s",
            port,
            stable_port,
        )
        # The entry has no update listener, so the update does not reload it.
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_DEVICE: stable_port}
        )


async def async_setup_entry(hass: HomeAssistant, entry: FhtCulConfigEntry) -> bool:
    """Set up culfw from a config entry."""
    # The runtime reads the port from the entry when it builds the transport.
    await _async_migrate_port(hass, entry)
    runtime = await FhtCulRuntime.async_create(hass, entry)
    port = runtime.transport.port
    # Home Assistant logs the reason on every retry, so logging it here would repeat it.
    try:
        await runtime.transport.connect()
    except CulPortMissingError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cul_missing",
            translation_placeholders={"port": port, "error": str(err)},
        ) from err
    except CulPortBusyError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cul_busy",
            translation_placeholders={"port": port, "error": str(err)},
        ) from err
    except CulPortPermissionError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cul_permission",
            translation_placeholders={"port": port, "error": str(err)},
        ) from err
    except CulTimeoutError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cul_no_answer",
            translation_placeholders={"port": port, "error": str(err)},
        ) from err
    except CulProtocolError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cul_not_culfw",
            translation_placeholders={"port": port, "error": str(err)},
        ) from err
    except CulError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cul_not_ready",
            translation_placeholders={"port": port, "error": str(err)},
        ) from err
    # Home Assistant also runs the on_unload callbacks when the setup fails, so the
    # port closes whatever goes wrong from here on.
    entry.async_on_unload(runtime.async_shutdown)
    # Not async_listen_once: removing a one-time listener that already fired logs an
    # error when the entry is unloaded after the stop event.
    entry.async_on_unload(
        hass.bus.async_listen(EVENT_HOMEASSISTANT_STOP, runtime.async_shutdown)
    )
    await runtime.async_start()
    entry.runtime_data = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if entry.options.get(CONF_ADD_CARD, DEFAULT_ADD_CARD):
        await async_add_card(hass, entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FhtCulConfigEntry) -> bool:
    """Unload a config entry."""
    # The shutdown of the runtime closes the CUL. It is registered with async_on_unload.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: FhtCulConfigEntry) -> None:
    """Delete the stored device state, the issues and the card resource of an entry."""
    await create_store(hass, entry.entry_id).async_remove()
    await async_remove_card(hass, entry)
    async_delete_issues(hass)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: FhtCulConfigEntry, device_entry: dr.AnyDeviceEntry
) -> bool:
    """Allow removing an FHT device, but never the CUL.

    A silent device is forgotten and comes back with its next telegram. A device that
    still transmits is ignored, because it would come back at once.
    """
    # Home Assistant offers the removal in every state of the entry, but the runtime
    # that has to forget the device exists only while the entry is loaded.
    if entry.state is not ConfigEntryState.LOADED:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="entry_not_loaded"
        )
    runtime = entry.runtime_data
    device_ids = {
        device_id for domain, device_id in device_entry.identifiers if domain == DOMAIN
    }
    if CUL_IDENTIFIER in device_ids:
        # The CUL itself stays, because every FHT device is attached to it.
        return False
    for device_id in device_ids:
        runtime.async_remove_device(device_id)
    return True
