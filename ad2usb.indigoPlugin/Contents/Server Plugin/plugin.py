#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# ad2usb Alarm Plugin
# Originally developed Richard Perlman -- indigo AT perlman DOT com

import logging  # needed for CONSTANTS
from datetime import datetime
import os
import re
import time
import serial
import sys
import indigo   # Not needed. But it supresses lint errors
from ad2usb import ad2usb
import AD2USB_OTP
import AD2USB_Constants  # Global Constants

################################################################################
# Now, Let's get started...
################################################################################


class Plugin(indigo.PluginBase):
    ########################################
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        # assume some logger exists
        self.logger.debug(u"called with id:{}, name:{}, version:{}".format(pluginId, pluginDisplayName, pluginVersion))
        self.logger.debug(u"preferences:{}".format(pluginPrefs))

        # check and set the python version first
        # TO DO: remove in 3.1
        try:
            self.pythonVersion = sys.version_info.major
        except Exception as err:
            self.logger.warning(u"Unable to determine Python version 2 or 3; assuming 3. Error:{}".format(str(err)))
            self.pythonVersion = 3

        # set the default debug playback file name and status
        self.panelMessagePlaybackFilename = indigo.server.getLogsFolderPath(
            pluginId=self.pluginId) + "/" + "panelMessagePlayback.txt"
        self.isPlaybackCommunicationModeSet = False  # flag for settings in Configure

        # call method to upgrade (if needed) and get preferences
        # this method will set several properties of plugin based on prefs
        # need to do this before any logging to set logging levels
        self.__upgradeAndGetPreferences(pluginPrefs)

        # set logging levels
        self.__setLoggingLevels()

        # set the URL and AlarmDecoder Config: configSettings
        # these are computed after we've fetched preferences and set plugin properties
        self.URL = ''
        self.configSettings = {}

        try:
            self.__setURLFromConfig()

        except Exception as err:
            self.logger.critical(
                "URL is not set - Use the Plugins Config menu to configure your AlarmDecoder settings. Error:{}".format(str(err)))
            self.logger.critical("Error:{}".format(str(err)))

        # if the preferences are set to log panel messages initialize the log file
        if self.isPanelLoggingEnabled is True:
            self.logger.info("Panel logging is enabled")
            self.__initPanelLogging()

        # init other properties
        self.faultList = []
        self.lastZoneFaulted = 0
        self.zonesDict = {}
        self.advZonesDict = {}
        self.virtualDict = {}
        self.zoneGroup2zoneDict = {}
        self.zone2zoneGroupDevDict = {}
        self.triggerCache = {}

        self.pluginDisplayName = pluginDisplayName
        self.pluginPrefs = pluginPrefs

        self.isThisFirstStartup = True
        self.hasAlarmDecoderConfigBeenRead = False
        self.previousCONFIGString = ''
        self.showFirmwareVersionInLog = True

        self.previousOTPValues = []
        self.OTPAttempts = []

        # adding new logging object introduced in API 2.0
        self.logger.info(u"Plugin init completed")

     ########################################
    def __del__(self):
        indigo.PluginBase.__del__(self)

    ########################################################
    # plugin startup (initialization) and shutdown
    ########################################################
    def startup(self):
        self.logger.debug(u"called")

        self.zonesDict = {}
        self.advZonesDict = {}

        mode = 'Basic'
        if self.ad2usbIsAdvanced:
            mode = 'Advanced'

        self.isThisFirstStartup = True

        # initilizae the ad2usb object with the plugin as a parameters
        # ad2usb init will:
        # opens communication
        # gets the firmware version and log it
        # get the current configuration of the board and log it and change the preferences in memory
        self.ad2usb = ad2usb(self)

        # create an OTP object - this should work regardless of OTP module status
        self.otp = AD2USB_OTP.OTP(folderPath=self.OTPConfigPath, logger=self.logger, isEnabled=self.isOTPEnabled)

        # monitor variable changes
        indigo.variables.subscribeToChanges()

        # remove this in later version - added in 3.3.0 to help migrate Panel Arm Events:
        # modigied in version 3.4.0 to throw and error and tell user to delete the Trigger
        self.__migratePanelArmTriggers()

        self.logger.info(u"Plugin startup completed. Ready to open link to the ad2usb in {} mode.".format(mode))

    ########################################################
    def shutdown(self):
        self.logger.debug(u"Called")

        self.ad2usb.stopAD2USBComm()

        self.logger.info("Plugin shutdown completed")

    ########################################################
    # device setup/shutdown Calls from Indigo
    ########################################################
    def deviceStartComm(self, dev):
        self.logger.debug(u"called with Name:{}, id:{}, TypeId:{}, clearAllOnRestart:{}".format(
            dev.name, dev.id, dev.deviceTypeId, self.clearAllOnRestart))

        # Always load the basic Dict because we need a zone number to device lookup in advanced mode too.
        self.basicBuildDevDict(dev, 'add', self.ad2usbKeyPadAddress)

        if self.ad2usbIsAdvanced:
            self.advancedBuildDevDict(dev, 'add', self.ad2usbKeyPadAddress)

        # migrate for version 1.8.0 state from old displayState to zoneState
        # migrate for version 3.2.0 to add lastFaultTime
        if ((dev.deviceTypeId == 'alarmZone') or (dev.deviceTypeId == 'zoneGroup')
                or (dev.deviceTypeId == 'alarmZoneVirtual')):

            # migrate for version 1.8.0 state from old displayState to zoneState
            if dev.displayStateId == 'displayState':
                # refresh from updated Devices.xml
                self.logger.info(u"Upgrading states on device:{}".format(dev.name))
                self.logger.debug(u"current device:{}".format(dev))
                dev.stateListOrDisplayStateIdChanged()
                self.setDeviceState(dev, AD2USB_Constants.k_CLEAR)
                self.logger.debug(u"revised device:{}".format(dev))

            # migrate for version 3.2.0 to add lastFaultTime
            localStates = dev.states
            if 'lastFaultTime' not in localStates:
                dev.stateListOrDisplayStateIdChanged()

            # migrate for version 3.3.4 to add lastBatteryRestore
            if (dev.deviceTypeId == 'alarmZone'):
                localStates = dev.states
                if 'lastBatteryRestore' not in localStates:
                    dev.stateListOrDisplayStateIdChanged()

        if dev.deviceTypeId == 'ad2usbInterface':

            # migrate for version 3.1.0 state from old displayState to panelState
            if dev.displayStateId == 'displayState':
                # refresh from updated Devices.xml
                self.logger.info(u"Upgrading states on device:{}".format(dev.name))
                self.logger.debug(u"current device:{}".format(dev))
                dev.stateListOrDisplayStateIdChanged()
                self.setKeypadDeviceState(dev, AD2USB_Constants.k_PANEL_READY)
                self.logger.debug(u"revised device:{}".format(dev))

            # migrate for version 3.2.1 to add lastFaultTime and acPower
            # migrate for version 3.3.0 to add zonesBypassList
            # migrate for version 3.4.0 to add homeKitState
            localStates = dev.states
            if ('lastADMessage' not in localStates) or ('zonesBypassList' not in localStates) or ('homeKitState' not in localStates):
                dev.stateListOrDisplayStateIdChanged()

        # if clear all devices is set or a new device clear the devices with zoneState state
        if ((dev.deviceTypeId == 'alarmZone') or (dev.deviceTypeId == 'zoneGroup')
                or (dev.deviceTypeId == 'alarmZoneVirtual')):

            # if the no current state or we want to clear on restart
            if dev.displayStateValRaw == "" or self.clearAllOnRestart:
                self.setDeviceState(dev, AD2USB_Constants.k_CLEAR, True)  # True for ignore Bypass

        # if its an alarmZone or virtualZone device check if the device
        # is marked as bypass in Indigo and load or del the cache
        # zone bypass cache is not kept for new starts so bypass state should not
        # be set on plugin restart
        if ((dev.deviceTypeId == 'alarmZone') or (dev.deviceTypeId == 'alarmZoneVirtual')):
            try:
                validZoneNumber = int(dev.pluginProps['zoneNumber'])
                if self.isDeviceBypassed(dev):
                    # add to bypass list if not present
                    if validZoneNumber not in self.ad2usb.listOfZonesBypassed:
                        self.ad2usb.listOfZonesBypassed.append(validZoneNumber)
                else:
                    # remove from bypass list if present
                    if validZoneNumber in self.ad2usb.listOfZonesBypassed:
                        self.ad2usb.listOfZonesBypassed.remove(validZoneNumber)

            except Exception as err:
                self.logger.warning(u"unable to determine zone number for device:{}, err:{}".format(dev.name, str(err)))

        self.logger.info(u"Device startup completed for {}".format(dev.name))

    ########################################################
    def deviceStopComm(self, dev):
        self.logger.info(u"called with Name:{}, id:{}, TypeId:{}".format(dev.name, dev.id, dev.deviceTypeId))

        # We always load the basic Dict because we need a zone number to device lookup in advanced mode too.
        try:
            self.basicBuildDevDict(dev, 'del', self.ad2usbKeyPadAddress)
        except Exception as err:
            self.logger.error(u"basicBuildDevDict error: {}".format(err))

        if self.ad2usbIsAdvanced:
            try:
                self.advancedBuildDevDict(dev, 'del', self.ad2usbKeyPadAddress)
            except Exception as err:
                self.logger.error(u"advancedBuildDevDict error: {}".format(err))

        self.logger.info("Device stop completed for {}".format(dev.name))

    ########################################################
    # start/stop/restart Calls from Indigo
    ########################################################
    def runConcurrentThread(self):
        try:
            # add some dumps of internal dictionaries
            self.logger.debug("Trigger Cache:{}".format(self.triggerCache))
            self.logger.debug("Advanced Device Dict:{}".format(self.advZonesDict))

            self.logger.info(u"AlarmDecoder message processing started")

            # check if this is a fresh start versus runConcurrentThread being called
            # a second time in the same instance
            if self.isThisFirstStartup:
                # if so - clear all devices if the properties flag is set
                if self.clearAllOnRestart:
                    self.__clearAllDevices(includeDisabled=True)

                # reset the first start flag - is reset to True in init and startup
                self.isThisFirstStartup = False

            # when runConcurrentThread starts set the flag to start reading messages
            self.ad2usb.stopReadingMessages = False
            failedCounter = 1

            while True and (failedCounter < 50):
                # is communicaiton to AlarmDecoder OK?
                if self.ad2usb.isCommStarted:
                    self.logger.debug('AlarmDecoder comm has successfully started, will attempt to read message...')

                    # reset failed counter
                    failedCounter = 0

                    # call the old message Read functon which tests messages in new parser
                    if self.ad2usb.stopReadingMessages:
                        self.logger.warning('Reading of panel messages has been stopped...')
                    else:
                        # add code to ensure we have 1 keypad device before reading
                        # errors are generated in the method if no keypad exists
                        if len(self.getAllKeypadDevices()) > 0:
                            self.ad2usb.panelMsgRead(self.ad2usbIsAdvanced)

                    # TO DO: FUTURE
                    # newMessage = self.ad2usb.newReadMessage()
                    # if newMessage.needsProcessing:
                    #   self.newProcessMessage(newMessage)

                # else we had a comm failure
                else:
                    # try to open the communication again with force reset
                    if self.isPlaybackCommunicationModeSet and self.hasPlaybackFileBeenRead:
                        self.logger.warning("Finished reading panel playback file")
                    else:
                        self.logger.error(
                            'Unable to communicate with AlarmDecoder ({} times) - attempting to reconnect...'.format(failedCounter))

                    failedCounter += 1

                    if not self.ad2usb.setSerialConnection(True):
                        # next try to start comms again with VER and CONFIG
                        self.logger.error('Unable to re-establish communications - resetting communications...')
                        if not self.ad2usb.startAD2USBComm():
                            self.logger.error(
                                'Unable to re-establish communications - check AlarmDecoder and Plugin Configure settings')

                # built in sleep
                self.sleep(0.5)

            # failed counter > 50
            self.logger.error('AlarmDecoder communication fail count exceeded 50 consecutive times')

        except self.StopThread:
            self.ad2usb.stopReadingMessages = True
            self.logger.info('AlarmDecoder StopThread received')
            pass    # Optionally catch the StopThread exception and do any needed cleanup.

        except Exception as err:
            self.logger.critical("Error reading and processing AlarmDecoder messages - error:{}".format(str(err)))

        self.logger.info(u"runConcurrentThread completed")

    ########################################################
    # def stopConcurrentThread(self):
    #     self.logger.debug(u"Called")
    #
    #     # TO DO: rename this property to stopReadingMessages
    #     self.ad2usb.shutdown = True
    #     self.stopThread = True
    #
    #     self.logger.info(u"StopConcurrentThread completed")

    ########################################################
    # TO DO: This method is never called
    def restart(self):
        self.logger.debug(u"Called")
        self.logger.debug('do nothing')

        # TO DO: remove some of these log entry once startComm and stopAD2USBComm has logging
        # self.logger.info(u"Stopping")

        # self.ad2usb.stopAD2USBComm()
        # self.sleep(5)

        # self.logger.info(u"Starting")
        # self.ad2usb.startComm(self.ad2usbIsAdvanced, self.ad2usbCommType, self.ad2usbAddress, self.ad2usbPort, self.ad2usbSerialPort)

        # self.logger.info(u"completed")

    ########################################################
    # Action callbacks
    ########################################################
    def virtZoneManage(self, pluginAction):
        """
        Does three things:
        1. Updates the Indigo device state for the Virtual Managed Indigo device
        2. Sends a message to the AlarmDecoder via the 'L' command.
        3. Updates the Keypad device for the partition of the device
        """
        self.logger.debug(u"call with:{}".format(pluginAction))

        try:

            # part 0 - setup - get device ID, device zone as a padded string, and device partition
            devId = pluginAction.deviceId
            virtDevice = indigo.devices[devId]
            virtZoneNumber = self.__getPaddedNumber(virtDevice.pluginProps['zoneNumber'])

            # BUG: the property vZonePartitionNumber must have been old
            # it no longer exists in Devices.xml as of 1.6.0 and onward
            # use zonePartitionNumber instead
            # we check for both to be safe using a dictionary and keys
            # and default to 1 if neither are found
            virtualZonePropertiesDict = virtDevice.pluginProps.to_dict()
            if 'zonePartitionNumber' in virtualZonePropertiesDict.keys():
                virtPartition = virtDevice.pluginProps['zonePartitionNumber']
            elif 'vZonePartitionNumber' in virtualZonePropertiesDict.keys():
                virtPartition = virtDevice.pluginProps['vZonePartitionNumber']
            else:
                virtPartition = '1'

            # TO DO: added this in 3.0 to fix likely bug where virtual zone
            # could get KeyError if it is first zone state to change
            # TO DO: remove this code block below to reference all current keypad devices
            if not self.ad2usb.zoneListInit:
                for address in self.getAllKeypadAddresses():
                    self.ad2usb.zoneStateDict[address] = []
                self.ad2usb.zoneListInit = True

            # part 1 - write the message to AlarmDecoder

            # The L command can be used to open or close zones.
            # There are two parameters: the zone and the state.
            # The zone is a zero-padded two-digit number and the state is either 0 or 1.
            action = pluginAction.props['virtualAction']
            if (action == '0') or (action == '1'):
                panelMsg = 'L' + virtZoneNumber + action + '\r'
                self.logger.debug(u"Sending panel message: {}".format(panelMsg))
                self.ad2usb.panelMsgWrite(panelMsg)

                # TO DO: remove this and log success within panelMsgWrite
                self.logger.debug(u"Sent panel message: {}".format(panelMsg))

            # Part 2 - Update the Indigo Device State
            # Update device UI States
            # This shouldn't be necessary, but the AD2USB doesn't send EXP messages for virtual zones

            # set default newState
            newZoneState = AD2USB_Constants.k_CLEAR
            if action == '0':   # Clear
                newZoneState = AD2USB_Constants.k_CLEAR
            elif action == '1':   # Fault
                newZoneState = AD2USB_Constants.k_FAULT
            elif action == '2':   # Trouble
                # TO DO: remove this block
                # TO DO: this used to be string of Trouble - it is not Error
                # uiValue = 'Trouble' / displayStateValue = 'trouble'
                newZoneState = AD2USB_Constants.k_ERROR
            else:
                # ERROR
                pass

            self.setDeviceState(virtDevice, newZoneState)

            # part 3 - update the keypad zone fault list

            # get keypad device for partition
            # but if that is not found then just get the first keypad
            myKeypadDevice = self.getKeypadDeviceForPartition(virtPartition)

            # if keypad does not exist for the specific partition do nothing
            if myKeypadDevice is None:
                self.logger.warning("ad2usb Keypad device not found with partition:{}".format(virtPartition))
                return

            # we have a keypad device
            else:
                myKeypadAddress = myKeypadDevice.pluginProps['panelKeypadAddress']
                self.logger.debug("Updating Keypad Device:{} with partition:{}".format(
                    myKeypadDevice.name, virtPartition))

                # init the zone state list if needed
                if myKeypadAddress not in self.ad2usb.zoneStateDict.keys():
                    self.ad2usb.zoneStateDict[myKeypadAddress] = []

                # set default newState
                if newZoneState == AD2USB_Constants.k_CLEAR:   # Clear
                    try:   # In case someone tries to set a clear zone to clear
                        self.ad2usb.updateZoneFaultListForKeypad(keypad=myKeypadAddress, removeZone=int(virtZoneNumber))
                    except Exception as err:
                        pass
                    self.logger.debug(u"Clear - state list: {}".format(self.ad2usb.zoneStateDict))

                elif newZoneState == AD2USB_Constants.k_FAULT:   # Fault
                    self.ad2usb.updateZoneFaultListForKeypad(keypad=myKeypadAddress, addZone=int(virtZoneNumber))
                    self.logger.debug(u"Fault - state list: {}".format(self.ad2usb.zoneStateDict))

                elif newZoneState == AD2USB_Constants.k_ERROR:   # Trouble
                    # TO DO: this used to be string of Trouble - it is not Error
                    # uiValue = 'Trouble' / displayStateValue = 'trouble'
                    # should it be in state list?
                    self.ad2usb.updateZoneFaultListForKeypad(keypad=myKeypadAddress, addZone=int(virtZoneNumber))
                    self.logger.debug(u"Trouble - state list: {}".format(self.ad2usb.zoneStateDict))
                else:
                    # ERROR
                    pass

                myKeypadDevice.updateStateOnServer(key='zoneFaultList', value=str(
                    self.ad2usb.zoneStateDict[myKeypadAddress]))

        except Exception as err:
            self.logger.error("Unable to update Virtual Zone Device, error:{}".format(str(err)))

        self.logger.debug(u"completed")

    ########################################################
    def panelMsgWrite(self, pluginAction):
        # self.logger.debug(u"called with:{}".format(pluginAction))
        self.logger.debug(u"called")

        if pluginAction.props['keypadAddress'] == '':
            address = self.ad2usbKeyPadAddress
        else:
            address = pluginAction.props['keypadAddress']

        panelMsg = pluginAction.props['panelMessage']

        # check if the message is as function key
        if panelMsg == 'F1' or panelMsg == 'f1':
            panelMsg = chr(1) + chr(1) + chr(1)
        elif panelMsg == 'F2' or panelMsg == 'f2':
            panelMsg = chr(2) + chr(2) + chr(2)
        elif panelMsg == 'F3' or panelMsg == 'f3':
            panelMsg = chr(3) + chr(3) + chr(3)
        elif panelMsg == 'F4' or panelMsg == 'f4':
            panelMsg = chr(4) + chr(4) + chr(4)

        # check if the message contains a variable
        if re.search(r'%%v:\d+%%', panelMsg) is None:
            # its not a variable and we just use the panel message provided
            pass
        # it looks like a variable, check with the method that returns a tuple: Bool, String
        else:
            isVariableSub = self.substituteVariable(panelMsg, True)
            # check the tuple value
            if isVariableSub[0]:
                # if the tuple is true call the method again to get variables value
                self.logger.debug('Panel Message is a variable:{}'.format(panelMsg))
                panelMsgValue = self.substituteVariable(panelMsg, False)
                # replace the message with the variable value
                panelMsg = panelMsgValue
            else:
                # unable to parse variable and we just use the value as passed
                self.logger.error('Value from Panel Message variable:{} cannot be determined. Error:{}. Panel message will not be sent.'.format(panelMsg, isVariableSub[1]))
                return  # no message sent

        self.logger.debug("created panel message")

        self.ad2usb.panelMsgWrite(panelMsg, address)

        self.logger.debug("sent panel message")

    ########################################################
    def panelQuckArmWrite(self, pluginAction):
        self.logger.debug(u"called with:{}".format(pluginAction))

        if pluginAction.props['keypadAddress'] == '':
            address = self.ad2usbKeyPadAddress
        else:
            address = pluginAction.props['keypadAddress']

        panelMsg = pluginAction.props['armingCode']

        self.logger.debug(u"Created panel message: {}".format(panelMsg))

        self.ad2usb.panelMsgWrite(panelMsg, address)

        self.logger.debug(u"completed")

    def panelQuickArmWriteToKeypad(self, pluginAction):
        try:

            self.logger.debug("called with:{}".format(pluginAction))

            # define actions we support by this method
            k_ACTION_NAMES = {'homeKitArmStay': 'HomeKit Arm-Stay', 
                              'homeKitArmAway': 'HomeKit Arm-Away'}            

            # define keys we can pass
            k_ACTION_QUICKARM_KEYPAD_KEYS = {'homeKitArmStay': '#3',
                                             'homeKitArmAway': '#2'}

            # get the name of the Action being called
            actionId = pluginAction.pluginTypeId
            actionName = k_ACTION_NAMES.get(actionId)  # default to None
            if actionName is None:
                self.logger.debug("Unknown Action Id:{}".format(actionId))
                self.logger.warning("Unable to perform Action Id:{} using panelQuickArmWriteToKeypad".format(actionId))
                return False  # no message sent

            # get keypad device from ID
            deviceId = int(pluginAction.deviceId)
            keypadDevice = self.getKeypadDeviceForId(deviceId)

            # get address of keypad (e.g. "18")
            address = ''
            if keypadDevice is None:
                self.logger.warning("Keypad device not found or is disabled when attempting to run Action:{}. Update the selected Keypad Device.".format(actionName))
                return False  # no write to panel

            else:
                address = keypadDevice.pluginProps.get('panelKeypadAddress','')
                self.logger.debug("Using Keypad Device id:{} with address:{} to write to".format(deviceId, address))

            # check if keypad address is the default address and no "K" prefix is required
            if address == self.ad2usbKeyPadAddress:
                self.logger.debug("Keypad address is the default address - resetting address to empty string")
                address = ''
            else:
                self.logger.debug("Keypad address:{} is not the default address:{}".format(address, self.ad2usbKeyPadAddress))


            # set the panel message based on the action id/action name
            panelMsg = k_ACTION_QUICKARM_KEYPAD_KEYS.get(actionId)
            if panelMsg is not None:
                self.logger.debug("Created panel message: {}".format(panelMsg))
                # write the message
                self.ad2usb.panelMsgWrite(panelMsg, address)
                self.logger.debug("completed")
                return True
            
            else:
                self.logger.warning("No valid panel message found for: {}".format(actionName))
                return False  # no write to panel

        except Exception as err:
            self.logger.error("Error while attempting to send Quick Arm panel message - error:{}".format(str(err)))
            return False

    def panelWriteWithCode(self, pluginAction):
        """
        Callback for Actions that require an alarm code. Will find the alarm code based on Configure settings.
        It must be enabled. If enabled, it can be a Variable, use the OTP Configuration file, or is entered in Preferences.
        Actions can be: Arm-Stay (CODE), Arm-Night-Stay (CODE), Arm-Away (CODE), Arm-Night-Stay (CODE), Arm-Max (CODE), or Disarm.
        """

        try:
            self.logger.debug("called with:{}".format(pluginAction))

            # define some local constants of the plugins that may call this method
            k_ACTION_NAMES = {'armStayCode': 'Arm-Stay (CODE)', 
                              'armNightStayCode': 'Arm-Night-Stay (CODE)',
                              'armAwayCode': 'Arm-Away (CODE)',
                              'armInstantCode': 'Arm-Max (CODE)',
                              'armMaxCode': 'Arm-Max (CODE)',
                              'disarmPanel': 'Disarm',
                              'homeKitArmStay': 'HomeKit Arm-Stay', 
                              'homeKitArmNightStay': 'HomeKit Arm-Night-Stay',
                              'homeKitArmAway': 'HomeKit Arm-Away',
                              'homeKitDisarm': 'HomeKit Disarm'}

            k_ACTION_KEYPAD_KEYS = {'armStayCode': '3',
                                    'armNightStayCode': '33',
                                    'armAwayCode': '2',
                                    'armInstantCode': '7',
                                    'armMaxCode': '8',
                                    'disarmPanel': '1',
                                    'homeKitArmStay': '3', 
                                    'homeKitArmNightStay': '33',
                                    'homeKitArmAway': '2',
                                    'homeKitDisarm': '1'}
            
            # get the name of the Action being called
            actionId = pluginAction.pluginTypeId
            actionName = k_ACTION_NAMES.get(actionId)
            if actionName is None:
                self.logger.debug("Unknown Action Id:{}".format(actionId))
                return False  # no message sent

            # get device to ultimately determine the keypad address and thus partition to send to
            address = ''  # the default
            deviceId = int(pluginAction.deviceId)
            keypadDevice = self.getKeypadDeviceForId(deviceId)

            if keypadDevice is None:
                self.logger.warning("Keypad device not found or is disabled when attempting to run Action:{}. Update the selected Keypad Device.".format(actionName))
                return False  # no write to panel

            else:
                address = keypadDevice.pluginProps.get('panelKeypadAddress','')
                self.logger.debug("Sending message to Keypad Device id:{} with address:{}".format(deviceId, address))


            # check if keypad address is the default address and no "K" prefix is required
            if address == self.ad2usbKeyPadAddress:
                self.logger.debug("Keypad address is the default address - resetting address to empty string")
                address = ''
            else:
                self.logger.debug("Keypad address:{} is not the default address:{}".format(address, self.ad2usbKeyPadAddress))


            # get the keys to pass
            keysToPass = k_ACTION_KEYPAD_KEYS.get(actionId)
            if keysToPass is None:
                self.logger.debug("No keypad message found for Action ID:{}".format(actionId))
                return False  # no message sent
            else:
                # are keys valid
                for c in keysToPass:
                    if c not in '0123456789*#':
                        self.logger.debug("Invalid keypad message found in:{}".format(keysToPass))
                        return False  # no message sent

                self.logger.debug("Keypad message for action is:{}".format(keysToPass))

            # get the code if its enabled
            code = None
            if self.isCodeSaved:
                code = self.__getAlarmCode()
            else:
                self.logger.error("Attempting to perform Action:{} that requires an alarm code but saving of an alarm code is not enabled. Check Configure settings to enable code or disable the action.".format(actionName))


            # check ths code is valie
            if code is None:
                self.logger.error("Alarm code could not be found or was not valid - {} command not sent".format(actionName))
                return False  # no message sent

            else:
                if address == '':
                    self.logger.debug("Action:{} - sending CODE+{} to default keypad".format(actionName, keysToPass))
                else:
                    self.logger.debug("Action:{} - sending CODE+{} to keypad address:{}".format(actionName, keysToPass, address))

                # send the message
                self.ad2usb.panelMsgWrite(code + keysToPass, address)

                code = None  # clear the code
                return True

        except Exception as err:
            code = ''
            self.logger.error("Unable to execute Action:{} - error:{}".format(actionName, str(err)))
            return False  # no message sent

    def homeKitActions(self, pluginAction):
        """
        Called by a hidden Actions for HomeKit Arm-Stay, Arm-Away, Arm-Night-Stay, and Disarm. Will verfiy HomeKit is enabled
        and then pass the action parameter directly to the appropiate method depending on if HomeKit is setup for code use or quick arming.
        """
        try:
            # to test this code:
            # pObj = indigo.server.getPlugin("com.berkinet.ad2usb")
            # pObj.isEnabled()
	        # pObj.executeAction("writeArmAwayPanel", props={'keypadAddress':'', 'armingCode':'#2'})

            # define some local constants of the plugins that may call this method
            k_ACTION_NAMES = {'homeKitArmStay': 'HomeKit Arm-Stay', 
                              'homeKitArmNightStay': 'HomeKit Arm-Night-Stay',
                              'homeKitArmAway': 'HomeKit Arm-Away',
                              'homeKitDisarm': 'HomeKit Disarm'}

            k_QUICK_ARM_ONLY = {'homeKitArmStay': 'HomeKit Arm-Stay', 
                              'homeKitArmAway': 'HomeKit Arm-Away'}

            # get the name of the Action being called
            actionId = pluginAction.pluginTypeId
            actionName = k_ACTION_NAMES.get(actionId)
            if actionName is None:
                self.logger.debug("Unknown HomeKit Action Id:{}".format(actionId))
                return False  # no message sent

            # verify HomeKit integration is enabled
            if not self.isHomeKitEnabled:
                self.logger.warning("Attempting to run HomeKit Action:{} - but HomeKit is not enabled. Use Configure to enable HomeKit integration.".format(actionName))
                return False  # no message sent

            # get the flag if we will use Quick Arming or pass a Code
            if self.hkArmMethod == 'quickArm':

                # we can only run Arm-Stay and Arm-Away with Quick Arm
                if actionId in k_QUICK_ARM_ONLY:
                    self.panelQuickArmWriteToKeypad(pluginAction)
                    return True
                else:
                    self.logger.warning("Action:{} cannot be run via Quick Arm - requires using an Alarm Code. Use Configure change HomeKit settings.".format(actionName))
                    return False
            
            elif self.hkArmMethod == 'useCode':
                self.panelWriteWithCode(pluginAction)
                return True

            else:
                self.logger.warning("Attempting to run HomeKit Action:{} - but unable to determing method. Check Configure settings.".format(actionName))
                return False  # no message sent

        except Exception as err:
            pass

    def __getAlarmCode(self):
        """
        Retrieves the alarm code from an Indigo variable, OTP, or from with the preferences. It also validates that the code (string) is valid.
        Returns the code (4 digit only string) or None if code was not found or was not valid.
        """

        try:
            # get the code
            code = ''

            # check if we're set to an Indigo variable first
            if self.codeLocation == AD2USB_Constants.k_CODE_USE_VARIABLE:

                # validate the variable
                isVariableSub = self.substituteVariable(self.alarmCodeVariable, True)

                # check the tuple value
                if isVariableSub[0]:
                    # if the tuple is true call the method again to get variables value
                    self.logger.debug('Alarm code is a variable:{}'.format(self.alarmCodeVariable))
                    # replace the code with the variable value
                    code = self.substituteVariable(self.alarmCodeVariable, False)
                else:
                    # unable to parse variable and we just use the value as passed
                    self.logger.error('Value from Alarm code variable:{} cannot be determined. Error:{}'.format(self.alarmCodeVariable, isVariableSub[1]))
                    return None # None is no code found

            # check if stored in prefs
            elif self.codeLocation == AD2USB_Constants.k_CODE_USE_PREFS:
                if hasattr(self, 'alarmCode'):
                    code = self.alarmCode

            # check if stored in OTP
            elif self.codeLocation == AD2USB_Constants.k_CODE_USE_OTP:
                # this applies for OTP
                code = self.otp.getAlarmCode()

            else:
                code = None

            # validate the code is a 4-digit string
            if self.isValidAlarmCodeString(code):
                self.logger.debug("Valid alarm panel code found in:{}".format(self.codeLocation))
                return code

            else: 
                # log error and return
                self.logger.error("Invalid code value in setting:{}.".format(self.codeLocation))
                return None

        except Exception as err:
            self.logger.error("Unable to get alarm code:{}".format(str(err)))
            return None

    ########################################################
    def forceZoneStateChange(self, pluginAction):
        self.logger.debug(u"called with:{}".format(pluginAction))

        # get the device ID from the Dynamic Menu
        zoneDeviceId = int(pluginAction.props['zoneDevice'])
        # get the device object
        zoneDevice = indigo.devices[zoneDeviceId]

        # get the zone state and force to lower case
        try:
            newZoneState = pluginAction.props['zoneState']
            newZoneState = newZoneState.lower()

        except Exception as err:
            self.logger.error("Unable to get zoneState:{}".format(str(err)))
            newZoneState = 'ERROR GETTING zoneState'

        # TO DO: address inconsistencies:
        # Actions.xml is 'clear' & 'faulted'
        # zoneState is 'Clear' & 'faulted'
        if newZoneState == 'clear':
            self.setDeviceState(zoneDevice, AD2USB_Constants.k_CLEAR)
        elif (newZoneState == 'faulted') or (newZoneState == 'fault'):
            self.setDeviceState(zoneDevice, AD2USB_Constants.k_FAULT)
        else:
            self.logger.error("Cannot force zone state change. Unknown state:{}".format(newZoneState))

        self.logger.debug(u"completed")

    ########################################################
    # Functions for configuration dialogs
    ########################################################

    ########################################################
    # Let us know the operating mode inside of a device configuration window
    # TO DO: Remove when we convert from advanced mode to advanced device. This is called before the dialog is shown
    # and by default just takes the pluginProps of the device and returns that. 
    def getDeviceConfigUiValues(self, pluginProps, typeId, devId):
        self.logger.debug(u"Called")

        valuesDict = pluginProps
        errorMsgDict = indigo.Dict()

        # Override the device ConfigUI isAdvanced value here with the global value:
        valuesDict["isAdvanced"] = self.pluginPrefs["isAdvanced"]
        valuesDict["numPartitions"] = self.numPartitions

        self.logger.debug(u"completed")

        return (valuesDict, errorMsgDict)

    ########################################
    def closedPrefsConfigUi(self, valuesDict, UserCancelled):
        self.logger.debug(u"Called")

        # TO DO: refactor to readPreferences and restart if needed
        # Need to look at where loop resides to be interrupted

        # capture previous AlarmDecoder communication settings since we need to reset if these change
        previousCommType = self.ad2usbCommType
        previousAddress = self.ad2usbAddress
        previousPort = self.ad2usbPort
        previousSerialPort = self.ad2usbSerialPort

        # TO DO: need to address all parameters in this code
        if UserCancelled is False:

            # make a copy of the dict and only log what we want to
            dictKeysToHide = {'alarmCode', 'ad2usbEmulationLabel', 'ad2usbEmulationSpace', 'ad2usbRelLabel', 'ad2usbZxpLabel',
                              'ad2usbZxpLabel', 'hkViaCodeNotes', 'homeKitPartition', 'infoLabel', 'makeSpace1',
                              'makeSpace2', 'makeSpace3', 'modeNotes1', 'msgControl', 'msgTestFail1', 'msgTestFail2',
                              'msgTestFail4', 'msgTestSuccess', 'pcSep1', 'sectionLabel1', 'sectionLabel2', 'sectionLabel3',
                              'sectionLabel4', 'sectionLabel5', 'sectionLabel6', 'simpleSeparator1', 'simpleSeparator2', 
                              'simpleSeparator3', 'simpleSeparator4', 'simpleSeparator5', 'simpleSeparator6', 
                              'variableFormatNotes'}

            prettyString = ''
            for key in valuesDict:
                if key not in dictKeysToHide:
                    # newDictForLog.update( { key: valuesDict[key] } )
                    prettyString = prettyString + "\n\t{}: {}".format(key, valuesDict[key]) 

            self.logger.info("Updated configuration values:{}".format(prettyString))

            self.ad2usbCommType = valuesDict['ad2usbCommType']
            if self.ad2usbCommType == 'IP':
                self.ad2usbAddress = valuesDict["ad2usbAddress"]
                self.ad2usbPort = valuesDict["ad2usbPort"]
                self.isPlaybackCommunicationModeSet = False
            elif self.ad2usbCommType == 'USB':
                self.ad2usbSerialPort = valuesDict["ad2usbSerialPort"]
                self.isPlaybackCommunicationModeSet = False
            elif self.ad2usbCommType == 'messageFile':
                self.isPlaybackCommunicationModeSet = True
            else:
                self.logger.warning(
                    "Unexpected AlarmDecoder communication type in preferences:{}".format(self.ad2usbCommType))
                pass

            # update the URL property
            self.__setURLFromConfig()

            self.ad2usbIsAdvanced = valuesDict["isAdvanced"]
            self.logUnknownDevices = valuesDict["logUnknownDevices"]
            self.logArmingEvents = valuesDict["logArmingEvents"]
            self.logUnknownLRRMessages = valuesDict["logUnknownLRRMessages"]
            self.clearAllOnRestart = valuesDict["restartClear"]
            self.numPartitions = int(valuesDict.get("panelPartitionCount", '1'))

            # we have a hidden value in Prefs for ad2usbKeyPadAddress
            # get the current address from the environment
            currentAddress = self.getAlarmDecoderKeypadAddress()
            if self.isValidKeypadAddress(currentAddress):
                # only change/set the hidden parameter is the address is valid
                valuesDict['ad2usbKeyPadAddress'] = currentAddress
            else:
                pass  # do not change if invalid

            # OTP Config file
            self.isOTPEnabled = valuesDict.get("enableOTP", False)
            self.OTPConfigPath = valuesDict.get("OTPConfigPath", '')

            # reset the OTP object
            self.otp = AD2USB_OTP.OTP(folderPath=self.OTPConfigPath, logger=self.logger, isEnabled=self.isOTPEnabled)

            # Alarm Code settings
            self.isCodeSaved = valuesDict.get("enableCode", False)
            self.codeLocation = valuesDict.get("codeLocation", AD2USB_Constants.k_CODE_USE_VARIABLE)

            if self.codeLocation == AD2USB_Constants.k_CODE_USE_VARIABLE:
                self.alarmCodeVariable = valuesDict.get("alarmCodeVariable", None)
                self.alarmCode = None

            elif self.codeLocation == AD2USB_Constants.k_CODE_USE_PREFS:
                self.alarmCode = valuesDict.get("alarmCode", None)
                self.alarmCodeVariable = None

            else:
                # this applies for OTP
                self.alarmCode = None
                self.alarmCodeVariable = None

            # HomeKit integration
            self.isHomeKitEnabled = valuesDict.get("isHomeKitEnabled", False)
            self.hkArmMethod = valuesDict.get("hkArmMethod", 'quickArm')

            # logging parameters
            self.indigoLoggingLevel = valuesDict.get("indigoLoggingLevel", logging.INFO)
            self.pluginLoggingLevel = valuesDict.get("pluginLoggingLevel", logging.INFO)
            self.isPanelLoggingEnabled = valuesDict.get("isPanelLoggingEnabled", False)
            self.isCodeMaskingEnabled = valuesDict.get("isCodeMaskingEnabled", True)

            # if the PanelLogging is now on (True) and the object does not exist run the init for PanelLogging
            if self.isPanelLoggingEnabled:
                if not hasattr(self, 'panelLogger'):
                    self.__initPanelLogging()

            # reset the logging levels
            self.__setLoggingLevels()

            # if the comms have changed then reset the serial connection
            if (previousCommType != self.ad2usbCommType):
                self.logger.info(
                    "AlarmDecoder type changed to {} - opening new serial connection".format(self.ad2usbCommType))
                self.ad2usb.setSerialConnection(True)  # force a reset
            else:
                # if the type is IP but IP or port changed then force a reset
                if self.ad2usbCommType == 'IP':
                    if (previousAddress != self.ad2usbAddress) or (previousPort != self.ad2usbPort):
                        self.logger.info(
                            "AlarmDecoder IP changed to {}:{} - opening new serial connection".format(self.ad2usbAddress, self.ad2usbPort))
                        self.ad2usb.setSerialConnection(True)  # force a reset

                # if the type is USB but IP or port changed then force a reset
                elif self.ad2usbCommType == 'USB':
                    if previousSerialPort != self.ad2usbSerialPort:
                        self.logger.info("AlarmDecoder USB changed - opening new serial connection")
                        self.ad2usb.setSerialConnection(True)  # force a reset

            self.logger.info(u"Plugin preferences have been updated")

        else:
            self.logger.debug(u"user cancelled Config dialog")

        self.logger.debug(u"completed")

    ########################################################
    # Validation methods
    ########################################################
    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        self.logger.debug(u"Called")
        self.logger.debug(u"Received: typeId:{} devId:{} valuesDict:{}".format(typeId, devId, valuesDict))

        errorMsgDict = indigo.Dict()
        areErrors = False

        if typeId == 'ad2usbInterface':

            for dev in indigo.devices.iter("self"):
                # self.numPartitions == 1:
                # TO DO: this code prevents replacing the keypad address with an empty one unless it was already empty
                # but why is it in the for loop?
                if valuesDict[u'panelKeypadAddress'] == '' and valuesDict[u'panelPartitionNumber'] == '1':
                    valuesDict[u'panelKeypadAddress'] = self.ad2usbKeyPadAddress

                if dev.deviceTypeId == 'ad2usbInterface' and dev.configured:
                    try:
                        if valuesDict[u'panelPartitionNumber'] == dev.pluginProps[u'panelPartitionNumber'] and dev.id != devId:
                            errorMsgDict[u'panelPartitionNumber'] = 'Found an existing panel device for the same parttion.\nOnly one panel device per partition is allowed.'
                            errorMsgDict[u'showAlertText'] = 'Found an existing panel device for the same partition.\nOnly one panel device per partition is allowed.'
                            self.logger.error(u"Only one panel device per partition is allowed")
                            areErrors = True
                    except:
                        valuesDict[u'panelPartitionNumber'] = "1"

                    try:
                        if valuesDict[u'panelKeypadAddress'] == dev.pluginProps[u'panelKeypadAddress'] and dev.id != devId:
                            errorMsgDict[u'panelKeypadAddress'] = 'Found an existing panel device with the same keypad address.\nOnly one panel device per keypad address is allowed.'
                            errorMsgDict[u'showAlertText'] = 'Found an existing panel device with the same keypad address.\nOnly one panel device per keypad address is allowed.'
                            self.logger.error(u"Only one panel device per keypad address is allowed.")
                            areErrors = True
                    except:
                        valuesDict[u'panelKeypadAddress'] = self.ad2usbKeyPadAddress

                    if int(valuesDict['panelPartitionNumber']) > self.numPartitions:
                        errorMsgDict[u'panelPartitionNumber'] = 'Partition number selected greater than configured partitions.'
                        errorMsgDict[u'showAlertText'] = 'Partition number selected greater than configured partitions.'

                        # TO DO: add device name details to this log message
                        self.logger.error(u"Partition number selected greater than configured partitions")
                        areErrors = True

            valuesDict[u'address'] = 'Keypad ' + valuesDict[u'panelKeypadAddress']

        elif typeId == 'alarmZone' or typeId == 'alarmZoneVirtual':
            self.logger.debug(u"Validate option alarmZone/alarmZoneVirtual")
            zoneNumber = valuesDict[u'zoneNumber']
            if len(zoneNumber) == 1:
                zoneNumber = '0' + zoneNumber

            if len(zoneNumber) == 0:
                valuesDict[u'address'] = ''
            else:
                valuesDict[u'address'] = 'Zone ' + zoneNumber

            if int(valuesDict['zonePartitionNumber']) > self.numPartitions:
                errorMsgDict[u'zonePartitionNumber'] = 'Partition number selected greater than configured partitions.'
                errorMsgDict[u'showAlertText'] = '-> Partition number selected greater than configured partitions.'
                areErrors = True

        self.logger.debug(u"Validated device config is: {}".format(valuesDict))

        if areErrors:
            if devId == 0:
                self.logger.error(u"Errors found adding new device")
            else:
                self.logger.error(u"Errors found while editing device id:{}".format(devId))
            return (False, valuesDict, errorMsgDict)
        else:
            self.logger.info(u"Device id: {} changes are valid".format(devId))
            return (True, valuesDict)

    ########################################################
    def validatePrefsConfigUi(self, valuesDict):
        """
        Indigo's required method to validate Plugin Config Prefreences. See PluginConfig.xml.
        """

        # init the error message object first since its used in Exception
        errorMsgDict = indigo.Dict()

        try:

            self.logger.debug(u"called with:{}".format(valuesDict))

            isPrefsValid = True
            debugLogMessage = ''

            # validate the prefs

            # verify and set the URL - as it may be new
            try:
                self.setURL(valuesDict['ad2usbCommType'], valuesDict['ad2usbAddress'],
                            valuesDict['ad2usbPort'], valuesDict['ad2usbSerialPort'])

            except Exception as err:
                errorMsgDict[u'ad2usbCommType'] = u"Invalid AD2USB communication settings"
                self.logger.error('Error in AlarmDecoder communication settings:{}'.format(str(err)))
                isPrefsValid = False
                debugLogMessage = 'AD2USB Communication Settings Error.'

            # we have a hidden value in Prefs for ad2usbKeyPadAddress
            currentAddress = self.getAlarmDecoderKeypadAddress()
            self.logger.debug("Current address is:{}".format(currentAddress))

            if self.isValidKeypadAddress(currentAddress):
                valuesDict['ad2usbKeyPadAddress'] = currentAddress
            else:
                pass  # do not change if invalid

            # validate the OTP Config folder if it is enabled
            isOTPEnabled = valuesDict.get('enableOTP', False)
            if isOTPEnabled:
                self.logger.debug("OTP is enabled")
                pathToCheck = valuesDict.get('OTPConfigPath', '')

                # test the path
                isFolderValid, folderMessage = self.otp.isValidFolder(folderToCheck=pathToCheck)
                if not isFolderValid:
                    isPrefsValid = False
                    errorMsgDict['OTPConfigPath'] = folderMessage
                    debugLogMessage = debugLogMessage + ' ' + errorMsgDict['OTPConfigPath']

            # validate Alarm Code settings
            isCodeSaved = valuesDict.get("enableCode", False)
            if isCodeSaved:
                self.logger.debug("Saving of Alarm Code is enabled")

                # get location settings
                codeLocation = valuesDict.get("codeLocation", "")
            
                # see if code location is valid
                if codeLocation == AD2USB_Constants.k_CODE_USE_VARIABLE:
                    # if selecting variable make sure its a valid variable
                    homeKitVariable = valuesDict.get("alarmCodeVariable", '')

                    if re.search(r'^%%v:\d+%%$', homeKitVariable) is None:
                        # its not a variable 
                        isPrefsValid = False
                        errorMsgDict['alarmCodeVariable'] = 'Variable should be in format: %%v:VARID%%'
                        debugLogMessage = debugLogMessage + ' ' + errorMsgDict['alarmCodeVariable']

                    # it looks like a variable, check with the method that returns a tuple: Bool, String
                    isVariableSub = self.substituteVariable(homeKitVariable, True)
                    # check the tuple value
                    if isVariableSub[0]:
                        # if the tuple is true call the method again to get variables value
                        self.logger.debug('Alarm code is a valid variable:{}'.format(homeKitVariable))
                        # codeValue = self.plugin.substituteVariable(homeKitVariable, False)
                        # self.logger.info('Converted HomeKit alarm code variable:{} to code'.format(homeKitVariable))
                    else:
                        # unable to parse variable and we just use the value as passed
                        self.logger.error('Value from HomeKit alarm code variable:{} cannot be determined.'.format(homeKitVariable))
                        isPrefsValid = False
                        errorMsgDict['alarmCodeVariable'] = isVariableSub[1]  # the error message from substituteVariable method
                        debugLogMessage = debugLogMessage + ' ' + errorMsgDict['alarmCodeVariable']

                elif codeLocation == AD2USB_Constants.k_CODE_USE_OTP:
                    # if selecting OTP just make sure OTP is enabled - OTP validation takes care of the rest
                    if not isOTPEnabled:
                        isPrefsValid = False
                        errorMsgDict['codeLocation'] = 'OTP must be enabled to use for HomeKit'
                        debugLogMessage = debugLogMessage + ' ' + errorMsgDict['codeLocation']

                elif codeLocation == AD2USB_Constants.k_CODE_USE_PREFS:
                    # if code entered in Configure just make sure its 4-digit string of only 0-9
                    alarmCode = valuesDict.get("alarmCode", '')
                    if not self.isValidAlarmCodeString(alarmCode):
                        isPrefsValid = False
                        errorMsgDict['alarmCode'] = 'Alarm code must be 4-digits'
                        debugLogMessage = debugLogMessage + ' ' + errorMsgDict['alarmCode']

                else:
                    isPrefsValid = False
                    errorMsgDict['codeLocation'] = 'Invalid alarm user code selection'
                    debugLogMessage = debugLogMessage + ' ' + errorMsgDict['codeLocation']
                
            # check HomeKit settings
            isHomeKitEnabled = valuesDict.get("isHomeKitEnabled", False)
            hkArmMethod = valuesDict.get("hkArmMethod", None)

            if isHomeKitEnabled and (hkArmMethod == 'useCode') and (not isCodeSaved):
                isPrefsValid = False
                errorMsgDict['hkArmMethod'] = 'Using a code with HomeKit requires that "Saving of Alarm Code" is enabled'
                debugLogMessage = debugLogMessage + ' ' + errorMsgDict['hkArmMethod']

            # TO DO: add code to check readability, etc.

            # All other Plugin Config items are checkboxes or pull downs and are constrained
            # end checking preferences

            # if prefs are not valid return the error
            if not isPrefsValid:
                self.logger.debug(u"invalid Plugin preferences:{}".format(debugLogMessage))
                return (False, valuesDict, errorMsgDict)
            else:
                # if we made it this far all checks are complete and user choices look good
                # so return True (client will then close the dialog window).
                self.logger.debug(u"completed")
                return (True, valuesDict)

        except Exception as err:
            self.logger.error(u"Unexpected error validating Plugin Config:{}".format(str(err)))
            errorMsgDict = indigo.Dict()
            errorMsgDict['ad2usbCommType'] = "Unexpected error. Check Indigo Event Log for more details."
            errorMsgDict['showAlertText'] = "Unexpected error. Check Indigo Event Log for more details."
            return (False, valuesDict, errorMsgDict)

    def isValidAlarmCodeString(self, code):
        """
        Reads the code (string) and returns True is the code is a 4-digit number (zero padded is fine) or False otherwise.
        """
        try:
            # check if its None
            if code is None:
                return False
            
            # is it a string
            if not isinstance(code, str):
                self.logger.debug('Error validating alarm code - not a string')
                return False

            # does it only contain 0-9
            lengthOfCode = 0
            for c in code:
                lengthOfCode = lengthOfCode + 1
                if c not in '0123456789':
                    self.logger.debug('Error validating alarm code - contains character other than digits:{}'.format(c))
                    return False
                else:
                    pass

            # and is it only 4 digits long
            if lengthOfCode != 4:
                self.logger.debug('Error validating alarm code:{} is more than 4-digits'.format(lengthOfCode))
                return False

        except Exception as err:
            self.logger.debug('Error validating alarm code - error:{}'.format(str(err)))
            return False

        # if we get here its contains valid int characters and is only 4 digits
        return True

    def setAlarmDecoderConfigDictFromPrefs(self, valuesDict):
        """
        Reads the parameter 'valuesDict' (dictionary) which is expected to match the items defined in
        Indigo's PluginConfig.xml. It then sets the property 'configSettings' which is used to write
        the config to the AlarmDecoder.

        Returns three values: Success/Fail (boolean), valueDict (dictionary), and
        errorMsgDict (Indigo dict). Success means all the AlarmDecoder settings are valid.

        **parameters:**
        valuesDict - the dictionary from Indigo's plugin preferences
        """
        self.logger.debug(u"called with:{}".format(valuesDict))

        # init the error message in case we never use it it is defined
        errorMsgDict = indigo.Dict()

        # verify and set the URL - as it may be new
        try:
            self.__setURLFromConfig()

        except Exception as err:
            errorMsgDict['ad2usbCommType'] = "Invalid AD2USB communication settings"
            self.logger.error('error in AlarmDecoder communication settings:{}'.format(str(err)))
            return (False, valuesDict, errorMsgDict)

        # The keypad address is required. Without it we cannot continue
        # make sure keypad address is valid - 2 digits
        validKeypadAddress = self.keypadAddressFrom(valuesDict['ad2usbKeyPadAddress'])
        if validKeypadAddress is None:
            errorMsgDict[u'ad2usbKeyPadAddress'] = "A valid keypad address is required"
            return (False, valuesDict, errorMsgDict)
        else:
            # set configSettings, this menu dictionary, and the hidden preference
            self.configSettings['ADDRESS'] = validKeypadAddress
            valuesDict['ad2usbKeyPadAddress'] = validKeypadAddress
            self.pluginPrefs['ad2usbKeyPadAddress'] = validKeypadAddress

        # virtual zone expanders - no more than 2
        zxCount = 0
        decoderConfigEXP = 'NNNNN'
        expanderList = ['ad2usbExpander_1', 'ad2usbExpander_2', 'ad2usbExpander_3',
                        'ad2usbExpander_4', 'ad2usbExpander_5']

        for index, key in enumerate(expanderList):
            if valuesDict[key]:
                # make sure we limit it to two (2) max
                zxCount += 1
                # index starts with 0 but bit positon starts with 1
                bitPosition = index + 1
                # set the bit
                decoderConfigEXP = self.setFlagInString(decoderConfigEXP, bitPosition, valuesDict[key])

        self.configSettings['EXP'] = decoderConfigEXP

        if zxCount > 2:
            errorMsgDict[u'ad2usbExpander_1'] = u"A maximum of 2 virtual zone expanders are allowed"
            return (False, valuesDict, errorMsgDict)

        # virtual relays
        decoderConfigREL = 'NNNN'
        decoderConfigREL = self.setFlagInString(decoderConfigREL, 1, valuesDict['ad2usbVirtRelay_1'])
        decoderConfigREL = self.setFlagInString(decoderConfigREL, 2, valuesDict['ad2usbVirtRelay_2'])
        decoderConfigREL = self.setFlagInString(decoderConfigREL, 3, valuesDict['ad2usbVirtRelay_3'])
        decoderConfigREL = self.setFlagInString(decoderConfigREL, 4, valuesDict['ad2usbVirtRelay_4'])
        self.configSettings['REL'] = decoderConfigREL

        # LRR
        decoderConfigLRR = 'N'
        decoderConfigLRR = self.setFlagInString(decoderConfigLRR, 1, valuesDict['ad2usbLrr'])
        self.configSettings['LRR'] = decoderConfigLRR

        # Deduplicate
        decoderConfigDEDUP = 'N'
        decoderConfigDEDUP = self.setFlagInString(decoderConfigDEDUP, 1, valuesDict['ad2usbDeduplicate'])
        self.configSettings['DEDUPLICATE'] = decoderConfigDEDUP

        # if we made it this far all checks are complete and user choices look good
        # so return True and the dictionaries
        self.logger.debug(u"completed")
        return (True, valuesDict, errorMsgDict)

    ########################################################

    def validateEventConfigUi(self, valuesDict, typeId, devId):
        self.logger.debug(u"Called")
        self.logger.debug(u"received: typeId:{} devId:{} valuesDict:{}".format(typeId, devId, valuesDict))

        errorMsgDict = indigo.Dict()
        areErrors = False

        if typeId == 'userEvents':
            try:
                # foo = str(int(valuesDict[u'userNumber']))  # Throw an error if not an int
                # TO DO: fix this validation from 01-49
                valuesDict[u'userNumber'] = str(valuesDict[u'userNumber'])
            except:
                errorMsgDict[u'userNumber'] = 'User number must be an integer.'
                valuesDict[u'userNumber'] = 'User number must be an integer.'
                areErrors = True

        if areErrors:
            self.logger.error(u"completed with errors")
            return (False, valuesDict, errorMsgDict)
        else:
            self.logger.info(u"Event id:{} validation completed".format(devId))
            return (True, valuesDict)

    ########################################################
    # Confg callback methods
    ########################################################

    def NewConfigButtonPressed(self, valuesDict, typeId):
        """
        Reads the AlarmDecoder config from the AlarmDecoder and updates the plugin Menu
        "AlarmDecoder Configuration" dialog settings from the AlarmDecoder so they can be reviewed and
        updated by saving the dialog. Note that this only sends the CONFIG message and waits
        for the runConcurrentThread method to read the CONFIG messsage and update a property
        that is has been read. This method must return valuesDict to conform to Indigo. Message
        control is handled by property ADButtonMsgControl with values:

        ADButtonMsgControl:
        0 - default - blank
        1 - CONFIG message sent
        2 - CONFIG message read
        3 - Unable to send message to AlarmDecoder
        4 - Connection type does not support automatic configuration (Playback)
        5 - AlarmDecoder not defined in Plugin config (IP, USB, or Playback)
        6 - Error while attempting to read
        """
        self.logger.debug(u"called with: {}".format(valuesDict))

        try:
            # set a flag
            self.hasAlarmDecoderConfigBeenRead = False
            self.logger.debug("ad2usbCommType is:{}".format(self.ad2usbCommType))

            # test first if the AlarmDecoder communication has been setup in Plugin configure
            # so we know if we have and IP or USB
            if (self.ad2usbCommType == 'IP') or (self.ad2usbCommType == 'USB'):

                # send config - detailed logging is handled by the underlying methods
                self.logger.debug("sending CONFIG command to AlarmDecoder")
                if self.ad2usb.sendAlarmDecoderConfigCommand():
                    self.logger.debug("sending CONFIG command was successful")
                    valuesDict['ADButtonMsgControl'] = '1'
                else:
                    self.logger.debug("sending CONFIG command failed")
                    valuesDict['ADButtonMsgControl'] = '3'

                # the reading of the CONFIG response is handled on another thread
                # we wait a max of the 2 x SERIAL_TIMEOUT
                timeout = time.time() + (2 * self.ad2usb.getTimeout())

                # we loop for up to the timeout set above or until the CONFIG was read
                self.logger.debug("waiting to read CONFIG command...")
                while (time.time() < timeout) and (self.hasAlarmDecoderConfigBeenRead is False):
                    time.sleep(1)  # sleep for 1 second

                if self.hasAlarmDecoderConfigBeenRead:
                    self.logger.debug("successfully read CONFIG command...")
                    valuesDict['ADButtonMsgControl'] = '2'  # success

                    # this method updates the valuesDict from the configSettings property
                    self.logger.debug("updating dialog values from CONFIG...")
                    self.updateValuesDictFromADConfigSettings(valuesDict)

                    return valuesDict

                else:
                    self.logger.debug("timed out waiting for CONFIG to be read...")
                    valuesDict['ADButtonMsgControl'] = '6'  # error
                    self.logger.warning(
                        "Unable to read the config from the AlarmDecoder or possible timeout while waiting. Try again.")
                    return valuesDict

            elif self.ad2usbCommType == 'messageFile':

                # we can't read the config in playback mode so set the flag as if we did
                # but we do have the settings in the plugin property if CONFIG message was read in playback file
                # we can test both scenarios here by changing True or False
                if True:
                    self.hasAlarmDecoderConfigBeenRead = True
                    valuesDict['ADButtonMsgControl'] = '2'  # success load settings test
                    self.updateValuesDictFromADConfigSettings(valuesDict)
                else:
                    self.hasAlarmDecoderConfigBeenRead = False
                    valuesDict['ADButtonMsgControl'] = '4'  # invalid commType test

                return valuesDict

            else:
                # the user needs to return to the Plugin config and update the settings for the AlarmDecoder
                valuesDict['ADButtonMsgControl'] = 5
                self.logger.warning('Unknown AlarmDecoder communication type:{}'.format(self.ad2usbCommType))
                return valuesDict

        except Exception as err:
            valuesDict['ADButtonMsgControl'] = 6
            self.logger.error(u"unable to read AlarmDecoder Config:{}".format(str(err)))
            return valuesDict

    def updateValuesDictFromADConfigSettings(self, valuesDict):
        """
        Updates the provided valuesDict object (typically for a Config dialog) values from the plugin's
        property 'configSettings'. This is used to set the valuesDict properties to the values
        in the configSettings property. The configSettings property is updated anytime the CONFIG
        message is read from the AlarmDecoder.

        Returns True is update was successful, False if it was unsuccessful.
        """
        self.logger.debug(u"called with: {}".format(valuesDict))

        try:
            # test if configSettings is not empty
            if bool(self.configSettings):
                self.logger.debug("current AlarmDecoder Config dictionary values:{}".format(valuesDict))
                self.logger.debug("current AlarmDecoder configSettings are:{}".format(self.configSettings))

                # update the values
                valuesDict['ad2usbKeyPadAddress'] = self.configSettings['ADDRESS']

                valuesDict['ad2usbLrr'] = self.getFlagInString(self.configSettings['LRR'])

                valuesDict['ad2usbExpander_1'] = self.getFlagInString(self.configSettings['EXP'], 1)
                valuesDict['ad2usbExpander_2'] = self.getFlagInString(self.configSettings['EXP'], 2)
                valuesDict['ad2usbExpander_3'] = self.getFlagInString(self.configSettings['EXP'], 3)
                valuesDict['ad2usbExpander_4'] = self.getFlagInString(self.configSettings['EXP'], 4)
                valuesDict['ad2usbExpander_5'] = self.getFlagInString(self.configSettings['EXP'], 5)

                valuesDict['ad2usbVirtRelay_1'] = self.getFlagInString(self.configSettings['REL'], 1)
                valuesDict['ad2usbVirtRelay_2'] = self.getFlagInString(self.configSettings['REL'], 2)
                valuesDict['ad2usbVirtRelay_3'] = self.getFlagInString(self.configSettings['REL'], 3)
                valuesDict['ad2usbVirtRelay_4'] = self.getFlagInString(self.configSettings['REL'], 4)

                valuesDict['ad2usbDeduplicate'] = self.getFlagInString(self.configSettings['DEDUPLICATE'])

                self.logger.debug(u"newly updated config dictionary is:{}".format(valuesDict))
                self.logger.debug(u"completed with valid config")

                return True

            # else configSettings is empty - possibly because Plugin just restarted and no CONFIG mms read
            else:
                self.logger.warning(
                    "No AlarmDecoder CONIFG settings in memory. This is possible when the Plugin has just restarted. Sending CONFIG message to AlarmDecoder.")
                self.ad2usb.sendAlarmDecoderConfigCommand()

                return False

        except Exception as err:
            self.logger.error(
                u"Error while setting dictionary from AlarmDecoder configSettings property:{}".format(str(err)))
            return False

    def getMenuActionConfigUiValues(self, menuId):
        """
        Callback method called prior to MenuItem being opened. For configureAlarmDecoder this loads
        settings from the configSettings property - the last known/read AlarmDecoder settings.
        """
        valuesDict = indigo.Dict()
        errorDict = indigo.Dict()

        # fill in the valuesDict here with pre-fill data
        if menuId == 'configureAlarmDecoder':
            if self.updateValuesDictFromADConfigSettings(valuesDict):
                # we reset the flag here to indicate the CONFIG message needs to be read
                # TO DO: possibe bug - if the dialog is open too long the message could be
                self.hasAlarmDecoderConfigBeenRead = False

            else:
                errorDict["makeSpace3"] = "Error loading previous values"
                errorDict["showAlertText"] = "Error loading previous AlarmDecoder values. Use the \"Read Config\" button in Step 1 read the current AlarmDecoder settings."

        return (valuesDict, errorDict)

    def getAlarmDecoderKeypadAddress(self):
        """
        Returns the cached value of the AlarmDecoder Keypad adddress set via 'ADDRESS' configuration.
        Returns keypad address as string or returns None if it is not set.
        """
        if 'ADDRESS' in self.configSettings:
            return self.configSettings['ADDRESS']
        else:
            return None

    ########################################################
    # ConfigUI callbacks from Actions and Devices
    def getPartitionList(self, filter="", valuesDict=None, typeId="", targetId=0):
        """
        Returns a list of tuples of keypad address number (string) and parition number (string) for all Keypad devices.
        Ex: [('18', '1'), ('19', '2')]
        """
        self.logger.debug("Called")

        myArray = []
        emptyArray = []

        try:

            for oneKeypad in self.getAllKeypadDevices():
                try:
                    partition = oneKeypad.pluginProps['panelPartitionNumber']
                    panelKeypadAddress = oneKeypad.pluginProps['panelKeypadAddress']
                    myArray.append((panelKeypadAddress, partition))

                except Exception as err:
                    self.logger.error("Unable to read partition and/or address from keypads, error:{}".format(str(err)))
                    return emptyArray

            self.logger.debug("Completed with valid list of keypads:{}".format(myArray))
            return myArray

        except Exception as err:
            self.logger.error("Unable to read partition and/or address from keypads, error:{}".format(str(err)))
            return emptyArray

    ########################################################
    # Functon for getZoneDevList to sort the zone list on zone number
    def asint(self, s):
        try:
            return int(s), ''
        except ValueError:
            return sys.maxint, s

    ########################################################
    def getZoneDevList(self,  filter="", valuesDict=None, typeId="", targetId=0):
        self.logger.debug(u"Called")

        myArray = []
        tempDict = {}

        for device in indigo.devices.iter("self"):
            if device.deviceTypeId == 'alarmZone' or device.deviceTypeId == 'alarmZoneVirtual':
                zoneNumber = device.pluginProps['zoneNumber']
                if len(zoneNumber) == 1:
                    zoneNumber = '0' + zoneNumber
                value = zoneNumber + ' - ' + device.name
                tempDict[zoneNumber] = value

        self.logger.debug(u"tempDict:{}".format(tempDict))
        # Take the dict of zone numbers and names and turn it into a numerically sorted list
        sortedlist = [(k, tempDict[k]) for k in sorted(tempDict, key=self.asint)]
        self.logger.debug(u"sortedlist:{}".format(sortedlist))
        for key in sortedlist:
            self.logger.debug(u"zone tupple:{}".format(key))
            try:
                foo = int(key[0])  # Force an error if the key is non-numeric
                foo = foo  # Get rid of the stupid lintv error
                myArray.append(key)
            except:
                pass

        self.logger.debug(u"Returned myArray:{}".format(myArray))
        self.logger.debug(u"completed")

        return myArray

    def getAllZoneGroups(self, includeDisabled=False):
        """
        Returns an array of device.id [integer] for all Zone Group devices. By default
        disabled Zone Group devices are not included. Optionally pass parameter True
        to include disabled Zone Group devices.
        """
        self.logger.debug(u"called")

        zoneGroups = []

        try:
            # all devices
            for device in indigo.devices.iter("self"):
                # just the Zone Groups
                if device.deviceTypeId == 'zoneGroup':
                    if device.enabled or (includeDisabled is True):
                        zoneGroups.append(device.id)

            self.logger.debug(u"all zones groups are:{}".format(zoneGroups))
            return zoneGroups

        except Exception as err:
            self.logger.error(u"error retrieving Zone Groups from Indigo, msg:{}".format(str(err)))

            # return an empty dictionary
            return []

    def getZoneNumbersForZoneGroup(self, zoneGroupDeviceId=0):
        """
        returns an array of Zone Numbers (Address) [string] for a single Zone Group devices

        **parameters**:
        zoneGroupDeviceId -- an integer that is the device.id of the Zone Group
        """

        self.logger.debug(u"called with zone group device id:{}".format(zoneGroupDeviceId))

        try:
            # get the Zone Group device provided
            device = indigo.devices[zoneGroupDeviceId]
            self.logger.debug(u"zone group device name is:{}".format(device.name))

            # check if we have the property by converting to a standard dict
            pluginPropsLocalDict = device.pluginProps.to_dict()
            self.logger.debug(u"zone group pluginProps are:{}".format(pluginPropsLocalDict))

            if 'zoneDeviceList' in pluginPropsLocalDict.keys():
                # return if it is a list
                zoneList = pluginPropsLocalDict['zoneDeviceList']
                self.logger.debug(u"zone group zone list is:{}".format(zoneList))
                if isinstance(zoneList, list):
                    self.logger.debug(u"zones list found - zone list is:{}".format(zoneList))
                    return zoneList
                else:
                    self.logger.debug(u"return empty list - property zoneList not a list")
                    return []
            else:
                self.logger.debug(u"return empty list - property zoneList not found in device")
                return []

        except Exception as err:
            self.logger.error(u"error retrieving Zones for Zone Groups:{} from Indigo, msg:{}".format(
                zoneGroupDeviceId, str(err)))

            # return an empty dictionary
            self.logger.debug(u"return empty list due to error")
            return []

    def getAllZoneGroupsForZone(self, forZoneNumber=''):
        """
        returns an array of device.id [integer] that is all the Zone Group devices for the Zone Number (Address) provided

        **parameters**:
        forZoneNumber -- an string that is the Zone Number (Address)
        """

        self.logger.debug(u"called with zone address:{}".format(forZoneNumber))

        zoneGroups = []
        try:
            # for each zone group
            for deviceId in self.getAllZoneGroups():
                # for each zone address in the zone group
                for zone in self.getZoneNumbersForZoneGroup(deviceId):
                    # if the zone address is what we are looking for
                    if zone == forZoneNumber:
                        # append it to the list
                        zoneGroups.append(deviceId)

            self.logger.debug(u"Zone:{} is in Groups:{}".format(forZoneNumber, zoneGroups))
            return zoneGroups

        except Exception as err:
            self.logger.error(
                u"error retrieving Zone Groups for Zone Address:{} - error:{}".format(forZoneNumber, str(err)))
            return []

    # TO DO: simplify and leverage getDeviceForZoneNumber()
    def getDeviceIdForZoneNumber(self, forZoneNumber=''):
        """
        Returns the device.id (integer) for the Zone Number (Address) provided or 0 if not found.
        This only looks at Alarm Zone and Virtual Zone devices. Keypad devices are not included.

        **parameters**:
        forZoneNumber -- an string that is the Zone Number (Address)
        """

        self.logger.debug(u"called with zone number:{}".format(forZoneNumber))

        try:
            # convert zone to a string if needed
            zoneNumberAsString = ''
            if isinstance(forZoneNumber, str):
                zoneNumberAsString = forZoneNumber
            else:
                zoneNumberAsString = str(forZoneNumber)

            for device in indigo.devices.iter("self"):
                # TO DO: do I need this restriction?
                if device.deviceTypeId == 'alarmZone' or device.deviceTypeId == 'alarmZoneVirtual':
                    deviceProperties = device.pluginProps.to_dict()
                    self.logger.debug(u"device properties are:{}".format(deviceProperties))
                    zoneNumber = deviceProperties.get('zoneNumber', "NONE")
                    if zoneNumber == zoneNumberAsString:
                        self.logger.debug(u"found device id:{} for zone number:{}".format(
                            device.id, zoneNumberAsString))
                        return device.id

            # did not find device
            self.logger.error(u"Unable to find device id for zone number:{}".format(forZoneNumber))
            return 0

        except Exception as err:
            self.logger.error("Error trying to get device id for zone number:{}, error:{}".format(
                forZoneNumber, str(err)))
            return 0

    def getDeviceForZoneNumber(self, forZoneNumber=''):
        """
        Returns the Indigo device objcet for the Zone Number (Address) provided or None if not found.
        This only looks at Alarm Zone and Virtual Zone devices. Keypad devices are not included.

        **parameters**:
        forZoneNumber -- an string that is the Zone Number (Address)
        """

        self.logger.debug(u"called with zone number:{}".format(forZoneNumber))

        try:
            # convert zone to a string if needed
            zoneNumberAsString = ''
            if isinstance(forZoneNumber, str):
                zoneNumberAsString = forZoneNumber
            else:
                zoneNumberAsString = str(forZoneNumber)

            for device in indigo.devices.iter("self"):
                # TO DO: do I need this restriction?
                if device.deviceTypeId == 'alarmZone' or device.deviceTypeId == 'alarmZoneVirtual':
                    deviceProperties = device.pluginProps.to_dict()
                    self.logger.debug(u"device properties are:{}".format(deviceProperties))
                    zoneNumber = deviceProperties.get('zoneNumber', "NONE")
                    if zoneNumber == zoneNumberAsString:
                        self.logger.debug(u"found device id:{} for zone number:{}".format(
                            device.id, zoneNumberAsString))
                        return device

            # did not find device
            self.logger.error(u"Unable to find device id for zone number:{}".format(forZoneNumber))
            return None

        except Exception as err:
            self.logger.error("Error trying to get device id for zone number:{}, error:{}".format(
                forZoneNumber, str(err)))
            return None

    def getDeviceForZoneNumberAsInt(self, forZoneNumber=0):
        """
        Returns the Indigo device object for the Zone Number (integer) provided or None if not found.
        This only looks at Alarm Zone and Virtual Zone devices. Keypad devices are not included.

        **parameters**:
        forZoneNumber -- an integer that is the Zone Number (Address)
        """

        self.logger.debug(u"called with zone number:{}".format(forZoneNumber))

        try:
            # convert zone to a string if needed
            zoneNumberAsInt = 0
            if isinstance(forZoneNumber, int):
                zoneNumberAsInt = forZoneNumber
            else:
                zoneNumberAsInt = int(forZoneNumber)

            for device in indigo.devices.iter("self"):
                # TO DO: do I need this restriction?
                if device.deviceTypeId == 'alarmZone' or device.deviceTypeId == 'alarmZoneVirtual':
                    deviceProperties = device.pluginProps.to_dict()
                    self.logger.debug(u"device properties are:{}".format(deviceProperties))
                    zoneNumberAsString = deviceProperties.get('zoneNumber', '0')

                    # convert the property to an int for comparison
                    zoneNumberProperty = int(zoneNumberAsString)

                    if zoneNumberProperty == zoneNumberAsInt:
                        self.logger.debug(u"found device id:{} for zone number:{}".format(
                            device.id, zoneNumberAsString))
                        return device

            # did not find device
            self.logger.error(u"Unable to find device id for zone number:{}".format(forZoneNumber))
            return None

        except Exception as err:
            self.logger.error("Error trying to get device id for zone number:{}, error:{}".format(
                forZoneNumber, str(err)))
            return None

    def getZoneNumberForDevice(self, forDevice):
        """
        Returns a zone number (int) for a given Indigo Device object. Returns None if the
        object cannot be read or the zone number is 0 or not an integer.

        **parameters:**
        forDevice - Indigo Device Object
        """
        # set
        zoneName = None
        zoneNumber = None

        try:
            # get device ID and the device
            zoneName = forDevice.name
            zoneNumber = forDevice.pluginProps['zoneNumber']

            if int(zoneNumber) > 0:
                return int(zoneNumber)
            else:
                self.logger.error(
                    'Zone Number is not an valid value:{} for device named:{}'.format(zoneNumber, zoneName))
                return None

        except Exception as err:
            if zoneName is None:
                self.logger.error('Unable to get Zone Name - error:{} for device object:{}'.format(str(err), forDevice))
            elif zoneNumber is None:
                self.logger.error('Unable to get Zone Number - error:{} for device named:{}'.format(str(err), zoneName))
            else:
                self.logger.error(
                    'Unable to get Zone Number - error:{} for device object:{}'.format(str(err), forDevice))

            return None

    def getZoneStateForDeviceId(self, forDeviceId=0):
        """
        returns the state property "zoneState" (string) for device id.
        returns 'NOT_FOUND' if the device exists but the Zone State does not
        returns 'ERROR' if an error is encountered

        **parameters**:
        forDeviceId -- an integer that is the indigo.device.id
        """

        self.logger.debug(u"called with device id:{}".format(forDeviceId))
        if forDeviceId == 0:
            return 'NOT_FOUND'

        try:
            # get the device
            device = indigo.devices[forDeviceId]
            self.logger.debug(u"found device id:{}".format(forDeviceId))

            # get the zoneState device as a standard dict
            deviceStates = device.states.to_dict()
            self.logger.debug(u"device states are:{}".format(deviceStates))

            # get the zoneState
            if 'zoneState' in deviceStates:
                zoneState = deviceStates['zoneState']
                self.logger.debug(u"found zoneState:{} in device:{}".format(zoneState, device.name))
                return zoneState

            else:
                self.logger.warning(u"Unable to get zoneState for device:{} ({})".format(device.name, forDeviceId))
                return 'NOT_FOUND'

        except Exception as err:
            self.logger.error("Error trying to get zone state for device id:{}, error:{}".format(forDeviceId, str(err)))
            return 'ERROR'

    def updateAllZoneGroups(self):
        """
        Updates all the applicable Zone Groups when a Zone changes. call this method after an alarm zone state update
        """

        self.logger.debug(u"called")

        try:
            # check and update every zone group
            for zoneGroupDeviceId in self.getAllZoneGroups():

                # get the Zone Group state
                zoneGroupDevice = indigo.devices[zoneGroupDeviceId]
                currentZoneGroupZoneState = zoneGroupDevice.displayStateValRaw
                self.logger.debug(u"updating zone group:{}, id:{}, current zone state:{}".format(
                    zoneGroupDevice.name, zoneGroupDeviceId, currentZoneGroupZoneState))

                # start as false - but if we find one zone as fault the group is fault
                zoneGroupIsFaulted = False
                for zoneNumber in self.getZoneNumbersForZoneGroup(zoneGroupDeviceId):
                    deviceId = self.getDeviceIdForZoneNumber(zoneNumber)
                    if deviceId != 0:
                        # TO DO: replace this with standard methods to get device state
                        zoneState = self.getZoneStateForDeviceId(deviceId)
                        self.logger.debug(u"checking alarm zone number:{}, id:{}, with state:{}".format(
                            zoneNumber, deviceId, zoneState))
                        if zoneState == AD2USB_Constants.k_FAULT:
                            zoneGroupIsFaulted = True
                            self.logger.debug(u"zone group:{} will be faulted".format(zoneGroupDevice.name))
                            break

                # determine the new zone group state
                newZoneGroupZoneState = AD2USB_Constants.k_CLEAR
                if zoneGroupIsFaulted:
                    newZoneGroupZoneState = AD2USB_Constants.k_FAULT

                # update the device state if it changed
                self.logger.debug(u"zone group state current:{}, new:{}".format(
                    currentZoneGroupZoneState, newZoneGroupZoneState))
                if newZoneGroupZoneState != currentZoneGroupZoneState:
                    self.logger.debug(u"updating zone group:{} to state:{}".format(
                        zoneGroupDevice.name, newZoneGroupZoneState))
                    self.setDeviceState(zoneGroupDevice, newZoneGroupZoneState)
                else:
                    self.logger.debug(u"zone group:{} is not changed".format(zoneGroupDevice.name))

        except Exception as err:
            self.logger.error("Error trying to update all zone groups, current zone group id:{}, error:{}".format(
                zoneGroupDeviceId, str(err)))

    def updateRFBatteryForZone(self, zoneNumber):
        """
        Updates the indigo.device state 'lastBatteryRestore' for a given zone number.

        **parameters**:
        zoneNumber -- a valid zone number (int)
        """

        self.logger.debug(u"called with zone number:{}".format(zoneNumber))

        try:
            # force the parameter to an int
            zoneAsInt = int(zoneNumber)

            # get the device from the zone
            deviceToUpdate = self.getDeviceForZoneNumberAsInt(forZoneNumber=zoneAsInt)

            # check if we found the device
            if deviceToUpdate is not None:

                # confirm its a device type of alarmZone
                if (deviceToUpdate.deviceTypeId == 'alarmZone'):
                    validDeviceStates = deviceToUpdate.states
                    if 'lastBatteryRestore' in validDeviceStates:
                        now = datetime.now()
                        timeStamp = now.strftime("%Y-%m-%d %H:%M:%S")
                        deviceToUpdate.updateStateOnServer(key='lastBatteryRestore', value=timeStamp)

            else:
                self.logger.warning(u"No device found for zone:{}. Unable to set last battery restore time.".format(zoneAsInt))

        except Exception as err:
            self.logger.error("Unable to set last battery restore on zone:{}, error:{}".format(zoneNumber, str(err)))

    def setDeviceState(self, forDevice, newState='NONE', ignoreBypass=False):
        """
        Updates the indigo.device for a given device object (indigo.device) and new state (string)
        the state is the key - not the value in the Devices.xml. The default logic for Bypassed
        devices is to update the text display and internal state but not the icon. If ignoreBypass
        is set to True, devices will CLEAR and FAULT normally and ignore the Bypass state. This
        feature is used internally to reset all devices.

        **parameters**:
        forDevice -- a valid indigo.device object
        newState -- a string for the new state value - use a k_CONSTANT
        ignoreBypass -- boolean (default False) - see above
        """
        self.logger.debug(u"called with name:{}, id:{}, new state:{}".format(forDevice.name, forDevice.id, newState))

        try:
            # get the current bypass state of the device
            isBypassed = self.isDeviceBypassed(forDevice)

            # for a force reset to all devices we pass the optional ignoreBypass
            if ignoreBypass:
                isBypassed = False

            if newState == AD2USB_Constants.k_CLEAR:
                if isBypassed:
                    forDevice.updateStateOnServer(key='zoneState', value=AD2USB_Constants.k_CLEAR,
                                                  uiValue=AD2USB_Constants.kZoneStateUIValues[AD2USB_Constants.k_BYPASS])
                    forDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                else:
                    forDevice.updateStateOnServer(key='zoneState', value=AD2USB_Constants.k_CLEAR,
                                                  uiValue=AD2USB_Constants.kZoneStateUIValues[AD2USB_Constants.k_CLEAR])
                    forDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)

                forDevice.updateStateOnServer(key='onOffState', value=False)

            elif newState == AD2USB_Constants.k_FAULT:
                forDevice.updateStateOnServer(key='zoneState', value=newState,
                                              uiValue=AD2USB_Constants.kZoneStateUIValues[newState])
                forDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)

                forDevice.updateStateOnServer(key='onOffState', value=True)

                # update the last Fault datetime
                localState = forDevice.states
                if 'lastFaultTime' in localState:
                    now = datetime.now()
                    timeStamp = now.strftime("%Y-%m-%d %H:%M:%S")
                    forDevice.updateStateOnServer(key='lastFaultTime', value=timeStamp)

            elif newState == AD2USB_Constants.k_ERROR:
                forDevice.setErrorStateOnServer('Error')
                forDevice.updateStateImageOnServer(indigo.kStateImageSel.Error)

            else:
                self.logger.error(u"Unable to set device name:{}, id:{}, to state:{}".format(
                    forDevice.name, forDevice.id, newState))

            # update any Zone Groups
            try:
                # now that zones have been updated we can refresh the zone groups
                self.updateAllZoneGroups()
            except Exception as err:
                self.logger.error("Error updating Zone Groups:{}".format(str(err)))

        except Exception as err:
            self.logger.error(u"Unable to set device:{}, to state:{}, error:{}".format(forDevice, newState, str(err)))

    def setKeypadDeviceState(self, forDevice, newState='NONE'):
        """
        Updates the indigo.device for a given ad2usb keypad device object (indigo.device) and new state (string)
        The state is the key - not the value in the Devices.xml.

        **parameters**:
        forDevice -- a valid indigo.device object
        newState -- a string for the new state value - use a k_CONSTANT
        """
        self.logger.debug(u"called with name:{}, id:{}, new state:{}".format(forDevice.name, forDevice.id, newState))

        try:

            # skip if not a keypad device
            if forDevice.deviceTypeId != 'ad2usbInterface':
                return False

            # this addresses READY and all ARMED states
            if newState in AD2USB_Constants.k_SENSOR_ON_ICON_STATES:
                forDevice.updateStateOnServer(key='panelState', value=newState,
                                              uiValue=AD2USB_Constants.k_PANEL_STATE_UI_VALUES[newState])
                forDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)

            elif newState in AD2USB_Constants.k_SENSOR_TRIPPED_ICON_STATES:
                forDevice.updateStateOnServer(key='panelState', value=newState,
                                              uiValue=AD2USB_Constants.k_PANEL_STATE_UI_VALUES[newState])
                forDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)

            elif newState in AD2USB_Constants.k_SENSOR_ERROR_ICON_STATES:
                forDevice.updateStateOnServer(key='panelState', value=newState,
                                              uiValue=AD2USB_Constants.k_PANEL_STATE_UI_VALUES[newState])
                forDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)  # Error icon not yet implemented

            else:
                self.logger.error(u"Unable to set device name:{}, id:{}, to state:{}".format(
                    forDevice.name, forDevice.id, newState))

        except Exception as err:
            self.logger.error(u"Unable to set device:{}, to state:{}, error:{}".format(forDevice, newState, str(err)))

    def isDeviceBypassed(self, forDevice):
        """
        checks the bypass status of a current Indigo device. it checks Indigo - not the alarm panel

        **parameters:**
        forDevice -- an Indigo Device object
        """
        self.logger.debug(u'called')

        try:
            currentStates = forDevice.states.to_dict()
            currentBypassState = currentStates.get('bypassState', False)
            self.logger.debug(u'able to read current bypass state:{}'.format(currentBypassState))

            if currentBypassState is True:
                self.logger.debug(u'current bypass state is boolean:{}'.format(currentBypassState))
                return True

            elif currentBypassState is False:
                self.logger.debug(u'current bypass state is boolean:{}'.format(currentBypassState))
                return False

            # legacy case just in case
            elif isinstance(currentBypassState, str) is True:
                self.logger.debug(u'current bypass state is string:{}'.format(currentBypassState))
                if currentBypassState.upper() == 'TRUE':
                    return True
                else:
                    return False

            else:
                self.logger.warning(u'current bypasss tate neither boolean or string')
                return False

        except Exception as err:
            self.logger.error(u'error attempting to determine current bypass state, msg:{}'.format(str(err)))
            return False

    ########################################
    # Indigo Event Triggers: Start and Stop
    ########################################
    def triggerStartProcessing(self, trigger):
        self.logger.info("Enabling trigger:{}".format(trigger.name))
        self.logger.debug("adding trigger:{} to cache".format(trigger))

        # new trigger cache property
        # designed to work even if triggers were not migrated
        try:
            # common to all Triggers
            tid = trigger.id
            triggerType = trigger.pluginTypeId
            events = trigger.pluginProps['indigoTrigger'].to_list()
            partition = trigger.pluginProps['panelPartitionNumber']
            triggerName = trigger.name

            # set user variables to a default
            users = ''
            anyUser = True
            
            # look for these types first to process them quickly
            if (triggerType == 'systemEvents') or (triggerType == 'alarmEvents'):
                anyUser = True

            # else if the event is a user event and the userOption is None - make it selectUser - for migration in v3.3.0
            elif triggerType == 'userEvents':
                # see if this Trigger has been updated since v3.3.0
                userOption = trigger.pluginProps.get('userOption', None)
                if (userOption is None) or (userOption == 'selectUser'):
                    anyUser = False
                    users = trigger.pluginProps.get('userNumber','')
                elif userOption == 'anyUser':
                    anyUser = True

            # to be deprecated after version 3.3.0
            elif triggerType == 'armDisarm':
                anyUser = True
                # throw deprecated warning for Panel Arming Events
                self.logger.error("AD2USB Panel Arming Events are deprecated.") 
                self.logger.error("Delete the Trigger named:{} and replace with a User Action with the 'Any User' option selected.".format(triggerName))

            # build the dictionary
            self.triggerCache[tid] = {'events': events, 'partition': partition, 'name': triggerName, 'type': triggerType, 'anyUser': anyUser, 'users': users}

        except Exception as err:
            self.logger.error("Problem updating new Trigger cache:{}".format(str(err)))

        self.logger.debug(u"updated (post add) Trigger Cache:{}".format(self.triggerCache))

    ########################################
    def triggerStopProcessing(self, trigger):
        self.logger.info(u"Disabling trigger:{}".format(trigger.name))

        # new cache - remove the trigger id if it exists
        tid = trigger.id
        if tid in self.triggerCache:
            self.logger.debug(u"trigger:{} id:{} removed from cache".format(trigger.name, tid))
            del self.triggerCache[tid]

        self.logger.debug(u"updated (post remove) Trigger Cache:{}".format(self.triggerCache))

    def __setURLFromConfig(self):
        """
        sets the object property "URL" (string) based on the plugin configuration dialog settings
        """
        self.logger.debug(u"called")

        self.setURL(self.ad2usbCommType, self.ad2usbAddress, self.ad2usbPort, self.ad2usbSerialPort)

    def setURL(self, commType=None, ipAddress='127.0.0.1', ipPort='', serialPort=None):
        """
        sets the object property "URL" (string) based on the parameters typically provided from the configuration dialog

        **parameters**:
        commType -- either 'IP', 'USB', or 'messageFile' (string)
        ipAddress -- a valid hostname or IP Address (string)
        ipPort -- a valid port number (string)
        serialPort -- a valid USB port selection
        """
        self.logger.debug(u"called with commType:{} ip:{} port:{} serial:{}".format(
            commType, ipAddress, ipPort, serialPort))

        # determine and set communication type and URL properties
        if commType == 'IP':
            self.URL = 'socket://' + ipAddress + ':' + ipPort
            self.isPlaybackCommunicationModeSet = False
        elif commType == 'USB':
            self.URL = serialPort
            self.isPlaybackCommunicationModeSet = False
        elif commType == 'messageFile':
            # seth the URL to the filename and set the flag to True
            self.URL = self.panelMessagePlaybackFilename
            self.isPlaybackCommunicationModeSet = True
        else:
            self.logger.debug(u"invalid commType:{}".format(commType))
            self.logger.debug(u"previous URL will remain:{}".format(self.URL))
            raise Exception(
                'Unable to establish communication to AlarmDecoder. Invalid connection type of:{}'.format(commType))

        self.logger.debug(u"ad2USB URL property set to:{}".format(self.URL))

    def generateAlarmDecoderConfigString(self, sortList=False):
        """
        Reads the internal property 'configSettings' and returns a valid AlarmDecoder config string.
        If the 'sortList' paramater of True is passed it will sort the keys before generating the string.
        The sort is used primarily to be able to detect changes to the string.
        ex: 'CADDRESS=20&DEDUPLICATE=Y\\r'
        """
        self.logger.debug(u'called')

        configString = 'C'  # setting CONFIG always starts with C

        if sortList:

            for parameter in sorted(self.configSettings):
                configString = configString + parameter + '=' + self.configSettings[parameter] + '&'

        else:

            for parameter, setting in self.configSettings.items():
                configString = configString + parameter + '=' + setting + '&'

        # strip the last '&' since it is not needed
        self.logger.debug(u'CONFIG string is:{}'.format(configString[:-1]))
        return configString[:-1] + '\r'  # strip the trailing '&' and add '\r'

    def updateAlarmDecoderConfig(self, valuesDict, typeId):
        """
        Callback used by the AlarmDecoder Configuration Menu Dialog to update the AlarmDecoder CONFIG settings.
        """
        self.logger.debug(u'called with:{}'.format(valuesDict))

        errorDict = indigo.Dict()

        # check to see if the AlarmDecoder was read first
        if self.hasAlarmDecoderConfigBeenRead:
            pass
        else:
            errorDict["makeSpace3"] = "AlarmDecoder Configuration not read."
            errorDict["showAlertText"] = "You must read and load the current AlarmDecoder values before updating. Use the \"Read Config\" button in Step 1 to read the current AlarmDecoder settings."
            return (False, valuesDict, errorDict)

        # validate the field and update configSettings property
        (isSettingsValid, valuesDict, errorDict) = self.setAlarmDecoderConfigDictFromPrefs(valuesDict)

        if isSettingsValid:
            # write the new config to the AlarmDecoder
            configString = self.generateAlarmDecoderConfigString()
            if self.ad2usb.writeAlarmDecoderConfig(configString):
                self.logger.info(
                    u"AlarmDecoder CONFIG message:{} has been sent. Check the Event Log to verify it was successful.".format(configString))
                self.logger.info(u"Plugin preferences have been updated")

                return (True, valuesDict, errorDict)
            else:
                self.logger.warning(u"AlarmDecoder CONFIG:{} was not sent".format(configString))
                errorDict["makeSpace3"] = "AlarmDecoder Configuration not written."
                errorDict["showAlertText"] = "Unable to send the CONFIG message to the AlarmDecoder. AlarmDecoder Configuration will not be updated."
                return (False, valuesDict, errorDict)

        else:
            self.logger.warning(u"AlarmDecoder CONFIG was not updated from valuesDict:{}".format(valuesDict))
            return (False, valuesDict, errorDict)

    def __initPanelLogging(self):
        try:
            # setup a new logger
            panelLogger = logging.getLogger("panelMessageLog")
            self.logger.debug("panel logger created")

            # determine the filename from Indigo paths
            panelFileName = indigo.server.getLogsFolderPath(pluginId=self.pluginId) + "/" + "panelMessages.log"
            self.logger.info('set panel message log filename to:{}'.format(panelFileName))

            # create a new handler
            panelLogHandler = logging.handlers.TimedRotatingFileHandler(
                filename=panelFileName, when="midnight", interval=1, backupCount=30)
            self.logger.debug("panel logging handler created")

            # set the handler log level - we don't really use log levels for the panel log yet
            panelLogHandler.setLevel(logging.DEBUG)
            self.logger.debug("panel log handler level set")

            # set the formatter
            pfnFormatter = logging.Formatter('%(asctime)s.%(msecs)03d | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
            panelLogHandler.setFormatter(pfnFormatter)
            self.logger.debug("panel logger format set")

            # add the handler to the logger object
            panelLogger.addHandler(panelLogHandler)
            self.logger.debug("panel logger handler added")

            # set the logger log level
            panelLogger.setLevel(logging.DEBUG)
            self.logger.debug("panel logger level set")

            # add it as a property to the object
            self.panelLogger = panelLogger
            self.isPanelLoggingEnabled = True
            self.logger.debug("panel logger setup completed")

        except Exception as err:
            self.logger.error("unable to configure panel logging. disabling.")
            self.logger.error("error msg:{}".format(str(err)))
            # turn off panel logging regardless of the preferences
            self.isPanelLoggingEnabled = False

    def __upgradeAndGetPreferences(self, pluginPrefs):
        # Preferences Use Cases handled by private method
        # 1. First time run - no setting - use defaults
        # 2. Upgrade - need to inspect older preferences if they exist and migrate
        # 3. Run with existing preferences/settings

        # BEGIN PREFERENCE MIGRATION logic
        # the start of this method allows for converting old preferences to new ones

        # General Logic:
        # Do new preferences exist?
        #   Yes - this is not a migration
        #   No - check for old prefereces - do they exist?
        #       Yes - migrate preference logic to set new values
        #       No - this same as running for first time

        # 1. LOGGING PREFERNCES migration
        # this section does nothing if new log preferences are set

        # check if new Indigo Log settings do not yet exist
        if pluginPrefs.get("indigoLoggingLevel", "9999") not in AD2USB_Constants.kLoggingLevelNames.keys():
            # look for old logging preferences
            oldLogSetting = pluginPrefs.get("showDebugInfo1", "9999")  # as of 1.6.1

            if oldLogSetting == "0":
                pluginPrefs['indigoLoggingLevel'] = "ERROR"  # ERROR
            elif (oldLogSetting == "1") or (oldLogSetting == "2"):
                pluginPrefs['indigoLoggingLevel'] = "INFO"  # INFO
            elif (oldLogSetting == "3") or (oldLogSetting == "4"):
                pluginPrefs['indigoLoggingLevel'] = "DEBUG"  # "DEBUG
            # this case is neither old or new preferences set - set a default
            else:
                pluginPrefs['indigoLoggingLevel'] = "INFO"  # INFO

        # check if new plugin Log settings do not yet exist
        if pluginPrefs.get("pluginLoggingLevel", "9999") not in AD2USB_Constants.kLoggingLevelNames.keys():
            # look for old logging preferences
            oldLogSetting = pluginPrefs.get("showDebugInfo1", "9999")  # as of 1.6.1

            if (oldLogSetting == "0") or (oldLogSetting == "1") or (oldLogSetting == "2"):
                pluginPrefs['pluginLoggingLevel'] = "INFO"  # INFO
            elif (oldLogSetting == "3") or (oldLogSetting == "4"):
                pluginPrefs['pluginLoggingLevel'] = "DEBUG"  # DEBUG
            # this case is neither old or new preferences set - set a default
            else:
                pluginPrefs['pluginLoggingLevel'] = "INFO"  # INFO

        # END OF PREFERENCE MIGRATION logic

        # now set all the properties based on the preferences
        # we need to have defaults in case this is a new setup and prefs don't exist
        # since log settings are migrated or set to a default above don't need
        # to deal with those

        self.ad2usbCommType = pluginPrefs.get('ad2usbCommType', 'IP')

        self.ad2usbAddress = pluginPrefs.get("ad2usbAddress", '127.0.0.1')
        self.ad2usbPort = pluginPrefs.get("ad2usbPort", '10000')
        self.ad2usbSerialPort = pluginPrefs.get("ad2usbSerialPort", '')

        self.ad2usbIsAdvanced = pluginPrefs.get("isAdvanced", False)
        self.logUnknownDevices = pluginPrefs.get("logUnknownDevices", False)

        self.clearAllOnRestart = pluginPrefs.get("restartClear", True)
        self.numPartitions = int(pluginPrefs.get("panelPartitionCount", '1'))

        # TO DO: this is part of AlarmDecoder CONFIG - do we need it here ?
        self.ad2usbKeyPadAddress = pluginPrefs.get("ad2usbKeyPadAddress", '18')

        self.logArmingEvents = pluginPrefs.get("logArmingEvents", True)
        self.logUnknownLRRMessages = pluginPrefs.get("logUnknownLRRMessages", True)
        self.indigoLoggingLevel = pluginPrefs.get("indigoLoggingLevel", "INFO")  # 20 = INFO
        self.pluginLoggingLevel = pluginPrefs.get("pluginLoggingLevel", "INFO")  # 20 = INFO
        self.isPanelLoggingEnabled = pluginPrefs.get("isPanelLoggingEnabled", False)
        self.isCodeMaskingEnabled = pluginPrefs.get("isCodeMaskingEnabled", True)

        self.isOTPEnabled = pluginPrefs.get("enableOTP", False)
        self.OTPConfigPath = pluginPrefs.get("OTPConfigPath", '')

        self.isCodeSaved = pluginPrefs.get("enableCode", False)
        self.codeLocation = pluginPrefs.get("codeLocation", AD2USB_Constants.k_CODE_USE_VARIABLE)
        self.alarmCode = pluginPrefs.get("alarmCode", None)
        self.alarmCodeVariable = pluginPrefs.get("alarmCodeVariable", None)

        self.isHomeKitEnabled = pluginPrefs.get("isHomeKitEnabled", False)
        self.hkArmMethod = pluginPrefs.get("hkArmMethod", 'quickArm')

        # computed settings
        if self.ad2usbCommType == 'messageFile':
            self.isPlaybackCommunicationModeSet = True

        # new settings

    def __setLoggingLevels(self):
        # check for valid logging level first
        # we're using level names as strings in the PluginConfig.xml and logging uses integers

        # Indigo Log
        if self.indigoLoggingLevel in AD2USB_Constants.kLoggingLevelNames.keys():
            self.indigo_log_handler.setLevel(AD2USB_Constants.kLoggingLevelNames[self.indigoLoggingLevel])
            self.logger.info(u"Indigo logging level set to:{} ({})".format(
                self.indigoLoggingLevel, AD2USB_Constants.kLoggingLevelNames[self.indigoLoggingLevel]))
        else:
            self.indigo_log_handler.setLevel(logging.INFO)
            self.logger.error(u"Invalid Indigo logging level:{} - setting level to INFO".format(self.indigoLoggingLevel))

        # plugin log

        # change the formatter to add thread ID
        pluginLogFormatter = logging.Formatter(
            '%(asctime)s.%(msecs)03d\t%(levelname)s\t%(thread)d %(name)s.%(funcName)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        self.plugin_file_handler.setFormatter(pluginLogFormatter)

        if self.pluginLoggingLevel in AD2USB_Constants.kLoggingLevelNames.keys():
            self.plugin_file_handler.setLevel(AD2USB_Constants.kLoggingLevelNames[self.pluginLoggingLevel])
            self.logger.info(u"Plugin logging level set to:{} ({})".format(
                self.pluginLoggingLevel, AD2USB_Constants.kLoggingLevelNames[self.pluginLoggingLevel]))
        else:
            self.plugin_file_handler.setLevel(logging.INFO)
            self.logger.error(
                u"Invalid pluging logging level:{} - setting level to INFO".format(self.pluginLoggingLevel))

    def getFlagInString(self, string='', bit=1):
        """
        expects a CONFIG string in the format of '[YN]{d}' (e.g. 'YNYYYNY') and returns True or False
        if the specific bit (1-N) is Y or N. An empty string, invalid bit length or invalid character will return False

        **parameters:**
        string -- a string of Y and N - of any length
        bit -- integer of which bit (character) you are interested in. Valid parameters are 1 to the length of the string
        """

        self.logger.debug(u'getting bit:{} from string:{}'.format(bit, string))

        # make sure bit is valid
        if (bit > len(string)) or (bit < 1):
            return False

        # make sure string is > 0 characters
        if len(string) == 0:
            return False

        # test the single character of the desired bit
        position = bit - 1  # strings start with 0
        flag = string[position:position + 1]
        if (flag == 'Y') or (flag == 'y'):
            self.logger.debug(u'bit:{} of string:{} is True'.format(bit, string))
            return True
        else:
            self.logger.debug(u'bit:{} of string:{} is False'.format(bit, string))
            return False

    def setFlagInString(self, string='', bit=1, newValue=None):
        """
        expects a CONFIG string in the format of '[YN]{d}' (e.g. 'YNYYYNY'), a bit number, and the new value
        to set (True or False). It returns the string with the bit specified updated. An empty string,
        invalid bit length or invalid new value will return the string unchanged

        **parameters:**
        string -- a string of Y and N - of any length
        bit -- integer of which bit (character) you are interested in. Valid parameters are 1 to the length of the string
        """

        self.logger.debug(u'setting bit:{} of string:{} to:{}'.format(bit, string, newValue))

        # make sure bit is valid
        if (bit > len(string)) or (bit < 1):
            return string

        # make sure string is > 0 characters
        if len(string) == 0:
            return string

        position = bit - 1
        newStringArray = list(string)

        if newValue is True:
            newStringArray[position] = 'Y'
            newString = "".join(newStringArray)
            self.logger.debug(u'new string is:{}'.format(newString))
            return newString

        if newValue is False:
            newStringArray[position] = 'N'
            newString = "".join(newStringArray)
            self.logger.debug(u'new string is:{}'.format(newString))
            return newString

        # we should never get here but just in case
        return string

    def getZoneDeviceForEXP(self, address=None, channel=None, includeDisabled=False):
        """
        Returns an Indigo EXP Zone device object for the address and channel provided. By default disabled devices
        will not be included. Optionally pass parameter 'includeDisabled' with a value of True to include disable
        devices too. Return a device object if found, None if not.
        """
        try:
            if (address is None) or (channel is None):
                return None

            for device in indigo.devices.iter("self"):
                # just the Zone Devices
                if device.deviceTypeId == 'alarmZone':
                    # just the EXP devices
                    if device.pluginProps['ad2usbZoneType'] == 'zoneTypeEXP':
                        self.logger.debug("looking for address:{}, channel:{} in:{}".format(
                            address, channel, device.pluginProps))

                        # just the match of the address and channel
                        # ad2usbZoneTypeEXP_Board, ad2usbZoneTypeEXP_Device
                        if (int(device.pluginProps['ad2usbZoneTypeEXP_Board']) == int(address)) and (int(device.pluginProps['ad2usbZoneTypeEXP_Device']) == int(channel)):

                            # only if enabled of the includeDisabled flag is True
                            if device.enabled or (includeDisabled is True):
                                return device

            # if we are here the device was not found or was disabled
            if includeDisabled:
                self.logger.warning(
                    "Indigo EXP Device for address:{}, channel:{} was not found".format(address, channel))
                return None
            else:
                self.logger.warning(
                    "Indigo EXP Device for address:{}, channel:{} not found or disabled.".format(address, channel))
                return None

        except Exception as err:
            self.logger.error("Error retrieving Indigo EXP Device for address:{}, channel:{} msg:{}".format(
                address, channel, str(err)))
            return None

    def getAllKeypadDevices(self, includeDisabled=False):
        """
        Returns an array of 'ad2usb Keypad' Indigo device objects. By default disabled
        keypad devices will not be included. Optionally pass parameter of True to include
        disable devices too.
        """
        try:
            self.logger.debug('called')

            allKeypadDevices = []

            # get all the keypad devices
            for device in indigo.devices.iter("self"):
                # just the Keypad Devices
                if device.deviceTypeId == 'ad2usbInterface':
                    if device.enabled or (includeDisabled is True):
                        allKeypadDevices.append(device)

            return allKeypadDevices

        except Exception as err:
            self.logger.error(u"error retrieving ad2usb Keypad devices from Indigo, msg:{}".format(str(err)))
            # return emptyArray
            emptyArray = []
            return emptyArray

    def getAllKeypadAddresses(self, includeDisabled=False):
        """
        Returns an array of keypad addresses (strings). The array is the address from each 'ad2usb Keypad'
        Indigo device objects. By default disabled keypad devices will not be included. Optionally pass
        the parameter of True to include disable devices too.
        """
        try:
            self.logger.debug('called')

            allKeypadAddresses = []

            # get all the keypad devices
            for device in indigo.devices.iter("self"):
                # just the Keypad Devices
                if device.deviceTypeId == 'ad2usbInterface':
                    if device.enabled or (includeDisabled is True):

                        # get the address from each keypad
                        localProps = device.pluginProps.to_dict()
                        if 'panelKeypadAddress' in localProps:
                            allKeypadAddresses.append(localProps['panelKeypadAddress'])

            self.logger.debug("found {} keypad addresses:{}".format(len(allKeypadAddresses), allKeypadAddresses))
            return allKeypadAddresses

        except Exception as err:
            self.logger.error(u"error retrieving ad2usb Keypad addresses from Indigo, msg:{}".format(str(err)))
            # return emptyArray
            emptyArray = []
            return emptyArray

    def getKeypadAddressFromDevice(self, keypadDevice=None):
        """
        Returns a valid keypad address from an Indigo ad2usb keypad device object. None is returned if address is
        does not exist.

        **parameters**
        keypadDevice - a valid Indigo ad2usb keypad device object
        """
        try:
            self.logger.debug("called with:{}".format(keypadDevice))

            if keypadDevice is None:
                return None

            # get a Python dict from plugin properities
            localProps = keypadDevice.pluginProps.to_dict()
            if 'panelKeypadAddress' in localProps:
                self.logger.debug("keypad address found:{}".format(localProps['panelKeypadAddress']))
                # check if its all digits
                if localProps['panelKeypadAddress'].isdigit():
                    return localProps['panelKeypadAddress']
                else:
                    self.logger.debug("keypad address found but not valid:{}".format(localProps['panelKeypadAddress']))
                    return None

            # if we get this far it does not exist
            self.logger.debug("did not find keypad adddress for keypad device")
            return None

        except Exception as err:
            self.logger.error("error getting keypad address for ad2usb Keypad device, msg:{}".format(str(err)))
            return None

    def getKeypadDeviceForDevice(self, forDevice=None):
        """
        A keypad Indigo device object is returned if the partition number of the zone device
        'forDevice' matches keypad's partition setting. Otherwise None is returned.

        **parameters**
        forDevice - an Indigo zone device
        """
        try:
            # make sure we have device parameter
            if forDevice is None:
                return None

            # set the default value for the keypad
            keypadDevice = None

            # get the partition from provided device
            validPartition = forDevice.pluginProps['zonePartitionNumber']
            if validPartition.isdigit():
                self.logger.debug("looking for keypad device for partition:{}".format(validPartition))
                keypadDevice = self.getKeypadDeviceForPartition(partition=validPartition)
            else:
                self.logger.warning(
                    "Device:{} does not have a valid parition set. Cannot determine associated keypad.".format(forDevice.name))
                return None

            if keypadDevice is None:
                self.logger.warning("Device:{} with parition:{} does not have an associated Indigo ad2usb Keypad device.".format(
                    forDevice.name, validPartition))
                return None
            else:
                self.logger.debug("found keypad device for partition:{}".format(validPartition))
                return keypadDevice

        except Exception as err:
            self.logger.error("error searching for ad2usb Keypad device for device, msg:{}".format(str(err)))
            return None

    def getKeypadDeviceForId(self, deviceId=None):
        """
        A keypad Indigo device object is returned if the device id provided is a keypad device. Otherwise None is returned.

        **parameters**
        deviceId - an Indigo device id value as an integer (e.g. 5512462)
        """
        try:
            # check parameters
            if deviceId is None:
                return None

            # ensure its an int
            deviceIdAsInt = int(deviceId)
            self.logger.debug("Searching for ad2usb Keypad device id:{} - int value:{}".format(deviceId, deviceIdAsInt))
 
            # get all keypads
            allKeypadDevices = self.getAllKeypadDevices()

            # the case of no keypad devices
            if len(allKeypadDevices) == 0:
                if int(self.numPartitions) == 1:
                    self.logger.error("No Indigo ad2usb Keypad device found; exactly one (1) should be defined")
                else:
                    self.logger.error("No Indigo ad2usb Keypad device found; one (1) per partition should be defined")

                return None

            # if we have keypad devices search for one that matches deviceId
            else:
                for oneKeypadDevice in allKeypadDevices:
                    if oneKeypadDevice.id == deviceIdAsInt:
                        self.logger.debug("found keypad:{} match for device id:{}".format(oneKeypadDevice.name, deviceId))
                        return oneKeypadDevice

            # if we get this far it does not exist
            self.logger.debug("did not find keypad match for device id:{}".format(deviceId))
            return None

        except Exception as err:
            self.logger.error("error searching for ad2usb Keypad device by id, msg:{}".format(str(err)))
            return None

    def getKeypadDeviceForPartition(self, partition=None):
        """
        A keypad Indigo device object is returned if the partition number of the keypad device
        matches partition parameter. Otherwise None is returned.

        **parameters**
        partition - a partition value as a string (e.g. "2")
        """
        try:
            allKeypadDevices = self.getAllKeypadDevices()
            partitionAsString = str(partition)

            # the case of no devices
            if len(allKeypadDevices) == 0:
                if int(self.numPartitions) == 1:
                    self.logger.error("No Indigo ad2usb Keypad device found; exactly one (1) should be defined")
                else:
                    self.logger.error("No Indigo ad2usb Keypad device found; one (1) per partition should be defined")

                return None

            # the case of mutiple keypad devices and parition parameter provided but not '0'
            elif (partition is not None):
                for oneKeypadDevice in allKeypadDevices:
                    if oneKeypadDevice.pluginProps['panelPartitionNumber'] == partitionAsString:
                        return oneKeypadDevice

            # if we get this far it does not exist
            self.logger.debug("did not find keypad match for partition:{}".format(partitionAsString))
            return None

        except Exception as err:
            self.logger.error("error searching for ad2usb Keypad device by partition, msg:{}".format(str(err)))
            return None

    def getKeypadDeviceForAddress(self, address=None):
        """
        Returns a keypad device matching the address (string). If found the device object is returned.
        None is returned if no address parameter is provided, if no keypad is found with the address,
        of the address provided is invalid.

        **parameters**
        address - a keypad address value as a string (zero-padded, 2-digits) (e.g. "18")
        """
        try:
            if address is None:
                return None

            if not self.isValidKeypadAddress(address):
                return None

            allKeypadDevices = self.getAllKeypadDevices()
            addressAsInt = int(address)

            # the case of no devices
            if len(allKeypadDevices) == 0:
                if int(self.numPartitions) == 1:
                    self.logger.error("No Indigo ad2usb Keypad device found; exactly one (1) should be defined")
                else:
                    self.logger.error("No Indigo ad2usb Keypad device found; one (1) per partition should be defined")

                return None

            # now look thru each keypad for one that matches address and return it
            for eachKeypad in allKeypadDevices:
                localProps = eachKeypad.pluginProps.to_dict()
                if 'panelKeypadAddress' in localProps:
                    # if the addresses match via integer comparison
                    if int(localProps['panelKeypadAddress']) == addressAsInt:
                        self.logger.debug("found keypad match for address (as int):{}".format(addressAsInt))
                        return eachKeypad

            # if we get this far it does not exist
            self.logger.debug("did not find keypad match for address (as int):{}".format(addressAsInt))
            return None

        except Exception as err:
            self.logger.error("error searching for ad2usb Keypad device by address, msg:{}".format(str(err)))
            return None

    def updateKeypadDevice(self, newAddress='', oldAddress=''):
        """
        This method is called when the AlarmDecoder Keypad Address may have changed. It will do several things:
        It will do nothing if the old and new addresses are the same or the new address is not a valid address.
        If the new address is valid and different it will update the hidden preference for the keypad and
        update the plugin legacy property 'ad2usbKeyPadAddress'. It will als look for the appropiate
        keypad device and change the address. This is trivial for single (1) parition systems since they will
        have one keypad device but more complicated when multiple keypads exist.

        Return True if the keypad was updated, False if it was not, and None if either address is invalid of there was
        and error.
        """
        try:
            # do nothing is newAddress = oldAddress
            if newAddress == oldAddress:
                return False

            # test that new the new address is valid
            if self.isValidKeypadAddress(newAddress):
                # update the legacy property
                self.ad2usbKeyPadAddress = newAddress

                # update the hidden preference
                self.pluginPrefs['ad2usbKeyPadAddress'] = newAddress

            # return is invalid new address
            else:
                return None

            # need to update panelKeypadAddress and address property
            # get all keypads
            allKeypads = self.getAllKeypadDevices()

            # test the single keypad device case
            # a single keypad
            if len(allKeypads) == 1:
                newPluginProps = allKeypads[0].pluginProps
                newPluginProps['address'] = 'Keypad ' + newAddress
                newPluginProps['panelKeypadAddress'] = newAddress

                # replace the values on the server
                allKeypads[0].replacePluginPropsOnServer(newPluginProps)

            else:
                # store if the old address is valid.
                # we will suppress log messages if old address was invalid for first time runs
                isValidOldAddress = self.isValidKeypadAddress(oldAddress)
                if isValidOldAddress:
                    # look for the old address exists
                    keyPadDevice = self.getKeypadDeviceForAddress(oldAddress)
                else:
                    keyPadDevice = None

                possibleDuplicateKeypad = self.getKeypadDeviceForAddress(newAddress)

                # scenarios:
                # 1. keypad exists with old address and no keypad found with new address: update keypad
                # 2. no keypad exists with old address and no keypad found with new address: alert error to add keypad
                # 3. keypad exists with old address and keypad found with new address: alert warn to review keypad devices
                # 4. no keypad exists with old address and keypad found with new address: alert error to possible remove keypad

                # scenario 1
                if (keyPadDevice is not None) and (possibleDuplicateKeypad is None):
                    self.logger.info("Updating Keypad Device:{} with keypad address:{} from Alarm Decoder. Review your Keypad Devices if needed.".format(
                        keyPadDevice.name, newAddress))

                    newPluginProps = keyPadDevice.pluginProps
                    newPluginProps['address'] = 'Keypad ' + newAddress
                    newPluginProps['panelKeypadAddress'] = newAddress

                    # replace the values on the server
                    keyPadDevice.replacePluginPropsOnServer(newPluginProps)

                # scenario 2
                elif (keyPadDevice is None) and (possibleDuplicateKeypad is None):
                    self.logger.error(
                        "No Keypad Device exists with (new?) keypad address:{} from Alarm Decoder. Add at least one Keypad Devices with the address of your AlarmDecoder.".format(newAddress))

                # scenario 3
                elif (keyPadDevice is not None) and (possibleDuplicateKeypad is not None):
                    self.logger.warning(
                        "Detected change in Alarm Decoder address:{}. Review your Keypad Indigo Device settings.".format(newAddress))

                # scenario 4
                elif (keyPadDevice is None) and (possibleDuplicateKeypad is not None):
                    if isValidOldAddress:
                        self.logger.warning(
                            "Detected change in Alarm Decoder address:{}. Review your Keypad Indigo Device settings.".format(newAddress))

        except Exception as err:
            self.logger.error(
                "Error while attempting to update Keypad Device with new AlarmDecoder address:{}".format(str(err)))

    def updateLastADMessageOnKeypads(self):
        """
        Updates all Keypad devices state 'lastADMessage' with the current date-time. The 'lastADMessage' state is used
        as a heartbeat to confirm the AlarmDecoder is still working when the panel is armed. So far, only RFX messsages are
        seen when panel is armed.
        """
        try:
            self.logger.debug("called")
            now = datetime.now()
            timeStamp = now.strftime("%Y-%m-%d %H:%M:%S")

            for eachKeypad in self.getAllKeypadDevices():
                self.logger.debug("Updating lastADMessage on Keypad Device:{} with new lastADMessage:{}".format(eachKeypad.name, timeStamp))
                eachKeypad.updateStateOnServer(key='lastADMessage', value=timeStamp)

        except Exception as err:
            self.logger.error("Error while attempting to update all Keypad Devices with new lastADMessage:{}".format(str(err)))

    def isValidKeypadAddress(self, address=None):
        """
        Test the provided keypad address (string) to make sure its a zero-padded string between 01 and 99.
        Returns True or False.
        """
        # return if nothing is passed
        if address is None:
            self.logger.debug('invalid keypad address of:{}'.format(address))
            return False

        # return if not a string
        if not isinstance(address, str):
            self.logger.debug('invalid keypad address is not a string:{}'.format(address))
            return False

        # make sure every character is a digit
        allDigits = True  # assume its true
        for c in address:
            if c.isdigit():
                pass
            else:
                allDigits = False
                self.logger.debug('invalid keypad address:{} contains a non-digit character'.format(address))

        # if every character is a digit test the value range
        if allDigits and (int(address) > 0) and (int(address) <= 99):
            self.logger.debug('valid keypad address:{}'.format(address))
            return True
        else:
            self.logger.debug('invalid keypad address:{} not between 1 and 99'.format(address))
            return False

    def isValidPartition(self, partition=None):
        """
        Checks if provided partition number (string) is set in a Keypad device. Returns True if it exist, False otherwise.
        """
        try:
            if partition is None:
                return False

            partitionList = []
            for keypadAndPartition in self.getPartitionList():
                partitionList.append(keypadAndPartition[1])

            if partition not in partitionList:
                self.logger.debug('Unable to find partition:{} in list of Keypad devices:{}'.format(partition, partitionList))
                return False
            else:
                # partition found in a keypad device
                return True
        
        except Exception as err:
            self.logger.debug('Unable to validate partition:{} - error:{}'.format(partition, str(err)))
            return False
        
    def keypadAddressFrom(self, addressToTransform=''):
        """
        Transform provided address 'addressToTransform' (string) to be a two-digit valid keypad
        address (01-99). Returns the valid string ('01' to '99') or None if cannot be converted.
        """
        try:
            address = addressToTransform

            # if its not a string make it one
            if not isinstance(address, str):
                address = str(address)

            # remove all non-digits
            newString = ''
            for c in address:
                if c.isdigit():
                    newString = newString + c

            address = newString

            # try to make it an valid integer
            try:
                addressAsInt = int(address)
                addressAsInt = abs(addressAsInt)
            except Exception as err:
                self.logger.warning(
                    'provided keypad address:{} is not a valid keypad address (01-99). Error:{}'.format(addressToTransform, str(err)))
                addressAsInt = 0

            # convert address as an integer to zero padded string
            if (addressAsInt > 9) and (addressAsInt < 100):
                return str(addressAsInt)

            elif (addressAsInt > 0) and (addressAsInt < 10):
                return '0' + str(addressAsInt)

            else:
                self.logger.warning(
                    'Provided keypad address:{} is not a valid keypad address (01-99).'.format(addressToTransform))
                return None

        except Exception as err:
            self.logger.warning(
                'provided keypad address:{} is not a valid keypad address (01-99). Error:{}'.format(addressToTransform, str(err)))
            return None

    def basicBuildDevDict(self, dev, funct, ad2usbKeyPadAddress):
        """
        Build/Modify device property dictionaries for basic mode. Called on startup and
        shutdown this method build an internal cache 'zoneDict'.
        """
        self.logger.debug(u"Called for function:{}".format(funct))
        self.logger.debug(u"received device:{}".format(dev))

        # This block is for adding new zones or keypads
        if funct == 'add':
            if dev.deviceTypeId == 'alarmZone' or dev.deviceTypeId == 'alarmZoneVirtual':
                zoneDevId = dev.id
                zoneName = dev.name
                # Make an excepton for pseudo zones, etc. that aren't supported in basic mode
                # If the panel can't report it, neither can we.
                try:
                    zoneNumber = int(dev.pluginProps['zoneNumber'])
                except:
                    zoneNumber = 0

                zoneState = ""   # dev.states['zoneState']
                zoneLogChanges = dev.pluginProps['zoneLogChanges']
                zoneIndex = zoneNumber
                self.zonesDict[zoneIndex] = {'devId': zoneDevId, 'number': zoneNumber,
                                             'logChanges': zoneLogChanges, 'name': zoneName, 'state': zoneState}
                self.logger.debug(u"added record for device:{}, zone:{}".format(zoneName, zoneNumber))
                self.logger.debug(u"wrote record:{}".format(self.zonesDict[zoneIndex]))

            elif dev.deviceTypeId == 'ad2usbInterface':
                pass

            elif dev.deviceTypeId == 'zoneGroup':
                self.addGroupDev(dev)

        # This block is for deleting zones
        elif funct == 'del':
            if dev.deviceTypeId == 'alarmZone':
                zoneNumber = int(dev.pluginProps['zoneNumber'])
                zoneName = dev.name

                del self.zonesDict[zoneNumber]
                self.logger.debug(u"deleted entry for zone number:{}, zone name:{}".format(zoneNumber, zoneName))

        self.logger.debug(u"completed")

    # For advanced mode
    def advancedBuildDevDict(self, dev, funct, ad2usbKeyPadAddress):
        """
        Build/Modify device property dictionaries for advanced mode. Called on startup and
        shutdown this method build an internal cache 'advZonesDict'.
        """
        self.logger.debug(u"Called for device:{}, type:{}, function:{}".format(dev.name, dev.deviceTypeId, funct))
        self.logger.debug(u"received device:{}".format(dev))

        # This block is for adding new zones or keypads
        if funct == 'add':
            if dev.deviceTypeId == 'alarmZone' or dev.deviceTypeId == 'alarmZoneVirtual':
                zoneType = dev.pluginProps['ad2usbZoneType']
                zoneType = zoneType[-3:]
                zoneDevId = dev.id
                zoneName = dev.name
                zoneNumber = dev.pluginProps['zoneNumber']
                zoneState = ""   # dev.states['zoneState']
                zoneLogChanges = dev.pluginProps['zoneLogChanges']

                # BUG: logSupervision only exists on alarmZone devices in Devices.xml
                # it doesn't appear this property is ever used anyway
                if dev.deviceTypeId == 'alarmZone':
                    zoneLogSupervision = dev.pluginProps['logSupervision']
                else:
                    zoneLogSupervision = "1"  # TO DO: remove this

                zonePartition = dev.pluginProps['zonePartitionNumber']

                if zoneType == 'REL':
                    zoneBoard = dev.pluginProps['ad2usbZoneTypeREL_Board']
                    zoneDevice = dev.pluginProps['ad2usbZoneTypeREL_Device']
                    if len(zoneBoard) == 1:
                        zoneBoard = '0' + zoneBoard
                    if len(zoneDevice) == 1:
                        zoneDevice = '0' + zoneDevice
                    zoneIndex = zoneBoard + ',' + zoneDevice
                elif zoneType == 'EXP':
                    zoneBoard = dev.pluginProps['ad2usbZoneTypeEXP_Board']
                    zoneDevice = dev.pluginProps['ad2usbZoneTypeEXP_Device']
                    if len(zoneBoard) == 1:
                        zoneBoard = '0' + zoneBoard
                    if len(zoneDevice) == 1:
                        zoneDevice = '0' + zoneDevice
                    zoneIndex = zoneBoard + ',' + zoneDevice
                elif zoneType == 'RFX':
                    zoneBoard = dev.pluginProps['ad2usbZoneTypeRFX_Id']
                    zoneDevice = dev.pluginProps['ad2usbZoneTypeRFX_Loop']
                    zoneIndex = zoneBoard
                    if len(zoneDevice) == 1:
                        zoneDevice = '0' + zoneDevice

                self.advZonesDict[zoneIndex] = {'type': zoneType, 'board': zoneBoard, 'device': zoneDevice, 'devId': zoneDevId, 'number': zoneNumber,
                                                'logChanges': zoneLogChanges, 'logSupervision': zoneLogSupervision, 'name': zoneName, 'state': zoneState, 'partition': zonePartition}
                self.logger.debug(u"added record for device:{}, zone:{}".format(zoneName, zoneNumber))
                self.logger.debug(u"wrote record:{}".format(self.advZonesDict[zoneIndex]))

            elif dev.deviceTypeId == 'ad2usbInterface':
                pass

            elif dev.deviceTypeId == 'zoneGroup':
                self.addGroupDev(dev)

        # This block is for deleting zones
        elif funct == 'del':
            if dev.deviceTypeId == 'alarmZone':
                zoneType = dev.pluginProps['ad2usbZoneType']
                zoneType = zoneType[-3:]
                zoneDevId = dev.id
                zoneName = dev.name
                zoneNumber = dev.pluginProps['zoneNumber']
                zoneState = ""

                if zoneType == 'REL':
                    zoneBoard = dev.pluginProps['ad2usbZoneTypeREL_Board']
                    zoneDevice = dev.pluginProps['ad2usbZoneTypeREL_Device']
                    if len(zoneBoard) == 1:
                        zoneBoard = '0' + zoneBoard
                    if len(zoneDevice) == 1:
                        zoneDevice = '0' + zoneDevice
                    zoneIndex = zoneBoard + ',' + zoneDevice
                elif zoneType == 'EXP':
                    zoneBoard = dev.pluginProps['ad2usbZoneTypeEXP_Board']
                    zoneDevice = dev.pluginProps['ad2usbZoneTypeEXP_Device']
                    if len(zoneBoard) == 1:
                        zoneBoard = '0' + zoneBoard
                    if len(zoneDevice) == 1:
                        zoneDevice = '0' + zoneDevice
                    zoneIndex = zoneBoard + ',' + zoneDevice
                elif zoneType == 'RFX':
                    zoneBoard = dev.pluginProps['ad2usbZoneTypeRFX_Id']
                    zoneDevice = dev.pluginProps['ad2usbZoneTypeRFX_Loop']
                    zoneIndex = zoneBoard
                    if len(zoneDevice) == 1:
                        zoneDevice = '0' + zoneDevice

                del self.advZonesDict[zoneIndex]
                self.logger.debug(u"deleted entry for zone number:{}, name:{}, type:{}".format(
                    zoneNumber, zoneName, zoneType))

        self.logger.debug(u"completed")

    # TO DO: I should be able to remove this now - replaced by getZoneNumbersForZoneGroup()
    # and getAllZoneGroupsForZone()
    def addGroupDev(self, dev):
        """
        Maintain zone group device cache data. Data is stored in 'zone2zoneGroupDevDict' property for
        map of zones -> groups and 'zoneGroup2zoneDict' for zone group -> zones.

        **parameters:**
        dev - Indigo device object for a Zone Group device
        """
        self.logger.debug(u"Called")
        self.logger.debug(u"received device:{}".format(dev))

        zoneDeviceList = dev.pluginProps[u'zoneDeviceList']
        zoneLogChanges = dev.pluginProps[u'zoneLogChanges']
        self.logger.debug(u"Received: zoneDevceList:{}, zoneLogChanges:{}".format(zoneDeviceList, zoneLogChanges))

        # TO DO:
        # restructure?
        # zoneGroupDevices = { name: { 'zone': state, ... }, name: {..} }
        # zoneGroupForZone = { 'zone': groups: [group1, group2, ... ], 'zone' }

        try:
            for zone in zoneDeviceList:
                self.logger.debug(u"...found:{}".format(zone))
                # Create a zone number to zoneGroup device table
                if zone in self.zone2zoneGroupDevDict:
                    self.logger.debug(u"IF        got here for:{}, {}".format(zone, self.zone2zoneGroupDevDict[zone]))
                    self.zone2zoneGroupDevDict[zone].append(int(dev.id))
                else:
                    self.logger.debug(u"%IF NOT       got here for:{}".format(zone))
                    self.zone2zoneGroupDevDict[zone] = []
                    self.zone2zoneGroupDevDict[zone].append(int(dev.id))

                # Create a zoneGroup device to zone state table
                if dev.id in self.zoneGroup2zoneDict:
                    self.zoneGroup2zoneDict[dev.id][zone] = 'Clear'
                else:
                    self.zoneGroup2zoneDict[dev.id] = {}
                    self.zoneGroup2zoneDict[dev.id][zone] = 'Clear'

            self.logger.debug(u"...returned zone2zoneGroupDevDict:{}".format(self.zone2zoneGroupDevDict))
            self.logger.debug(u"...returned zoneGroup2zoneDict:{}".format(self.zoneGroup2zoneDict))
        except Exception as err:
            self.logger.error(u"error adding group zone device:{}".format(str(err)))

    def __clearAllDevices(self, includeDisabled=False):
        """
        Clears the state of all enabled AlarmDecoder plugin devices: Zone, Zone Group, Virtual Zone, and Keypad.
        If disabled flag is set to True then it will also try to clear disabled devices.
        """
        try:
            self.logger.debug("called with:{}".format(includeDisabled))

            # get all the AlarmDecoder devices
            for device in indigo.devices.iter("self"):

                # Clear the device is the device is enabled or the includeDisabled flag is True
                if (device.enabled is True) or (includeDisabled is True):

                    # clear zone devices
                    if device.deviceTypeId == 'alarmZone':
                        device.updateStateOnServer(key='bypassState', value=False, clearErrorState=True)
                        self.setDeviceState(forDevice=device, newState=AD2USB_Constants.k_CLEAR, ignoreBypass=True)

                    # clear virtual zone devices
                    elif device.deviceTypeId == 'alarmZoneVirtual':
                        device.updateStateOnServer(key='bypassState', value=False, clearErrorState=True)
                        self.setDeviceState(forDevice=device, newState=AD2USB_Constants.k_CLEAR, ignoreBypass=True)

                    # clear zone groups
                    elif device.deviceTypeId == 'zoneGroup':
                        self.setDeviceState(forDevice=device, newState=AD2USB_Constants.k_CLEAR, ignoreBypass=True)

                    # the Keypad Devices
                    elif device.deviceTypeId == 'ad2usbInterface':
                        self.setKeypadDeviceState(forDevice=device, newState=AD2USB_Constants.k_PANEL_READY)

        except Exception as err:
            self.logger.error("Unable to clear all devices - msg:{}".format(str(err)))
            return False

    def __getPaddedNumber(self, zoneNumber):
        """
        Returns a 2-digit padded zone number as a string. Returns None if zoneNumber is neither
        a string or int or not in the range of 00-99

        **parameters:**
        zoneNumber - integer or string of the zone number to convert to string
        """
        if isinstance(zoneNumber, int):
            if (len(str(zoneNumber)) == 1) and (zoneNumber <= 99) and (zoneNumber >= 0):
                return '0' + str(zoneNumber)
            else:
                return str(zoneNumber)

        elif isinstance(zoneNumber, str):
            if len(zoneNumber) == 1:
                return '0' + zoneNumber
            else:
                return zoneNumber[:2]

        else:
            self.logger.debug('Unable to generate padded zone string')
            return None

    def logPluginProps(self):
        self.logger.info("ZoneDict:{}".format(self.zonesDict))
        self.logger.info("Advanced ZonesDict:{}".format(self.advZonesDict))
        self.logger.info("Preferences:{}\n".format(self.pluginPrefs))

    def logDeviceProps(self):
        for device in indigo.devices.iter("self"):
            self.logger.info("Device:{}".format(device))

    def sendAlarmDecoderConfigCommand(self):
        # set the previous CONFIG string to empty to force message to be written to console log
        self.previousCONFIGString = ''
        self.ad2usb.sendAlarmDecoderConfigCommand()

    def sendAlarmDecoderVersionCommand(self):
        self.showFirmwareVersionInLog = True
        self.ad2usb.sendAlarmDecoderVersionCommand()

    def variableUpdated(self, origVar, newVar):
        """
        Indigo's built in plugin method to detect variable changes.
        """
        self.logger.debug("Called with {}:{}".format(newVar.name, newVar.value))
        # check for variable name
        if (newVar.name == 'ArmAwayOTP') or (newVar.name == 'ArmStayOTP'):

            if self.isOTPEnabled:
                if self.otp.isValidOTP(newVar.value):
                    code = self.otp.getAlarmCode()
                    if code is None:
                        self.logger.error(
                            "Invalid alarm code configured. Check configuration file to ensure alarm code is set.")
                    else:

                        if newVar.name == 'ArmAwayOTP':
                            self.logger.info('OTP Validated. Arming Alarm AWAY now')
                            messageToSend = code + '2'
                            self.ad2usb.panelMsgWrite(messageToSend)

                        if newVar.name == 'ArmStayOTP':
                            self.logger.info('OTP Validated. Arming Alarm STAY now')
                            messageToSend = code + '3'
                            self.ad2usb.panelMsgWrite(messageToSend)

                        code = None
                else:
                    self.logger.warning('OTP for Arming Alarm is not valid.')
            else:
                self.logger.warning(
                    "OTP is not enabled. Check that it is enabled with a valid Folder Pathin 'Configure' - or required Python Modules may be missing.")

        if newVar.name == 'DisarmOTP':

            if self.isOTPEnabled:
                if self.otp.isValidOTP(newVar.value):
                    self.logger.info('OTP Disarming Alarm  - Validated. Disarming Alarm now')
                    code = self.otp.getAlarmCode()
                    if code is None:
                        self.logger.error(
                            "Invalid alarm code configured. Check configuration file to ensure alarm code is set.")
                    else:
                        messageToSend = code + '1'
                        self.ad2usb.panelMsgWrite(messageToSend)
                        code = None
                else:
                    self.logger.warning('OTP for Disarming Alarm is not valid.')
            else:
                self.logger.warning(
                    "OTP is not enabled. Check that it is enabled with a valid Folder Pathin 'Configure' - or required Python Modules may be missing.")

        if newVar.name == 'BypassOTP':

            if self.isOTPEnabled:
                if self.otp.isValidOTP(newVar.value):
                    self.logger.info('OTP Bypass - Validated. Bypassing Zones now')
                    code = self.otp.getAlarmCode()
                    if code is None:
                        self.logger.error(
                            "Invalid alarm code configured. Check configuration file to ensure alarm code is set.")
                    else:
                        # get the bypass zones from a variable
                        zonesToBypassVar = indigo.variables["ZonesToBypassOTP"]
                        zonesToBypass = self.__validZoneList(zonesToBypassVar.value)

                        # confirm zones are valid
                        if zonesToBypass is not None:
                            # build a string of zones
                            self.logger.info("Bypassing Zones:{} ({})".format(zonesToBypassVar.value, zonesToBypass))

                            # send the message to the panel
                            messageToSend = code + '6' + zonesToBypass
                            self.ad2usb.panelMsgWrite(messageToSend)
                            code = None
                else:
                    self.logger.warning('OTP for Bypassing Zones is not valid.')
            else:
                self.logger.warning(
                    "OTP is not enabled. Check that it is enabled with a valid Folder Pathin 'Configure' - or required Python Modules may be missing.")

    def generateOTPConfig(self):
        """
        Menu item to create or update the OTP Conifiguration file and QR Code file.
        """
        try:
            if self.otp.writeOTPConfigFiles():
                self.logger.info("OTP Configuration file '{}' updated with new Shared Key.".format(self.otp.fileName))

                if self.otp.writeOTPQRCode():
                    self.logger.info("OTP QR Code file updated.")

        except Exception as err:
            self.logger.error("Unable to update OTP Configuration files. Error:{}".format(str(err)))

    def createOTPVars(self):
        """
        Menu item to create any missing OTP Variables.
        """
        try:
            # defined the variables as a list
            OTPVars = {'ArmAwayOTP': False, 'ArmStayOTP': False,
                       'BypassOTP': False, 'ZonesToBypassOTP': False, 'DisarmOTP': False}

            # get all the variables and see which ones exist
            for var in indigo.variables:
                if var.name in OTPVars:
                    OTPVars[var.name] = True

            # log which ones exists
            varsThatExist = []
            # look at each variable (the key)
            for key in OTPVars:

                # if its True - its exists
                if OTPVars[key]:
                    varsThatExist.append(key)

                # if its False we need to created it
                else:
                    newVar = indigo.variable.create(key, value="")
                    self.logger.info("Created variable:{}".format(key))

            self.logger.info("Variables {} already exist and will not be created.".format(', '.join(varsThatExist)))

        except Exception as err:
            self.logger.error("Unable to created all OTP Variables. Error:{}".format(str(err)))

    def __validZoneList(self, zones):
        """
        Expects a comma separated list of zones and returns an even number of digits only or None.
        Example: zones parameter = '1,14,7'; returns '011407'
        """
        try:
            # split the string on comma
            myZoneList = zones.split(",")
            # put the list back into a string
            myZoneString = ''.join(myZoneList)

            # contains only digits
            if myZoneString.isdigit():
                # even number of digits - 2, 4, 6, ...
                if len(myZoneString) % 2 == 0:
                    return myZoneString
                else:
                    self.logger.warning("Zone Bypass list not even number of digits")
                    return None
            else:
                self.logger.warning("Zone Bypass list contains values other than digits")
                return None

        except Exception as err:
            self.logger.warning("Error reading list of Zones:{} - msg:{}".format(zones, str(err)))
            return None

    def __migratePanelArmTriggers(self):
        """
        Used to set the property to AnyUser for any existing Panel Arming Events. In a later verison it now throws an error if any Panel Arming Triggers exist.
        """
        try:
            haveLoggedWarning = False
            # for this plugin's triggers
            for trigger in indigo.triggers.iter("self"):
                # if they are the to-be-deprecated Panel Arming Events
                if trigger.pluginTypeId == "armDisarm":
                    # get the properties
                    localPropsCopy = trigger.pluginProps
                    # set the property to Any User for easier conversion
                    localPropsCopy["userOption"] = "anyUser"
                    # update the properties
                    trigger.replacePluginPropsOnServer(localPropsCopy)

                    # log and warn user
                    if not haveLoggedWarning:
                        # self.logger.warning("AD2USB Panel Arming Events will be deprecated in future release:")
                        self.logger.error("AD2USB Panel Arming Events are deprecated as of version 3.4.0. If you still need to migrate them, revert to version 3.3.4 and migrate them to User Actions. Otherwise, please delete these Triggers:")
                        haveLoggedWarning = True

                    self.logger.error("Delete Trigger:{}".format(trigger.name))

        except Exception as err:
            self.logger.error("Error while trying to migrate deprecated Panel Arming Triggers:{}".format(str(err)))
