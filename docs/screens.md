# Screens of the setup

This page shows every screen that the setup, the reconfiguration and the options of the
integration display, in the order the user meets them. A test builds the page: it runs
the real flows, takes the fields from their data schema and every text from
`translations/en.json`, and compares the result with this file, so the page cannot say
anything that the code does not do. Do not edit it by hand. After a change of a flow or
a text, regenerate it with `UPDATE_SCREENS=1 uv run pytest tests/test_screens.py` and
read the difference.

How to read the mockups:

- The first line of a box is the title of the dialog, the last line is its button.
  Home Assistant labels the button **Next** when more screens follow and **Submit**
  when the screen ends the flow, unless the screen has a button text of its own. A
  menu has one button for each choice, and a progress step has a bar instead of
  buttons: it goes on by itself when the work is done.
- A star marks a required field. The text in brackets shows the control, with the value
  that the field has when the dialog opens: the default of the field, or the value that
  the flow suggests, such as the central code that the CUL stores.
- The descriptions are shown without their formatting marks (bold and code), and the
  placeholders hold example values.

## Config flow

Add the integration under **Settings** > **Devices & services** > **Add integration**. If the CUL is plugged in, Home Assistant also lists it as a discovered device. The flow reads the CUL before it asks for the central code and changes nothing on the stick while it reads. After the central code it offers to listen to the radio, because a device announces itself only when it sends, and it creates the entry after the summary of the devices that were heard.

### Connect the CUL

Step `user`. The first screen when the user adds the integration without a discovered CUL.

```text
┌────────────────────────────────────────────────────────────────────┐
│ Connect the CUL                                                    │
├────────────────────────────────────────────────────────────────────┤
│ Home Assistant reads the version and the central code from the CUL │
│ to check the connection. It does not change anything on the stick. │
│                                                                    │
│ Serial port *                                                      │
│     [ Select a serial port ▾ ]                                     │
│     The port of the CUL. A path such as /dev/ttyACM0 is stored as  │
│     its stable path under /dev/serial/by-id/ when the host has     │
│     one. If another program such as FHEM uses the CUL, stop it     │
│     first.                                                         │
│                                                                    │
│                                                           [ Next ] │
└────────────────────────────────────────────────────────────────────┘
```

### CUL found

Step `usb_confirm`. The first screen when Home Assistant found the CUL by USB discovery. The dialog has no fields.

```text
┌────────────────────────────────────────────────────────────────────┐
│ CUL found                                                          │
├────────────────────────────────────────────────────────────────────┤
│ Do you want to set up the CUL at                                   │
│ /dev/serial/by-id/usb-busware.de_CUL868-if00? Home Assistant reads │
│ the version and the central code from the CUL to check the         │
│ connection. It does not change anything on the stick.              │
│                                                                    │
│                                                         [ Submit ] │
└────────────────────────────────────────────────────────────────────┘
```

### Central code

Step `house_code`. Both ways lead here after the CUL was read. The user enters the central code as two numbers, so the user never has to convert a code to hexadecimal, and the text shows the hexadecimal form of the code that the CUL holds. The two numbers are two boxes below each other, because the form of a Home Assistant config flow cannot place two fields side by side.

```text
┌────────────────────────────────────────────────────────────────────┐
│ Central code                                                       │
├────────────────────────────────────────────────────────────────────┤
│ The central code is the code of the CUL, the central of your FHT   │
│ system. FHEM calls it FHTID, and this documentation also calls it  │
│ the house code. The CUL currently holds 016 052 (hex 1034).        │
│ Thermostats that work with FHEM keep working with the same code.   │
│                                                                    │
│ New setup: choose any code and release every FHT80b for            │
│ registration. Hold PROG until Sond shows, select CEnt, press PROG, │
│ choose nA and confirm with PROG. It then shows On.                 │
│                                                                    │
│ The security code (CodE) of a thermostat is a different code that  │
│ you do not change here. To read it, hold PROG until Sond shows,    │
│ choose CodE with the wheel and confirm with PROG. The display      │
│ shows Code 1 with three digits, for example 063. Confirm again and │
│ it shows Code 2, for example 072.                                  │
│                                                                    │
│ To see or change the central code later, select Reconfigure under  │
│ Settings > Devices & services > culfw (CUL).                       │
│                                                                    │
│ Central code, first number *                                       │
│     [   16 ]  (number from 1 to 99)                                │
│     1 to 99, for example 16                                        │
│                                                                    │
│ Central code, second number *                                      │
│     [   52 ]  (number from 1 to 99)                                │
│     1 to 99, for example 52                                        │
│                                                                    │
│                                                           [ Next ] │
└────────────────────────────────────────────────────────────────────┘
```

