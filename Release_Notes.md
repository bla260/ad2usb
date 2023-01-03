**IMPORTANT:** Version 3.0 and above requires Indigo 2022.1 or later and runs under Python 3. Read the version 3.0.0 release notes below first if you're upgrading from 1.x.

v 3.3.3 January 3, 2023
- Bug fix. "Write to Panel" Actions variable substitution did not work correctly. This has been fixed. Variables can be anywhere in the string/message (ex: "12346%%v:58295773%%"). 

v 3.3.2 January 1, 2023
- Bug fixes.
  - Fixed bug that prevented Keypad State `Zone Bypass List` from displaying correctly.
  - No longer report an error for AlarmDecoder messages when configuration is retrieved (`!UART` and `!Reading`).
- Changed error messages to warning messages when unknown AlarmDecoder messages are seen.

v 3.3.1 December 24, 2022 (replaced version 3.3.0)
- Added Time-Based One-Time Password Algorithm capability (OTP). Refer to the README on how to use this new capability for added security if you want to arm/disarm your alarm panel remotely using Indigo Touch or Indigo Client UI. This new feature requires the installation of one required and one optional, but recommended, Python modules. If you don't plan on using this capability; you do not need to install these modules and this release and future releases will continue to work. You need to restart the Indigo server after installing these modules.
  - PyOTP. Required for OTP functionality. 
  - qrcode. Optional for OTP functionality but required if you plan on generating a QRCODE image for easier setup on your mobile device.
- Major changes to Plugin Triggers and Events.
  - Triggers created for User Actions have several new features. You can now choose if the Event applies to any user or specific user(s). When listing specific users(s) you can continue to provide a single user code number (ex: `02`) or use the new feature of providing a comma seperated list of users (ex: `02,07,11,22`). The valid range for user numbers is 1 to 49. You can also provide an Indigo Variable as the user(s) in the format:`%%v:VARID%%` where `VARID` is the variable ID (ex: `%%v:1929322623%%`). The variable's value can contain one or more user codes.
  - **Panel Arming Events will be deprecated and removed in the next release**. Use the updated User Actions instead. A User Action with the new "Any User" setting is functionally the same as the Panel Arming Events. 
    - With this release any Triggers you have based on Panel Arming Events will not allow you to make changes to the Panel Arming Events details but they will continue to work. The Event Log will warn you that these type of Trigger Events exist on startup or execution of the Trigger. In a future release these type of events will be removed and your Panel Arming Event Triggers will cease to work. You can easily migrate these triggers as described next.
    - To migrate your existing Panel Arming Event Triggers simply change the Event from "Panel Arming Events (deprecated)" to "User Actions." The type of Alarm Event and Partition will be set based on the value of your Panel Arming Event setting and the new field "Any User" will be selected by default. Upon saving the Trigger as a User Action Trigger it will be migrated.
    - While you can rollback this release of the plugin, Panel Arming Events Triggers that were migrated will remain User Action Triggers after the rollback and you will need to manually change these back to Panel Arming Events.
  - Fixed two bugs that have existed since version 1.6.0 or earlier. I recommend you review the bug fixes below and then review and update your Triggers if needed before upgrading the plugin.
    - More than one Trigger for an event. If you had more than one Trigger defined for an event, when the event occurred only one of these Triggers would be executed. As of this version, **all** Triggers defined for an event will be executed. For example, if you had two Triggers defined for a Panel Arming Event of Disarmed, only one of these would be executed when the panel was Disarmed. With this release, both Triggers will be executed.
    - More than one Alarm Event per Trigger. The Trigger dialog box `Edit Event Settings...` has always allowed selection of multiple Arming, System, or Alarm Events. However, if multiple events were selected, the Trigger would only be run on the first selected event from the list. This bug has been fixed. Multiple events are now supported. For example, you can now have a single Trigger based on User Actions Events for both Arm Stay or Arm Away events that will be executed if either of those events occur.
  - New Events. A new event `Alarm Cancelled` has been added to User Action Triggers and new event `Interior Alarm` has been added to Alarm Event Triggers. The `Interior Alarm` event is only supported in the newer Alarm Decoder firmware version 2.2a.8.8.
