# Protocol notes and sources

This page records what the protocol layer in `custom_components/culfw/pyculfw/` knows about the ELV FHT radio protocol and the culfw firmware, and where each piece of that knowledge comes from. The code carries only the constraints that a reader needs next to the line. The file names and revisions of the sources live here, so that they have one place to be corrected and reviewed.

## Provenance and license

The protocol tables of the library are facts about a radio protocol: command codes, bit positions, thresholds and timings. They were derived by reading the sources listed below and were checked against live radio traffic. The rule is that only these facts, and no code of FHEM, culfw or node-cul, go into this repository.

The integration is licensed under the Apache License 2.0 (`LICENSE`). FHEM and culfw are published under the GNU General Public License, so the rule above is what keeps the two apart: the protocol constants are facts that any implementation of the protocol needs, they were checked against live radio traffic, and the code in this repository was written for this integration. A contributor who adds a table or a constant names its source here and does not copy code from the GPL projects. The license of node-cul and of the manuals was not confirmed, so they are cited as references only. This page lists the sources as file names and revisions on purpose, without line numbers, because line numbers change with every revision.

## Sources

The revisions, commits and tags below were checked against the upstream repositories on 2026-10-17.

FHEM, the home automation server that the integration replaces (Subversion trunk at svn.fhem.de, the revision is the last change of the file):

- `trunk/fhem/FHEM/11_FHT.pm`, revision 26173: the module for the FHT80b room controller.
- `trunk/fhem/FHEM/09_CUL_FHTTK.pm`, revision 18391: the module for the FHT80 TF window contact.
- `trunk/fhem/FHEM/00_CUL.pm`, revision 24815: the module for the CUL stick.

culfw, the firmware of the CUL, in two copies:

- Subversion trunk at sourceforge.net/p/culfw, repository revision 570: `trunk/culfw/clib/fht.c` (last changed in revision 570), `trunk/culfw/clib/rf_receive.c` (revision 570) and `trunk/culfw/clib/rf_send.c` (revision 557).
- The master branch of a-culfw (github.com/heliflieger/a-culfw), commit `f4305ea7ca9aba2ace6978c9c29e2645072e5c66` of 2019-08-03, which was the head of the branch when it was read on 2026-10-16: the same three files below `culfw/clib/` plus `culfw/clib/fht.h`, `culfw/clib/rf_receive.h`, `culfw/clib/rf_send.h`, `culfw/clib/fncollection.c`, `culfw/clib/clock.c` and `culfw/Devices/CUL/board.h`. For `fht.c` it has the same logic as the trunk apart from the support of several transceivers.

The roles of the files are: `fht.c` and `fht.h` for the FHT80b protocol, the send buffer, the emulation of the FHT80 TF and the direct mode for FHT8v valves. `rf_receive.c` for the report mode and the format of reported telegrams. `rf_send.c` for the duty cycle credit and the `LOVF` notice. `fncollection.c` for the write of the central code to the EEPROM. `clock.c` for the clock, and `board.h` for the size of the FHT send buffer. The command reference is at culfw.de/commandref.html. The stick in use reports `V 1.66 CUL868`.

node-cul 1.0.0 (github.com/hobbyquaker/cul, tag `v1.0.0`, commit `f916fecf340eb3d250f4a5a1818a86b01d6e6e71`), a JavaScript client for culfw:

- `lib/parse.js`: the RSSI of a reported line.
- `lib/fht.js` and `lib/fhttk.js`: the decoding of FHT80b and FHT80 TF telegrams.

Documentation:

- The FHEM wiki page for the FHT80b (wiki.fhem.de/wiki/FHT80b).
- The manuals of the devices from ELV: `62489_fht_80b.pdf` for the FHT 80B and `85836_fht8_tfsa.pdf` for the FHT80 TF window contact.

Wire evidence:

- A recording of the lines that FHEM read from the CUL at log level 5, from 2026-10-16 17:55:58 to 2026-10-18 18:14:00 (CEST), with the telegrams of 3 FHT80b room controllers and 8 FHT80 TF window contacts (the third room controller is heard from 2026-10-17 17:30 on). The first window of about four hours, with 2 FHT80b and 8 FHT80 TF, is the one that the tables below count. The test fixture `tests/fixtures/fhem_verbose5_2026-10-18.log` holds it, and `tests/fixtures/README.md` describes its time range, its gap and its counts.
- The event logs of FHEM for the same devices from 2023 to 2026. They are not part of the repository. They show which readings occur spontaneously and how often.

## Where each table comes from

Telegram layout:

- With report mode `X21`, culfw reports a received telegram as the letter `T`, the decoded bytes in hex without the checksum, and one byte with the RSSI (`rf_receive.c`). `00_CUL.pm` passes 5 of the bytes in front of the RSSI to `11_FHT.pm`, and `09_CUL_FHTTK.pm` reads 3 address bytes and 1 status byte, so an FHT80b telegram has 5 bytes before the RSSI byte and an FHT80 TF telegram has 4.
- The RSSI in dBm is the signed byte divided by two, minus 74, which is the offset of the CC1101 radio chip at 868 MHz. The sources are `00_CUL.pm` and `lib/parse.js` of node-cul. `tests/pyculfw/test_capture_parse.py` writes the same formula out and compares it with the parser for every telegram of the recording. It also compares the parser with the dBm value that FHEM logged for each telegram (the `CUL_Parse` rows), which is equal for all 15674 telegrams.

FHT80b room controller (`parser.py`):

- The table of command codes, including the week program readings from code 0x14 to 0x2f, is the code table of `11_FHT.pm`.
- The decoding of the value byte follows `11_FHT.pm`: temperatures in half degrees, the special values `on` and `off` of the desired temperature, the modes, the bits of the warnings, the whole degrees of the low temperature offset and the switch times in steps of 10 minutes.
- The meaning of the actuator telegram depends on the status byte, and the order of the cases is the one of `11_FHT.pm`.
- A status byte with the high nibble 7 marks a telegram of a central. `11_FHT.pm` stores these with the prefix `FHZ_`, and culfw drops them in report mode `X21` (`rf_receive.c`).
- The measured temperature is computed from the low and the high byte as in `11_FHT.pm`.

FHT80 TF window contact (`parser.py`):

- The status codes for open, closed, sync and test and the bit for a weak battery come from `09_CUL_FHTTK.pm`. The same codes appear in `lib/fhttk.js` of node-cul.
- The telegram of the contact is repeated with bit 7 of the status set. `09_CUL_FHTTK.pm` maps only the codes 81, 82, 91 and 92 back to the base code, while `lib/fhttk.js` masks the bit for every code. The parser follows node-cul.
- The nominal heartbeat of a contact is 240 + 16 - 2 * (the last 3 bits of its address) seconds. The source is the emulation of the contact in `fht.c`. The medians measured for the 8 contacts of the recording agree with it.
- No source documents a tamper or sabotage code. An unknown status code is kept as it is.

CUL commands and answers (`transport.py`, `const.py`):