### Overwrite the central code?

Step `confirm_house_code`. This screen follows only when the numbers differ from the central code that the CUL stores. Here the user enters 57 and 36 although the CUL stores 016 052. The text shows both codes in the display form and in hexadecimal.

```text
┌────────────────────────────────────────────────────────────────────┐
│ Overwrite the central code?                                        │
├────────────────────────────────────────────────────────────────────┤
│ The CUL holds the central code 016 052 (hex 1034). Overwriting it  │
│ with 057 036 (hex 3924) rewrites the EEPROM of the CUL and clears  │
│ all its FHT buffers. FHT80b thermostats that are registered with   │
│ 016 052 (hex 1034) no longer accept commands until you release     │
│ them for registration (CEnt, nA) and they register with 057 036    │
│ (hex 3924). The security code (CodE) of a thermostat does not      │
│ change.                                                            │
│                                                                    │
│                                                      [ Overwrite ] │
└────────────────────────────────────────────────────────────────────┘
```

### Find your devices

Step `listen_menu`. The setup continues here once the central code is settled, from both ways in. The user chooses between listening and setting up without devices. The choice comes before the listening, because a progress step takes no input and ends by itself. A user whose thermostats have no batteries yet skips the listening and adds the devices later.

```text
┌────────────────────────────────────────────────────────────────────┐
│ Find your devices                                                  │
├────────────────────────────────────────────────────────────────────┤
│ Devices announce themselves only when they send, so the            │
│ integration listens to the radio for about 5 minutes. Thermostats  │
│ send about every 2 minutes. Window contacts send when they change  │
│ and otherwise about every 4 minutes, so open or close a contact to │
│ make it appear sooner.                                             │
│                                                                    │
│ Every thermostat needs working batteries and CEnt on On (the       │
│ previous step describes the release with nA), otherwise it does    │
│ not send and does not appear. A device that is missing can be      │
│ added later: the integration adds new devices automatically (see   │
│ the option Add new devices automatically) or lists them as         │
│ candidates. You can also skip the listening now, for example while │
│ the batteries are out.                                             │
│                                                                    │
│                                             [ Listen for devices ] │
│                                                                    │
│                                [ Skip and set up without devices ] │
└────────────────────────────────────────────────────────────────────┘
```

### Listening for devices

Step `listen`. The progress step while the integration listens for five minutes. The lists grow while devices are heard, here one thermostat and one window contact. The number in brackets is the signal strength. The step ends by itself and closing the dialog cancels the setup. The CUL is opened with the central code it holds, so the listening writes nothing to the stick.

```text
┌────────────────────────────────────────────────────────────────────┐
│ Listening for devices                                              │
├────────────────────────────────────────────────────────────────────┤
│ Devices appear when they send. Thermostats send about every 2      │
│ minutes, window contacts about every 4 minutes. A thermostat with  │
│ empty batteries or with CEnt not on On does not appear. You can    │
│ add it later: the integration adds new devices automatically       │
│ (option) or lists them as candidates.                              │
│                                                                    │
│ This takes about 5 minutes. If you close this dialog, the setup is │
│ cancelled.                                                         │
│                                                                    │
│ Thermostats heard: 1                                               │
│ - FHT80b 093 016 (-74 dBm)                                         │
│                                                                    │
│ Window contacts heard: 1                                           │
│ - FHT80 TF 783646 (-66 dBm)                                        │
│                                                                    │
│ ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒                           │
└────────────────────────────────────────────────────────────────────┘
```

### Devices found

Step `summary`. The last screen. It lists what was heard and asks what each window contact watches, and whether the integration reads the week programs. The entry is created with these answers as its options. The field of a contact is named after the contact, so it has no translation of its own. Without any device heard, the screen has only the week program switch.

