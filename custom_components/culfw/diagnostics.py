"""Diagnostics support for culfw."""

from dataclasses import asdict
from datetime import datetime
import re
from typing import Any
from urllib.parse import urlsplit

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .const import CONF_HOUSE_CODE, CUL_IDENTIFIER, DOMAIN
from .entity import contact_attributes, controller_attributes, cul_attributes
from .pyculfw import (
    DeviceType,
    FhtDevice,
    FhtWindowContact,
    InvalidationReason,
    SendRecord,
    display_code,
)
from .runtime import FhtCulConfigEntry, FhtCulRuntime, command_name, contact_type

# The integration has no credentials, but the FHT house code is the radio address that
# anyone in range can use to talk to the thermostats. The device addresses are needed to
# debug radio problems and are kept. The house code in the attributes of an entity is
# redacted under both of its names, the hexadecimal and the display form.
TO_REDACT = {CONF_HOUSE_CODE, "house_code_display"}

# The error of a CUL that keeps another house code names both codes, and the code it
# keeps is the one that another central uses. The text shows a code as the two numbers
# of the display, and older text and the CUL itself show four hex digits.
HOUSE_CODE_IN_TEXT = re.compile(
    r"(house code\W+)(?:[0-9A-Fa-f]{4}|\d{3} \d{3})\b", re.IGNORECASE
)

# The error of a failed connection names the address that was tried, as a tuple like
# `('192.168.1.50', 2000)`, and that address can be the one that a host name resolved
# to, so the host name of the URL alone does not find it.
ADDRESS_IN_TEXT = re.compile(
    r"\('[^']*', \d+(?:, \d+, \d+)?\)|\b\d{1,3}(?:\.\d{1,3}){3}\b"
)


def _redact_port(port: str) -> str:
    """Return the port with the address of a remote serial port hidden.

    The URL of a remote port (`socket://`, `rfc2217://` or `esphome://`) names a host
    and may carry credentials, while a device path of this host is what a bug report
    needs.
    """
    scheme, separator, _ = port.partition("://")
    return f"{scheme}{separator}{REDACTED}" if separator else port


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FhtCulConfigEntry
) -> dict[str, Any]:
    """Return the state of the CUL, all devices and the latest raw lines."""
    # An entry that is not loaded, for example while the CUL is unplugged, has no
    # runtime. It still gets its data, its state and the reason, because that is when
    # the download is needed most.
    if entry.state is not ConfigEntryState.LOADED:
        return _entry_state(entry)
    runtime = entry.runtime_data
    now = dt_util.now()
    return async_redact_data(
        {
            **_entry_state(entry),
            "transport": _transport(runtime, now),
            "cul": _cul(runtime),
            "counters": _counters(runtime),
            "outbox": _outbox(runtime),
            "candidates": {
                device_id: candidate.to_dict()
                for device_id, candidate in runtime.network.candidates.items()
            },
            "ignored_devices": sorted(runtime.network.ignored),
            # What the learner holds per contact: its proposal with the confidence and
            # the events behind it, the votes and points of each thermostat and the
            # last answers of the thermostats with their delay.
            "window_pairing": runtime.network.pairing.report(),
            "devices": {
                device_id: _device(entry, device, now)
                for device_id, device in runtime.network.devices.items()
            },
            "raw_lines": _raw_lines(runtime),
        },
        TO_REDACT,
    )


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: FhtCulConfigEntry, device_entry: dr.AnyDeviceEntry
) -> dict[str, Any]:
    """Return the state of one FHT device (or the CUL) and its raw lines."""
    if entry.state is not ConfigEntryState.LOADED:
        return {
            **_entry_state(entry),
            "identifiers": sorted(device_entry.identifiers),
        }
    runtime = entry.runtime_data
    now = dt_util.now()
    for domain, device_id in device_entry.identifiers:
        if domain != DOMAIN:
            continue
        if device_id == CUL_IDENTIFIER:
            return async_redact_data(
                {
                    "transport": _transport(runtime, now),
                    "cul": _cul(runtime),
                    "counters": _counters(runtime),
                    "raw_lines": _raw_lines(runtime),
                },
                TO_REDACT,
            )
        device = runtime.network.devices.get(device_id)
        if device is None:
            return {"device_id": device_id, "state": None}
        channel = runtime.outbox.channel_states().get(device_id)
        prefix = f"T{device.code.upper()}"
        return async_redact_data(
            {
                "device_id": device_id,
                "state": _device(entry, device, now),
                "channel": None if channel is None else asdict(channel),
                "raw_lines": _raw_lines(runtime, prefix),
            },
            TO_REDACT,
        )
    return {}


def _entry_state(entry: FhtCulConfigEntry) -> dict[str, Any]:
    """Return the data and options of the entry with its state and the reason."""
    return {
        "entry": async_redact_data(
            {
                "data": {
                    **entry.data,
                    CONF_DEVICE: _redact_port(entry.data[CONF_DEVICE]),
                },
                "options": dict(entry.options),
            },
            TO_REDACT,
        ),
        "state": entry.state.value,
        "reason": None
        if entry.reason is None
        else _scrub(
            entry.reason, entry.data.get(CONF_HOUSE_CODE), entry.data[CONF_DEVICE]
        ),
    }


def _scrub(text: str, house_code: str | None, port: str) -> str:
    """Return the text of an error without the house codes and the remote port."""
    text = _scrub_house_codes(text, house_code)
    if _redact_port(port) == port:
        return text
    text = text.replace(port, _redact_port(port))
    # The cause of a failed connection names the host without the scheme.
    parts = urlsplit(port)
    for host in filter(None, (parts.netloc, parts.hostname)):
        text = re.sub(re.escape(host), REDACTED, text, flags=re.IGNORECASE)
    return ADDRESS_IN_TEXT.sub(REDACTED, text)


