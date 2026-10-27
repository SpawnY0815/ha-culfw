"""Constants for the culfw protocol layer."""

from datetime import timedelta
from typing import Final

# The CDC-ACM serial port ignores the baud rate, and FHEM uses the same value.
DEFAULT_BAUDRATE: Final = 9600
DEFAULT_COMMAND_TIMEOUT_SECONDS: Final = 3.0
DEFAULT_OPEN_TIMEOUT_SECONDS: Final = 10.0
VERSION_ATTEMPTS: Final = 3
# A port that is open but dead raises no error on a read or a write, so a command that
# nobody answers is the only sign. One of them can be a line that got lost on the way,
# three in a row mean that the CUL does not listen any more.
PORT_LOST_AFTER_TIMEOUTS: Final = 3
# Report mode X21 reports all received messages and appends the RSSI.
REPORT_MODE: Final = 0x21

# The command `t` returns a 32-bit tick counter, which runs at this rate.
UPTIME_TICKS_PER_SECOND: Final = 125

# The week program has four switch times per day (from1, to1, from2, to2), the codes
# 0x14 (mon-from1) to 0x2F (sun-to2).
WEEK_PROGRAM_FIRST: Final = 0x14
WEEK_PROGRAM_LAST: Final = 0x2F
DAYS_PER_WEEK: Final = 7
# A read of the week program is complete when all of its times are known.
WEEK_PROGRAM_SIZE: Final = WEEK_PROGRAM_LAST - WEEK_PROGRAM_FIRST + 1
# A day has two periods, each from a start to an end. The controller regulates to the
# day temperature inside a period and to the night temperature outside.
WEEK_PROGRAM_PERIODS: Final = 2
MINUTES_PER_DAY: Final = 24 * 60

# The command codes that the transport may queue for an FHT80b: mode, holiday, desired
# temperature, date and time, report1 and report2, the day, night, low temperature
# offset and window open temperatures, and the week program. Actuator and protocol
# codes are never sent.
FHT_SEND_CODES: Final = frozenset(
    {
        0x3E,
        0x3F,
        0x40,
        0x41,
        0x60,
        0x61,
        0x62,
        0x63,
        0x64,
        0x65,
        0x66,
        0x82,
        0x84,
        0x85,
        0x8A,
    }
    | set(range(WEEK_PROGRAM_FIRST, WEEK_PROGRAM_LAST + 1))
)
# One message holds up to 8 commands.
FHT_MAX_COMMANDS: Final = 8
# An FHT80b house code has two parts from 1 to 99 (hex 01 to 63), set on the device.
# culfw routes a "T" line by its first byte: from 0x69 on it goes to the FHT80 TF
# emulation, and the code of the CUL itself with a first byte up to 7 above its own goes
# to the direct mode for FHT8v valves.
FHT_CODE_PART_MIN: Final = 0x01
FHT_CODE_PART_MAX: Final = 0x63
# The number of valves that the direct mode of culfw addresses.
FHT8V_SLOTS: Final = 8

# Temperatures count half degrees. The desired temperature "off" is 5.5 °C, which closes
# the valve, and "on" is 30.5 °C, which opens it fully. The settings (day, night and
# window open temperature) take everything from off to on, while a thermostat only
# asks for the temperatures between the two switches.
TEMP_STEP: Final = 0.5
TEMP_OFF: Final = 5.5
TEMP_ON: Final = 30.5
SETTING_TEMP_MIN: Final = TEMP_OFF
SETTING_TEMP_MAX: Final = TEMP_ON
CLIMATE_TEMP_MIN: Final = TEMP_OFF + TEMP_STEP
CLIMATE_TEMP_MAX: Final = TEMP_ON - TEMP_STEP
# The low temperature alarm offset is a whole number of degrees.
LOWTEMP_OFFSET_MIN: Final = 1
LOWTEMP_OFFSET_MAX: Final = 5

# The highest value of the date and time registers. The year counts from 2000 in two
# digits, and a day or a month starts at 1.
YEAR_MAX: Final = 99
MONTH_MAX: Final = 12
DAY_MAX: Final = 31
HOUR_MAX: Final = 23
MINUTE_MAX: Final = 59