```text
┌────────────────────────────────────────────────────────────────────┐
│ Devices found                                                      │
├────────────────────────────────────────────────────────────────────┤
│ Thermostats heard: 1                                               │
│ - FHT80b 093 016 (-74 dBm)                                         │
│                                                                    │
│ Window contacts heard: 1                                           │
│ - FHT80 TF 783646 (-66 dBm)                                        │
│                                                                    │
│ The number in brackets is the signal strength, which helps to tell │
│ your devices from those of a neighbor. You can ignore a device of  │
│ a neighbor later in the options. A device that is missing is added │
│ automatically as soon as it sends, so you can set up now and wait  │
│ for it.                                                            │
│                                                                    │
│ The devices listed here become devices in Home Assistant when      │
│ their next telegram arrives, so the naming dialog that follows     │
│ does not list them. Name them later on their device page under     │
│ Settings > Devices & services > Devices.                           │
│                                                                    │
│ If window contacts were heard, each one gets a field below where   │
│ you choose whether it watches a window or a door, because a        │
│ contact cannot tell. A contact also belongs to a thermostat, but   │
│ neither of them tells which. When the devices have sent for a      │
│ while, you can assign each contact to its thermostat, and change   │
│ the window or door choice, under Settings > Devices & services >   │
│ culfw (CUL) > Configure.                                           │
│                                                                    │
│ The integration also adds the week program card to your            │
│ dashboards, so that you can see and edit the week program of a     │
│ thermostat. You can turn that off later under Settings > Devices & │
│ services > culfw (CUL) > Configure.                                │
│                                                                    │
│ FHT80 TF 783646 *                                                  │
│     [ Window ▾ ]  (choices: Window, Door)                          │
│                                                                    │
│ Read week programs automatically *                                 │
│     [x] on                                                         │
│     Reading takes up to about 35 minutes per thermostat, one after │
│     another: the first two days arrive after about 11 minutes and  │
│     all seven after about 35 minutes, so 4 thermostats take about  │
│     2.5 hours. It runs in the background. You can change this      │
│     later under Settings > Devices & services > culfw (CUL) >      │
│     Configure.                                                     │
│                                                                    │
│                                                         [ Submit ] │
└────────────────────────────────────────────────────────────────────┘
```

### Errors of the setup

Every error appears in red above the buttons of the screen that caused it. The flow goes on when the user corrects the input.

- `cannot_connect`: Failed to connect to the serial port. Check that the CUL is plugged in and that Home Assistant is allowed to use the port.
- `port_missing`: The serial port does not exist. Check that the CUL is plugged in and select its port again.
- `port_in_use`: Another program is using the serial port. Stop that program, for example FHEM, and try again.
- `permission_denied`: Home Assistant is not allowed to open the serial port. Give the user that runs Home Assistant access to the port, for example by adding it to the dialout group.
- `no_answer`: The device does not answer. Check that it is a CUL with culfw.
- `not_culfw`: The device does not answer like a CUL with culfw. Check that you selected the right serial port.
- `invalid_house_code`: The CUL cannot use this central code. Enter each of the two numbers as a whole number from 1 to 99. The CUL cannot use a 0.
- `unknown`: Unexpected error

### Reasons to stop the setup

- `already_configured`: The CUL is already set up, and only one CUL is supported. To change the serial port or the central code, select Reconfigure in the menu of the integration.
- `cannot_listen`: Home Assistant could not listen to the CUL at {device}. Check that the CUL is still plugged in and that no other program uses it, then start the setup again.

## Reconfigure flow

Select **Reconfigure** in the menu of the integration to change the serial port or the central code. The form starts with the stored values. A new central code goes through the same confirmation as in the setup (see the screen about overwriting the central code in the config flow), and Home Assistant reloads the integration afterwards.

### Reconfigure the CUL

Step `reconfigure`. The only screen of the flow, followed by the confirmation above when the central code changes.

```text
┌────────────────────────────────────────────────────────────────────┐
│ Reconfigure the CUL                                                │
├────────────────────────────────────────────────────────────────────┤
│ Change the serial port, for example after you moved the stick to   │
│ another USB port, or the central code of the CUL, which is         │
│ currently 016 052 (hex 1034). A different central code is written  │
│ to the CUL after you confirm it. Every FHT80b must then be         │
│ released for registration again: hold PROG until Sond shows,       │
│ select CEnt, press PROG and choose nA. Home Assistant reloads the  │
│ integration afterwards.                                            │
│                                                                    │
│ Serial port *                                                      │
│     [ /dev/serial/by-id/usb-busware.de_CUL868-if00 ▾ ]             │
│     The port of the CUL. A path such as /dev/ttyACM0 is stored as  │
│     its stable path under /dev/serial/by-id/ when the host has     │
│     one.                                                           │
│                                                                    │
│ Central code, first number *                                       │
│     [   16 ]  (number from 1 to 99)                                │
│     1 to 99, for example 16                                        │
│                                                                    │
│ Central code, second number *                                      │
│     [   52 ]  (number from 1 to 99)                                │
│     1 to 99, for example 52                                        │
│                                                                    │
│                                                         [ Submit ] │
└────────────────────────────────────────────────────────────────────┘
```

