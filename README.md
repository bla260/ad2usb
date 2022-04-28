# ad2usb Indigo Plugin

## About
**ad2usb** is a plugin interface to the NuTech AD2* alarm system interface for Honeywell's Ademco Vista line of alarm panels.

## About "*TBP*" in this README
There are still several items marked "To Be Published" (*TBP*) in this document. Each subsequent release will attempt to replace these *TBP* sections with more complete documentation for the plugin.

## Required Hardware
This plugin requires both a [NuTech Alarm Decoder](https://www.alarmdecoder.com) (AD2) alarm interface and an alarm panel. Both the NuTech AD2USB and AD2Pi are supported. This interface supports a broad range of alarm panels manufactured by **Honeywell** and sold under the **ADEMCO VISTA** brand name and similar panels sold by First Alert. The list of supported panels includes (see Note 1):

- VISTA-4110XM
- VISTA-15P
- VISTA-20P
- VISTA-21IP
- VISTA-40
- VISTA-50P
- VISTA-128BPT/VISTA Turbo Series (see Note 2)
- VISTA-250BPT/VISTA Turbo Series (see Note 2)
- First Alert-FA148CP
- First Alert-FA148CPSIA
- First Alert-FA168CPS
- First Alert-FA168CPSSIA

A more complete list is available from NuTech on their website. While the NuTech Alarm Decoder AD2* interface also supports alarm panels sold by DSC, this plugin is not tested with those panels. Users with DSC panels should look at the DSC Alarm plugin.

**Notes** :
1. While the panels listed should work, the developer testing for each release is limited to only on a VISTA-20P. Leverage the [Indigo ad2usb User Forum](https://forums.indigodomo.com/viewtopic.php?f=22&t=7584) to ask other users about their experience with your specific alarm panel model.
2. Works only in the plugin's basic mode

## Features

This plugin adds new Indigo options for **Devices**, **Actions**, and **Trigger Events**. See the [Indigo Overview](https://wiki.indigodomo.com/doku.php?id=indigo_2021.2_documentation:overview) for more information about Devices, Actions, and Triggers.

### Devices

The ad2usb plugin adds the following device options to Indigo.

Device Type | Description
----------- | -----------
ad2usb Keypad | The Alarm Decoder Keypad emulator. You should add one Indigo ad2usb Keypad Device which represents your NuTech Alarm Decoder device.
Alarm Zone | Standard alarm zone such as window or door sensors. Add one Indigo Alarm Zone device for each sensor you have configured with your alarm panel that you want to integrate with Indigo.
Zone Group | Creates a group of Alarm Zones. This allows you to create a group of alarm zones devices that can be used within Indigo Triggers.
Indigo Managed Virtual Zone | *TBP*

### Actions

The ad2usb plugin adds the following new Actions for **ad2usb Keypad** and **Alarm Zone** devices. You can use Indigo Actions to Arm & Disarm your panel and invoke panel events. Four types of Arm Actions are available. Refer to your Alarm Users Guide for description of each. You can also writes an arbitrary message to the panel via the keypad. **CAUTION:** Having detailed knowledge of your alarm panel's operation is recommended before configuring the Write to Panel action.

Keypad Actions | Description (refer to you Alarm Panel Users Guide)
-------------- | -----------
Arm-Stay | Performs the keypad function STAY. Arms perimeter zones only and entry delay is on.
Arm-Instant | Performs the keypad function INSTANT. Same as STAY, except entry delay is off.
Arm-Away | Performs the keypad function AWAY. Arms the entire burglary system, perimeter and interior. Entry delay is on.
Arm-Max | Performs the keypad function MAX. Same as AWAY, except entry delay is off.
Write To Panel | Writes an arbitrary message to the panel via the keypad. **CAUTION:** Having detailed knowledge of your alarm panel's operation is recommended before configuring this action.


Alarm Zone Actions | Description
------------------ | ----------
Force a zone state change | *TBP*
Change a virtual zone's state | *TBP*

### Trigger Events

In addition to the ability to add Triggers for Device state changes, the ad2usb plugin has several other events you can create Indigo triggers for.

Event | Description
----- | -----------
Panel Arming Events | Detect when your panel is Disarmed, Armed Away, or Armed Stay
System Status Event | Detect when your alarm panel has any of these system status events: AC Power Loss, AC Power Restore, Panel Battery Low, Panel Battery Restore, RF Battery Low, RF Battery Restore, Trouble, and Trouble Restore
Alarm Events | Detect when your panel has any of these Alarm events: Panic Alarm, Fire Alarm, Audible Alarm, Silent Alarm, Entry Alarm, Aux Alarm, Perimeter Alarm, Alarm Tripped: Countdown started
User Actions | Detect when an alarm panel user ID you specify has initiated any these events: Disarmed, Armed Stay, Armed Away. **NOTE:** These events require either a real or emulated LRR. More information is *TBP*.

## Configuration and Setup
See Indigo's [Managing Plugins](https://wiki.indigodomo.com/doku.php?id=indigo_2021.2_documentation:getting_started#managing_plugins) documentation for details on installing and upgrading plugins.

### Quick Start - First Install
1. Download the plugin from the Plugin Store
2. Double-click the plugin icon to install the plugin within Indigo. Choose "Install and Enable the Plugin"
3. Choose "AD2SUB Alarm Interface" from the Plugins menu and choose Configure.
4. Configure the plugin's IP address or Serial settings for communication to your Alarm Decoder.
5. Configure the plugin's Keypad address to be the same keypad address you set in Alarm Decoder and on your alarm panel.

### Quick Start - Upgrading the ad2usb plugin
1. Refer to Indigo's [Plugins Menu](https://wiki.indigodomo.com/doku.php?id=indigo_2021.2_documentation:getting_started#plugin_menus_in_indigo) documentation.
2. Go to Indigo's Plugins -> Manage Plugins menu
3. Look to see if ad2usb plugin has an upgrade and if it is compatible with your version of Indigo.
4. Disable the ad2usb plugin
5. Download the latest version of the plugin if it is compatible with your version of Indigo
6. In the MacOS Finder, double-click on the downloaded plugin. Choose "Install and Enable"
7. Verify the new version of the plugin is running via the Plugins -> Manage Plugins menu. The running version number is shown after the plugin name.


### AD2USB Configuration
*TBP*

### Basic Mode
*TBP*

### Advanced Mode
*TBP*

### Logging
Logging levels can be modified in the plugin's configuration dialog. There are two log files in the standard Indigo Library directory. The first is Indigo's event log file with file name format `YYYY-MM-DD Events`. The other file in a subdirectory with the same name as the plugin: `com.berkinet.ad2usb` and the files are named using the format `plugin.log.YYYY-MM-DD`. The Indigo event log can be used to log standard Indigo device events, actions, and triggers. The plugin log can be used to record detailed debug info for panel messages, AD2USB configuration details, and other panel and plugin specific information. The information captured in each log file varies based on the logging level specified. A summary of logging is below.

Log Level | Indigo Event Log | ad2usb Plugin Log
--------- | ---------------- | -----------------
CRITICAL | Critical errors will be logged. | Critical errors will be logged.
ERROR | Errors will be logged. | Errors will be logged.
WARNING | Warnings will be logged. | Warnings will be logged.
INFO | Startup, shutdown, and changes to Indigo devices, actions, and triggers will be logged. | All INFO messages will be logged.
DEBUG | Limited debug messages will be logged. | All DEBUG messages will be logged.
