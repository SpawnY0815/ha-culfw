"""Serve the week program card and register it with the dashboards."""

import asyncio
from collections.abc import Awaitable, Callable
import hashlib
import logging
from pathlib import Path
from urllib.parse import urlsplit

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import CONF_RESOURCE_TYPE_WS, LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ID, CONF_TYPE, CONF_URL, EVENT_COMPONENT_LOADED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.loader import async_get_integration
from homeassistant.setup import ATTR_COMPONENT, EventComponentLoaded
from homeassistant.util.hass_dict import HassKey

from .const import CONF_ADD_CARD, DEFAULT_ADD_CARD, DOMAIN
from .runtime import FhtCulConfigEntry

_LOGGER = logging.getLogger(__name__)

CARD_FILE = "fht-schedule-card.js"
CARD_PATH = Path(__file__).parent / "frontend" / CARD_FILE
# The type of a dashboard resource that the bundle needs, because it is an ES module.
RESOURCE_TYPE = "module"
URL_BASE = f"/{DOMAIN}/frontend"

# The URL of the card with its cache buster, set by async_setup_frontend.
DATA_CARD_URL: HassKey[str] = HassKey(f"{DOMAIN}_card_url")
# Whether the bundle was offered to the web server, which happens once for the domain.
DATA_SERVED: HassKey[bool] = HassKey(f"{DOMAIN}_card_served")
DATA_SERVE_LOCK: HassKey[asyncio.Lock] = HassKey(f"{DOMAIN}_card_serve_lock")


def _card_url(version: str) -> str:
    """Return the URL of the bundle, with the version and a hash of the file.

    The hash makes a new URL for a bundle that changed without a new version, which
    happens while the card is under development, and it is the same on every start.
    The function reads the file, so it runs in the executor.
    """
    digest = hashlib.sha256(CARD_PATH.read_bytes()).hexdigest()[:12]
    return f"{URL_BASE}/{CARD_FILE}?v={version}-{digest}"


def _frontend_ready(hass: HomeAssistant) -> bool:
    """Return whether the frontend is set up, which the card needs to be seen at all."""
    return "frontend" in hass.config.components


def _async_when_frontend(
    hass: HomeAssistant,
    entry: FhtCulConfigEntry | None,
    action: Callable[[], Awaitable[None]],
) -> Awaitable[None] | None:
    """Run the action once the frontend is set up.

    Return the action to await when the frontend is set up already. Otherwise wait for
    the event that announces it and return None. The listener belongs to the entry,
    when there is one, and goes with it, so an unloaded entry gets no card.
    """
    if _frontend_ready(hass):
        return action()
    state = {"done": False}

    @callback
    def _unsubscribe() -> None:
        if not state["done"]:
            state["done"] = True
            remove()

    async def _loaded(_event: Event[EventComponentLoaded]) -> None:
        _unsubscribe()
        await action()

    @callback
    def _is_frontend(data: EventComponentLoaded) -> bool:
        return data[ATTR_COMPONENT] == "frontend"

    remove = hass.bus.async_listen(
        EVENT_COMPONENT_LOADED, _loaded, event_filter=_is_frontend
    )
    if entry is not None:
        entry.async_on_unload(_unsubscribe)
    return None