- Added all the remaining Long Range Radio (LRR) events for processing triggers with the newer AlarmDecoder firmware version 2.2a.8.8 except for "ALARM AUX" which was not easily matched SAIC code. If you depended on this event, please post in the forum and I can work with you to identify the correct code. More details are below:
  - Events "Zone BYPASS" On/Off, "24 Hour Non-Burglary Zone" Fault/Clear, "Periodic test report", "Trouble", "Trouble Restore", "AC Power Lost" and "AC Power Restore" were tested and are now able to be processed and will no longer log WARNING messages. (NOTE: From my own testing and research, VISTA panels will only report "AC Power Lost" event after a random delay of up to 4 hours. Thus, most users may not find this feature useful. An alternative is to create a Device State Changed Trigger on the Keypad Device where the state "AC Power" becomes "Off" for loss of power; or "On" when power is restored).
  - New events "Interior Alarm" and "Alarm Cancelled" were tested and have been added as new Indigo Events which you can created Triggers from.
  - All of these remaining events have been added but have not been tested on an actual panel. The README will indicate which have been tested and which have not.
- Removed logging of leading four digit codes passed to the AlarmDecoder. This is to prevent any user codes from being in the event log and/or files. This setting can be overridden by unselecting the new Configure setting `Mask Alarm Codes` (checked by default). When masked, the log will replace the four digit code send to panel in the log with `CODE+` string. For example, when Disarming the logs will show `CODE+1`.
- Renamed menu items `Get AlarmDecoder Settings` to `AlarmDecoder - Get Settings` and `Get AlarmDecoder Firmware Version` to `AlarmDecoder - Get Firmware Version`
- Alarm Action "Write to Panel" can now use Indigo Variables.
- New Keypad State `Zone Bypass List` added. The value is a string with the list of zones that are bypassed (ex: "11,17,22")
- Replaced version 3.3.0 released the same day which had a minor bug in OTP key generation - that version has been removed.

v 3.2.1 September 5, 2022
- Changed Indigo ad2usb Keypad Device custom state "AC Power" (acPower) possible values from "1" or "0" to "On" or "Off". From my own testing any device change trigger you had created on this state change should migrate without any change.
- Added more Long Range Radio (LRR) events for newer AlarmDecoder firmware version 2.2a.8.8:
  - Now support "AC Power Lost" and "AC Power Restore" events. These LRR events will no longer log WARNING messages. (NOTE: From my own testing and research, VISTA panels will only report this LRR event after a random delay of up to 4 hours. Thus, most users may not find this feature useful. An alternative is to create a Device State Changed Trigger on the Keypad Device where the state "AC Power" becomes "Off" for loss of power; or "On" when power is restored).
  - Events for "Zone BYPASS" On/Off and "24 Hour Non-Burglary Zone" Fault/Clear will no longer log WARNING messages; however the plugin does not yet support creating Triggers on these LRR events.
- Added new Keypad Custom State 'Last AD2USB Msg Time' (lastADMessage) that shows the last time an AlarmDecoder message has been read. This is useful when away for extended periods to confirm the Plugin is still processing messages since other plugin device states typically do not change.
- Updated Keypad Device states names in the Trigger dialog from "Ready to Arm" to "Ready" and from "Faulted" to "Fault" for consistency.
- Fixed a bug preventing the Bypass state from being restored when a zone device is disabled and enabled.

