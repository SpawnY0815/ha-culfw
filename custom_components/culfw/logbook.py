"""Describe culfw events for the logbook."""

from collections.abc import Callable
from typing import Any

from homeassistant.components.logbook import (
    LOGBOOK_ENTRY_MESSAGE,
    LOGBOOK_ENTRY_NAME,
    LazyEventPartialState,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, EVENT_CHANNEL_BROKEN, EVENT_COMMAND_EXPIRED, EVENT_WATCHDOG
from .pyculfw import (
    InvalidationReason,
    SendFailure,
    WatchdogEventKind,
    WatchdogStep,
    device_label,
)

# The logbook shows the message as is and has no translation hook.
_KIND_TEXTS: dict[WatchdogEventKind, str] = {
    WatchdogEventKind.SILENCE: "no telegram received",
    WatchdogEventKind.SUCCEEDED: "step succeeded",
    WatchdogEventKind.FAILED: "step failed",
    WatchdogEventKind.SKIPPED: "step skipped",
    WatchdogEventKind.RECOVERED: "telegrams are back",
    WatchdogEventKind.EXHAUSTED: "all steps failed",
    WatchdogEventKind.ABORTED: "escalation aborted",
}
_STEP_TEXTS: dict[WatchdogStep, str] = {
    WatchdogStep.PING: "ping (V)",
    WatchdogStep.REOPEN: "reopen port",
    WatchdogStep.CLEAR_BUFFER: "clear FHT buffer (T01)",
    WatchdogStep.REBOOT: "reboot (B00)",
    WatchdogStep.USB_RESET: "USB reset",
    WatchdogStep.POWER_CYCLE: "power cycle",
}
# Why a requested value never reached the controller: the retirements of the pending
# queue and the failures of a message after it was staged.
_REASON_TEXTS: dict[str, str] = {
    InvalidationReason.EXPIRED: "the controller did not echo it in time",
    InvalidationReason.UNCLAIMED_EOB: "the CUL dropped a message",
    InvalidationReason.BUFFER_PURGE: "the FHT buffer of the CUL was cleared",
    InvalidationReason.CUL_RESET: "the CUL restarted",
    InvalidationReason.LINK_OUTAGE: "the CUL was unreachable for too long",
    InvalidationReason.HOUSE_CODE_REWRITE: "the central code of the CUL was rewritten",
    SendFailure.UNKNOWN_DEVICE: "the controller is not known",
    SendFailure.DEVICE_SILENT: "the controller is silent",
    SendFailure.DEVICE_UNCONFIRMED: "the controller never echoed a command",
    SendFailure.DEVICE_UNRESPONSIVE: "the controller stopped echoing commands",
    SendFailure.NOT_CONNECTED: "the CUL is not connected",
    SendFailure.NO_CREDIT: "the CUL has no radio budget left",
    SendFailure.CREDIT_EXHAUSTED: "the radio budget of the CUL stayed used up",
    SendFailure.BUFFER_FULL: "the FHT buffer of the CUL is full",
    SendFailure.NOT_QUEUED: "the CUL did not take the message",
    SendFailure.BLOCKED: "the command is not allowed",
    SendFailure.CUL_ERROR: "the CUL did not answer",
}


def _kind_text(kind: str) -> str:
    """Return the text for a kind, or the raw value if it is not known."""
    try:
        return _KIND_TEXTS[WatchdogEventKind(kind)]
    except ValueError:
        return kind


def _step_text(step: str) -> str:
    """Return the text for a step, or the raw value if it is not known."""
    try:
        return _STEP_TEXTS[WatchdogStep(step)]
    except ValueError:
        return step


def _reason_text(reason: str) -> str:
    """Return the text for a reason, or the raw value if it is not known."""
    return _REASON_TEXTS.get(reason, reason.replace("_", " "))


def _requested_text(requested: Any) -> str:
    """Return the requested value without a needless decimal."""
    return f"{requested:g}" if isinstance(requested, float) else str(requested)


def _device_name(hass: HomeAssistant, device_id: str) -> str:
    """Return the name of the device in the registry, or the one made from its ID.

    A device that left the registry is still named for its events, such as "FHT80b 063 072".
    An ID that is no FHT device names the integration.
    """
    devices = dr.async_get(hass).async_get_devices(identifiers={(DOMAIN, device_id)})
    if devices and (name := devices[0].name_by_user or devices[0].name):
        return name
    label = device_label(device_id)
    return "culfw" if label == device_id else label


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[
        [str, str, Callable[[LazyEventPartialState], dict[str, Any]]], None
    ],
) -> None:
    """Describe the watchdog, command expired and channel broken events."""

    @callback
    def _describe(event: LazyEventPartialState) -> dict[str, Any]:
        """Describe a watchdog event."""
        data = event.data
        message = f"Watchdog: {_kind_text(str(data.get('kind')))}"
        if step := data.get("step"):
            message += f", {_step_text(str(step))}"
        if reason := data.get("reason"):
            message += f" ({str(reason).replace('_', ' ')})"
        if detail := data.get("detail"):
            message += f" - {detail}"
        return {LOGBOOK_ENTRY_NAME: "culfw", LOGBOOK_ENTRY_MESSAGE: message}

    @callback
    def _describe_expired(event: LazyEventPartialState) -> dict[str, Any]:
        """Describe a command that the controller never confirmed."""
        data = event.data
        command = str(data.get("code")).replace("_", " ").capitalize()
        requested = _requested_text(data.get("requested"))
        reason = _reason_text(str(data.get("reason")))
        return {
            LOGBOOK_ENTRY_NAME: _device_name(hass, str(data.get("device"))),
            LOGBOOK_ENTRY_MESSAGE: f"{command} {requested} was not confirmed: {reason}",
        }

    @callback
    def _describe_broken(event: LazyEventPartialState) -> dict[str, Any]:
        """Describe a controller that stopped echoing the messages."""
        return {
            LOGBOOK_ENTRY_NAME: _device_name(hass, str(event.data.get("device"))),
            LOGBOOK_ENTRY_MESSAGE: (
                "Stopped echoing commands, so nothing is sent to it on its own "
                "until it echoes a command again"
            ),
        }

    async_describe_event(DOMAIN, EVENT_WATCHDOG, _describe)
    async_describe_event(DOMAIN, EVENT_COMMAND_EXPIRED, _describe_expired)
    async_describe_event(DOMAIN, EVENT_CHANNEL_BROKEN, _describe_broken)