- The commands `V`, `X`, `X21`, `T01`, `T02`, `T03` and `t` and the format of their answers are in the culfw command reference and in `00_CUL.pm`. The tick counter returned by `t` runs at 125 ticks per second, so the 32-bit counter wraps after about 397 days.
- `T02` prints the FHT send buffer (`fht80b_print()` in `fht.c`): `N/A` when it is empty, otherwise one token `HHHH:CCVV,CCVV` per queued message, separated by spaces. `T0200` prints only the thermostat codes. An entry disappears when its controller has acknowledged the message, and FHEM uses the dump to avoid queuing a message twice. The format is read from the source and has not been seen on a culfw 1.66 CUL. The transport reads it at most every 30 seconds and only while a message may be in flight, and `USE_T02_GATE` keeps the result out of every decision until the cutover has verified the format.
- The central code of the CUL (the house code of the CUL, `FHTID` in FHEM) is written to the EEPROM by `T01` followed by four hex digits, and the write clears all FHT send buffers (`fht.c`, `fncollection.c`). The init sequence of the transport writes it only when the stored code differs.
- The routing of a `T` line follows `fhtsend()` in `fht.c`. A first byte from 0x69 on goes to the emulation of the FHT80 TF. A code that has the second byte of the CUL's own central code and a first byte up to 7 above the CUL's own goes to the direct mode for FHT8v valves (`FHT_8V_NUM` in `fht.h`). Everything else is queued for an FHT80b.
- A message takes 3 + 2n bytes of the FHT send buffer, with n commands. This is the `fht_addbuf()` layout in `fht.c`. The buffer has 174 bytes on the CUL868 (`FHTBUF_SIZE` in `board.h`). A message that does not fit is dropped and culfw prints `EOB` (`fht.c`). When the 1 % duty cycle credit is not enough for a packet, culfw prints `LOVF` (`rf_send.c`).
- `11_FHT.pm` limits one message to 8 commands and the desired temperature to 5.5 to 30.5 °C.

How a command reaches an FHT80b (`outbox.py`, `devices.py`):

- A command is only queued in the send buffer of the CUL. culfw transmits it when the FHT80b reports in its own time slot, which comes every 115 + (the low byte of the security code of the thermostat & 7) / 2 seconds. One queued message per controller is sent per slot (`fht.c`). The recording confirms the period of 115 and 117 seconds for the two controllers.
- The controller confirms each command by repeating it with the value it stored. With report mode `X21` culfw hides the handshake packets, so these echoes are the only visible proof of delivery (`fht.c`, `rf_receive.c`).
- culfw replaces the minute of a time message by its own running minute when it finally sends the message, so a message that waited for a slot still carries the right minute (`fht.c`, `clock.c`).
- A queued message for a controller that never transmits again stays in the buffer until the buffer is cleared. This is why the outbox only queues for controllers that were heard recently.

Values of this integration that are policy and not protocol:

- The thresholds after which a controller (2 hours) or a contact (4 hours) counts as gone. They are chosen far above the periods above, because a missing telegram of a working device is normal and the dead devices in the logs of FHEM stayed silent for months.
- The minimum duty cycle credit and the reserve in the send buffer in `pyculfw/const.py`, and the 15 minutes after which a command that was not echoed is shown as not applied.
- The radio budget. culfw refills the duty cycle credit by one unit of 10 ms per second (1 percent) up to 900 units, and the integration sends a message only with at least 300 units (3 seconds). An empty account therefore needs 300 seconds to reach the minimum, and on 2026-10-19 the credit stayed between 0.7 and 3 seconds for about 25 minutes after the batteries of a thermostat were replaced (the likely cause is in "Restart of a thermostat and the radio budget" below). A request of the user does not fail for a lack of credit: it is staged as pending, the flusher asks again every 10 seconds, and the message goes out as soon as the credit is enough. The wait is bounded by `CREDIT_WAIT_LIMIT`, 8 minutes: the 5 minutes of a complete refill plus 3 minutes for the traffic of the other thermostats, which leaves 7 of the 15 minutes of the pending timeout for the controller to collect the message in two or three of its time slots. A message that finds the credit too low for that long in a row is dropped, its commands are reported as expired with the reason `credit_exhausted`, and the controller is read back. A request that the integration made on its own (the nightly time sync, the refresh planner) needs `AUTOMATIC_MIN_CREDIT_10MS`, 500 units (5 seconds), which is the 300 units of the user plus one message of 8 commands (12 packets of about 75 ms, each sent twice by culfw, 180 units), so the account keeps a reserve for the user. It is skipped while the credit is short and asked again by its own schedule. A time message that waited gets the local date, hour and minute of the moment the outbox queues it in the CUL (the minute is replaced by culfw again when the controller collects it), so a wait across the turn of an hour or a midnight does not set the clock wrong. Only the time between queuing and collecting, a few minutes at most, is not covered.
- The outbox sends a controller nothing when it has been silent for 15 minutes (about eight of its cycles), holds the commands of the first 3 seconds back so that they travel in one message, and sends the next message to a controller only after the echo of the last command of the previous one, after the buffer showed that the message left it, or after 6 minutes. Two messages in a row without any echo cut a controller off from everything the integration sends on its own.
- The pending model. A command that was accepted is pending until the controller echoes it, and the echo is the only proof that it arrived. It stays pending for at most 15 minutes, then it is reported as expired and the controller is read back. A day of the week program is one of seven messages that go one slot after the other, so its 15 minutes count from the moment its message is sent, and it has 30 minutes while it waits for its turn. It is also over when the stick was reset or its buffer was emptied, because the message is gone with it. The echo of a time command (code 0x60 to 0x64) is matched by the code alone, because culfw puts its own minute into the minute command. The daily time sync (04:05 local time) is an urgent message of its own with the minute last, sent through the outbox only to controllers that are not cut off, and the echo of the minute is the acknowledgement. The asynchronous delivery (up to about six minutes) and the 15 minutes are policy, and only the real stick can show how long the controllers need.
- The refresh planner (`refresh.py`) asks a controller for its mode, desired temperature and settings with report2 (mask 0x4F) on first contact, after a reset of the CUL, after commands were lost and every 24 hours, and for mode and desired temperature (mask 0x0A) after an echoed mode or holiday command of its own. It asks at most once per 30 minutes and one controller per cycle. The week program is read with report1 (mask 0xFF) by the same cycle, after the settings, and only when the option is on (see below). Which of these reports the controller answers, and how soon, is a property of the device that only the real stick can show.

## Timing, queue and acknowledgement in short

These are the rules the code is built on. The sections above name the sources.