v 3.2.0 August 18, 2022
- This version is the first to support both AlarmDecoder firmware versions 2.2a.6 and the newer version 2.2a.8.8. The use of the newer firmware could be considered a BETA since the Plugin isn't yet able to read all of the panel messages for Triggers Events when using the newer firmware. It has been released to allow the community to help determine all the newer panel message formats in order to ensure a timely future release can account for all of Trigger Events while using the newer firmware. Users of the older firmware should not have any concerns upgrading to this version.
- AlarmDecoder Firmware version 2.2a.8.8 is now supported but with some caveats on what Triggers can be detected with this version. With the help of this community, future versions should be able to expand the number of events that can be processed from the panel. Please read these release notes carefully before upgrading.
  - Background. Long Range Radio (LRR) message formats in the AlarmDecoder were changed from firmware version 2.2a.6 to the newer version 2.2a.8.8. The older firmware 2.2a.6 had 25 different LRR message types of which 18 are used by this plugin for possible Trigger Events you can configure (see the updated README section: Trigger Events for details on each event type). The new LRR message format in version 2.2a.8.8 firmware is now based on the SIA DC-05-1999.09 standard. This standard includes over 200 report codes/message types.  
  - Current limitation with this Plugin version and firmware 2.2a8.8. Not all possible events were tested on a panel prior to this release. At present only three (3) of the (18) Trigger Events in this plugin have been mapped to the newer LRR message formats: Arm Stay, Arm Away, and Disarm. The updated README also identifies which events are mapped and which are not yet mapped. **IMPORTANT:** If you upgrade to the newer firmware version any Triggers you have for events not yet identified and mapped to the new codes will **NOT** be executed.
  - Help is needed identifying and mapping the remaining codes. The remaining eight (8) codes that need to be identified for System Events are: AC Power Lost, AC Power Restore, Battery low, Battery Restore, RF Battery low, RF Battery Restore, Trouble, and Trouble Restore. The remaining seven (7) codes that need to be identified for Alarm Events are: Panic Alarm, Fire Alarm, Audible Alarm, Silent Alarm, Entry Alarm, Aux Alarm, and Perimeter Alarm. To aid in their identification a new logging option has been introduced with this version that will log any unknown LRR messages to the Indigo Event Log Console to help facilitate mapping these LRR messages to existing Trigger Events in future releases of this plugin. Please post any of these warning messages in the User Forum so the new message codes can be readily identified and added to the Plugin.
- Changes to the Configure Dialog
  - Renamed the section "Log Configuration" to "Logging Options".
  - Moved "Log Arm/Disarm events" option to the "Logging Options" section.
  - Added new setting option: "Log Unknown LRR Messages." This setting has been added to help identify all the different panel messages with the newer AlarmDecoder firmware. It is turned on by default. It will log unknown Long Range Radio (LRR) reporting events to the Indigo Event log as WARNING messages. An LRR message is considered "unknown" if this Plugin does not have a corresponding Trigger Event for that message.
- New Zone Device state added. A new device state `lastFaultTime` has been added that will show the last date and time the zone had a Fault.
- Updated README provides a more detailed explanation of Trigger Events and now has a Table of Contents.

v 3.1.0 August 6, 2022
- Changes to Alarm Keypad (ad2usb Keypad) device.
  - Changes to the Alarm Keypad Ready/Armed states. Internal to the plugin, the device state `displayState` for keypad devices has been removed. If you have any Indigo Trigger Types of "Device State Changed" based on the AD2SUB Alarm Keypad Device states `Alarm State Changed...` (usually the first options in the Trigger pull down) you should disable these Triggers before upgrading and then edit and re-save each of these Triggers after upgrading. Other Triggers based on ad2usb Keypad states other than `Alarm State Changed` are not impacted by this change.
  - Alarm Keypad (ad2usb Keypad) Device State. In version 3.0.0 the list of valid states were: Ready (Not Armed), Fault, Armed Stay, Armed Away, and Error. Additional states Armed Night-Stay, Armed Instant, and Armed Max have been added. Refer to your alarm panel guide for more information about these states.
  - Multiple Keypad Devices. Read the updated README for information about the rules and behavior for multiple ad2usb Keypad devices. In summary, you can have one ad2usb Keypad Indigo device per partition and should have one, and only one, ad2usb Keypad Indigo device associated with the keypad address of the AlarmDecoder.
- Clear All Zones Devices configuration setting. The behavior for this setting has changed. When this option was selected all AD2SUB Alarm Interface devices are set to Clear/Ready on restart of the plugin. There is no change in that behavior. What is new is now AD2SUB Alarm Interface devices are also set to Clear/Ready when enabling communication for a single device. Thus, if a single Indigo AD2SUB Alarm Interface device is out of sync with your alarm panel you can first clear the fault for that zone on your alarm panel and then disable and re-enable communications for that device in the Indigo Client UI and it will reset the state to Clear.
- AlarmDecoder Configuration is now under its own Menu. The AlarmDecoder configuration options have been removed from the Plugin Configure menu to its own menu making a clear separation of when you are changing your Plugin settings versus writing new settings to the AlarmDecoder. With the exception of the keypad address, AlarmDecoder configuration settings are no longer stored as Preferences. The reason for this was several fold, most importantly to not have the Plugin depend on saved AlarmDecoder settings that could be changed at anytime via changes to the AlarmDecoder from a program other than the Plugin. Instead, whenever the Plugin sees a new CONFIG confirmation message it will read the current settings of the AlarmDecoder and update the needed properties and settings.
- New Menu Options. There are two new menu options in the Plugins, A2USB Alarm Interface menu. The menu **Get AlarmDecoder Settings**, will send a CONFIG (Settings) message to your AlarmDecoder. The menu **Get AlarmDecoder Firmware** Version will send a VER (Firmware Version) message. The next time either of these messages are read they will be logged in the Event Log.
- Added automatic connection reset when the Plugin loses communication with the AlarmDecoder.
- Fixed a bug when a zone number is not a numeric in the Keypad Message. This would typically result in an error message `Error:invalid literal for int() with base 10:`
- Internal. More changes to the new AlarmDecoder message parsing methods. `EXP` messages are now parsed using the new methods. Please post in the User forum if there are any new `WARNING` messages in the Indigo Event Log. Read the release notes from version 3.0.0 for more background.
- The Plugin forum was moved on July 25th. The About Plugin menu in Indigo now redirects to the new Indigo forum for this plugin.
- Updated README. Even long time users should (re)read the README to review the changes.