# The answer to `T02` is only a serial exchange, but the dump grows with the queue, so
# the transport reads it at most this often, and only while a message may be in flight.
FHT_QUEUE_POLL_INTERVAL_SECONDS: Final = 30.0
# The format of the `T02` answer comes from the culfw source and has not been seen on
# hardware. Until the cutover verifies it, the dump serves diagnostics only and no
# decision about a command depends on it. Flip this once the format is verified.
USE_T02_GATE: Final = False

# The size of the FHT send buffer of the CUL868, which holds every message until the
# controller has collected it.
FHT_BUFFER_SIZE_BYTES: Final = 174

# Pause sending below 300 credit units, which is 3 seconds of the 9 second burst.
MIN_CREDIT_10MS: Final = 300
# A message that the integration sends on its own needs more, so that the account keeps
# MIN_CREDIT_10MS for a request of the user. The radio side of the largest message is 8
# commands plus 4 handshake packets of about 75 ms, and culfw repeats an unanswered
# packet once, which is 12 * 2 * 7.5 = 180 units. MIN_CREDIT_10MS plus that is 480,
# rounded up.
AUTOMATIC_MIN_CREDIT_10MS: Final = 500
# A message of the user waits for this much credit before it is dropped. The credit
# grows by one unit of 10 ms per second, so an empty account reaches the 300 units of
# MIN_CREDIT_10MS after 300 seconds, and the thermostat restart that was observed (a
# controller that synchronizes with its valves) keeps the credit near zero for much
# longer. 8 minutes are the 5 minutes of a complete refill plus 3 minutes for the
# traffic of the other thermostats, and they leave 7 of the 15 minutes of
# PENDING_TIMEOUT for the controller to collect the message, which takes two or three
# of its time slots.
CREDIT_WAIT_LIMIT: Final = timedelta(minutes=8)
# Keep the critical level of 32 bytes free for the time sync of the other controllers.
BUFFER_RESERVE_BYTES: Final = 32

# After a battery change, and when the user starts SYnC in its menu, an FHT80b counts
# down 120 seconds with its valves and sends an actuator telegram every second instead
# of every two minutes (status 0x2C, the value is twice the seconds that are left).
SYNC_SECONDS: Final = 120
# The countdown ends with a regulating actuator telegram a few seconds after the last
# counting one, and a telegram of the countdown can get lost.
SYNC_MARGIN: Final = timedelta(seconds=15)

# A controller that has been silent for longer than this gets no command, because it
# would not collect it and the message would stay in the buffer. The controller talks
# every 2 minutes, so this is about eight of its cycles, far more than the 3 percent of
# lost telegrams cost. The availability of its entities follows the longer threshold of
# the device model.
SEND_MAX_SILENCE: Final = timedelta(minutes=15)
# The outbox waits this long after the first command before it sends the message, so
# that commands which belong together travel in one message.
COALESCE_DELAY: Final = timedelta(seconds=3)
# The outbox sends the next message to a controller when the echo of the last command
# of the previous one arrived, or after this long. A message waits for the time slot of
# the controller, which comes about every 2 minutes, and the conversation takes seconds.
GATE_TIMEOUT: Final = timedelta(minutes=6)
# While a message is in flight the outbox looks this often at the free buffer, which is
# the way out when the echo got lost.
GATE_POLL_INTERVAL: Final = timedelta(seconds=30)
# The outbox tries again after this long when a message has to wait for credit, for room
# in the buffer or for the link.
DEFER_RETRY: Final = timedelta(seconds=10)
# A controller that did not echo this many messages in a row is not sent anything that
# the user did not ask for.
BREAKER_THRESHOLD: Final = 2

# A command that the FHT80b has not echoed after this long is shown as not applied. It
# waits for the time slot of the controller, which comes about every 2 minutes, and
# culfw repeats it. A day of the week program waits for the days before it, so its
# time counts from the sending, and it gets twice this long while it is staged.
PENDING_TIMEOUT: Final = timedelta(minutes=15)

# The settings of a controller (day, night and window open temperature, low temperature
# offset) change only at the device, so the integration asks for them once a day, and
# otherwise when it has a reason to doubt what it knows.
REFRESH_INTERVAL: Final = timedelta(hours=24)
# Automatic requests for the same controller are at least this far apart, whatever the
# reason, so that a controller that does not answer is not asked over and over.
REFRESH_MIN_GAP: Final = timedelta(minutes=30)