- Slot timing: an FHT80b transmits its actuator telegram every 115 + (the low byte of the security code of the thermostat & 7) / 2 seconds, which is 115 to 118.5 seconds. It listens only right after that telegram, so a command can only be delivered in that window. An FHT80 TF transmits about every 4 minutes (240 + 16 - 2 * the last 3 bits of its address, in seconds) and on a change.
- Queue semantics: the CUL keeps the commands in the FHT send buffer (174 bytes on the CUL868, 3 + 2n bytes per message with n commands) and sends one message per controller in each time slot. A message that does not fit is dropped (`EOB`). The 1 percent duty cycle is a credit that culfw counts in units of 10 ms, and `LOVF` says that a packet was held back. A queued message stays in the buffer until its controller collects it or the buffer is cleared.
- Echo acknowledgement: the controller repeats every command it took with the value it stored, in a telegram of its own. With report mode `X21` this echo is the only visible proof of delivery. The codes of the time (`year` to `minute`) are matched by code only, because culfw writes its own running minute into the message when it sends it. A value that differs from the requested one means that the controller clamped it or that someone turned the dial, and the device value wins.
- Report requests: `report1` asks for the week program and `report2` for the settings. They are commands like any other, and the controller answers with the readings in its following slots. The value of `report1` is a bit mask of the weekdays (Monday 0x01, Tuesday 0x02, Wednesday 0x04, Thursday 0x08, Friday 0x10, Saturday 0x20, Sunday 0x40, all 0x7F), and 0xFF asks for everything. The value of `report2` is a bit mask of the settings: warnings 0x01, mode 0x02, day, night and window open temperature 0x04, desired temperature 0x08 and low temperature offset 0x40, all together 0x4F. The bits 0x10 and 0x20 are undefined. The integration asks for 0x4F on first contact, after a reset, after lost commands and once a day, and for 0x0A (mode and desired temperature) after its own mode or holiday command. It asks for the week program (0xFF) once after the first contact of a confirmed controller whose settings are known, after a reset of the CUL or a rewrite of its central code, and 24 hours after the last complete read.
- The automatic read of the week program. On 2026-10-18 a real thermostat answered a report1 request for all days in its time slots: the first two days after about 11 minutes and all seven (28 times) after about 35 minutes. So the planner keeps the reads apart. It starts a read only when the option is on, the controller is confirmed, its settings are known, it was heard within 15 minutes, the outbox has not cut it off and holds no message for it, no report request is staged or in the CUL, no read of any controller is running (until it is complete, or for one hour after the request, or while times that someone asked for arrive), the last start was 10 minutes ago and the connect of the CUL was 5 minutes ago. A read that stays incomplete is asked for again after 6 hours. A read is complete when 28 different switch times arrived at most 30 minutes apart (a time that arrives twice is counted once, so a repeated telegram does not spoil the read), and `week_program_read_at` of the controller, which the store keeps, is the time of the last one; an unknown time counts as due. The report1 is the last message in the queue of a controller, so the commands of the user go first, and the outbox sends it automatically only to a confirmed controller (the probe that an unknown controller gets is a report2).

## Restart of a thermostat and the radio budget

On 2026-10-19 the batteries of the thermostat 460F were replaced on the test instance. The duty cycle credit of the CUL, normally about 9 seconds, fell to 0.7 to 3 seconds within a few minutes and stayed low for about 25 minutes. This section separates what the data shows from what is hypothesis.

Evidence:

- The telegrams of 460F in that time, for example `T460F002C5FFB`, `T460F002C5DFC`, `T460F002C5BFA`, are actuator telegrams (command 0x00) with the status byte 0x2C. The low nibble 0xC is the countdown of the synchronization (`synctime` in `11_FHT.pm`), and the value byte is twice the seconds that are left plus 3: `5F` is 46 seconds, `5D` is 45, `5B` is 44. The manual (chapter 4.1) says that a thermostat asks the central for the date and time after the batteries went in, and that it then synchronizes with its valves for about 2 minutes ("SYnC Auto"). Chapter 3.9.6 describes the same countdown from 120 to 0 in steps of 1 second for the menu entry SYnC.
- The recording has the same sequence for 3f48 (first heard on 2026-10-17 at 17:30:11 after a battery change): one telegram for the first valve (command 0x01, status 0x2F, the pair state), then 115 actuator telegrams with the status 0x2C, one per second from 17:30:12 to 17:32:10 (a few are missing, the radio loses telegrams), whose values count from 0xEF (118 seconds) down to 0x03 (0 seconds) in steps of 2, and the first telegram with the status 0x26 (a valve position) at 17:32:14. After that the thermostat is back to its normal pace of one actuator telegram every 115 to 118 seconds. No other thermostat in the recording has the status 0x2C. `tests/pyculfw/test_devices.py` replays the whole recording and finds the countdown of 3f48 and nothing else.
- So during the synchronization a thermostat sends about 60 times more telegrams than usual, for about 2 minutes. That is a fact.
- The diagnostics download of 460F of 2026-10-20 (the owner's file, not part of this repository) was taken after the restart. Its raw lines (about 28 minutes from 06:26 UTC) show the thermostat at its normal pace of one actuator telegram every 118 seconds with the status 0xA6, and the counter `lovf` is 72: the stick printed `LOVF` 72 times since the integration started. The file has no sample of the credit, and the telegrams of the countdown themselves are not in it, because it keeps only the last 20 lines. The channel of 460F shows one probe (the first contact report2), trusted, not broken. The dump of the buffer of 04:07 local time holds the time message of 3924 only.
- The integration spends no credit by itself when it queues a message: `T` lines, `T02` and `T03` are answered by the stick without radio. A message costs credit when culfw sends it, in the time slot of the thermostat, as 4 + n packets for n commands (can xmit, start xmit, one packet per command, ack, end xmit), each about 75 ms (a comment in `fht.c`), and an unanswered packet is sent once more. So a report2 costs about 5 packets, a time message 9, a day of the week program 8. These are ordinary costs, a fraction of a second in each slot. The stick also acknowledges the telegrams of a thermostat with the status 0x69 (the measured temperature and the warnings, three telegrams every 10 to 20 minutes), which is a small constant cost of every thermostat.

Hypothesis (from reading `fht_hook()` in `fht.c`, not measured):

- For every telegram of a thermostat that has a message waiting in the buffer, culfw answers the actuator telegram with a packet (can xmit), expects the thermostat to answer it, and starts over when it does not. In the normal slot the thermostat answers and the message goes through. A thermostat that counts down its synchronization does not take part, but it sends an actuator telegram every second, so culfw would answer about every second one of them, and each answer is sent twice. That is about 60 answers and 120 packets in the countdown, about 8 units of 10 ms each, which is 960 units against a full account of 900. The simulator models exactly this (`FhtSim.start_sync()`), and its account ends below one second after a countdown with a message in the buffer, which is what the observation shows (0.7 to 3 seconds).
- The hypothesis needs a message in the buffer of the thermostat while it counts down. The observation notes of the test instance name one: the integration queued a first contact report2 as a probe (echoed at 21:52:41), and a report1 (`T460F65FF`) stayed in the buffer of the CUL. The notes do not say how these events were ordered in time relative to the countdown, so the hypothesis is not confirmed by them.
- The hypothesis does not explain why the credit stayed low for 25 minutes, because the countdown is over after 2 minutes and the account needs about 14 minutes to refill from 0.7 seconds. Something kept spending at about the refill rate. A thermostat that repeated the synchronization, another thermostat, or the messages of the integration itself could be the cause. The data of the test instance does not say, and the credit recovered after the time sync at 22:14 delivered the waiting message, which fits a message in the buffer that is answered again and again, but proves nothing.

What the integration does about it:

- It recognizes the countdown (`FhtRoomController.note_actuator()`): the first valve announced with the status 0x2F, and the status 0x2C with the seconds that are left. The controller counts as synchronizing until that time plus 15 seconds (`SYNC_MARGIN`), or until the first actuator telegram that regulates the valve, and 120 + 15 seconds after the announcement. The state is not stored.
- The outbox does not queue any message of its own (the time sync, the refresh planner) for a thermostat that synchronizes. A request of the user is not held, because the link between the countdown and the credit is a hypothesis, and this precaution is the one behavior that goes beyond the credit reserve and the counters. The message stays staged (the entities show it as requested) and goes out within `DEFER_RETRY` of the end of the countdown. Nothing is dropped by this wait: the silence limit of 15 minutes still applies, and the countdown ends by itself after about 2 minutes. A message that is already in the buffer when the countdown starts cannot be taken back, because `T01` clears the buffers of all thermostats.
- A report1 is never queued together with the first report2: the planner asks for the week program only of a controller that is confirmed, whose settings are known and that has no message staged or in the CUL, and not while any report request is on its way.
- The planner and the time sync need 500 units of credit for their own requests, so a thermostat that has just spent the account is not given more work, and the user keeps the 300 units of the account for the commands.
- The outbox keeps the credit around the last 20 messages (`FhtOutbox.send_log`): the credit that the CUL reported when the message was queued, and the one it reported when the message was over, together with the seconds in flight, whether the controller was synchronizing then, and an estimate of what the radio spent (the credit before plus one unit per second in flight minus the credit after). The diagnostics show it under `outbox.send_log`, the number of messages that waited for a countdown under `counters.held_for_sync`, and `synchronizing` for every thermostat. The next restart of a thermostat answers the open points with this data: how much credit the countdown costs with a message in the buffer and without one, and what keeps it low afterwards.

## Central code and security code

Two codes are easy to mix up. The central code belongs to the CUL and the security code belongs to each thermostat.

- The security code (`CodE`, chapters 1.3 and 3.9.4 of the manual of the FHT80b) is the individual code of a thermostat. The display shows the two parts one after the other as `Code 1` and `Code 2`, each with three digits from 000 to 099. They are one byte each on the radio, so the thermostat with the security code 063 072 has the device code `3F48`. Every telegram of a thermostat carries this code as its address (in the capture of the FHEM installation the first two bytes of the telegrams are the codes `5D10` and `3924` of the live thermostats), and the integration addresses a command to a thermostat by it (`T3F48...`). The integration shows it in the device name, in the serial number and in the attribute `display_code`. The manual says that the thermostat and its valve actuators need the same security code, so a changed security code has to be transmitted to the actuators again.
- The central code is the code of the CUL, `FHTID` in FHEM, and this integration also calls it the house code (`CONF_HOUSE_CODE`, the attributes `house_code` and `house_code_display`). `T01` followed by four hex digits writes it to the EEPROM of the CUL (`fncollection.c`). The thermostats register with a central, and chapter 3.9.9 of the manual (`CEnt`) describes three states: `On` for registered with the central, `Off` for no radio communication, and `nA` for released for registration at a central. A thermostat registers with one central only, so a thermostat that is registered with another central has to be released with `nA` first. The thermostat does not show the code of its central, only the `CEnt` state. The capture holds no telegram that has the central code of the CUL as its address.
- The setup asks for the central code as two numbers from 1 to 99, which `codes.py` converts to the two hex bytes. The range follows `FHT_CODE_PART_MIN` and `FHT_CODE_PART_MAX`: the transport refuses a part of 0 as a central code, while the security code of a thermostat can be 0 to 99. The conversion is the same for both codes, so the setup shows the hex form next to the numbers, and a user who knows FHEM finds the value of `FHTID`.

## Command code table

The codes of the FHT80b as `pyculfw/parser.py` knows them. The reading is the name that FHEM uses in `11_FHT.pm` (revision 26173). The codes 0x14 to 0x2F are the 28 switch times of the week program (`mon-from1` to `sun-to2`, four per day), and the integration sends all of them. The column on the right says whether the code is in `FHT_SEND_CODES` of the transport, the only codes that can leave the CUL.

| Code | Reading | Sent by the integration |
| --- | --- | --- |
| 0x00 | `actuator` | no |
| 0x01 | `actuator1` | no |
| 0x02 | `actuator2` | no |
| 0x03 | `actuator3` | no |
| 0x04 | `actuator4` | no |
| 0x05 | `actuator5` | no |
| 0x06 | `actuator6` | no |
| 0x07 | `actuator7` | no |
| 0x08 | `actuator8` | no |
| 0x3E | `mode` | yes |
| 0x3F | `holiday1` | yes |
| 0x40 | `holiday2` | yes |
| 0x41 | `desired-temp` | yes |
| 0x42 | `measured-low` | no |
| 0x43 | `measured-high` | no |
| 0x44 | `warnings` | no |
| 0x45 | `manu-temp` | no |
| 0x4B | `ack` | no |
| 0x53 | `can-xmit` | no |
| 0x54 | `can-rcv` | no |
| 0x60 | `year` | yes |
| 0x61 | `month` | yes |
| 0x62 | `day` | yes |
| 0x63 | `hour` | yes |
| 0x64 | `minute` | yes |
| 0x65 | `report1` | yes |
| 0x66 | `report2` | yes |
| 0x69 | `ack2` | no |
| 0x7D | `start-xmit` | no |
| 0x7E | `end-xmit` | no |
| 0x82 | `day-temp` | yes |
| 0x84 | `night-temp` | yes |
| 0x85 | `lowtemp-offset` | yes |
| 0x8A | `windowopen-temp` | yes |

`tests/pyculfw/test_protocol_doc.py` checks that this table lists every code of `FhtCode` and the same set of codes that the transport may send.

## Which contact belongs to which thermostat

The manual of the FHT80b (chapter 3.9.10, special function `FEn`) says that a thermostat stores up to 4 window contacts in the slots 1 to 4 and shows only the state of each slot on its display, never the code of a contact. So the pairing cannot be read from the thermostat, and nothing in the radio traffic names it. The warnings of a thermostat hold a window flag (bit 0x20, the aggregate of its contacts: it is up while at least one of them is open), which the thermostat sets some time after a contact sent its telegram. The data of the recording shows whether that is enough to tell the pairing.

The script `scripts/analyze_window_pairing.py` (tested by `tests/test_analyze_window_pairing.py`) reads a capture, takes every change of the state of a contact (the first state of a device is the baseline) and every change of the window flag in the warnings of a thermostat, and looks for the contacts that changed to the same state not more than 5 minutes before the flag changed. It then replays the events through the learner of the integration (`pyculfw/pairing.py`) and shifts the flag changes against the contact events to count what coincidence gives. The result for `tests/fixtures/fhem_verbose5_2026-10-18.log` (48 hours, 8 contacts, 3 thermostats):

- Contact events: 16 changes of state, 12 of them of `d7a3d8` (6 openings and 6 closings), 2 of `783646`, 2 of `060d98`. The other 5 contacts never changed their state during the recording.
- Flag changes: 12, all of the thermostat `5d10`. The thermostats `3924` and `3f48` never raised the flag.
- Every flag change has a contact event in front of it. For 11 of the 12 exactly one contact (`d7a3d8`) fits, and the 12th is ambiguous: `d7a3d8` closed 1 second before and `783646` closed about 2.5 minutes before, both within the window. Ambiguity is rare here, but it exists, and two contacts that open at once give the same picture.
- The delay from the contact to the flag is 8 to 226 seconds, median 100 seconds, for the 11 clear cases. So "a few minutes" is right. A window of 4 minutes is the shortest that holds all of them (2 minutes loses 2 of the 11), and the integration uses 5 minutes, which leaves a margin of about one third. A longer window finds nothing more, and it lets chance vote: by the chance test below the best pair got 1 vote at 5 minutes, 2 at 10 and 15 minutes, 3 at 30 minutes and 5 at 60 minutes.
- Score (votes of a contact for a thermostat): `d7a3d8` for `5d10` 11, every other pair 0. An opening of `d7a3d8` while the flag of `3924` was down was never followed by a flag change of `3924` (6 times), and the same for `3f48` (3 times). The single openings of `060d98` and `783646` also left the flag of `3924` down, and the flag of `5d10` was already up at those moments, so they say nothing about `5d10`.
- Chance: moving the flag changes by whole multiples of 10 minutes against the contact events (278 runs) gave at most one vote for any pair, in 41 runs, and none in the others. The learner needs 3.
- Replayed through the learner, `d7a3d8` is proposed for `5d10` with the third consistent vote, at 2026-10-17 11:16:45, about 17 hours after the start of the recording and after the third opening or closing of the contact.

What the data supports, and what it does not:

- A flag change that exactly one contact precedes is a reliable sign, and the delays are consistent, so learning is reliable for a contact that opens and closes, and it is conservative by design: only a clear flag change counts, and the proposal needs 3 votes without a rival.
- It can assign only what the flag shows. The flag changes when the first contact of a thermostat opens and when the last one closes, so an opening while another contact of the same thermostat is already open shows nothing, and neither does a short opening that is over before the thermostat reports. In the recording 1 of 8 contacts (12.5 percent) can be assigned with confidence, and that is a statement about the house and not about the method: 5 contacts never changed their state, and the 2 others changed twice each while the only thermostat that reacts at all had its flag up. The contact of a room that is never opened is never assigned by the radio.
- A contact that two thermostats follow collects votes for both and gets no proposal. A thermostat that does not tell on the radio (the three dead thermostats of the house, or one that is out of range) cannot be assigned either.
- The analysis cannot show that the pairing is right in the sense of the owner. It shows that the flag of `5d10` follows `d7a3d8` and no other contact. The owner has to confirm that the two are in the same room, which is why the integration only proposes, and the user decides.

The decision for the first version of the learner, which the section "The learner with both signals" below extends: the learner is built in `pyculfw/pairing.py`. It proposes a thermostat for a contact when at least 3 flag changes of that thermostat were explained by exactly that contact, within 5 minutes after its change of state, and the votes of all other thermostats are at most a quarter of its own. It halves the votes of a contact when they add up to more than 20, so a contact that moved to another thermostat can win its proposal back. The proposal is the attribute `thermostat_source: suggested` of the contact and the default of its select in the options, and it never replaces an assignment of the user, including the choice not assigned. The votes are stored with the devices.

### The answer of a thermostat within seconds

The window flag shows a minute or more after a contact changed, so the first analysis needs a window of 5 minutes. A second signal is much tighter. A thermostat that has a contact answers its change of state with a telegram that no unpaired thermostat sends at that moment: the desired temperature (code 0x41), the warnings (code 0x44), or both.

**Live test of the owner (evidence).** On 2026-10-20 the owner paired the contact `c45fa5` with the office thermostat `3F48` (display 063 072) on the test instance and recorded two rounds. The second round was clean, after the thermostat had synchronized with the new contact. Its telegrams are the fixture `tests/fixtures/live_test_of_the_owner_2026-10-20.capture`:

| Time (UTC) | Telegram | Reading |
| --- | --- | --- |
| 11:33:31 | `TC45FA50119` | `c45fa5` opened |
| 11:33:32 | `T3F4841691802` | `3F48`: desired temperature 12.0 degrees, status 0x69 |
| 11:33:32 | `T3F4844692002` | `3F48`: warnings 0x20, the window flag |
| 11:41:43 | `TC45FA50215` | `c45fa5` closed |
| 11:42:26 | `T3F4841692AFA` | `3F48`: desired temperature 21.0 degrees, 43 seconds later |
| 11:42:27 | `T3F48446900FA` | `3F48`: warnings 0, the flag cleared |

The first round, right after the pairing and before the thermostat had synchronized, is known by its times only: the thermostat answered the opening after 1 second as well (desired temperature 12.0 at 12:51:30 local time) but the flag did not show, and the restore after the closing took about 3.5 minutes. The contact repeats its state about every 4 minutes (its closed telegrams at 10:44:19 and 10:48:25 are 246 seconds apart). The fixture holds no regular telegrams of the thermostats, so the tests add made-up ones, which `regular_traffic()` of `tests/test_analyze_window_pairing.py` says.

**How the script finds an answer.** `scripts/analyze_window_pairing.py` lists, for every change of state of a contact, the telegrams of every thermostat that follow it and that the regular schedule of the thermostat does not explain. A telegram is regular when it is an actuator telegram (codes 0x00 to 0x08, about every 2 minutes), a measured temperature (0x42, 0x43), or a warnings telegram that comes not more than 125 seconds after a measured temperature. That last rule covers the burst of measured temperature and warnings, and the repeat of the warnings with the next actuator telegram, which came 60 to 119 seconds later in the recording. The cost of the rule is that a warnings telegram of an answer can hide in that window, so the desired temperature is the surer sign. A thermostat counts from its first telegram, a telegram has to come after the contact telegram in the capture (the order decides within one second), and the first state of a device is a baseline and no event. The answer window is 10 seconds, 3 seconds count as quick, and the delays are listed up to 5 minutes. An answer is clear when no other contact changed within the 10 seconds in front of any of its telegrams. The chance is the share of the time since a thermostat was first heard that is covered by the 10 seconds in front of its off-schedule telegrams, which is the chance that an event at a random time meets one.

**The recording of the house** (`tests/fixtures/fhem_verbose5_2026-10-18.log`, 16 contact events, 3 thermostats). The three thermostats sent 35 (`5d10`), 14 (`3f48`) and 8 (`3924`) off-schedule telegrams in 48 hours, and 30, 14 and 8 of them have no contact event in the 10 seconds in front. Of the 25 desired temperatures in the recording, 10 sit at the same times on all three thermostats (around 06:00 and 23:00, 21.0 and 17.0 degrees), which looks like the switch times of the week program. The chance that an event meets such a telegram within 10 seconds is 0.15 percent for `5d10` and `3f48` and 0.05 percent for `3924`.

Answers within 10 seconds, with the number of events that the thermostat could hear (it was first heard before them) and, in brackets, the answers within 3 seconds:

| Contact | `3924` | `3f48` | `5d10` |
| --- | --- | --- | --- |
| `d7a3d8` (12 events) | 0 of 12 | 0 of 7 | 3 of 12 (2) |
| `060d98` (2 events) | 0 of 2 | not heard yet | 0 of 2 |
| `783646` (2 events) | 0 of 2 | not heard yet | 0 of 2 |

The other 5 contacts never changed their state. `3f48` is first heard on 2026-10-17 at 17:30, so it heard 7 of the 12 events of `d7a3d8`. Of the 27 pairs other than `d7a3d8` and `5d10`, none was answered within 10 seconds, and chance predicts 0.02. For the pair itself chance predicts 0.02 answers in 12 events, and 3 came.

The delay of the first off-schedule telegram of `5d10` after the 12 events of `d7a3d8`, up to 5 minutes: 0 and 1 seconds (2 events), 7 (1), 11, 38, 50 and 56 (4), 103, 103, 104, 150 and 225 (5). Every event was answered, so the window of 10 seconds catches a quarter of them, 60 seconds catches 7 of 12 and 5 minutes all 12. The content is the same every time: each of the 6 openings was followed by a desired temperature of 12.0 degrees, and each of the 6 closings by 21.0 degrees. In 10 of the 12 events a warnings telegram followed the desired temperature within a second (in one of them inside a measurement burst), with the flag set after an opening and cleared after a closing. In 10 of the 12 events the first answer came in the second of an actuator telegram of `5d10`, and the two that did not are the quickest ones (0 and 1 seconds). The spread is 0 to 225 seconds where the live test of `3F48` gave 1 and 43 seconds.

A longer window adds no sure pair and lets chance in: at 5 minutes `3924` stays at 0, `3f48` gets one answer to `d7a3d8` (216 seconds, 1 of 7, where chance predicts 0.3), `5d10` answers one closing of `783646` after 147 seconds, which is the answer to the closing of `d7a3d8` 2.5 minutes later, so that answer is ambiguous. The chance for an event to meet an off-schedule telegram within 5 minutes is 4.1 percent for `5d10`, 4.5 percent for `3f48` and 1.4 percent for `3924`.

**Ambiguity.** Two contacts changed within 10 seconds of each other never in the recording: the shortest gap between events of two different contacts is 147 seconds. The 10-second window therefore has no ambiguous answer, and the 5-minute window has one (the one above). A house in which two rooms are aired together would give ambiguous answers within 10 seconds too, and the script leaves them out, as the flag analysis does.

**What the recording says about the pairing.**

| Device | Said by the recording |
| --- | --- |
| `d7a3d8` | `5d10` answered all 12 changes (3 within 10 seconds). `3924` and `3f48` answered none within 10 seconds. So it goes with `5d10` as far as the radio tells |
| `060d98` | 2 events, no answer from `3924`, which speaks against that pair. `5d10` had its flag up (`d7a3d8` was open), so no statement for it. `3f48` was not heard yet |
| `783646` | The same as `060d98`, with one more reason for no statement: the 147 seconds answer of `5d10` belongs to `d7a3d8` |
| `3a0548`, `4c02fb`, `895c97`, `d1fb33` | Never changed, nothing to say |
| `c45fa5` | Never changed in the recording. The live test says `3F48` |
| `5d10` | Answers `d7a3d8` |
| `3924` | Answered none of the 16 events, which are 12 of `d7a3d8` and 4 of the others |
| `3f48` | Heard 7 events of `d7a3d8` and answered none. Its own contact is `c45fa5` by the live test, two days after the recording |

The recording has 3 of the 5 known thermostats. `460F` (heard since 2026-10-19) is not in it, and `4440` has never been received.

**Evidence and hypothesis.** Evidence, measured:

- The thermostat `3F48` answered the opening of `c45fa5` with the desired temperature and the warnings after 1 second, and the closing after 43 seconds, in the one clean round of the owner. The first round is the owner's report without telegrams.
- `5d10` answered each of the 12 changes of `d7a3d8` within 225 seconds with the desired temperature that fits the direction, and 3 of them within 10 seconds, while the chance for that is 0.15 percent per event.
- No thermostat answered any other contact within 10 seconds, and no answer was ambiguous within 10 seconds.
- 12 of the 25 telegrams with code 0x41 in the recording are answers of `5d10` to a contact, so they are no echoes of commands of FHEM, as the README of the fixtures called them before.

Hypothesis, not shown:

- A paired thermostat answers quickly in general. It is shown for `3F48` in one round and for `5d10` in 3 of 12 events, and the other 9 of `5d10` took 11 to 225 seconds.
- The slow answers wait for the next transmit slot of the thermostat, because 10 of 12 first answers share their second with an actuator telegram. The cause is not known, and the repeat of the contact telegram 64 seconds later, which 5 of the 12 events show, does not line up with the answers.
- A thermostat that has not synchronized with its contact answers late and shows no flag, as the first round suggests.
- 12.0 degrees is the window open temperature of the thermostat (register `windowopen-temp`) and 21.0 degrees is the temperature before the opening. The recording is consistent, and the registers of the thermostats were not read for it.
- A thermostat whose flag is already up does not answer the opening of a second contact. The silence of `5d10` for `060d98` and `783646` fits, and so does a wrong pairing.
- A tight window alone is slower than the flag in this house: the third answer within 10 seconds came on 2026-10-18 at 11:56:41, where the learner of `pyculfw/pairing.py` proposed `d7a3d8` on 2026-10-17 at 11:16:45. The signal is much more specific, and it works for the events that do not change the flag.

### The learner with both signals

The learner of `pyculfw/pairing.py` uses the answer within seconds as its main signal and keeps the window flag as the weaker one. Every telegram of a thermostat goes through it (`note_telegram()`), every change of the window flag (`note_thermostat()`) and every change of the state of a contact (`note_contact()`). The repeats of a contact (the live test shows its state every 4 minutes) are no changes and never reach it.

**What counts.**

| Observation | Votes | Points |
| --- | --- | --- |
| A desired temperature or a warnings telegram off the schedule of a thermostat, or a change of its window flag, within 3 seconds after a change of exactly one contact, when no other contact changed within 3 seconds of it and no other contact changed unanswered within the 5 minutes before | quick answer for the pair | 6 |
| A change of the window flag within 5 minutes after a change of exactly one contact to the same state (the first version of the learner), or a quick answer that an unanswered change of another contact within the 5 minutes before could have caused as well | slow vote for the pair | 2 |
| A thermostat that transmitted within 10 minutes before the change could have heard it, and stayed silent in the 3 seconds, while another thermostat gave a quick answer | silent vote against the pair | -1 |

The schedule of a thermostat is the actuator telegrams, the measured temperature and the warnings telegram within 125 seconds after a measured temperature, as in the script. A thermostat is named for a contact when it has at least 5 points and the points of all other thermostats add up to at most a quarter of its own. So one clean change that exactly one thermostat answered quickly is enough for a proposal (6 points), and three changes of the flag are enough when no thermostat answers quickly (3 times 2 points). Further changes confirm the proposal: they add points to the pair and silence to the others, and a rival that answers as well takes the proposal back. The points of a contact are halved when the positive ones add up to more than 40, so a contact that moved to another thermostat can win again.

Why these numbers: the evidence behind the quick answer is that no other pair was answered within 10 seconds in the 16 events of the recording, where chance gives 0.15 percent per event, and that `3F48` answered `c45fa5` after 1 second. That justifies a proposal from one event, and the points make it exactly as strong as the three flag votes that the first version asked for. The silent vote counts one point because a thermostat that is busy with its own transmission misses a change now and then, and it costs a pair less than a quick answer gives, so one miss followed by one answer still reaches the 5 points. Silence is counted only when another thermostat answered, because without an answer nobody can tell the thermostat that has the contact from the ones that do not, and a contact that nobody answers (an unpaired one, or a pair that is out of range) would otherwise punish every thermostat. The silent vote is taken back when the same thermostat answers later within 5 minutes, because the slow answers of `5d10` took 11 to 225 seconds: a quick window alone would have counted its silence against the pair it belongs to.

**Order and timing.** The quick votes are cast when the quick window of the change has closed, with the first call after it, whichever device it concerns, so the proposal does not flicker when a second thermostat answers a moment later. The learner never waits, it works on the times it is given. Contacts that changed within 3 seconds of each other are ambiguous for the quick signal and give no votes. An answer that comes after the quick window and is not a change of the flag is logged but gets no vote, because the chance for an unrelated desired temperature in 5 minutes is 4 percent per event (see above); it only takes back a silent vote. The flag rule is unchanged for changes later than 3 seconds.

**Crowded answers.** A quick answer is attributed to the contact that changed in the 3 seconds before it. In the recording 9 of the 12 answers of the true pair came 11 to 225 seconds late, so an answer that falls within 3 seconds after a contact can also be the late answer to an earlier contact, for example when two rooms are aired in a row. When another contact changed within the 5 minutes before (to the same state, for a change of the flag) and none of the other thermostats answered that change, the answer counts as a slow vote of 2 points, not as a quick answer of 6, and it takes no silent votes along. One such answer is no proposal, and a pair needs three of them. When another thermostat did answer the earlier contact, that change is explained and the answer stays a quick one, so airing two rooms in a row, each answered quickly, gives both a proposal. This is a deliberate trade: a quick thermostat that follows a slow one is rated lower, in exchange for no proposal from a single coincidence of a late answer.

**Confidence and events.** The user sees why a thermostat is suggested. The confidence follows the points of the proposed thermostat: low below 8 points (one quick answer, or three changes of the flag), medium from 8 (a quick answer and one more sign, as in the live test) and high from 12 (two quick answers, or six changes of the flag). Another thermostat with points of its own lowers it by one level, down to low. The events are the quick and the slow votes of the pair, so a change of the contact counts once, however many signs it left, and a change that two contacts could have caused counts for nobody. These numbers are a presentation of the votes and add no evidence: they are the attributes `thermostat_confidence` and `thermostat_events` of the contact, the words in the label of the suggestion in the options, and `confidence` and `events` under `window_pairing` in the diagnostics. The learner reports a contact as changed when its proposal or this evidence changes, so the attributes are not stale until the next telegram of the contact.

**Diagnostics.** For each contact the learner keeps the last 10 answers: thermostat, the time of the change, the delay in seconds, the direction and whether the change was ambiguous. They are stored with the votes and shown under `window_pairing` in the diagnostics, next to the votes and points per thermostat and the current proposal. The version marker of the stored votes is 2. A store without a marker holds the changes of the window flag per pair, which load as slow votes, and a marker the code does not know is left alone.

**Result on the live test of the owner** (replay of `tests/fixtures/live_test_of_the_owner_2026-10-20.capture`, test `test_the_live_test_of_the_owner_proposes_the_office_thermostat`): the opening at 11:33:31 is answered by `3F48` after 1 second. The quick window closes with the next telegram, which is the closing of the contact at 11:41:43, and at that time `c45fa5` is proposed for `3F48`. One change was enough, so the proposal stands after the opening alone. The closing is answered after 43 seconds and the flag falls at 11:42:27, 44 seconds after the closing: that is one slow vote, and the learner ends with 1 quick answer and 1 slow vote, 8 points. No thermostat was silent, because the fixture holds no regular telegrams, so none was known before the change.

**Result on the recording of the house** (replay of `tests/fixtures/fhem_verbose5_2026-10-18.log`, test `test_the_learner_on_the_recording_of_the_house`): `d7a3d8` is proposed for `5d10` on 2026-10-17 at 11:16:45, with the third change of the flag, exactly when the first version proposed it, and no other contact gets a proposal. The tight signal does not make it faster here, because `5d10` answered only 2 of the 12 changes within 3 seconds (on 2026-10-17 at 12:22:14 and on 2026-10-18 at 11:56:40, both after the proposal). At the end of the recording the pair has 1 quick answer and 11 slow votes, 28 points, `3924` and `3f48` have 1 silent vote each, both 0 points. One of the 12 changes is a quick answer that the first version counted as ambiguous; it came while the other contact, which had closed 2.5 minutes before, was unanswered, so it counts as a slow vote. The other contacts of the house never got a vote: `060d98` and `783646` changed twice each while the flag of `5d10` was up, and the other five never changed.

**Limits.**

- A thermostat that answers late and has no flag (the first round of the live test) gets no vote from the slow signal. It gets one when it answers within 3 seconds once, or when its flag changes.
- A desired temperature that the user or a command of Home Assistant causes within 3 seconds of a contact change looks like an answer. That is a chance event, and a rival in the votes of the next change takes the proposal back.
- A late answer to one contact that falls within 3 seconds after another contact is attributed to the other contact only with the weight of a slow vote (see "Crowded answers"), so it cannot make a proposal alone. The 0.15 percent below covers a random off-schedule telegram, not this case.
- A proposal from one change can be wrong by chance (0.15 percent per event for a thermostat). The proposal is only a suggestion, the user confirms it in the options, and the next changes correct it: after a wrong proposal the right thermostat needs three clean changes to win it back.

## Verified on hardware

The first tests on a real busware CUL868 with culfw 1.66 ran on 2026-10-18 and 2026-10-19 on the test instance (Home Assistant 2026.10.2 in a virtual machine, FHEM stopped). The commands were tested mostly on one thermostat (3F48), the reads on several. The raw measurements of those runs are not part of this repository, so the rows state what was seen and the dates, not the byte-exact telegrams. A row that says "not yet" is still an assumption that the simulator in `tests/culfw_sim/` makes, and the checks for the cutover (below) fill it with a date or turn it into a deviation.

| Statement | Source of the assumption | Verified |
| --- | --- | --- |
| A controller echoes a command it took with the value it stored, and the entity stops being pending | `11_FHT.pm` | 2026-10-18: a command was pending for 40 to 120 seconds, then the echo arrived and `pending` turned false |
| The status byte of an echo is 0x69, and the echoes of one message come in the order sent | `fht.c` | not yet, the first run measured the delay only |
| A controller echoes a report request like any other command | `fht.c` | not yet, the answers to the requests were seen (below), the echo of the request itself was not checked |
| A controller answers report2 with the day, night and window open temperature in the following slots | `11_FHT.pm` | 2026-10-18 and 2026-10-19: the thermostats answered and the number entities filled in |
| `set_temperature` in automatic mode keeps the mode and is a temporary override until the next switch time | decision D7, the manual | 2026-10-18: the mode stayed automatic after a setpoint |
| The presets comfort and eco, the HVAC modes off and auto and the setpoint work and are echoed | the climate entity | 2026-10-18 |
| A holiday is set, and its end is read back from the registers of the thermostat | `11_FHT.pm` | 2026-10-18 |
| What a thermostat does after the end time of a holiday or party (leaves the mode silently, sends the mode on its own) | `11_FHT.pm`, the manual | not yet |
| A real thermostat answers a report1 request for all days in its slots | `11_FHT.pm` | 2026-10-18: the first telegrams came after about 11 minutes and all seven days (28 switch times) after about 35 minutes |
| One day of the week program is written in one message and reads back as written | `11_FHT.pm` | 2026-10-18: a day was written and the read-back equaled it |
| The stick comes back after it was detached and attached again through QEMU | the USB integration of Home Assistant | 2026-10-18: lost in under 20 seconds, back in under 10 seconds, one log line each |
| A virtual machine that has no USB device yet takes the stick without a restart | `qm` documentation | 2026-10-18: no. The first attach needed a restart of the virtual machine, a later one did not, because the slot existed |
| The stick has the by-id link `usb-busware.de_CUL868-if00` | `BY_ID` in `tests/common.py` | 2026-10-18, and the entry stores that link as its port |
| While a thermostat counts down its synchronization (status 0x2C), it sends an actuator telegram every second for about 2 minutes | `11_FHT.pm`, the manual chapter 4.1, the recording | 2026-10-17 in the recording (3F48) and 2026-10-19 on the test instance (460F) |
| The duty cycle credit of the CUL falls when a thermostat restarts after a battery change | the credit of the test instance on 2026-10-19 | 2026-10-19: the credit, normally about 9 seconds, fell to 0.7 to 3 seconds within minutes and stayed low for about 25 minutes. The button for the time was refused with `no_credit` meanwhile, and the credit recovered after the time sync of 22:14 |
| The cause of that fall is a message in the buffer that culfw answers about every second telegram of the countdown, and each answer costs credit | `fht_hook()` in `fht.c` | not yet, this is a hypothesis. The `outbox.send_log` of the diagnostics is meant to show it at the next restart of a thermostat |
| A thermostat acknowledges the date and time that the integration sent | `11_FHT.pm` | 2026-10-19: 460F acknowledged the time after its battery change. The detail that the echo carries the hour and minute of the CUL is not yet |
| The echo of a time command carries the hour and minute of the CUL | `fht.c`, `clock.c` | not yet |
| The `T02` dump has the format `HHHH:CCVV,CCVV` per queued message | `fht80b_print()` in `fht.c`, no sample | not yet |
| A controller echoes the value it stored when it clamps a value | `11_FHT.pm` | not yet |
| `T01` followed by the same central code rewrites the EEPROM and clears the buffer | `fncollection.c` | not yet for the rewrite. The clearing of the buffer was seen with FHEM on 2026-10-16 (the free bytes went from 0x09 to 0xAE) |
| A mode and a temperature command in one message are both applied, the mode first | behavior of FHEM, no source line | not yet |
| `X21` hides the handshake packets of the controller | `rf_receive.c` | not yet |
| The display of an FHT80b shows the decimal value of each security code byte with three digits, so 3F48 shows Code 1 = 063 and Code 2 = 072 | manual chapter 3.9.4 (two parts, 000 to 099), FHEM wiki, node-cul `fht.js` | 2026-10-19 for 3F48: the office thermostat shows Code 1 = 063 and, after a confirmation with PROG, Code 2 = 072 (read by the owner on its display) |
| The same conversion holds for the other thermostats: 3924 shows 057 036 and 5D10 shows 093 016 | the conversion in `pyculfw/codes.py` | not yet, the two values are calculated and still to be compared on the displays |
| The release of a thermostat that is registered with another central (`CEnt`, then `nA`) lets it register with this CUL | manual chapter 3.9.9 | not yet, the procedure was not run with the integration |
| The window flag of a thermostat follows the opening or closing of its contact by 8 to 226 seconds | the recording of 2026-10-16 to 2026-10-18 (`d7a3d8` and `5d10`), the manual chapter 3.9.10 | not yet, the owner has to confirm that the two are in the same room |
| A paired thermostat answers a change of state of its contact with an off-schedule desired temperature and warnings telegram | the live test of the owner and the recording of 2026-10-16 to 2026-10-18 | 2026-10-20: `c45fa5` and `3F48`, 1 second after the opening and 43 seconds after the closing, in one clean round. In the recording `5d10` answered 12 of 12 changes of `d7a3d8` within 225 seconds, 3 of them within 10 seconds (see "The answer of a thermostat within seconds") |

## Hardware notes

These come from the tests of the owner on the real thermostats, not from the stick:

- The values 30.5 and 5.5 °C of the desired temperature are the display values On and OFF of the thermostat. The manual of the FHT80b describes On as the heating pause (chapter 3.6, "Heizpause"): the valve opens and stays open without control, and the thermostat offers it in manual mode only. OFF closes the valve, and it opens only when the temperature falls below 5 °C (chapter 3.7, closing the valve). The integration therefore has no boost preset and shows 30.5 °C as no preset.
- On 2026-10-18 the owner selected a preset and then set the HVAC mode auto. The preset stayed, because the desired temperature stays until the next switch time of the week program. The mode alone does not write a setpoint.

## Differences from the sources

The parser leaves out three features of FHEM on purpose:

- The `Reliability` reading of the FHT80 TF. `09_CUL_FHTTK.pm` sets the timestamp to the current time before it checks its age, so the reading is always `ok`. Whether a device is alive is decided from the time of its last telegram.
- The de-duplication of FHT80 TF telegrams within 5 seconds. Every telegram counts as a sign of life, and the `repeat` flag tells a repetition apart.
- The `tmpcorr` attribute, a correction of the measured temperature. The library reports what the device sent.

The decoding differs from the sources in these places:

- The assembler uses a low byte of the measured temperature only once. FHEM keeps it, so after a lost low byte it pairs a stale low byte with a new high byte. For example 25.5 °C is sent as 00 and ff, 25.6 °C as 01 and 00, and a lost low byte makes 01 with the stale ff read as 51.1 °C.
- `lib/fht.js` of node-cul scales the high byte of the measured temperature by 25.5 and reads the warnings as an index instead of bits. The parser follows FHEM for both.

## Open points

- The meaning of the command code 0x45, called `manu-temp` in `11_FHT.pm`, is unknown. It was never seen on the air.
- The high nibble of the status byte of an actuator telegram varies independently in two bits, and its meaning is undocumented. The parser decodes only the cases that `11_FHT.pm` knows.
- The codes for sync, test and a weak battery of the FHT80 TF come from the sources only. They were not seen in the recording.
- The echo of a command that this integration queued was seen on a real stick on 2026-10-18 (pending for 40 to 120 seconds). Not recorded in detail are the status byte of an echo, which is inferred from the way `11_FHT.pm` reads it, and the order of the echoes of one message.
- The outbox ends the wait for a message with the echo of its last command, which assumes that the controller echoes in the order it received the commands. It also assumes that a free buffer which is as free as before the oldest message in flight means that all of them left it, and that a controller which collects a message in its slot echoes it within seconds. A controller that is paired to another central, or one that transmits but does not collect, shows up only as messages without an echo. Whether the stick prints `EOB` before the answer to the next `T03` on the real line, which the outbox relies on to judge a send, is not verified either.
- That `T01` rewrites the EEPROM even when the code is unchanged follows from the source of `fncollection.c`. It was not tested on a stick, and the init sequence of the transport avoids the write in that case.
- The refresh planner assumes that a controller answers a report2 request with its registers in the slots after the request, and that the day, night, window open and low temperature telegrams are among the answers (they set `settings_read_at`). A controller that echoes the request but never reports its settings is asked again every 30 minutes.
- The automatic read of the week program follows the timing that one thermostat showed on 2026-10-18 (about 35 minutes for the week, the first telegrams after about 11 minutes). Other thermostats were not timed. A thermostat that answers more slowly keeps the read running past the window of one hour, which lets the next controller start while it is still answering, and a read that does not complete within the window is asked for again after 6 hours.

- What kept the credit low for about 25 minutes after the batteries of 460F were replaced. The countdown explains the first fall at best, and the link between a waiting message and the fall is a hypothesis. See "Restart of a thermostat and the radio budget".
- The display codes of 3924 and 5D10, the release procedure of a thermostat that belongs to another central (`CEnt`), and what a thermostat does after the end of a holiday or party were not checked on a real device. The rows "not yet" of the table above list the rest.

## Checks for the cutover

The first runs on the real stick (2026-10-18 and 2026-10-19) answered the questions about the echo of a value, the modes, the week program and the reconnect. These questions are still open, because the simulator can only assume the answers (see `tests/culfw_sim/README.md`):

- Does the controller echo a report request like any other command? The outbox does not depend on it. A report that nobody echoed leaves the queue quietly when its message left the buffer, and it neither counts against the controller nor makes it known. Without the echo, a controller that never echoed a command of the user stays unconfirmed, and the daily time sync waits until the user presses the sync button or sets a value.
- What does the answer to `T02` look like on culfw 1.66? While a message is in flight, the outbox reads it at most every 30 seconds and keeps the last answer, and the diagnostics show it under `outbox.fht_queue`. Compare it with the format in the notes above before `USE_T02_GATE` is switched on.
- Does a controller echo the value it stored when it clamps a value? The outbox counts a message whose echo shows another value as unechoed.