v 3.0.0 July 11, 2022
- **IMPORTANT:** Python 3 version. Requires Indigo 2022.1 or later.
- **MORE IMPORTANT:** This is a major release. Numerous internal changes were required for Python 3 compatibility. Extensive internal changes were made in this release to facilitate more thorough testing in this and future releases. While this release has been tested more than others, not all code paths have been tested. Please see [this section of the README](https://github.com/bla260/ad2usb#helpful-troubleshooting-techniques) for guidance on how to get assistance and the log file settings and entries that may be needed.
- Changed "Battery" to "RF Battery" in Trigger System Status Events to distinguish it from the Alarm Panel's Battery
- Bug fix with Virtual Zones that caused a `KeyError` after a plugin restart when a Virtual Zone is the first zone to Fault before any standard Alarm Zone.
- Internal. Added new AlarmDecoder message parsing methods. In this release, these new methods are used to read the `CONFIG`, `VER`, and `LRR` messages, all other AlarmDecoder message types are parsed only for the purpose of logging WARNING messages (not an error) to the log files if the new parsing encounters any messages from your AlarmDecoder that the new parsing method is unable to read. This change and these WARNING messages are in preparation for future plugin compatibility with the latest AlarmDecoder firmware version. Warnings messages will be in the format `Unable to parse: REASON - message:MSG` where `REASON` and `MSG` will be an internal reason and the AlarmDecoder message respectively. Please report any of these warning messages in the [User Forum](https://forums.indigodomo.com/viewtopic.php?f=22&t=7584).
- Long Range Radio (LRR) messages (firmware version V2.2a.6 format) processing changes were made to use new message parsing.
- Added reading of the AlarmDecoder firmware version and settings on startup using new parsing methods (see below). This change is in preparation for compatibility with the newer AlarmDecoder firmware versions. The firmware version and CONFIG settings of the AlarmDecoder will be logged as INFO messages on startup. If the Plugin is identifies and incompatible version of the firmware version **it may not start**. Currently, only the firmware version V2.2a.6 is compatible with the Plugin.
- Updated README documentation.

v 1.8.2 June 2, 2022
- Summary: this is a maintenance release to fix two bugs with Indigo Managed Virtual Zones.
- Fixed bug `KeyError: key vZonePartitionNumber not found in dict` which would appear as an ERROR in the logs when a Virtual Zone's state changed.
- Fixed bug `exception in deviceStartComm(...): 'key logSupervision not found in dict'` that would appear as an ERROR in the log on startup.
- **IMPORTANT:** if this release causes new errors in Virtual Zones that have worked for some time you should edit and re-save all of your Virtual Zone devices or delete and recreate them. This is likely due to property changes for Virtual Zones made after they were created.

v 1.8.1 May 26, 2022
- Summary: this is a maintenance release to add some improvements to logging and one bug fix.
- Fixed bug `basicBuildDevDict error: basicBuildDevDict() takes exactly 4 arguments (3 given)` and `advancedBuildDevDict error: advancedBuildDevDict() takes exactly 4 arguments (3 given)` which would appear in ERROR log during plugin shutdown or restart.
- Updated plugin log file (`plugin.log`) format to include thread ID for better debugging.
- Updated README documentation

v 1.8.0 May 21, 2022
- Summary: In many ways this is the BETA release for planned version 3.0 to be compatible with Indigo 2022.1 and Python 3. This release is mostly internal changes. Visible changes include how Bypass states are displayed in the client UI and the Trigger selection options for Alarm Device state changes.
- AlarmDecoder Communications. In preparation of Python 3 all plugin communication to/from the AlarmDecoder have been rewritten. While these change should be transparent they were significant. All panel reads and writes and the plugin Configure Dialog (including the "Read ad2usb Config" button) were revised.
- Zone Group was refactored to always get a group's device state from Indigo versus a local cache.
- Changes to Device States. Alarm Zone Device, Zone Group Device, and Indigo Managed Virtual Zone Device states have been updated. **If you have any Triggers on Device State changes please read carefully.**
  - Alarm Zone and Indigo Managed Virtual Zone devices now have these three state variables with possible values shown in parenthesis: `zoneState` (Fault or Clear), `onOffState` (On or Off), and `bypassState` (On or Off).
  - There is no functional change to `zoneState` and `onOffState`. Any triggers on changes to these states should not require updates after upgrading to this version.
  - The device state `bypassState` has been changed from a `string` to an Indigo state property `boolean` type with values of On or Off. Any Triggers you have the were based on changes to `bypassState` will likely need to be updated to use the new state values. Zone Groups do not have `bypassState` so this only applies to Alarm Zone and Virtual Zone devices.
  - The device state `displayState` has been removed. If you had any Triggers based on changes to `displayState` they will need be updated to use one of the other states.
  - Indigo Client UI display of Alarm Zones in Bypass state. When an Alarm Zone is set to Bypass = On it will display the generic Indigo "Sensor Off" icon (grey circle) and the text "Bypass" in the Indigo Client UI. Bypassed zones do not Fault on the panel and thus will not change state even if the sensor is tripped.
- Corrected minor errors in several log messages
- Updated README documentation

v 1.7.1 May 11, 2022
- Requires Indigo 7.0 or later
- Changes to logging. Logging is now done via [Indigo's logging API](https://wiki.indigodomo.com/doku.php?id=indigo_2021.2_documentation:plugin_guide#logging) which uses Python's standard logger facility. There are now two logging level options in the Configuration dialog. One is for the Indigo Event log and the other is for the separate plugin log. This allows you to have your Indigo Event log at a different log level than the dedicated plugin log file. For example, you can keep the plugin log at DEBUG to capture verbose details while setting the Indigo Event Log to INFO to not overwhelm the Indigo logs. Your previous plugin log settings will be migrated as follows: None (0) is converted to ERROR. Normal (1) and Verbose (2) are converted to INFO. Debug (3) and Intense Debug (4) are converted to DEBUG. Note that if you downgrade or rollback to version 1.6.1 after upgrading to this version your log settings will be reset to the 1.6.1 default of Normal (1). See the updated plugin's store "About" page or the [README on the GitHub page](https://github.com/bla260/ad2usb) for details about the logging levels.
- Added new Panel Message Log. In addition to the logging changes above you can now optionally set via the Configuration a new log file that is written to in the same directory as the plugin's log file. This file is an alarm panel message log. If enabled, the messages AlarmDecoder receives are logged in this file. Thirty (30) days of panel messages are kept. The log file format is a simple timestamp and message.
- Corrected a typo in Devices.xml that may have resulted in keypad device not having a valid default partition number on initial creation of the device. This likely only impacted new installations.
- Corrected some errors around Zone Group states being displayed for new Zone Groups and when a Zone Group change states. There are still some error messages in the logs that indicate there are likely issues when Zones are deleted but still exist in Zone Groups and when Zone Groups are deleted. Most of these would likely be resolved by restarting the plugin. These potential issues will be addressed in a future release.
- Removed the Configuration settings and the associated feature for receiving notification of plugin updates via email. Indigo provides plugin update information within the application's Plugin, Manage Plugins menu.
- Internal code change to error handing `except` syntax to support Python 2 and 3.
- Updated **README** to add more documentation. The README can be found on GitHub or the About page of the Plugin Store for this plugin.
- Updated **Release Notes** to be a markdown document in the root of the GitHub directory for easy access.

v1.6.1 Apr 1, 2022
- First release on GitHub - functionally identical to 1.6.0

v1.6.0 Nov 26, 2017
- Startup now creates zoneDicts for both basic and advanced mode.
- Added support for zone bypass state tracking (bypassState) and UI state column display.
- Corrected a bunch of spelling errors in these notes.
- Added pass through logging for panel errors.
- Fixed readline() error in read config.

v1.5.5 Mar 10, 2014
- Turned off debugging in validateDeviceConfigUi

v1.5.4 Mar 10, 2014
- Changed coding on events triggered by user number to support 3 digits
- Revised debugging in advanced message read.
- Advanced read: Added error handling for attempts to clear a zone that was not faulted - I.e. on startup.
- Changed code to accept non decimal "zone" numbers in large panels
- Fixed bug where zone onOffState was not updated in basic mode

v1.5.3 Dec 19, 2013
- Added code to detect dropped network connection in panelMessageRead() and do automatic retries

v1.5.2 Dec 8, 2013
- Changed plugin property panelPartitionNumber to panelPartitionCount
- Fixed logic bug in device config verification that prevented some users from upgrading

v1.5.1 Dec 8, 2013
- Fixed bug in work-around code for missing properties.

v1.5.0 Dec 7, 2013
- Added code to trap the cases where a keypad device does not contain panelPartitionNumber or ad2usbKeyPadAddress
- Modified error reporting to skip null (usually on reboot) and SER2SOCK connection messages.
- Fixed bug with single partition systems in the main panel read method.

v1.0.4t Dec 2, 2013
- Fixed a small issue where wireless supervision messages triggered zone group update messages even though no change had occurred.
- Fixed a small issue where group zone change messages were printed even when no state change occurred.
- Fixed bug that prevented startup after upgrade from 1.0.4 to 1.0.4s

v1.0.4s Nov 22, 2013
- Fixed an error in quick arm actions that reversed stay and away
- Added event support to basic mode
- Added ALARM_TRPPED event. Starts when entry countdown timer starts.

v1.0.4r Nov 21, 2013
- Restored onOffState state for compatibility with other plugins (like the Group Trigger plugin)
- Added events for RFLOWBATT and RFLOWBATT_RESTORE
- Made a change in the panel message routine that prevented writes to keypad devices low numbered addresses.

v1.0.4q Nov 20, 2013
- Added events

v1.0.4p Nov 19, 2013
- Fixed issue with logging changes in un-numbered, non-enrolled wireless zones
- Changed display control for panel keypad device address selection to offer the keypad pulldown if there is more than 1 partition
- Resolved issue in selecting second keypad in multi-partition system

v1.0.4n Nov 18, 2013
- Revised device config verification keypad address heuristic

v1.0.4m Nov 18, 2013
- Added error detection if more than one partition is addressed in panel messages

v1.0.4l Nov 18, 2013
- Added option to show/hide arming events in the Indigo log.
- Improved Plugin configuration organization and on-screen information.
- Fixed zone state display for virtual zones.
- Bug: In Advanced mode, if virtual zones are included in a Zone group, the zone group will not be updated on changes in the virtual zone.

v1.0.4k Nov 17, 2013
- Fixed a bug in basic setup mode.
- Added the operations mode to the startup log message

v1.0.4j Nov 16, 2013
- Fixed problem created in 1.0.4g in LRR message handling and reporting.

v1.0.4i Nov 16, 2013
- Added zone groups

v1.0.4h Nov 15, 2013
- Changed zone addresses to have a leading zero if < 10
- Fixed bug in panel arming actions.
- Added action to force a zone state device to clear or faulted
- Added an Advanced Mode option for wireless zones to invert the sense of the input.

v1.0.4g Nov 15, 2013
- Changed "Indigo Alarm Zone" to "Indigo Managed Virtual Zone".
- Changed 'state' state to 'panelState'
- Added state 'armedState' (one of: unArmed, armedStay, armedAway, armedMax or armedInstant)
- Added support for up to 8 partitions
- Added actions to armMax and armInstant
- Added support for DEVICES address column display of keypadaddress or zone number
- Added travis' update checker class
- Deleted state 'onOffState.' Added state 'displayState' and set displayState as the UiDisplayStateId
- Added panel state: zoneFaultList to display all faulted zones
- Note: All ad2usb devices must be redefined after installing this update.

v1.0.4 Jul 22, 2012
- Fixed bug in ConfigButtonPressed.

v1.0.3 Jul 17, 2012
- Fixed bug in config code length check.

v1.0.2 Feb 19, 2012
- Added option to force all zone devices to clear on restart.

v1.0.1 Feb 19, 2012
- Added code to trap older firmware that cannot use auto-config.

v1.0.0 Feb 10, 2012
- First release.
- When used with Indigo 5.0.4 resolves lost ser2sock connection issue.

v0.9.23 Feb 03, 2012
- Added Arm-Stay and Arm-Away actions.
- Added partition selection menu to zone device dialogs. This is not currently working, but will enable future support for multiple partitions.
- Fixed problem with basic mode on commercial (50, 128, etc.) panels.
- Restart on mode or interface change works if using Indigo 5.0.3.

v0.9.22 Jan 12, 2012
- Fixed a bug in the LRR configuration option.
- Revised RFX zone state checking to use a full bitmap mask.
- Added test for new zones to create initial state of Clear.

v0.9.21 Jan 9, 2012
- Minor cosmetic changes in Advanced zone Device dialog.
- Removed error messages when changing from basic to advanced mode.
- Revised auto config and validation to resolve USB issues.

v0.9.20 Jan 3, 2012
- Fixed bug in basic mode fault clearing.
- Made the release notes visible in the release package (linked).

v0.9.19 Dec 22, 2011
- Changed to use states['onOffState'] for compatibility.
- Fixed bug in USB port selection.

v0.9.18 Dec 22, 2011
- Added extended debugging in panel write method.
- Fixed bug in connection sharing.

v0.9.17 Dec 21, 2011
- Fixed a small bug in the response to "HIT * FOR..." messages.
- Added a 32bit binary for ser2sock.

v0.9.16 Dec 20, 2011
- Added version checking on startup.
- Added ability to read config from ad2usb in plugin config.

v0.9.15 Dec 16, 2011
- Fixed a bug in basic mode handling of onState setting.
- Cleaned up the code to Pythonize it a bit more and remove a few global variables.
- Added support information for launchctl.

v0.9.14 Dec 14, 2011
- Fixed a bug in USB Port setting.
- Added support for Meta-Triggers plugin.

v0.9.13 Dec 13, 2011
- Fixed a bug in keyboard address setting validation.
- Revised some labeling for clarity.

v0.9.12 Dec 09, 2011
- Added iPad keypad control page demo.
- Added AC/Batt display to iPhone keypad.

v0.9.11a Dec 08, 2011
- Fixed bug that prevented * from being sent.

v0.9.11 Dec 08, 2011
- Revised detection of "Press * for Faults" messages for improved message handling in advanced mode.

v0.9.10 Dec 03, 2011
- Changed demo control page keypad to display a "zones bypassed" lamp.
- Added validation for USP port option to plugin preferences.
- Added support for setting the ad2usb configuration. The config options available depend on the plugin mode: advanced or basic.
- Fixed serious bug in detection of "Press * to show faults" message.
- Known issues:
- When changing operating modes in the plugin config dialog, a series of AD2USB Alarm Interface Error messages like "exception in deviceStopComm(..." may be logged to the Indigo log. These can be ignored.
- Occasionally, when changing plugin config prefs, an AD2USB Alarm Interface Error: "plugin runConcurrentThread function returned or failed; will attempt again in 10 seconds" may be logged to the Indigo log. This can be ignored.
- On first setup the plugin config dialog cannot read the actual config from the ad2usb board and the ad2usb board config options will all be set to defaults. After the ad2usb board has been configured, the plugin will remember the config settings.

v0.9.9 Dec 01, 2011
- Added alarmedZone as state item for device type alarmPanel
- When the panel is in an alarmed state, this will indicate the zone that tripped the alarm and log a message to the indigo log.
- Reduced the verbosity of debug mode.
- Changed the panel device name from alarmKeypad to ad2usbInterface.
- Added code to allow use with no alarm zone devices.
- Fixed bug in writing to the panel.
- Added support for panel lights (Ready/Armed)
- Added an example keypad control page (pro only)

v0.9.8 Nov 29, 2011
- Bug fixes in USB support

v0.9.7 Nov 28, 2011
- Added basic mode, virtual zones and F-key support. Improved restart after config change

v0.9.4-0.9.6 Nov 21 to Nov 27, 2011
- Internal releases. Bug fixes and code optimization.

v0.9.4 Nov 21, 2011
- Various bug fixes with IP Address validation and IP port setting.

v0.9.0 Nov 19, 2011
- First public release. Required REL, EXP and RFX message support