async def _async_serve(hass: HomeAssistant) -> None:
    """Serve the bundle, once for the domain, and remember its URL.

    A path can be registered only once. The web server refuses a path after it started
    to serve, which a test client does; Home Assistant registers at run time without
    that problem. A refusal is not an error here, because the thermostats work without
    the card. It leaves no URL, so nothing points the dashboards at a missing file.
    """
    async with hass.data.setdefault(DATA_SERVE_LOCK, asyncio.Lock()):
        if hass.data.get(DATA_SERVED):
            return
        hass.data[DATA_SERVED] = True
        integration = await async_get_integration(hass, DOMAIN)
        try:
            url = await hass.async_add_executor_job(_card_url, str(integration.version))
        except OSError as err:
            # A damaged installation must not take the integration down with it.
            _LOGGER.warning("The week program card is not available: %s", err)
            return
        try:
            await hass.http.async_register_static_paths(
                [StaticPathConfig(f"{URL_BASE}/{CARD_FILE}", str(CARD_PATH), False)]
            )
        except RuntimeError as err:
            _LOGGER.debug("The week program card cannot be served now: %s", err)
            return
        hass.data[DATA_CARD_URL] = url


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Serve the bundle of the week program card as soon as the frontend is there.

    The frontend is an after dependency of the integration, not a dependency, so a
    setup without a user interface does not pull it in. Whether a dashboard loads the
    card is up to each config entry, see async_add_card().
    """
    if pending := _async_when_frontend(hass, None, lambda: _async_serve(hass)):
        await pending


async def async_add_card(hass: HomeAssistant, entry: FhtCulConfigEntry) -> None:
    """Make the dashboards load the card as long as the entry is loaded.

    Without a frontend there is nothing to do until it is set up, and then this runs.
    In the storage mode of the dashboards the card becomes a resource, which is the
    list the dashboards load before they draw a card. Where that cannot be done, the
    frontend gets the URL as an extra module, which it loads in parallel and may
    finish after the first draw of a dashboard. The bundle defines its element only
    once, so a user who also lists the file by hand loses nothing.
    """

    async def _add() -> None:
        await _async_serve(hass)
        await _async_add_to_dashboards(hass, entry)

    if pending := _async_when_frontend(hass, entry, _add):
        await pending


async def _async_add_to_dashboards(
    hass: HomeAssistant, entry: FhtCulConfigEntry
) -> None:
    """Add the resource or the extra module, when the bundle is served."""
    if (url := hass.data.get(DATA_CARD_URL)) is None:
        return
    resources = (
        lovelace.resources if (lovelace := hass.data.get(LOVELACE_DATA)) else None
    )
    if isinstance(resources, ResourceStorageCollection):
        try:
            await _async_set_resource(resources, url)
        except HomeAssistantError as err:
            _LOGGER.warning(
                "Could not add the week program card to the dashboard resources, "
                "loading it as an extra module instead: %s",
                err,
            )
        else:
            return
    else:
        _LOGGER.debug(
            "The dashboard resources are in YAML mode or not set up, so the week "
            "program card loads as an extra module. To load it before the dashboards "
            "draw, add %s as a JavaScript module to the resources",
            url,
        )
    frontend.add_extra_js_url(hass, url)
    entry.async_on_unload(lambda: frontend.remove_extra_js_url(hass, url))


async def _async_load(resources: ResourceStorageCollection) -> None:
    """Load the stored resources like the websocket command of the dashboards."""
    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True


def _find_resource(
    resources: ResourceStorageCollection, url: str
) -> dict[str, str] | None:
    """Return the resource that holds the bundle under any version, or None."""
    path = urlsplit(url).path
    for item in resources.async_items():
        if urlsplit(item[CONF_URL]).path == path:
            return item
    return None


async def _async_set_resource(resources: ResourceStorageCollection, url: str) -> None:
    """Add the bundle as a resource, or bring the entry of an older version up to date.

    An entry is the one of the bundle when its path matches, whatever follows the
    path, so adding the resource again never makes a second one. Only the first match
    is changed, and no other resource is touched.
    """
    await _async_load(resources)
    if (item := _find_resource(resources, url)) is None:
        await resources.async_create_item(
            {CONF_RESOURCE_TYPE_WS: RESOURCE_TYPE, CONF_URL: url}
        )
    elif item[CONF_URL] != url or item[CONF_TYPE] != RESOURCE_TYPE:
        await resources.async_update_item(
            item[CONF_ID], {CONF_RESOURCE_TYPE_WS: RESOURCE_TYPE, CONF_URL: url}
        )


async def async_remove_card(hass: HomeAssistant, entry: FhtCulConfigEntry) -> None:
    """Delete the resource of the card, unless the user edited it.

    This is for an entry that is removed for good. An entry that is only unloaded
    leaves the resource, because the dashboards would break for the time it is gone.
    The resource is shared by all entries, so it stays while another loaded entry
    still wants the card.
    """
    if (url := hass.data.get(DATA_CARD_URL)) is None:
        return
    if any(
        other.entry_id != entry.entry_id
        and other.state is ConfigEntryState.LOADED
        and other.options.get(CONF_ADD_CARD, DEFAULT_ADD_CARD)
        for other in hass.config_entries.async_entries(DOMAIN)
    ):
        return
    lovelace = hass.data.get(LOVELACE_DATA)
    resources = lovelace.resources if lovelace else None
    if not isinstance(resources, ResourceStorageCollection):
        return
    await _async_load(resources)
    item = _find_resource(resources, url)
    if item is not None and item[CONF_URL] == url:
        await resources.async_delete_item(item[CONF_ID])