def _scrub_house_codes(text: str, house_code: str | None) -> str:
    """Return the text without the configured house code and the code of a CUL."""
    if house_code:
        for shown in (house_code, display_code(DeviceType.FHT80B, house_code)):
            text = re.sub(re.escape(shown), REDACTED, text, flags=re.IGNORECASE)
    return HOUSE_CODE_IN_TEXT.sub(rf"\g<1>{REDACTED}", text)


def _transport(runtime: FhtCulRuntime, now: datetime) -> dict[str, Any]:
    transport = runtime.transport
    statistics = asdict(transport.statistics)
    # The text of an error can name the house code, for example when the CUL kept
    # another one than the integration wrote.
    if statistics["last_error"] is not None:
        statistics["last_error"] = _scrub(
            statistics["last_error"], transport.house_code, transport.port
        )
    link_down = runtime.network.link_down_for(now)
    return {
        "state": transport.state.value,
        "connected": transport.connected,
        "port": _redact_port(transport.port),
        "version": transport.version,
        "house_code": transport.house_code,
        "cul_was_reset": transport.cul_was_reset,
        "house_code_writes": transport.house_code_writes,
        "statistics": statistics,
        "link_down_seconds": None
        if link_down is None
        else round(link_down.total_seconds()),
    }


def _cul(runtime: FhtCulRuntime) -> dict[str, Any]:
    status = runtime.cul.data
    return {
        # The same names and values as the state attributes of the CUL entity.
        "attributes": cul_attributes(
            runtime.transport.version, runtime.transport.house_code
        ),
        "status": None if status is None else asdict(status),
        "last_poll_ok": runtime.cul.last_update_success,
        "watchdog_escalating": runtime.watchdog.escalating,
    }


def _counters(runtime: FhtCulRuntime) -> dict[str, Any]:
    """Return the counters since the start of the entry."""
    network = runtime.network
    return {
        "eob": network.eob_count,
        "lovf": network.lovf_count,
        "purges": runtime.watchdog.purge_count,
        # Messages that waited while a thermostat counted down its synchronization.
        "held_for_sync": runtime.outbox.held_for_sync,
        "rejected_telegrams": {
            "from_central": network.central_telegram_count,
            "from_ignored_devices": network.ignored_telegram_count,
            "unknown_codes": network.unknown_code_count,
        },
        # The commands that were retired without an echo, by the reason.
        "invalidations": {
            reason.value: network.retired_counts.get(reason, 0)
            for reason in InvalidationReason
        },
    }


def _outbox(runtime: FhtCulRuntime) -> dict[str, Any]:
    """Return the dump of the FHT buffer and the command channel of each controller."""
    outbox = runtime.outbox
    queue = outbox.fht_queue
    at = outbox.fht_queue_at
    return {
        "fht_queue": None
        if queue is None
        else {
            house_code: [f"{code:02X}{value:02X}" for code, value in commands]
            for house_code, commands in queue.items()
        },
        "fht_queue_at": None if at is None else at.isoformat(),
        "channels": {
            device_id: asdict(state)
            for device_id, state in outbox.channel_states().items()
        },
        "send_log": [_send_record(record) for record in outbox.send_log],
    }


def _send_record(record: SendRecord) -> dict[str, Any]:
    """Return the credit around a message, with what the radio spent in between.

    The credit grows by one unit of 10 ms per second up to its maximum, so the estimate
    is a lower bound when the account was full at the end.
    """
    spent = None
    if (
        record.credit_before_10ms is not None
        and record.credit_after_10ms is not None
        and record.seconds_in_flight is not None
    ):
        spent = round(
            record.credit_before_10ms
            + record.seconds_in_flight
            - record.credit_after_10ms
        )
    return {
        **asdict(record),
        "at": record.at.isoformat(),
        "estimated_spent_10ms": spent,
    }


def _device(
    entry: FhtCulConfigEntry, device: FhtDevice, now: datetime
) -> dict[str, Any]:
    runtime = entry.runtime_data
    silent_for = runtime.network.silent_for(device, now)
    state = {
        **device.to_dict(),
        "stale": runtime.network.is_stale(device, now),
        "silent_seconds": None
        if silent_for is None
        else round(silent_for.total_seconds()),
    }
    if isinstance(device, FhtWindowContact):
        # The same names and values as the state attributes of the entity of the device.
        state["attributes"] = contact_attributes(
            device,
            contact_type(entry.options, device.device_id),
            runtime.contact_assignment(device.device_id),
        )
    else:
        state["attributes"] = controller_attributes(
            device,
            runtime.transport.house_code,
            now,
            runtime.window_contacts(device.device_id),
        )
        holiday_end = device.holiday_end(now)
        # The stored form keeps only the commands that were sent. The diagnostics show
        # the staged ones too, because a command that waits for its message is what a
        # user who asks why a value did not arrive needs to see.
        state["holiday_end"] = None if holiday_end is None else holiday_end.isoformat()
        state["synchronizing"] = device.synchronizing(now)
        state["pending"] = [
            {
                "code": command_name(command.code),
                "raw": command.raw,
                "state": command.state.value,
                "message_id": command.message_id,
                "queued_at": command.queued_at.isoformat(),
                "age_seconds": round((now - command.queued_at).total_seconds()),
            }
            for command in device.pending.commands()
        ]
    return state


def _raw_lines(
    runtime: FhtCulRuntime, prefix: str | None = None
) -> list[dict[str, str]]:
    return [
        {"time": time.isoformat(), "line": line}
        for time, line in runtime.raw_lines
        if prefix is None or line.upper().startswith(prefix)
    ]
