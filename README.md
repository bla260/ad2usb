# ad2usb Indigo Plugin

## About
**ad2usb** is a plugin interface to the NuTech AD2* alarm system interface for Honeywell's Ademco Vista line of alarm panels. It allows you to create Indigo devices for each of your alarm panel's sensors (e.g. door sensor, motion sensor, window sensor, ...) which can then take advantage of many of Indigo's features available for devices. It also allows you to read and send alarm messages by emulating an alarm panel keypad. There are addition features described in this document.

## About "*TBP*" in this README
There are still several items marked "To Be Published" (*TBP*) in this document. Each subsequent release will attempt to replace these *TBP* sections with more complete documentation for the plugin.

## Required Hardware
This plugin requires both a [NuTech AlarmDecoder](https://www.alarmdecoder.com) (AD2) alarm interface and an alarm panel. Both the NuTech AD2USB and AD2Pi are supported (see Note 1). This interface supports a broad range of alarm panels manufactured by **Honeywell** and sold under the **ADEMCO VISTA** brand name and similar panels sold by First Alert. The list of supported panels includes (see Note 2):

- VISTA-4110XM
- VISTA-15P
- VISTA-20P
- VISTA-21IP
- VISTA-40
- VISTA-50P
- VISTA-128BPT/VISTA Turbo Series (see Note 3)
- VISTA-250BPT/VISTA Turbo Series (see Note 3)
- First Alert-FA148CP
- First Alert-FA148CPSIA
- First Alert-FA168CPS
- First Alert-FA168CPSSIA

A more complete list is available from NuTech on their website. While the NuTech AlarmDecoder AD2* interface also supports alarm panels sold by DSC, this plugin is not tested with those panels. Users with DSC panels should look at the DSC Alarm plugin.

**Important Notes** :
1. An older version of the AlarmDecoders' firmware, version 2.2a.6, is required. The Plugin may not start or run with any other version. Support for the latest version of the firmware is planned in a future release in July 2022.
2. While the panels listed should work, the developer testing for each release is limited to only on a VISTA-20P. Leverage the [Indigo ad2usb User Forum](https://forums.indigodomo.com/viewtopic.php?f=22&t=7584) to ask other users about their experience with your specific alarm panel model.
3. Works only in the plugin's basic mode

## Features

This plugin adds new Indigo options for **Devices**, **Actions**, and **Trigger Events**. See the [Indigo Overview](https://wiki.indigodomo.com/doku.php?id=indigo_2021.2_documentation:overview) for more information about Devices, Actions, and Triggers.

### Devices

The ad2usb plugin adds the following device options to Indigo.

Device Type | Description
----------- | -----------
ad2usb Keypad | The AlarmDecoder Keypad emulator. You should add one Indigo ad2usb Keypad Device which represents your NuTech AlarmDecoder device.
Alarm Zone | Standard alarm zone such as window or door sensors. Add one Indigo Alarm Zone device for each sensor you have configured with your alarm panel that you want to integrate with Indigo. Each Alarm Zone device has these three state variables with possible values shown in parenthesis: `zoneState` (Fault or Clear), `onOffState` (On or Off), and `bypassState` (On or Off). States `zoneState` and `onOffState` are somewhat redundant since when an alarm zone changes state both are change, they exist so you can create triggers on any changes of the state name of your preference.
Zone Group | Creates a group of Alarm Zones. This allows you to create a group of alarm zones devices that treated as single device within Indigo Triggers. Zone groups have the same states as Alarm Zones with the exception they do not have the `bypassState`. Zone Groups change to Fault (or On) when **ANY** of their Zone's change from Clear to Fault (or Off to On). Zone Groups change to Clear (or Off) once **ALL** of their Zones are Clear (or Off).
Indigo Managed Virtual Zone | The AlarmDecoder's Zone Expander Emulation feature allows the AlarmDecoder to act in place of a physical expander board and make use of virtual zones with your panel. After enabling it on both the alarm panel and the AlarmDecoder you can begin opening and closing zones, which will be relayed back to the panel. [See the AlarmDecoder Protocol Documentation for more details.](https://www.alarmdecoder.com/wiki/index.php/Protocol#Zone_Emulation). You can create an Indigo Managed Virtual Zone to use this capability. After creating the Indigo Managed Virtual Zone, you call a specific Action, "Change a Virtual Zone's state", which will change the state of the device in Indigo and send Open or Close messages to your alarm panel. **CAUTION**: Do not set a trigger on a Virtual Zone's device change to call the "Change a Virtual Zone's state" or you will have an infinite loop. See the "Alarm Zone Actions" section.



### Actions

The ad2usb plugin adds new Actions for **ad2usb Keypad** and **Alarm Zone** devices.

#### Keypad Actions
You can use Indigo Actions to Arm & Disarm your panel and invoke panel events. Four types of Arm Actions are available. Refer to your Alarm Users Guide for description of each. You can also writes an arbitrary message to the panel via the keypad. **CAUTION:** Having detailed knowledge of your alarm panel's operation is recommended before configuring the Write to Panel action.

Keypad Actions | Description (refer to you Alarm Panel Users Guide)
-------------- | -----------
Arm-Stay | Performs the keypad function STAY. Arms perimeter zones only and entry delay is on.
Arm-Instant | Performs the keypad function INSTANT. Same as STAY, except entry delay is off.
Arm-Away | Performs the keypad function AWAY. Arms the entire burglary system, perimeter and interior. Entry delay is on.
Arm-Max | Performs the keypad function MAX. Same as AWAY, except entry delay is off.
Write To Panel | Writes an arbitrary message to the panel via the keypad. **CAUTION:** Having detailed knowledge of your alarm panel's operation is recommended before configuring this action.

#### Alarm Zone Actions
Alarm Zone actions are less likely to be used but available since most Alarm Zone devices simply change state based on data being sent from your alarm panel.

Alarm Zone Actions | Description
------------------ | ----------
Force Alarm Zone state change | This Action can be called to force an Alarm Zone's state in Indigo to either Clear or Fault. The Indigo device state is changed but no messages are sent to the AlarmDecoder. It is provided for any special use cases that are needed; but in general is not needed for normal operation.
Change a Virtual Zone's state | Zone Expander Emulation allows the AlarmDecoder to act in place of a physical expander board and make use of virtual zones with your panel. After enabling it on both the panel and the AlarmDecoder you can begin opening and closing zones, which will be relayed back to the panel. This Action will send `Clear (Closed)` or `Faulted (Open)` to your alarm panel for defined zone. [See the AlarmDecoder Protocol Documentation for more details](https://www.alarmdecoder.com/wiki/index.php/Protocol#Zone_Emulation)

### Trigger Events

In addition to the ability to add Triggers for Device state changes, the ad2usb plugin has several other events you can create Indigo triggers for.

Event | Description
----- | -----------
Panel Arming Events | Detect when your panel is Disarmed, Armed Away, or Armed Stay
System Status Event | Detect when your alarm panel has any of these system status events: AC Power Loss, AC Power Restore, Panel Battery Low, Panel Battery Restore, RF Battery Low, RF Battery Restore, Trouble, and Trouble Restore
Alarm Events | Detect when your panel has any of these Alarm events: Panic Alarm, Fire Alarm, Audible Alarm, Silent Alarm, Entry Alarm, Aux Alarm, Perimeter Alarm, Alarm Tripped: Countdown started
User Actions | Detect when an alarm panel user ID you specify has initiated any these events: Disarmed, Armed Stay, Armed Away. **NOTE:** These events require either a real or emulated LRR. More information is *TBP*.

### Indigo Client UI
#### General
After you configure the plugin and add your alarm devices to Indigo, the Indigo Client UI will show alarm panel device zone states than alarm panel device address (i.e. the alarm zone number).
#### Device States
##### Clear and Fault
The Indigo Client UI will show the Clear or Fault state of the zone. The green circle icon represents Clear and the red circle icon represents Fault.
##### Bypass
When an Alarm Zone is set to Bypass = On it will display the generic Indigo "Sensor Off" icon (grey circle) and the text "Bypass" in the Indigo Client UI. Bypassed zones do not Fault on the panel and thus will not change state even if the sensor is tripped.

## Configuration and Setup

### General

#### Alarm Panel
You need to be familiar with how to program your Alarm panel to add a new keypad address. Refer to your Alarm panel programming guide on how to add a keypad device.

#### AlarmDecoder
You should familiarize yourself with the setup and configuration of your AlarmDecoder. See [NuTech's AlarmDecoder website](https://www.alarmdecoder.com/index.php) for details on how to install and configure your AlarmDecoder. **IMPORTANT:** This plugin **will set** certain configuration parameters of your AlarmDecoder **every time** it is started **and** when the Plugin's menu Configure **settings are saved.** Only those AlarmDecoder configuration settings controlled by this plugin will be changed. Other AlarmDecoder configuration settings not managed by this plugin will not be changed. If you will be changing any AlarmDecoder configuration options not managed by this plugin, it is recommended that you stop the plugin first and restart it after you have made your changes. You can use the "Read ad2usb Config" button to read the AlarmDecoder's current settings. This button will log the current setting to the Indigo event log and update the Plugin's settings dialog to match the current AlarmDecoder settings. Configuration settings managed by this plugin should be changed through the Plugin Configure menu. The AlarmDecoder configuration settings managed by this plugin are below:
- ADDRESS - the keypad address
- CONFIGBITS - (select CONFIGBITS below can be set via this plugin)
  - Enable reporting of RFX messages (Mask 0x0100)
- EXP - Emulation of zone expanders 1-5
- REL - Emulation of relay expanders 1-4
- LRR - Emulation of Long Range Radio expander
- DEDUPLICATE - If enabled, removes duplicate alphanumeric keypad messages

#### Indigo Plugins
You should be familiar with installing and configuring Indigo plugins.See Indigo's [Managing Plugins](https://wiki.indigodomo.com/doku.php?id=indigo_2021.2_documentation:getting_started#managing_plugins) documentation for details on installing and upgrading plugins.

### Quick Start - First Install
1. Program your alarm panel to support the NuTech AlarmDecoder as a new keypad device (default from NuTech is "18").
2. Install and configure your NuTech AlarmDecoder. For network devices make sure you know the IP address and port (default is 10000) to communicate with the AlarmDecoder. Make any additional configration changes not managed by the Plugin to your AlarmDecoder via a terminal program or other supported method. In most cases the default settings of the AlarmDecoder are fine and no additional configuration is needed.
3. Download this plugin from the Indigo Plugin Store.
4. Double-click the plugin icon to install the plugin within Indigo. Choose "Install and Enable the Plugin"
5. Choose "AD2SUB Alarm Interface" from the Plugins menu and choose Configure. In many cases you will only need the minimum information the plugin needs to operate: **AD2USB connection settings**, **Number of Partitions** and **Keypad Address**:
  - Configure the IP address and port **OR** the USB Serial settings of your AlarmDecoder so the plugin knows how to connect to your AlarmDecoder.
  - Configure the Keypad address to be the same keypad address you set on your alarm panel. This setting will be used to configure your AlarmDecoder's ADDRESS configuration upon saving the plugin's configuration.
  - If you have more than one (1) alarm partition change the default of "1" to the number of partitions you have. If you are unsure, leave the setting as "1" partition.
8. Save the Configuration. **IMPORTANT:** this will save your plugin preferences in Indigo **AND** write/update the configuration on the AlarmDecoder.

### Quick Start - Upgrading the ad2usb plugin
1. Refer to Indigo's [Plugins Menu](https://wiki.indigodomo.com/doku.php?id=indigo_2021.2_documentation:getting_started#plugin_menus_in_indigo) documentation.
2. Go to Indigo's Plugins -> Manage Plugins menu
3. Look to see if ad2usb plugin has an upgrade and if it is compatible with your version of Indigo. If it has an upgrade:
  - Disable the ad2usb plugin
  - Download the latest version of the plugin if it is compatible with your version of Indigo
  - In the MacOS Finder, double-click on the downloaded plugin. Choose "Install and Enable"
  - Verify the new version of the plugin is running via the Plugins -> Manage Plugins menu. The running version number is shown after the plugin name.


### Plugin Configuration Details
It is recommended that you Disable and then Enable the Plugin after making Configure changes. A future release should resolve this issue.

#### AD2USB connection settings
- Select Local USB Port (for the AD2USB) or IP Network (for the AD2PI Network Appliance).
- For IP Network enter your IP address and port.

#### Operating parameters
- **Operate in advanced mode:** Most users will be fine with Basic Mode (the default). If Advanced Mode is needed enable it here.
  - Basic Mode - *TBP*
  - Advanced Mode - *TBP*

- **Log arm/disarm events:** Choose whether to log arm/disarm events. These events are logged with the log level of INFO and will only be visible in the logs if you log level setting are INFO or DEBUG.
- **Clear all Zone devices on plugin restart:** When selected all devices are set to Clear on restart of the plugin. This is the recommended setting. When set, if Indigo and your alarm panel are reporting not in sync then you can clear all faults on your alarm panel and then restart the plugin.
- **Number of Partitions:** Select the number of partitions for your alarm system. Refer to your alarm setup. The default of "1" is typical for most home installations.

#### AD2USB Device Configuration
These configuration parameters in this section will be written to the AlarmDecoder upon pressing the "Save" button if you have an IP based AlarmDecoder. This will overwrite whatever settings you have on your AlarmDecoder. You can also press the "Read ad2usb Config" (button) to read the current AlarmDecoder's configuration parameters into the Configuration dialog window.
- **Read ad2usb Config (button):** Pressing this button will attempt to read the current configuration parameters from the AlarmDecoder (IP only). It will replace the current settings in the Plugins Configure Dialog with the settings read from the AlarmDecoder.
- **Keypad Address:** Required. The keypad address assigned to the AlarmDecoder. Ensure to set this to the address you programmed on your alarm panel.
- **Remove duplicate messages:** If enabled, removes duplicate alphanumeric keypad messages.
- **Virtual Zone Expanders(s) (Max 2):** *TBP*
- **Virtual Relay Module(s):** *TBP*
- **Virtual Long Range Radio:** *TBP*

#### Log Configuration
- **Indigo Event Log Level**: See Logging section.
- **Plugin Log Level**: See Logging section.
- **Log Panel Messages**: See Logging section.

### Logging
There are three log files in the standard Indigo Library directory. Each has its own purpose and is described below.
1. **Indigo Event Log**: The first log is Indigo's event log file with file name format `YYYY-MM-DD Events`. The Indigo event log is used to log standard Indigo device events, actions, triggers, and plugins. It is configured and managed via Indigo and the plugin can write to it.
2. **Plugin Log**: The second log is the plugin's log file which is in a subdirectory with the same name as the plugin: `com.berkinet.ad2usb`. The log files are named using the format `plugin.log.YYYY-MM-DD`. The plugin log can be used to record detailed debug info for panel messages, AD2USB configuration details, and other panel and plugin specific information.
3. **Panel Message Log**: The third (optional) log file is in the same directory as the plugin log and named `panel.log`. It can be enabled via the Configuration menu. There are no logging levels associated with this log file. The panel log will log the messages received from your alarm panel by AlarmDecoder.

Logging levels for the Indigo and plugin log file can be modified in the plugin's configuration dialog. The information captured in each log file varies based on the logging level specified. Having separate settings allows you to capture detailed DEBUG details in the plugin's log but only log INFO messages to the Indigo log. Or for less verbose setting you can log INFO messages and above to the plugin's log bug only WARNING and above to Indigo's log. A summary of logging is below.

Log Level | Indigo Event Log & ad2usb Plugin Log |
--------- | ------------------------------------ |
CRITICAL | Only critical errors will be logged. Critical errors typically result in plugin failure and exit. This option will log the fewest entries.|
ERROR | Critical errors (see above) and non-fatal errors will be logged. Non-fatal errors should be investigated since the plugin may not behave has expected. They could be a result of configuration errors or plugin bugs.|
WARNING | In addition to critical and non-fatal errors, warnings will be logged. Warnings are neither fatal or critical but represent an unexpected condition that is logged.|
INFO | In addition to critical and non-fatal errors and warnings, this setting will log verbose information about the Indigo objects, the plugin, and the alarm panel. Startup, shutdown, and changes to Indigo devices, actions, and triggers will be logged. This log setting **is required** to log arm/disarm events. It is recommended this is the minimum log level for the plugin log and may be desired setting for the Indigo log for many users. |
DEBUG | In addition to all messages above, detailed debug messages will be logged. These messages are primarily used to understand the changes of internal variables, logic flow, and other details that can aid in the debugging process.|

## Helpful Troubleshooting Techniques

### Plugin and AlarmDecoder Version and Settings
Version 3.0.0 will log the Plugin and AlarmDecoder version and settings to the Indigo log window on startup. Please provide these details with any post on the User Forum.

### Enabling the log files
To be able to be supported you'll need to have some level of logging enabled. The recommended settings are:
1. Indigo Event Log - set to Errors, Warning, or Informational - any of those 3 settings will show any plugin errors in the Indigo Log
2. Plugin Log Level - set to "Verbose Debugging", this produces about +/-50MB log daily on a typical system but is essential. The filename is plugin.log.
3. Enable Log Panel Messages: Turn on. This log is +/-5MB daily. It is the raw panel messages from the decoder. The filename is panelMessages.log

The path for logs is `/Library/Application Support/Perceptive Automation/<Indigo Version Number>/Logs/com.berkinet.ad2usb`. Note that part of the file path is dependent on your version of Indigo.

### Reporting Bugs
Start by asking on the support forum. If more info is needed, I'll typically ask for this via a private message or email:

- Specify if it is a a USB or IP based AlarmDecoder
- AlarmDecoder VER and CONFIG settings. These are logged on startup in the Indigo Event log or can be found in the plugin log file.
  - Run the MacOS/Unix commands `grep VER plugin.log` and `grep CONFIG plugin.log` to get these settings. The most recent entries are what is needed.
- A copy of the `plugin.log` - typically ~500 lines before and after the ERROR entry or message that is causing the strange behavior is more than enough to understand the problem.
- A copy of the panel message log (`panelMessages.log`) - typically ~100 lines before and after the time of the ERROR will help isolate the messages and devices from your panel that caused the error.
