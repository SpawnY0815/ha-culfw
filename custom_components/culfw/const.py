"""Constants for the culfw integration."""

from datetime import timedelta

# Where the thermostat of a contact comes from: the user chose it, or the radio traffic
# suggests it and the user has not confirmed it yet.
ASSIGNMENT_MANUAL = "manual"
ASSIGNMENT_SUGGESTED = "suggested"

ATTR_UNTIL = "until"

# The directory of the stable names that udev gives to serial devices.
BY_ID_DIR = "/dev/serial/by-id/"

# Whether the integration adds the week program card to the dashboard resources.
CONF_ADD_CARD = "add_card"
# The recovery options: the watchdog may take these steps only when the user allows it.
CONF_ALLOW_REBOOT = "allow_reboot"
CONF_ALLOW_USB_RESET = "allow_usb_reset"
CONF_AUTO_ADD_DEVICES = "auto_add_devices"
# The actions on the candidates are asked for in the options form and never stored.
CONF_CANDIDATES_TO_ADD = "candidates_to_add"
CONF_CANDIDATES_TO_IGNORE = "candidates_to_ignore"
# The thermostat of each contact, by device ID. The thermostats do not tell which
# contacts they hold, so the user says. A contact that is not in it has no thermostat
# yet, and THERMOSTAT_NONE records that the user turned a suggestion down.
CONF_CONTACT_THERMOSTATS = "contact_thermostats"
# The contacts that watch a door, by device ID. A contact that is not in it watches a
# window, so the options hold only the exceptions.
CONF_CONTACT_TYPES = "contact_types"
CONF_FHT80B_STALE_HOURS = "fht80b_stale_hours"
CONF_FHT80TF_STALE_HOURS = "fht80tf_stale_hours"
# CONF_FIRST_PAIR and CONF_SECOND_PAIR are the fields in which the user enters the
# central code of the CUL as two numbers. They only exist in the forms, because the entry
# stores the code as CONF_HOUSE_CODE, the hexadecimal central code (FHTID in FHEM).
CONF_FIRST_PAIR = "first_pair"
CONF_HOUSE_CODE = "house_code"
CONF_IGNORED_DEVICES = "ignored_devices"
# Whether the integration reads the week programs of the thermostats on its own. The
# button of a thermostat works either way.
CONF_READ_WEEK_PROGRAMS = "read_week_programs"
CONF_SECOND_PAIR = "second_pair"

# The connection types of the device registry for the hexadecimal codes. The registry
# keeps them next to the identifiers, so a template can read the code of a device with
# device_attr(), and the two types keep the house code of the CUL apart from the code of
# a thermostat.
CONNECTION_DEVICE_CODE = "fht_device_code"
CONNECTION_HOUSE_CODE = "fht_house_code"

# What an FHT80 TF contact watches. The values are the names of the device classes of
# the binary sensor that shows the contact, and the options form offers them by these.
CONTACT_TYPE_DOOR = "door"
CONTACT_TYPE_WINDOW = "window"

# The device identifier of the CUL and the prefix of the unique IDs of its entities.
# Neither contains the config entry ID, so both survive adding the entry again.
CUL_IDENTIFIER = "cul"

# The model of the stick: the title of the config entry and the model of its device.
CUL_MODEL = "CUL868"

# The state of the CUL itself (T03, X and t) is polled, while FHT devices push their
# telegrams.
CUL_POLL_INTERVAL = timedelta(minutes=5)
CUL_UNREACHABLE_AFTER = timedelta(minutes=15)

DEFAULT_ADD_CARD = True
DEFAULT_FHT80B_STALE_HOURS = 2.0
DEFAULT_FHT80TF_STALE_HOURS = 4.0
DEFAULT_READ_WEEK_PROGRAMS = True

DOMAIN = "culfw"

# The Home Assistant bus event for a controller that stopped echoing the messages of this
# integration, with the device. Nothing automatic is sent to it until it echoes again.
EVENT_CHANNEL_BROKEN = f"{DOMAIN}_channel_broken"
# The Home Assistant bus event for a command that was requested and that the controller
# never took, with the device, the command, the requested value and the reason.
EVENT_COMMAND_EXPIRED = f"{DOMAIN}_command_expired"
# The Home Assistant bus event that is fired for every watchdog step.
EVENT_WATCHDOG = f"{DOMAIN}_watchdog"

# The free bytes in the FHT send buffer below which the issue is an error at once.
FHT_BUFFER_CRITICAL_BYTES = 0x20
# The free bytes below which the repair issue is a warning, after two polls in a row.
FHT_BUFFER_WARNING_BYTES = 0x80

# The longest time to the end of a holiday. The FHT80b stores the end as a day and a
# month, so a later end could not be told from one in the next days.
HOLIDAY_MAX_DAYS = 364

# How long the setup listens to the radio for devices, and how often the progress bar
# of that step moves. A thermostat sends about every 2 minutes and an idle window
# contact about every 4 minutes, so five minutes hear every device that is in range.
LISTEN_DURATION = timedelta(minutes=5)
LISTEN_TICK = timedelta(seconds=5)

# A stored port below this directory is a device node of this host. Anything else is a
# URL of a remote serial port (socket://, rfc2217:// or esphome://).
LOCAL_DEVICE_DIR = "/dev/"

# The number of raw lines that the diagnostics download keeps, and the longest part of a
# line that it keeps. A telegram has 13 characters at most, and a line that is longer is
# noise, which must not fill the memory with 200 lines of 64 KiB.
RAW_LINE_HISTORY = 200
RAW_LINE_MAX_LENGTH = 100

# The debounce for persisting the device state.
SAVE_DELAY_SECONDS = 60

# The section of the options form that holds the recovery options.
SECTION_RECOVERY = "recovery"

SERVICE_GET_SCHEDULE = "get_schedule"
SERVICE_SET_HOLIDAY = "set_holiday"
SERVICE_SET_SCHEDULE = "set_schedule"

# How often the availability is evaluated again against the time of the last telegram.
STALE_CHECK_INTERVAL = timedelta(minutes=1)

# The value of the thermostat select for a contact that belongs to no thermostat.
THERMOSTAT_NONE = "none"

# The prefix of the device nodes whose number depends on the order of enumeration, for
# example /dev/ttyACM0.
TTY_NODE_PREFIX = "/dev/tty"

# The fields of the action set_schedule, which are the weekdays counted from Monday.
WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def signal_command_update(entry_id: str, device_id: str) -> str:
    """Return the dispatcher signal for a request that was staged or sent to the CUL."""
    return f"{DOMAIN}_{entry_id}_command_{device_id}"


def signal_cul_update(entry_id: str) -> str:
    """Return the dispatcher signal for a change of the CUL connection or notices."""
    return f"{DOMAIN}_{entry_id}_cul_update"


def signal_device_removed(entry_id: str) -> str:
    """Return the dispatcher signal for a device that the user removed."""
    return f"{DOMAIN}_{entry_id}_device_removed"


def signal_device_update(entry_id: str, device_id: str) -> str:
    """Return the dispatcher signal for a telegram of a device."""
    return f"{DOMAIN}_{entry_id}_update_{device_id}"


def signal_new_device(entry_id: str) -> str:
    """Return the dispatcher signal for a device that was heard for the first time."""
    return f"{DOMAIN}_{entry_id}_new_device"


def signal_tick(entry_id: str) -> str:
    """Return the dispatcher signal to check the availability against the clock."""
    return f"{DOMAIN}_{entry_id}_tick"