## Options flow

Select **Configure** in the menu of the integration. The fields for new devices appear only while the CUL has heard devices that are not added yet, and the second screen appears only when the integration has an FHT80 TF contact or the user adds one. The third screen appears when the integration has a thermostat as well.

### culfw options

Step `init`. The thresholds, the automatic adding of devices, the devices that are waiting and the ignored devices, and the collapsed recovery section. The example shows a CUL that has heard two new devices while the automatic adding is off, and the user selects the contact to add.

```text
┌────────────────────────────────────────────────────────────────────┐
│ culfw options                                                      │
├────────────────────────────────────────────────────────────────────┤
│ FHT80b silent after *                                              │
│     [    2 ]  (number from 0.5 to 48, in h)                        │
│     Hours without any telegram after which an FHT80b counts as     │
│     gone: its values become unavailable and a repair is raised. It │
│     reports about every 2 minutes.                                 │
│                                                                    │
│ FHT80 TF silent after *                                            │
│     [    4 ]  (number from 0.5 to 48, in h)                        │
│     Hours without any telegram after which an FHT80 TF counts as   │
│     gone: its values become unavailable and a repair is raised. It │
│     reports about every 4 minutes.                                 │
│                                                                    │
│ Add new devices automatically *                                    │
│     [x] on                                                         │
│     Adds every FHT device that the CUL hears for the first time.   │
│     Turn it off when devices of a neighbor are in range: new       │
│     devices then wait here as candidates until you add or ignore   │
│     them.                                                          │
│                                                                    │
│ Add new devices                                                    │
│     [ nothing selected ▾ ]                                         │
│       Choices: FHT80b 093 016 (-74 dBm), FHT80 TF 783646 (-66 dBm) │
│     Devices that the CUL heard while new devices are not added     │
│     automatically, with their signal strength, which helps to tell │
│     your own devices from a neighbor's. The devices you select are │
│     added when you save.                                           │
│                                                                    │
│ Ignore new devices                                                 │
│     [ nothing selected ▾ ]                                         │
│       Choices: FHT80b 093 016 (-74 dBm), FHT80 TF 783646 (-66 dBm) │
│     The devices you select are added to the ignored devices when   │
│     you save, and their telegrams are dropped.                     │
│                                                                    │
│ Ignored devices                                                    │
│     [ nothing selected ▾ ]                                         │
│       Choices: FHT80b 018 052, Kitchen, FHT80 TF D4E5F6            │
│     Telegrams of these devices are dropped and the devices are     │
│     removed, for example a neighbor's FHT80b. Deleting a device    │
│     that still transmits adds it here.                             │
│                                                                    │
│ Read week programs automatically *                                 │
│     [x] on                                                         │
│     Reads the week program of each thermostat once after its first │
│     contact, again after the CUL was reset, and then every 24      │
│     hours, so that the Heating program calendar shows what the     │
│     thermostat holds, also after you changed it at the thermostat. │
│     A thermostat answers only in its time slots, so reading the    │
│     seven days takes about 35 minutes, and one thermostat is read  │
│     at a time. Turn it off to read a week program only with the    │
│     Refresh schedule button.                                       │
│                                                                    │
│ Add the week program card automatically *                          │
│     [x] on                                                         │
│     Adds the week program card to the resources of your            │
│     dashboards, so that FHT week program appears in the list of    │
│     cards when you edit a dashboard. Turn it off to add the file   │
│     /culfw/frontend/fht-schedule-card.js yourself as a JavaScript  │
│     module under Settings > Dashboards > menu Resources. Turning   │
│     it off does not remove a resource that is there already.       │
│                                                                    │
│ ▸ Recovery  (collapsed by default)                                 │
│     Last resorts of the watchdog when the CUL stays silent. Both   │
│     make the stick leave the USB bus for a moment, which is safe   │
│     only when Home Assistant gets the whole USB device and finds   │
│     the stick again under its path in /dev/serial/by-id/. That is  │
│     the case when a virtual machine gets the stick by vendor and   │
│     product ID. Leave both off when the stick is bound to a fixed  │
│     port such as /dev/ttyACM0.                                     │
│                                                                    │
│     Allow rebooting the CUL *                                      │
│         [ ] off                                                    │
│         Lets the watchdog reboot the CUL, which then enumerates on │
│         USB again. Turn it on only when the stick is passed        │
│         through by vendor and product ID and has a link under      │
│         /dev/serial/by-id/.                                        │
│                                                                    │
│     Allow resetting the USB link *                                 │
│         [ ] off                                                    │
│         Lets the watchdog reset the USB link of the stick, which   │
│         keeps the FHT buffers of the CUL. Turn it on only when the │
│         stick is passed through by vendor and product ID and has a │
│         link under /dev/serial/by-id/. The reset is used only when │
│         the serial port of the integration is that link.           │
│                                                                    │
│                                                           [ Next ] │
└────────────────────────────────────────────────────────────────────┘
```