# The week program is read once a day as well (REFRESH_INTERVAL counted from the last
# complete read), but it costs a controller much more radio time than the settings: it
# answers in its time slots, so the first two days arrived after about 11 minutes and
# all seven after about 35 on a real thermostat. So the reads are kept apart.
#
# Nothing is asked this long after the integration (re)connected to the CUL, because the
# first minutes belong to the commands of the user and to the first contact reports.
WEEK_PROGRAM_AFTER_CONNECT: Final = timedelta(minutes=5)
# A read that was asked for counts as running for this long, or until it is complete.
# No other controller is asked meanwhile.
WEEK_PROGRAM_READ_WINDOW: Final = timedelta(hours=1)
# The least time between the starts of two reads, whichever controllers they are for.
WEEK_PROGRAM_START_GAP: Final = timedelta(minutes=10)
# A read that did not complete (a telegram got lost) is asked for again after this long.
WEEK_PROGRAM_RETRY_GAP: Final = timedelta(hours=6)
# The telegrams of one read are at most this far apart. Times that arrive further apart
# belong to different reads, so a few old ones never complete a new read.
WEEK_PROGRAM_BATCH_GAP: Final = timedelta(minutes=30)

# A T01 purge rewrites two EEPROM bytes and drops every queued command of every
# controller, so the watchdog does it at most this often within the window. A permanent
# EOB storm would otherwise wear the EEPROM and discard the commands over and over.
PURGE_CAP: Final = 6
PURGE_WINDOW: Final = timedelta(hours=24)

# Two estimates of the boot time of the CUL (the time of the reading minus its uptime)
# that differ by less than this belong to the same boot. The readings take a moment and
# the clock of the CUL runs a little off, so the estimates are never exactly equal.
BOOT_TOLERANCE: Final = timedelta(minutes=1)

# A thermostat reports its window flag within this long after one of its contacts sent
# the telegram that caused it. On the recording of two days the delays were 8 to 226
# seconds, and a longer window only adds contacts that are not the cause.
PAIRING_MAX_DELAY: Final = timedelta(minutes=5)
# A thermostat that has the contact answers its change of state with a telegram that is
# not on its schedule, a desired temperature or a warnings register. The live test took
# 1 second and 43 seconds. On the recording of two days 2 of the 12 answers of the pair
# came within 3 seconds, and no other pair was answered within 10 seconds, where chance
# gives 0.15 percent per event. The learner counts an answer within this time as quick.
PAIRING_QUICK_REACTION: Final = timedelta(seconds=3)
# A warnings telegram this close behind a measured temperature belongs to the burst of
# the schedule of the thermostat and says nothing about a contact (60 to 119 seconds
# in the recording).
PAIRING_BURST_WINDOW: Final = timedelta(seconds=125)
# A thermostat that sent a telegram within this long before a contact changed could
# have heard it, so its silence counts as evidence. A thermostat sends a telegram about
# every 2 minutes.
PAIRING_ALIVE: Final = timedelta(minutes=10)
# What a vote is worth in points. A quick answer is enough for a proposal alone, a
# change of the window flag within minutes is a weaker sign, and the silence of a
# thermostat that could have heard the change counts least, because a thermostat that
# is busy transmitting something else misses a change now and then.
PAIRING_QUICK_POINTS: Final = 6
PAIRING_SLOW_POINTS: Final = 2
PAIRING_SILENT_POINTS: Final = 1
# The points a thermostat needs for a proposal: one quick answer, or three changes of
# the window flag. On the recording, chance gave one flag change at most.
PAIRING_MIN_POINTS: Final = 5
# The points for a medium and for a high confidence in a proposal. Medium is one quick
# answer and one more sign, as in the live test. High is two quick answers, the opening
# and the closing of one window, or six changes of the window flag.
PAIRING_MEDIUM_POINTS: Final = 8
PAIRING_HIGH_POINTS: Final = 12
# The learner names a thermostat only when the points of all other thermostats are at
# most this fraction of its own.
PAIRING_RIVAL_SHARE: Final = 0.25
# The votes of a contact are halved when their points add up to more than this, so that
# a contact that was paired with another thermostat can overturn the old votes.
PAIRING_POINT_LIMIT: Final = 40
# The answers of the thermostats that are kept per contact for the diagnostics.
PAIRING_REACTION_LOG: Final = 10
