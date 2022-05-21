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