### FHT80 TF contacts

Step `contact_types`. One select for each FHT80 TF contact, including the contact that the user adds. A contact that has been renamed shows its name in brackets. The names of the fields come from the device registry, so they have no translation of their own.

```text
┌────────────────────────────────────────────────────────────────────┐
│ FHT80 TF contacts                                                  │
├────────────────────────────────────────────────────────────────────┤
│ Choose for each FHT80 TF contact whether it watches a window or a  │
│ door. The contact cannot tell, and the choice sets the device      │
│ class of its open state. If you changed the device class of that   │
│ entity in its settings, your choice there stays.                   │
│                                                                    │
│ FHT80 TF 783646 *                                                  │
│     [ Window ▾ ]  (choices: Window, Door)                          │
│                                                                    │
│ FHT80 TF A1B2C3 (Kitchen) *                                        │
│     [ Window ▾ ]  (choices: Window, Door)                          │
│                                                                    │
│ FHT80 TF D4E5F6 *                                                  │
│     [ Window ▾ ]  (choices: Window, Door)                          │
│                                                                    │
│                                                           [ Next ] │
└────────────────────────────────────────────────────────────────────┘
```

### Window contacts of each thermostat

Step `contact_thermostats`. One select for each contact, with the thermostats of the house and the choice not assigned. The thermostat that the radio traffic suggests is the default of its contact and says so, here for the kitchen. The user confirms it by saving, and the choice only fills the attributes of the two devices.

```text
┌────────────────────────────────────────────────────────────────────┐
│ Window contacts of each thermostat                                 │
├────────────────────────────────────────────────────────────────────┤
│ Choose for each FHT80 TF contact the thermostat it is paired with. │
│ A thermostat stores up to four contacts and shows only the state   │
│ of each slot on its display, never the code of a contact, so the   │
│ thermostat cannot tell and the radio cannot say for sure. A        │
│ thermostat that answers when a contact opens or closes, usually    │
│ within seconds and sometimes after a minute or more, is suggested  │
│ for that contact, with a confidence of low, medium or high.        │
│ Opening and closing the window once is enough if the thermostat    │
│ answers quickly, otherwise it takes about two rounds. Nothing      │
│ changes until you save. The assignment is for your overview: it    │
│ adds the thermostat to the attributes of the contact and the       │
│ contact to the attributes of the thermostat. It changes nothing on │
│ the thermostats. To pair a contact with another thermostat, use    │
│ the menu FEn at the thermostat.                                    │
│                                                                    │
│ FHT80 TF 783646 *                                                  │
│     [ Not assigned ▾ ]  (choices: Not assigned, FHT80b 018 052)    │
│                                                                    │
│ FHT80 TF A1B2C3 (Kitchen) *                                        │
│     [ FHT80b 018 052 (suggested, medium confidence) ▾ ]            │
│       Choices: Not assigned, FHT80b 018 052 (suggested, medium     │
│       confidence)                                                  │
│                                                                    │
│ FHT80 TF D4E5F6 *                                                  │
│     [ Not assigned ▾ ]  (choices: Not assigned, FHT80b 018 052)    │
│                                                                    │
│                                                         [ Submit ] │
└────────────────────────────────────────────────────────────────────┘
```

### Errors of the options

- `candidate_conflict`: A device cannot be added and ignored at the same time. Select it in only one of the two lists.
