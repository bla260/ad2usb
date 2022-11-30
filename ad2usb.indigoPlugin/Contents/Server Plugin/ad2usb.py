#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# ad2usb Alarm Plugin
# Originally developed by Richard Perlman

import indigo  # Not really needed, but a specific import removes lint errors
from datetime import datetime
# import inspect
import os
import re
import serial
import sys
import string
import time
import AlarmDecoder
import AD2USB_Constants
# from string import atoi

# kRespDecode = ['loop1', 'loop4', 'loop2', 'loop3', 'bit3', 'sup', 'bat', 'bit0']
kRFXBits = ['bit0', 'bat', 'sup', 'bit3', 'loop3', 'loop2', 'loop4', 'loop1']
kBin = ['0000', '0001', '0010', '0011', '0100', '0101', '0110', '0111', '1000',
                '1001', '1010', '1011', '1100', '1101', '1110', '1111']
kEventStateDict = ['OPEN', 'ARM_AWAY', 'ARM_STAY', 'ACLOSS', 'AC_RESTORE', 'LOWBAT',
                   'LOWBAT_RESTORE', 'RFLOWBAT', 'RFLOWBAT_RESTORE', 'TROUBLE',
                   'TROUBLE_RESTORE', 'ALARM_PANIC', 'ALARM_FIRE', 'ALARM_AUDIBLE',
                   'ALARM_SILENT', 'ALARM_ENTRY', 'ALARM_AUX', 'ALARM_PERIMETER', 'ALARM_TRIPPED']
kADCommands = {'CONFIG': 'C\r', 'VER': 'V\r'}

# serial port timeout ex: 2 (seconds) or None (infinite)
k_SERIAL_TIMEOUT = 5

################################################################################
# Globals
################################################################################


################################################################################
class ad2usb(object):
    ########################################
    def __init__(self, plugin):
        """
        creates an AlarmDecoder object and starts AlarmDecoder communication

        **parameters:**
        plugin -- the Indigo plugin object
        """
        # the plugin gives us the loggger and URL
        # need to set this up first
        self.plugin = plugin

        # use indigo built-in logger API as of 1.7.1
        self.logger = self.plugin.logger

        # finally log init was called
        self.logger.debug(u'called')

        self.zoneListInit = False
        self.zoneStateDict = {}
        self.listOfZonesBypassed = []  # array with values of zone number as int
        self.lastApZonesBypassed = 0

        self.stopReadingMessages = False

        # set the debug panel playback file
        self.playbackLastLineNumberRead = 0  # tracks the current line
        self.playbackSleepTime = 8  # 5 seconds sleep between each message
        self.hasPlaybackFileBeenRead = False  # flag to set after reading file

        # set the firmware to unknown and the serial connection to None
        self.firmwareVersion = ''
        self.serialConnection = None
        self.isCommStarted = False  # this property is set in startAD2USBComm

        # this code executes before runConcurrentThread so no open reading is happening
        # send a VER and CONFIG message and read the output
        if self.startAD2USBComm():
            self.logger.info('AlarmDecoder initialized and communication started...')
        else:
            self.logger.critical('AlarmDecoder initilization communiation error...')

    ########################################
    def __del__(self):
        pass

    ########################################
    # hex to binary converter
    def hex2bin(self, s):
        self.logger.debug(u"called with:{}".format(s))

        bits = ''
        for i in range(len(s)):
            bits += kBin[int(s[i], base=16)]

        self.logger.debug(u"keypad address bit map:{}".format(bits))
        return bits

    ########################################
    # Event queue management and trigger initiation
    def executeTrigger(self, partition, user, event):
        self.logger.debug(u"called with partition:{}, user:{}, event:{}".format(partition, user, event))

        partition = str(partition)
        user = str(user)
        userAsInt = self.__getIntFromString(user)

        # new logic - we have event and parition from panel and user or non-user event
        # new cache - { event : { partition: 1, any user: True/False, user: number/variable/list } }
        # for each event that exists in the cache and matches the event
        for triggerId in self.plugin.triggerCache:
            triggerName = self.plugin.triggerCache[triggerId]['name']

            # if partition matches
            if partition == self.plugin.triggerCache[triggerId]['partition']:

                # if the event is one of the events 
                if event in self.plugin.triggerCache[triggerId]['events']:

                    # if its a user event
                    if self.plugin.triggerCache[triggerId]['type'] == 'userEvents':

                        # if its any user execute it
                        if self.plugin.triggerCache[triggerId]['anyUser'] is True:
                            self.logger.debug("Executing Any User Trigger:{}".format(triggerName))
                            indigo.trigger.execute(triggerId)

                        # else look at user variable and figure it out
                        else:
                            # get the users value
                            users = self.plugin.triggerCache[triggerId]['users']
                            
                            # get the users as an array of int
                            usersToCheck = self.__convertUsersStringToList(name=triggerName, userString=users)

                            # if the user from the event is in the list of users in the Trigger
                            if userAsInt in usersToCheck:
                                self.logger.debug("Executing User Match Trigger:{}".format(triggerName))
                                indigo.trigger.execute(triggerId)

                    else:
                        # execute the trigger if its not a userEvent
                        self.logger.debug("Executing Non-User Trigger:{}".format(triggerName))

                        # provide a deprecated warning for Panel Arming Events
                        if self.plugin.triggerCache[triggerId]['type'] == 'armDisarm':
                            self.logger.warn("AD2USB Plugin Triggers based on Panel Arming Events will be deprecated in a future release. Change Trigger named:{} from a Panel Arming Event to a User Action with the 'Any User' option selected.".format(triggerName))

                        indigo.trigger.execute(triggerId)

        self.logger.debug(u"completed")

    ########################################
    # Write arbitrary messages to the panel
    def panelMsgWrite(self, panelMsg, address=''):
        """
        Sends (writes) a message to the AlarmDecoder to be sent to the alarm panel. Messages can be
        prefixed by a keypad address to make the message come from another keypad address other than the
        AlarmDecoder. If no address is provided the message is sent from the AlarmDecoder's keypad
        ADDRESS settings. Note that messages will not be logged literally to prevent user codes from
        being logged. Four (4) digit codes with the message will be replaced by the word "CODE".

        **parameter:**
        panelMsg - the keypad entries to send to the AlarmDecoder keypad
        address - zero-padded two digit string representing keypad address
        """
        # strip panel codes from message
        messageToLog = ''
        try:
            # log the message safely

            # look for string that is Alarm User Code add and strip code
            # Master Code + [8] + User No. + New User's Code
            if re.search(r'^\d{4}8\d{6}', panelMsg) is None:
                messageToLog = re.sub(r'^\d{4}', 'CODE+', panelMsg)
            else:
                messageToLog = re.sub(r'^\d{4}8(\d{2})\d{4}', 'CODE+8+\\1+CODE', panelMsg)

            self.logger.debug(u"called with msg:{} for address:{}".format(messageToLog, address))

        except Exception as err:
            messageToLog = ''
            self.logger.warning("Unable to safely log write panel message - not logging it.")

        # TO DO: add log codes anyway setting
        # TO DO: add optional messageToLog to panelWriteWrapper

        try:
            # if no keypad address specified no need to prefix the message with K##
            if len(address) == 0:
                self.panelWriteWrapper(self.serialConnection, panelMsg)
            else:
                if len(address) == 1:
                    address = "0" + address
                panelMsg = 'K' + address + str(panelMsg)
                self.panelWriteWrapper(self.serialConnection, panelMsg)
                self.logger.info(u"Panel message:{} sent to AlarmDecoder".format(messageToLog))

        except Exception as err:
            self.logger.error(u"Unable to write panel message:{}".format(messageToLog))
            self.logger.error(u"Error message:{}, {}".format(str(err), sys.exc_info()[0]))

        self.logger.debug(u"completed")

    ########################################
    # Wireless zone state decode function for advanced mode
    def decodeState(self, zState):
        """
        Takes zState which is a 2 char hex (string) and sets dictionary values for RFX devices
        Returns a dictionary
        """
        self.logger.debug(u"called with:{}".format(zState))

        # OLD zoneState = ''
        returnDict = {}

        # OLD Python 2
        # for i in range(len(zState)):
        #    zoneState += kBin[string.atoi(zState[i], base=16)]

        # NEW Python 3 convert the string to an int
        rfxDataAsInt = int(zState, 16)
        self.logger.debug(u"int value is:{}, binary:{}".format(rfxDataAsInt, bin(rfxDataAsInt)))

        # for i in range(7, -1, -1):
        #     decodeVal = False
        #     if zoneState[i] == '1':
        #         decodeVal = True
        #
        #     returnDict[kRespDecode[i]] = decodeVal

        # NEW Python 3 test the 8 bits of the data and set dictionary
        # shift i bits right and bit AND with 1
        for i in range(0, 8):
            if ((rfxDataAsInt >> i) & 1) == 1:
                returnDict[kRFXBits[i]] = True
            else:
                returnDict[kRFXBits[i]] = False

        self.logger.debug(u"returned:{}".format(returnDict))
        return returnDict

        self.logger.debug(u"completed")

    ########################################
    # Read the zone messages in advanced mode
    def advancedReadZoneMessage(self, rawData):
        self.logger.debug(u"called with:{}:".format(rawData))

        validDev = False
        supervisionMessage = False

        if not self.zoneListInit:
            for address in self.plugin.getAllKeypadAddresses():
                self.zoneStateDict[address] = []
            self.zoneListInit = True

        # version 3.1 - removed EXP messages - these are now processed using new methods
        if rawData[1:4] == 'REL' or rawData[1:4] == 'RFX':   # a relay, expander module or RF zone event
            splitMsg = re.split('[!:,]', rawData)
            zoneDevType = splitMsg[1]
            self.logger.debug(u"zone type is:{}".format(zoneDevType))

            # Lets make sure we read something about this zone from the conf file
            # RELay and EXPander zones (REL & EXP) always show 01 for a fault and 00 for clear
            # For RELay and EXPander zones the index is the board and relay/input number. Eg. 12,01
            if zoneDevType == 'REL' or zoneDevType == 'EXP':
                zoneBoard = splitMsg[2]
                if len(zoneBoard) == 1:
                    zoneBoard = "0" + zoneBoard
                zoneInput = splitMsg[3]
                if len(zoneInput) == 1:
                    zoneInput = "0" + zoneInput
                zoneState = int(splitMsg[4], 16)
                zoneOff = int('00', 16)
                zoneOn = int('01', 16)
                zoneIndex = zoneBoard + ',' + zoneInput
                self.logger.debug(u"zone index is:{}".format(zoneIndex))
            # For RF zones the index in the device's unique serial number
            else:
                zoneIndex = splitMsg[2]
                zoneState = splitMsg[3][0:2]  # Lose the \r

            try:    # Lookup the zoneIndex in the zone device dictionary
                # and setup some variables to process the zone data
                zoneData = self.plugin.advZonesDict[zoneIndex]
                self.logger.debug(u"read zoneData:{}".format(zoneData))
                # Read the data for this zone into variables
                zType = zoneData['type']
                zDevId = zoneData['devId']
                zBoard = zoneData['board']
                zDevice = zoneData['device']
                zNumber = zoneData['number']
                zLogChanges = zoneData['logChanges']
                zLastState = zoneData['state']
                zLogSupervision = zoneData['logSupervision']
                zPartition = zoneData['partition']
                zName = zoneData['name']

                indigoDevice = indigo.devices[zDevId]

                # get the panel device and keypad address
                panelDevice = self.plugin.getKeypadDeviceForPartition(zPartition)
                if panelDevice is None:
                    self.logger.error("No keypad device found for partition:{} of device:{}".format(zPartition, zName))
                else:
                    panelKeypadAddress = panelDevice.pluginProps['panelKeypadAddress']

                    self.logger.debug(u"found zone info: zType={}, zDevId={}, zBoard={}, zDevice={}, zNumber={}, zLastState={}, zName={}, zPartition={}".format(
                        zType, zDevId, zBoard, zDevice, zNumber, zLastState, zName, zPartition))
                    self.logger.debug(u"found keypad:{}".format(panelDevice))

                    self.logger.debug(u"Indigo Device found:{}".format(zName))
                    validDev = True

            except Exception as err:  # An unrecognized device
                if self.plugin.logUnknownDevices:
                    self.logger.error(u"message:{} from unrecognized Zone device:{}".format(err, rawData))

            # We'll start with RELay & EXPander Zones since they are treated alike
            if validDev:
                if zType == 'REL' or zType == 'EXP':  # For Relay (on-board) and Expander zones
                    self.logger.debug(u"ready to update Indigo REL & EXP")
                    if zoneState == zoneOn:
                        self.logger.debug(u"zoneOn zoneNumber:{}, and States list:{}".format(
                            zNumber, self.zoneStateDict))
                        self.plugin.setDeviceState(indigoDevice, AD2USB_Constants.k_FAULT)

                        # Maintain the zone fault state
                        self.updateZoneFaultListForKeypad(keypad=panelKeypadAddress, addZone=int(zNumber))
                        panelDevice.updateStateOnServer(key='zoneFaultList', value=str(
                            self.zoneStateDict[panelKeypadAddress]))

                        stateMsg = 'Faulted'
                    elif zoneState == zoneOff:
                        self.logger.debug(u"zoneOff zoneNumber:{}, and States list:{}".format(
                            zNumber, self.zoneStateDict))
                        self.plugin.setDeviceState(indigoDevice, AD2USB_Constants.k_CLEAR)

                        # Maintain the zone fault state
                        try:
                            self.updateZoneFaultListForKeypad(keypad=panelKeypadAddress, removeZone=int(zNumber))

                        except:
                            self.logger.error(u"Unable to update state table for zone:{}, address:{}".format(
                                zNumber, panelKeypadAddress))

                        panelDevice.updateStateOnServer(key='zoneFaultList', value=str(
                            self.zoneStateDict[panelKeypadAddress]))

                        stateMsg = 'Clear'
                    else:
                        self.logger.error(u"zone:{}, name:{} has an UNKNOWN zone state:{}".format(
                            zNumber, zName, rawData))

                elif zType == 'RFX':  # for RF zones
                    self.logger.debug(u"ready to update Indigo RFX (Wireless)")

                    wirelessLoop = 'loop' + str(int(zDevice))  # remove any leading zeros
                    RFXDataBits = self.decodeState(zoneState)
                    if indigoDevice.pluginProps['zoneInvertSense']:
                        if RFXDataBits[wirelessLoop]:
                            RFXDataBits[wirelessLoop] = False
                        elif not RFXDataBits[wirelessLoop]:
                            RFXDataBits[wirelessLoop] = True
                        else:
                            self.logger.error(u"State:{} not found in:{}".format(
                                RFXDataBits, self.plugin.advZonesDict[zoneIndex]))

                    if RFXDataBits[wirelessLoop]:
                        self.logger.debug(u"zoneOn zoneNumber:{}, and States list:{}".format(
                            zNumber, self.zoneStateDict))
                        self.plugin.setDeviceState(indigoDevice, AD2USB_Constants.k_FAULT)

                        # Maintain the zone fault state
                        try:
                            self.updateZoneFaultListForKeypad(keypad=panelKeypadAddress, addZone=int(zNumber))
                            panelDevice.updateStateOnServer(key='zoneFaultList', value=str(
                                self.zoneStateDict[panelKeypadAddress]))
                        except:
                            pass  # probably a non-numeric zone

                        stateMsg = 'Faulted'
                    elif not RFXDataBits[wirelessLoop]:
                        self.logger.debug(u"zoneOff zoneNumber:{}, and States list:{}".format(
                            zNumber, self.zoneStateDict))
                        self.plugin.setDeviceState(indigoDevice, AD2USB_Constants.k_CLEAR)

                        # Maintain the zone fault state
                        try:
                            self.updateZoneFaultListForKeypad(keypad=panelKeypadAddress, removeZone=int(zNumber))

                            panelDevice.updateStateOnServer(key='zoneFaultList', value=str(
                                self.zoneStateDict[panelKeypadAddress]))
                        except:
                            pass  # probably a non-numeric zone

                        stateMsg = 'Clear'
                    else:
                        self.logger.error(u"State:{} not found in:{}".format(
                            zoneState, self.plugin.advZonesDict[zoneIndex]))

                    if RFXDataBits['sup']:
                        supervisionMessage = True
                        if zLogSupervision:  # make sure we want this logged
                            self.logger.info(u"Zone:{} supervision received. ({})".format(zName, rawData.strip()))
                            # Add update here to save last supervised to zone states

                else:  # An unrecognized message type
                    self.logger.error(u"Unrecognized message type for received data:{}".format(rawData))

                # If we are supposed to log zone changes, this is where we do it (unless this was a supervision message)
                if zLogChanges and not supervisionMessage:
                    self.logger.debug(u"Zone:{}, Name:{}, State changed to:{}".format(zNumber, zName, stateMsg))

                try:
                    if not supervisionMessage:
                        # replacing update Zone Group method
                        # self.updateZoneGroups(zNumber, stateMsg)
                        self.plugin.updateAllZoneGroups()
                except Exception as err:
                    self.logger.error(u"updateAllZoneGroups Error:{}".format(str(err)))

        else:
            if rawData[0:8] != '!setting' and rawData[0:7] != '!CONFIG' and rawData[0:2] != '!>' and rawData[0:4] != '!KPE' and rawData[0:8] != '!Sending' and rawData[0:4] != '!VER':
                self.logger.error(u"Unknown message received:{}".format(rawData))

        self.logger.debug(u"completed")

    ########################################
    # update Indigo on device state changes
    def updateIndigoBasicMode(self, zoneIndex, zoneState, panelDevice):
        self.logger.debug(u"called with index:{}, state:{}, panel:{}".format(zoneIndex, zoneState, panelDevice))

        if not self.zoneListInit:
            for address in self.plugin.getAllKeypadAddresses():
                self.zoneStateDict[address] = []
            self.zoneListInit = True

        zoneData = self.plugin.zonesDict[zoneIndex]
        zDevId = zoneData['devId']
        zLogChanges = zoneData['logChanges']
        zName = zoneData['name']
        indigoDevice = indigo.devices[zDevId]

        panelKeypadAddress = panelDevice.pluginProps['panelKeypadAddress']
        self.logger.debug(u"got address:{}".format(panelKeypadAddress))

        if zoneState == AD2USB_Constants.k_FAULT:
            self.updateZoneFaultListForKeypad(keypad=panelKeypadAddress, addZone=int(zoneIndex))
            self.logger.debug(u"faulted... state list:{}".format(self.zoneStateDict))
        else:
            self.updateZoneFaultListForKeypad(keypad=panelKeypadAddress, removeZone=int(zoneIndex))
            self.logger.debug(u"clear... State list:{}".format(self.zoneStateDict))

        # update the device state - this also call the Zone Group update
        self.plugin.setDeviceState(indigoDevice, zoneState)

        # update the panel device state info
        panelDevice.updateStateOnServer(key='zoneFaultList', value=str(self.zoneStateDict[panelKeypadAddress]))

        # If we are supposed to log zone changes, this is where we do it (unless this was a supervision message)
        if zLogChanges:
            self.logger.info(u"Zone:{}, Name:{}, State changed to:{}".format(zoneIndex, zName, zoneState))

    ########################################
    # Read the zone messages in basic mode
    # Special thanks to Sean Mathews of Nu Tech Software Solutions
    # (and the developer of the ad2usb) for this great algorithm for
    # tracking zone states without zone restore messages or timers.

    def basicReadZoneMessage(self, rawData, msgBitMap, msgZoneNum, msgText, msgKey, panelDevice):
        self.logger.debug(u"called with rawData:{}, msgBitMap:{}, msgZoneNum:{}, msgText:{}, msgKey:{}".format(
            rawData, msgBitMap, msgZoneNum, msgText, msgKey))

        systemReady = False
        if msgBitMap[0] == '1':
            systemReady = True

        zoneFault = False
        if msgKey == 'FAULT':
            zoneFault = True

        self.logger.debug(u"Ready:{}, Fault:{}".format(systemReady, zoneFault))

        # Before we can make any changes to the Indigo device, we need to get the device object

        # Here is the plan...
        # If the new zone is > the last zone, we can delete everything
        # > last zone and < new zone
        # Otherwise, if the last zone is > the new zone, we can delete everything
        # > last zone and <= end of list, plus, everything >= start of list and < new zone
        if zoneFault:
            removeList = []
            try:
                # If this succeeds, the zone was already in the list
                newZonePos = self.plugin.faultList.index(msgZoneNum)
                self.logger.debug(u"Found zone:{} in the list at pos:{}".format(msgZoneNum, newZonePos))

            except:
                # If it failed, we need to insert the zone into the list
                # and sort the list
                self.plugin.faultList.append(msgZoneNum)
                self.plugin.faultList.sort()
                newZonePos = self.plugin.faultList.index(msgZoneNum)

                zoneIndex = msgZoneNum

                self.updateIndigoBasicMode(zoneIndex, AD2USB_Constants.k_FAULT, panelDevice)

                self.logger.debug(u"Created new in the list, zone:{} at pos:{}".format(msgZoneNum, newZonePos))

            # Now that we are sure the zone is in the list, we can continue
            # Find the position of the last zone
            try:
                oldZonePos = self.plugin.faultList.index(self.plugin.lastZoneFaulted)
            except:
                oldZonePos = 0

            self.logger.debug(u"Last zone:{}, pos in the list:{}".format(self.plugin.lastZoneFaulted, oldZonePos))

            if msgZoneNum == self.plugin.lastZoneFaulted:
                for zoneCheck in range(newZonePos + 1, len(self.plugin.faultList)):
                    removeList.append(self.plugin.faultList[zoneCheck])
                    self.logger.debug(u"a - ZoneCheck:{}, pos:{}".format(self.plugin.faultList[zoneCheck], zoneCheck))

                for zoneCheck in range(0, newZonePos):
                    removeList.append(self.plugin.faultList[zoneCheck])
                    self.logger.debug(u"b - ZoneCheck:{}, pos:{}".format(self.plugin.faultList[zoneCheck], zoneCheck))

            elif msgZoneNum > self.plugin.lastZoneFaulted:
                for zoneCheck in range(oldZonePos + 1, newZonePos):
                    removeList.append(self.plugin.faultList[zoneCheck])
                    self.logger.debug(u"c - ZoneCheck:{}, pos:{}".format(self.plugin.faultList[zoneCheck], zoneCheck))

            elif msgZoneNum < self.plugin.lastZoneFaulted:
                for zoneCheck in range(oldZonePos + 1, len(self.plugin.faultList)):
                    removeList.append(self.plugin.faultList[zoneCheck])
                    self.logger.debug(u"d - ZoneCheck:{}, pos:{}".format(self.plugin.faultList[zoneCheck], zoneCheck))

                for zoneCheck in range(0, newZonePos):   # Changed to end at new pos instead of new pos -1
                    removeList.append(self.plugin.faultList[zoneCheck])
                    self.logger.debug(u"e - ZoneCheck:{}, pos:{}".format(self.plugin.faultList[zoneCheck], zoneCheck))

            removeList = sorted(removeList, reverse=True)

            for clearZone in removeList:
                remZonePos = self.plugin.faultList.index(clearZone)
                self.logger.debug(u"Deleting zone:{}, at pos:{}".format(self.plugin.faultList[remZonePos], remZonePos))

                zoneIndex = self.plugin.faultList[remZonePos]

                self.updateIndigoBasicMode(zoneIndex, AD2USB_Constants.k_CLEAR, panelDevice)

                del self.plugin.faultList[remZonePos]

            self.plugin.lastZoneFaulted = msgZoneNum

        else:  # systemReady is true
            self.logger.debug(u"number of zones cleared:{}, list was:{}".format(
                len(self.plugin.faultList), self.plugin.faultList))

            while len(self.plugin.faultList) > 0:
                remZonePos = len(self.plugin.faultList) - 1

                self.logger.debug(u"Deleting zone:{}, at pos:{}".format(self.plugin.faultList[remZonePos], remZonePos))
                self.logger.debug(u"Deleting position:{}".format(remZonePos))

                zoneIndex = self.plugin.faultList[remZonePos]

                self.updateIndigoBasicMode(zoneIndex, AD2USB_Constants.k_CLEAR, panelDevice)

                del self.plugin.faultList[remZonePos]

        self.logger.debug(u"Ready:{}, Fault:{}, Zone:{}".format(systemReady, zoneFault, msgZoneNum))
        self.logger.debug(u"The List:{}".format(self.plugin.faultList))

        self.logger.debug(u"completed")

    ########################################
    # Read the panel message stream
    #
    def panelMsgRead(self, ad2usbIsAdvanced):
        """
        Gets and processes a message from the AlarmDecoder. Will call a wrapper function to read
        the alarm panel message: IP, Serial, or from a File (test mode). Either the wrapper will
        timeout after a set number of seconds and this funciton will end - returning blank message or one (1)
        a message will be returned by the wrapper and processed.

        Returns None if no message processed (timeout), True if processed succesfully, False if
        an error was found during processing
        """
        self.logger.debug("call with isAdvanced:{}".format(ad2usbIsAdvanced))

        lastPanelMsg = ""
        doNotProcessThisMessage = False  # default to process every message
        rawData = ""
        messageReadSuccessfully = False
        skipOldMesssageProcessing = False  # used to skip legacy message processing

        try:
            # check if we've Disabled the plugin in the main thread before continuing
            if self.stopReadingMessages is True:
                return None

            # read the data from IP, Serial, or File device
            # will timeout set by k_SERIAL_TIMEOUT
            rawData = self.panelReadWrapper(self.serialConnection)

            # the panelReadWrapper will return with an empty message when the
            # serial timeout is reached - ignore these and loop back to read
            # we do this to enable Indigo to invoke a graceful Disable/Stop of the plugin
            if rawData == '':
                doNotProcessThisMessage = True
                self.logger.debug('read null message or timeout reached')
                return None
            else:
                # message Read was successful - log the raw message
                self.logger.debug(u"Read ad2usb message:{}".format(repr(rawData)))

                # write the message to the panel log too if panel logging is enabled
                if self.plugin.isPanelLoggingEnabled:
                    self.plugin.panelLogger.info(u"{}".format(rawData.rstrip()))

            # ############## New Message Parser ########################
            #

            # added this code to begin to test the message Object
            newMessageObject = AlarmDecoder.Message(rawData, self.firmwareVersion, self.logger)

            # process select messages - return if we don't want to process
            # using old methods
            if newMessageObject.isValidMessage:
                # set 2 values to use in Exception handler section
                messageReadSuccessfully = True
                messageType = newMessageObject.messageType

                if (newMessageObject.messageType == 'CONFIG') and newMessageObject.needsProcessing:
                    # store the current setting in the properties
                    self.processAlarmDecoderConfigMessage(newMessageObject)
                    skipOldMesssageProcessing = True

                elif (newMessageObject.messageType == 'VER') and newMessageObject.needsProcessing:
                    self.setFirmware(newMessageObject.firmwareVersion)
                    skipOldMesssageProcessing = True

                elif (newMessageObject.messageType == 'KPM') and newMessageObject.needsProcessing:
                    self.logger.debug('KPM message seen:{}'.format(newMessageObject))
                    # for now we process these messages using legacy code
                    skipOldMesssageProcessing = False

                elif (newMessageObject.messageType == 'EXP') and newMessageObject.needsProcessing:
                    self.logger.debug('EXP message seen')
                    if ad2usbIsAdvanced:
                        self.process_EXP_Message(newMessageObject)
                    skipOldMesssageProcessing = True

                elif (newMessageObject.messageType == 'RFX') and newMessageObject.needsProcessing:
                    self.logger.debug('RFX message seen')
                    # for now we don't do anything with RFX messages
                    skipOldMesssageProcessing = False

                elif (newMessageObject.messageType == 'REL') and newMessageObject.needsProcessing:
                    self.logger.debug('REL message seen')
                    # for now we don't do anything with REL messages
                    skipOldMesssageProcessing = False

                elif (newMessageObject.messageType == 'AUI') and newMessageObject.needsProcessing:
                    self.logger.debug('AUI message seen')
                    # for now we don't do anything with AUI messages
                    skipOldMesssageProcessing = True

                elif (newMessageObject.messageType == 'LRR') and newMessageObject.needsProcessing:
                    # attempt to send VER command if VER not known
                    if self.firmwareVersion == '':
                        self.logger.warning(
                            'LRR message seen but firmware unknown - will attempt to send firmware message to AlarmDecoder')
                        if self.sendAlarmDecoderVersionCommand() is False:
                            self.logger.error("Unable to send VER command.")

                    # check if we should process it
                    if newMessageObject.isValidMessage:
                        self.process_LRR_Message(newMessageObject)

                    skipOldMesssageProcessing = True
                    self.logger.debug('LRR message seen')

                elif (newMessageObject.messageType == 'LR2') and newMessageObject.needsProcessing:
                    # attempt to send VER command if VER not known
                    if self.firmwareVersion == '':
                        self.logger.warning(
                            'LRR message seen but firmware unknown - will attempt to send firmware message to AlarmDecoder')
                        if self.sendAlarmDecoderVersionCommand() is False:
                            self.logger.error("Unable to send VER command.")

                    # check if we should process it
                    if newMessageObject.isValidMessage:
                        self.process_LRR_Message(newMessageObject)

                    skipOldMesssageProcessing = True
                    self.logger.debug('LR2 message seen')

                else:
                    pass

            else:
                self.logger.warning("Unable to parse:{} - message:{}".format(
                    newMessageObject.invalidReason, newMessageObject.messageString))

            #
            #
            # ############## End New Message Parser ########################

        except Exception as err:
            # don't process any message we had an error reading
            doNotProcessThisMessage = True
            if messageReadSuccessfully:
                self.logger.error(u"Error processing AlarmDecoder message - error:{}".format(str(err)))
                self.logger.error(
                    u"Error processing AlarmDecoder message type:{} - raw data is:{}".format(messageType, rawData))
                self.logger.error(u"Will discard and try next message")

            else:
                self.logger.error(u"Error reading AlarmDecoder message - error:{}".format(str(err)))
                self.logger.error(u"Error reading AlarmDecoder message - raw data is:{}".format(rawData))
                self.logger.error(u"Will discard and try next message")

            return False

        #
        # Process Message Section
        #

        # if we don't want to process this message return
        if doNotProcessThisMessage:
            return None

        # used to skip legacy message processing
        if skipOldMesssageProcessing:
            return True  # message was processed in the new section

        # Start LEGACY / OLD processing the message
        # Start by checking if this message is "Press * for faults"
        try:
            if len(rawData) > 0 and rawData[0] == "[":  # A valid panel message
                self.logger.debug(u"raw zone type is:{}".format(rawData[0:4]))

                # First split the message into parts and see if we need to send a * to get the faults
                splitMsg = re.split('[\[\],]', rawData)
                msgText = splitMsg[7]
                # Python 3 fix:
                # was string.find(msgText, ' * ')
                if msgText.find(' * ') >= 0:
                    self.logger.debug(u"Received a Press * message:{}".format(rawData))
                    self.panelWriteWrapper(self.serialConnection, '*')
                    # That's all we need to do for this messsage

                elif rawData[30:38] == '00000000':
                    self.logger.debug(u"System Message: we passed on this one")
                    pass  # Ignore system messages (no keypad address)

                else:
                    # Get a list of keypad addresses this message was sent to
                    readThisMessage = False
                    foundAddress = False
                    lastAddress = ''
                    try:
                        # if only 1 partition, we don't care about keypad addresses
                        if self.plugin.numPartitions == 1:
                            panelKeypadAddress = str(self.plugin.ad2usbKeyPadAddress)
                            foundKeypadAddress = panelKeypadAddress
                            readThisMessage = True
                        else:
                            # The msg sub-string with the keypad addresses (in hex)
                            keypadAddressField = rawData[30:38]
                            # Convert the address field to a binary string
                            addrHex = self.hex2bin(keypadAddressField)
                            self.logger.debug(u"addrHex:{}".format(addrHex))
                            for panelKeypadAddress in self.plugin.getAllKeypadAddresses():       # loop through the keypad device dict
                                bitPosition = -1  # reset this each pass through the loop
                                panelAddress = -1  # reset this each pass through the loop
                                panelAddress = int(panelKeypadAddress)
                                self.logger.debug(u"panelAddress:{}".format(panelAddress))
                                # determine the bit position for the current address
                                bitPosition = 8 - (panelAddress % 8) + int(panelAddress / 8) * 8
                                self.logger.debug(u"bitPosition:{}, bit at bitPosition:{}".format(
                                    bitPosition, addrHex[bitPosition-1]))
                                if addrHex[bitPosition-1] == '1':                   # See if we have a one in our slot
                                    self.logger.debug(u"matched key={}".format(panelKeypadAddress))
                                    foundKeypadAddress = panelKeypadAddress
                                    readThisMessage = True   # Yes, we can read this message
                                    if foundAddress:
                                        self.logger.error(u"more than one matching keypad address. previous:{}, current:{}".format(
                                            lastAddress, panelKeypadAddress))
                                    foundAddress = True
                                    lastAddress = panelKeypadAddress

                    except Exception as keypadException:
                        self.logger.error(u"Keypad Address keypadAddressField:{}, panelAddress:{}, bitPosition:{}".format(
                            keypadAddressField, panelAddress, bitPosition))
                        self.logger.error(u"Keypad Address Error:{}".format(keypadException))

                    if readThisMessage:
                        # Now look to see if the message has changed since the last one we processed
                        self.logger.debug(u"Panel Message: Before:{}".format(lastPanelMsg))
                        self.logger.debug(u"Panel Message: Current:{}".format(rawData))
                        # If it hasn't, start again
                        if rawData == lastPanelMsg:  # The alarm status has not changed
                            self.logger.debug(u"no panel status change")
                        else:
                            # Example: [1000000100000000----]
                            # 1 = READY                           10 = ALARM OCCURRED STICKY BIT (cleared 2nd disarm)
                            # 2 = ARMED AWAY  <*                  11 = ALARM BELL (cleared 1st disarm)
                            # 3 = ARMED HOME  <*                  12 = BATTERY LOW
                            # 4 = BACK LIGHT                      13 = ENTRY DELAY OFF (ARMED INSTANT/MAX) <*
                            # 5 = Programming Mode                14 = FIRE ALARM
                            # 6 = Beep 1-7 ( 3 = beep 3 times )   15 = CHECK ZONE - TROUBLE
                            # 7 = A ZONE OR ZONES ARE BYPASSED    16 = PERIMETER ONLY (ARMED STAY/NIGHT)
                            # 8 = AC Power                        17 - 20 unused
                            # 9 = CHIME MODE
                            #
                            panelFlags = rawData[0:23]
                            panelBitStatus = panelFlags[1:4]
                            apReadyMode = panelFlags[1]

                            apArmedMode = '0'
                            armedMode = 'unArmed'
                            if panelFlags[2] == '1':
                                apArmedMode = '1'
                                armedMode = 'armedAway'
                                if panelFlags[13] == '1':
                                    armedMode = 'armedMax'
                            elif panelFlags[3] == '1':
                                apArmedMode = '1'
                                armedMode = 'armedStay'
                                if panelFlags[13] == '1':
                                    armedMode = 'armedInstant'

                            apProgramMode = panelFlags[5]
                            apZonesBypassed = panelFlags[7]
                            apACPower = self.__flagToBoolean(flag=panelFlags[8], defaultValue=True)
                            apChimeMode = panelFlags[9]
                            apAlarmOccurred = panelFlags[10]
                            apAlarmBellOn = panelFlags[11]
                            apBatteryLow = panelFlags[12]
                            apFireAlarm = panelFlags[14]
                            apCheckZones = panelFlags[15]

                            self.logger.debug(u"Panel message:{}".format(panelFlags))

                            # TO DO: replace with a function that looks at MAX/INSTANT
                            # if panelBitStatus in self.plugin.ALARM_STATUS:
                            #    panelState = self.plugin.ALARM_STATUS[panelBitStatus]
                            # else:
                            #    self.logger.error("Unknown Keypad Panel State:{}".format(panelBitStatus))
                            #    panelState = 'error'

                            lastPanelMsg = rawData
                            # panelDevice = indigo.devices[self.plugin.panelsDict[foundKeypadAddress]['devId']]
                            panelDevice = self.plugin.getKeypadDeviceForAddress(foundKeypadAddress)
                            self.logger.debug(u"Found dev:{}, id:{}".format(panelDevice.name, panelDevice.id))

                            # panelDevice = indigo.devices[self.plugin.alarmDevId]
                            # self.plugin.setKeypadDeviceState(panelDevice, panelState)

                            now = datetime.now()
                            timeStamp = now.strftime("%Y-%m-%d %H:%M:%S")

                            self.plugin.setKeypadDeviceState(panelDevice, newMessageObject.attr('panelState'))

                            panelDevice.updateStateOnServer(key='LCDLine1', value=rawData[61:77])
                            panelDevice.updateStateOnServer(key='LCDLine2', value=rawData[77:93])
                            panelDevice.updateStateOnServer(key='lastADMessage', value=timeStamp)
                            panelDevice.updateStateOnServer(key='programMode', value=apProgramMode)
                            panelDevice.updateStateOnServer(key='zonesBypassed', value=apZonesBypassed)
                            panelDevice.updateStateOnServer(key='acPower', value=apACPower)
                            panelDevice.updateStateOnServer(key='chimeMode', value=apChimeMode)
                            panelDevice.updateStateOnServer(key='alarmOccurred', value=apAlarmOccurred)
                            panelDevice.updateStateOnServer(key='alarmBellOn', value=apAlarmBellOn)
                            panelDevice.updateStateOnServer(key='batteryLow', value=apBatteryLow)
                            panelDevice.updateStateOnServer(key='fireAlarm', value=apFireAlarm)
                            panelDevice.updateStateOnServer(key='checkZones', value=apCheckZones)
                            panelDevice.updateStateOnServer(key='panelReady', value=apReadyMode)
                            panelDevice.updateStateOnServer(key='panelArmed', value=apArmedMode)
                            panelDevice.updateStateOnServer(key='armedMode', value=armedMode)
                            if apAlarmBellOn == '1' or apFireAlarm == 1:
                                splitMsg = re.split('[\[\],]', rawData)
                                # apAlarmedZone = int(splitMsg[3])  # try this as a string to deal with commercial panels
                                apAlarmedZone = splitMsg[3]
                                panelDevice.updateStateOnServer(key='alarmedZone', value=apAlarmedZone)
                                if apAlarmBellOn == '1':
                                    self.logger.info(u"alarm tripped by zone:{}".format(apAlarmedZone))
                                else:
                                    self.logger.info(u"fire alarm tripped by zone:{}".format(apAlarmedZone))

                            else:
                                panelDevice.updateStateOnServer(key='alarmedZone', value='n/a')
                                splitMsg = re.split('[\[\],]', rawData)

                            # Catch an alarm tripped event
                            try:
                                if rawData[61:74] == "DISARM SYSTEM":
                                    now = datetime.now()
                                    timeStamp = now.strftime("%Y-%m-%d %H:%M:%S")
                                    partition = panelDevice.pluginProps['panelPartitionNumber']
                                    function = 'ALARM_TRIPPED'
                                    user = 'unknown'
                                    self.logger.debug(u"alarm tripped:{}, partition:{}, function:{}".format(
                                        user, partition, function))

                                    panelDevice.updateStateOnServer(key='lastChgBy', value=user)
                                    panelDevice.updateStateOnServer(key='lastChgTo', value=function)
                                    panelDevice.updateStateOnServer(key='lastChgAt', value=timeStamp)
                                    if self.plugin.logArmingEvents:
                                        self.logger.info(
                                            u"Alarm partition {} set to {} caused/entered by {}".format(partition, function, user))

                                    self.executeTrigger(partition, user, function)
                            except Exception as err:
                                self.logger.error(u'ALARM TRIPPED:{}'.format(str(err)))

                        # Setup some variables for the next few steps
                        msgBitMap = splitMsg[1]

                        # Use the new KPM Message Object to avoid processing invalid numerics
                        if newMessageObject.attr('isValidNumericCode'):
                            msgZoneNum = int(splitMsg[3])
                        else:
                            msgZoneNum = 0

                        # see if message text contains a zone
                        validBypassZone = False
                        bMsgZoneNum = 0  # set to zero to reflect invalid bypass zone
                        try:
                            bMsgZoneNum = int(msgText[7:9])
                            validBypassZone = True
                        except:
                            bMsgZoneNum = 0  # set to zero to reflect invalid bypass zone
                            validBypassZone = False
                            # 0fc = comm failure; 0f* = Field?
                            # self.logError("%s: Panel reports: %s" % (funcName, msgText), self.logName)

                        msgKey = msgText[1:6]
                        self.logger.debug(u"msgKey is:{}, msgTxt is:{}, msgBitMap:{}, msgZoneNum:{}, bMsgZoneNum:{}, validBypassZone:{}".format(
                            msgKey, msgText, msgBitMap, msgZoneNum, bMsgZoneNum, validBypassZone))
                        if msgZoneNum in self.plugin.zonesDict:  # avoid issues with count down timers on arm
                            zoneData = self.plugin.zonesDict[int(msgZoneNum)]
                            zDevId = zoneData['devId']
                            zName = zoneData['name']
                            indigoDevice = indigo.devices[zDevId]

                        self.logger.debug(
                            u"number of zones bypassed - current:{}, last:{}".format(apZonesBypassed, self.lastApZonesBypassed))

                        # Manage bypassed zones
                        if apZonesBypassed != self.lastApZonesBypassed:
                            self.logger.debug(
                                u"change in zone bypass count - current:{}, last:{}".format(apZonesBypassed, self.lastApZonesBypassed))
                            # There has been a change is the bypass list
                            if apZonesBypassed == "0":
                                self.logger.debug(u"zones bypassed is now zero")
                                self.lastApZonesBypassed = apZonesBypassed
                                # Clear the bypass state of all zones
                                for zone in self.listOfZonesBypassed:
                                    bZoneData = self.plugin.zonesDict[int(zone)]
                                    bZDevid = bZoneData['devId']
                                    bIndigoDevice = indigo.devices[bZDevid]
                                    bIndigoDevice.updateStateOnServer(key='bypassState', value=False)

                                    # after setting bypass set the device state to itself (no change)
                                    # to force display to change from the Bypass state
                                    self.plugin.setDeviceState(bIndigoDevice, bIndigoDevice.displayStateValRaw)

                                    # clear the keypad state of zones bypassed
                                    # attempt to get the keypad device
                                    keypadDevice = self.plugin.getKeypadDeviceForDevice(forDevice=bIndigoDevice)
                                    if keypadDevice is not None:
                                        keypadDevice.updateStateOnServer(key='zonesBypassList', value='')

                                    self.logger.debug(
                                        u"clearing bypass state for zone:{}, devid:{}".format(zone, bZDevid))
                                    self.logger.debug(u"zone:{}, data:{}".format(zone, self.plugin.zonesDict[zone]))

                                # and now clear the list of bypassed zones
                                self.listOfZonesBypassed.clear()

                        if apZonesBypassed == "1" and msgKey == "BYPAS" and validBypassZone is True:
                            # A zone has been bypassed.
                            if bMsgZoneNum in self.listOfZonesBypassed:
                                self.logger.debug(
                                    u"zone bypass state zone:{}, name:{} already recorded".format(bMsgZoneNum, zName))
                            else:
                                self.listOfZonesBypassed.append(bMsgZoneNum)
                                self.logger.info(
                                    u"Alarm zone number:{}, name:{} has been bypassed".format(bMsgZoneNum, zName))
                                self.lastApZonesBypassed = apZonesBypassed
                                indigoDevice.updateStateOnServer(key='bypassState', value=True)

                                # after setting bypass set the device state to itself (no change)
                                # to force display to change from the Bypass state
                                self.plugin.setDeviceState(indigoDevice, indigoDevice.displayStateValRaw)

                                # update the keypad state of zones bypassed
                                # attempt to get the keypad device
                                keypadDevice = self.plugin.getKeypadDeviceForDevice(forDevice=indigoDevice)
                                if keypadDevice is not None:
                                    bypassZoneListString = ','.join(map(str(self.listOfZonesBypassed)))
                                    keypadDevice.updateStateOnServer(key='zonesBypassList', value=bypassZoneListString)

                        # OK, Now let's see if we have a zone event
                        if not ad2usbIsAdvanced and len(self.plugin.zonesDict) > 0:
                            self.logger.debug(u'calling basic')
                            self.logger.debug(u'Zone:{}, Key:{}'.format(msgZoneNum, msgKey))

                            if msgKey == "FAULT" or apReadyMode == '1':
                                if msgZoneNum != 0:
                                    self.logger.debug(u"ready to call basic msg handler")
                                    self.basicReadZoneMessage(rawData, msgBitMap, msgZoneNum,
                                                              msgText, msgKey, panelDevice)

            elif rawData[1:9] == u'SER2SOCK' or len(rawData) == 0:
                # ignore system messages
                self.logger.debug(u"SER2SOCK connection or null message - do nothing")
                pass

            elif rawData[1:4] == 'LRR':   # panel state information  - mostly for events
                pass  # converted to new message processing

            else:
                # We check the length of self.plugin.zonesDict so we will not try to update zones if none exist
                # and then call the advanced mode handler.
                # it is Ok that we skipped the panel update code, we'll catch that on the full ad2usb message

                if ad2usbIsAdvanced and len(self.plugin.zonesDict) > 0 and rawData[1:4] != "AUI":
                    self.logger.debug(u"Calling advanced for:{}".format(rawData[1:4]))
                    self.advancedReadZoneMessage(rawData)  # indigoDevice, panelKeypadAddress)

            self.logger.debug(u"panelMsgRead End")

        except Exception as err:
            self.logger.error(u'Error on line:{}'.format(sys.exc_info()[-1].tb_lineno))
            self.logger.error(u"Error:{}".format(str(err)))

        self.logger.debug(u"completed")

    def startAD2USBComm(self):
        """
        Initiates serial port open call and sends C and V commands and read CONFIG and VER.
        The reading of the output of these two messages will happen in runConcurrentThread.

        Return True for success; False for failure
        """
        self.logger.debug(u"called")

        try:
            # this section for panel playback
            # if comm is set to panel playback setSerial and use that value
            if self.plugin.isPlaybackCommunicationModeSet:
                self.logger.debug(u"Panel Message Playback Set - communication started")
                if self.setSerialConnection():
                    return True
                else:
                    return False

            # this section and below for IP and USB
            # otherwise lets track if we successfully read the VER and CONFIG messages
            verSendSuccess = False
            configSendSuccess = False

            # try to open the serial connection
            if self.setSerialConnection():
                self.logger.info(u"AlarmDecoder communication started...")

                if self.sendAlarmDecoderVersionCommand():
                    verSendSuccess = True
                    self.logger.info(u"AlarmDecoder VER (version) command sent")

                if self.sendAlarmDecoderConfigCommand():
                    configSendSuccess = True
                    self.logger.info(u"AlarmDecoder C (config) command sent")

            if verSendSuccess and configSendSuccess:
                self.logger.info(u"AlarmDecoder communication startup completed successfully")

                # TO DO: remove this? ported this log from old startComm
                for zone in sorted(self.plugin.zonesDict):
                    self.logger.debug(u"...Index:{}, Data:{}".format(zone, self.plugin.zonesDict[zone]))

                self.isCommStarted = True
                return True
            else:
                if not configSendSuccess:
                    self.logger.error(u"Unable to send AlarmDecoder CONFIG command")
                if not verSendSuccess:
                    self.logger.error(
                        u"Unable to send AlarmDecoder VERSION command. LRR messages will be ignored until firmware version is known.")

                self.isCommStarted = False
                return False

        except Exception as err:
            self.logger.error(u"Unable to open serial connection and read CONFIG and VER - error:{}".format(str(err)))
            self.isCommStarted = False
            return False

    ########################################
    def stopAD2USBComm(self):
        """
        This method is called by the plugin shutdown. It will close serial connection and
        set the 'isCommStarted' property to False
        """
        try:
            # set the flag first
            self.logger.debug(u"called")
            self.stopReadingMessages = True
            self.isCommStarted = False

            if self.serialConnection is not None:
                self.logger.debug(u'serial connection is some object:{}'.format(self.serialConnection))

                # if it is open we we close it
                if self.serialConnection.is_open:
                    self.logger.info(u'serial connection is open... attempting to close...')
                    self.serialConnection.close()
                    self.logger.info(u'serial connection is closed...')

        except Exception as err:
            self.logger.error(u"Error while closing connection on line {}".format(sys.exc_info()[-1].tb_lineno))
            self.logger.error(u"Error:{}".format(str(err)))

    def sendAlarmDecoderConfigCommand(self):
        """
        opens communication to the AlarmDecoder and runs the "C" command to get the current
        AlarmDecoder configuration string. This string will be read on another thread and
        then calls the process method to parse the config message string

        returns True or False based on success or failure
        """
        try:
            self.logger.debug(u'called')

            # don't run if in playback mode
            if self.plugin.isPlaybackCommunicationModeSet:
                self.logger.debug(u'Panel Message Playback Set - cannot send AlarmDecoder CONFIG command')
                return False

            if (self.plugin.ad2usbCommType == 'IP') or (self.plugin.ad2usbCommType == 'USB'):

                self.logger.debug(u'attempting to get serial connection')
                if (self.setSerialConnection()) and (self.serialConnection is not None):
                    self.logger.debug(u"established connection to send CONFIG command")

                    # send message to AlarmDecoder
                    configCommand = kADCommands['CONFIG']
                    self.logger.debug(u'attempting to send CONFIG command:{} to AlarmDecoder'.format(configCommand))
                    self.panelWriteWrapper(self.serialConnection, configCommand)
                    self.logger.debug(u'sent CONFIG command to AlarmDecoder')

                    return True

            else:
                self.logger.debug(u'commType is not IP or USB:{}'.format(self.plugin.ad2usbCommType))
                return False

        except Exception as err:
            self.logger.error(
                u"sending AlarmDecoder configuration command failed - error:{}".format(str(err)))
            return False

    def sendAlarmDecoderVersionCommand(self):
        """
        Opens communication to the AlarmDecoder and sends the "V" command to get the current
        AlarmDecoder VER message which contains firmware version and capabilties.

        Returns True for success; False if send message fails
        """
        try:
            self.logger.debug(u'called')

            # don't run if in playback mode
            if self.plugin.isPlaybackCommunicationModeSet:
                self.logger.debug(u'Panel Message Playback Set - cannot send AlarmDecoder VER command')
                return False

            if (self.plugin.ad2usbCommType == 'IP') or (self.plugin.ad2usbCommType == 'USB'):

                self.logger.debug(u'attempting to get serial connection')
                if (self.setSerialConnection()) and (self.serialConnection is not None):
                    self.logger.debug(u"established connection to send VER command")

                    # send message to AlarmDecoder
                    verCommand = kADCommands['VER']
                    self.logger.debug(u'attempting to send VER command:{} to AlarmDecoder'.format(verCommand))
                    self.panelWriteWrapper(self.serialConnection, verCommand)
                    self.logger.debug(u"VER command sent...")
                    return True

            else:
                self.logger.debug(u'commType is not IP or USB:{}'.format(self.plugin.ad2usbCommType))
                return False

        except Exception as err:
            self.logger.error(
                u"sending AlarmDecoder VER message failed, error:{}".format(str(err)))
            return False

    def writeAlarmDecoderConfig(self, configString=''):
        """
        opens communication to the AlarmDecoder and runs the "CONFIG" command
        to set the current AlarmDecoder configuration

        returns True or False based on success or failure
        """
        self.logger.debug(u'called')
        try:

            if (self.plugin.ad2usbCommType == 'IP') or (self.plugin.ad2usbCommType == 'USB'):

                # open a new connection as the URL could have changed
                self.logger.debug(u'attempting to connect to AlarmDecoder at:{}'.format(self.getURL()))

                if self.setSerialConnection():
                    self.logger.debug(u"established serial connection to write CONFIG")

                    if len(configString) > 0:
                        self.logger.debug(
                            u'attempting to update CONFIG settings:{} to AlarmDecoder'.format(configString))

                        if self.panelWriteWrapper(self.serialConnection, configString):
                            self.plugin.hasAlarmDecoderConfigBeenRead = False
                            self.logger.debug('AlarmDecoder CONFIG written successfully')
                            return True
                        else:
                            self.logger.error(u'AlarmDecoder CONFIG write failed')
                            return False
                    else:
                        self.logger.warning(u'AlarmDecoder CONFIG settings to write was empty')
                        return True

                else:
                    self.logger.error(u'Unable to get serial connection to write AlarmDecoder CONFIG')
                    return False

            elif self.plugin.ad2usbCommType == 'messageFile':
                # set this to test success and fail
                if True:
                    self.logger.debug(
                        'message Playback mode - simulate returning True'.format(self.plugin.ad2usbCommType))
                    return True
                else:
                    self.logger.debug(
                        'message Playback mode - simulate returning False'.format(self.plugin.ad2usbCommType))
                    return False

            else:
                self.logger.debug(
                    u'commType is not IP or USB:{} - cannot write to AlarmDecoder - returning False'.format(self.plugin.ad2usbCommType))
                return False

        except Exception as err:
            self.logger.error(
                u"reading AlarmDecoder configuration failed: URL:{}, CONFIG string:{}, error:{}".format(self.getURL(), configString, str(err)))
            return False

    def processAlarmDecoderConfigMessage(self, configMessage=None):
        """
        Parses a valid AlarmDecoder CONFIG message object (presumably read from the device) and sets the
        keys and values of the plugin property 'configSettings' to the CONFIG string keys and values.
        If the address has changed, it sets the legacy plugin property 'ad2usbKeyPadAddress', the keypad address
        preferences, and calls updateKeypadDevice with the old and new keypad address to automatically update
        applicable keypad devices.

        **parameter:**
        configMessage -- an AlarmDecoder.Message object
        """

        self.logger.debug(u"called with:{}".format(configMessage))

        try:
            # log the old settings
            self.logger.debug(u"prior configSettings were:{}".format(self.plugin.configSettings))

            # we loop thru settings vs. replace configSettings since a CONFIG message could
            # contain only a subset of parameters
            for newSetting in configMessage.attr('flags'):
                self.plugin.configSettings[newSetting] = configMessage.attr('flags')[newSetting]

            self.logger.debug(u"updated configSettings are:{}".format(self.plugin.configSettings))

            # check the new address is valid and the new address has changed
            if self.plugin.isValidKeypadAddress(self.plugin.configSettings['ADDRESS']):

                # did the address change outside of the plugin ?
                if self.plugin.configSettings['ADDRESS'] != self.plugin.ad2usbKeyPadAddress:
                    newAddress = self.plugin.configSettings['ADDRESS']
                    oldAddress = self.plugin.ad2usbKeyPadAddress
                    self.logger.info(u"AlarmDecoder reports a new keypad address:{}".format(newAddress))

                    # update the plugin property
                    self.plugin.ad2usbKeyPadAddress = newAddress

                    # update the prefrences
                    self.plugin.pluginPrefs['ad2usbKeyPadAddress'] = newAddress

                    # update the keypad device
                    self.plugin.updateKeypadDevice(newAddress=newAddress, oldAddress=oldAddress)

            else:
                self.logger.warning("Invalid ADDRESS:{} on AlarmDecoder".format(self.plugin.configSettings['ADDRESS']))

            # if we need to info log the CONFIG to the console do it

            # we log if we flagged that we should
            newSettingsString = self.plugin.generateAlarmDecoderConfigString()
            newSettingsString = newSettingsString[1:]  # remove the leading C
            newSettingsStringSorted = self.plugin.generateAlarmDecoderConfigString(True)  # sorted

            # log if we detect a change and we're not loggind due to flag: hasAlarmDecoderConfigBeenRead
            if self.plugin.hasAlarmDecoderConfigBeenRead:

                if newSettingsStringSorted != self.plugin.previousCONFIGString:
                    self.logger.info("AlarmDecoder CONFIG setting are now: {}".format(newSettingsString))

            # or log if the read flag is not set
            else:
                self.logger.info("AlarmDecoder CONFIG message read: {}".format(
                    configMessage.attr('configMessageString')))

                self.logger.info("AlarmDecoder CONFIG setting are now: {}".format(newSettingsString))
                self.plugin.hasAlarmDecoderConfigBeenRead = True

            # reset the previous CONFIG string to detect changes
            self.plugin.previousCONFIGString = newSettingsStringSorted

        except Exception as err:
            # no changes are made to configSettings dictionary
            self.logger.error('Error processing CONFIG message:{} - error:{}'.format(configMessage, str(err)))
            self.logger.debug(u"configSettings are:{}".format(self.plugin.configSettings))

    def readConfigSettingsFromPrefs(self):
        """
        read the AlarmDecoder configuration settings from the Indigo Plugin preferences
        this is used when you cannot read the settings from the AlarmDecoder
        """

    def panelReadMessageFromFile(self, fileName):
        """
        This method is used to read alarm panel messages from a text file instead of the AlarmDecoder.
        It is used for testing and debugging. It will read the panel message playback file and
        return a single message (line). It uses internal variable to keep track of the current line.
        It expects the playback file to be in the **EXACT** format as the panel message log:
        *datetime | panel_message_string* *BUT* will also allow a line to being with '#' that
        will be skipped.

        Return a string that is a panel message as if it was from the AlarmDecoder
        """
        self.logger.debug(u'called')

        try:
            # define all vars used in exception now
            # TO DO: this is inefficient but simple - may need to improve
            lineNumber = 0
            playbackCurrentMessage = ''
            line = ''

            # set the flag to catch we have read the entire file to true
            didReadEntireFile = True

            if not self.__doesPlaybackFileExist():
                self.logger.error("Unable to read playback file:{}".format(fileName))
                self.logger.error("Stopping reading messages")
                self.stopReadingMessages = True
                return ''

            with open(fileName, 'rt') as f:
                self.logger.debug(u'reading file:{}...'.format(fileName))

                for lineNumber, line in enumerate(f):
                    # increment the line number - first line is 1
                    lineNumber += 1

                    # check if current line number is > last read number (the next line after last read)
                    if lineNumber > self.playbackLastLineNumberRead:

                        self.logger.debug(u'reading line number:{}...'.format(lineNumber))
                        self.logger.debug(u'line:{}'.format(line))

                        # increment the last line number read
                        self.playbackLastLineNumberRead += 1

                        # we've read up to the last line so set the flag to False
                        didReadEntireFile = False

                        # skip the line if its a comment
                        if line.startswith('#'):
                            pass
                            # we don't break here so we just read the next comment

                        # lines that start with ~ are test comments to log to Indigo Log Window
                        elif line.startswith('~'):
                            self.logger.info(line.strip())
                            pass
                            # we don't break here so we just read the next comment

                        # else process it
                        else:
                            # split on the "|" and strip the whitespace from the message part of the file
                            lineItems = re.split(r'\|', line)
                            playbackCurrentMessage = lineItems[1].strip()

                            # because this is used for testing and is SO FAST
                            # we sleep for a set time before returning the message
                            # unless its countdown timer and then we sleep only 1 sec
                            if "May Exit Now" in playbackCurrentMessage:
                                time.sleep(1)
                            else:
                                time.sleep(self.playbackSleepTime)

                            # end the for loop we have the one line we're interested
                            break

                    else:
                        # do nothing since we've already processed this line
                        pass

                # end for loop

            # close the file
            f.close()

            # see if we've read the entire file; if so we tell the plugin to shutdown
            if didReadEntireFile:
                self.logger.debug(u'file has been read - will initiate shutdown')
                self.stopReadingMessages = True
                self.hasPlaybackFileBeenRead = True

            # return the message string
            self.logger.debug(u'returning message:{}'.format(playbackCurrentMessage))
            return playbackCurrentMessage

        except Exception as err:
            self.logger.error(
                u"Error reading from AlarmPanel filename:{}, line ({}):{} - error:{}".format(fileName, lineNumber, line, str(err)))
            return ''

    def panelReadWrapper(self, serialObject):
        """
        this is a wrapper to support Python 2 and 3 serial communications. Python 2 is a string. Python 3 is bytes and
        must be decoded. Returns a string of the message read or empty string if there are any errors or if timeout is reached
        """
        self.logger.debug(u'called')

        panelMessageAsString = ''
        myErrorMessage = ''
        try:
            # test if we're reading from a file first
            if self.plugin.isPlaybackCommunicationModeSet:
                self.logger.debug(u'attempting to read from the Message Playback file')

                if not self.__doesPlaybackFileExist():
                    self.logger.error("Playback file does not exist:{}".format(
                        self.plugin.panelMessagePlaybackFilename))
                    self.logger.error("Stopping reading messages")
                    self.stopReadingMessages = True
                    return ''
                else:
                    panelMessageAsString = self.panelReadMessageFromFile(self.plugin.panelMessagePlaybackFilename)
                    return panelMessageAsString

            # else we are reading from Serial port - either Python 2 or 3
            # TO DO: we can remove the Python 2 block post version 3.0.0
            else:
                myErrorMessage = 'checking Python verion'
                if self.plugin.pythonVersion == 3:
                    self.logger.debug(u'attempting to read from the AlarmDecoder')

                    # convert str to bytes for writing in Python 3
                    myErrorMessage = 'reading bytes from serial object'
                    panelMessageInBytes = serialObject.readline()

                    myErrorMessage = 'decoding bytes to string'
                    panelMessageAsString = panelMessageInBytes.decode("utf8")

                    self.logger.debug(u"read from AlarmDecoder (Python 3) bytes:{}".format(panelMessageInBytes))
                    self.logger.debug(u"read from AlarmDecoder (Python 3):{}".format(panelMessageAsString))
                else:
                    myErrorMessage = 'reading string from serial object'
                    panelMessageAsString = serialObject.readline()
                    self.logger.debug(u"read from AlarmDecoder (Python 2):{}".format(panelMessageAsString))

                return panelMessageAsString

        except Exception as err:
            self.logger.error(
                u"Error reading from AlarmPanel:{} - error:{}".format(myErrorMessage, str(err)))

            # attempt to restart communication
            if self.setSerialConnection(forceReset=True):
                self.logger.info("AlarmDecoder communication reset...")
            else:
                self.logger.error("Failed to reset AlarmDecoder communication. Check connection...")

            # return a blank message that will be skipped
            return ''

    def panelWriteWrapper(self, serialObject, message=''):
        """
        this is a wrapper to support Python 2 and 3 serial communications. Python 2 is a string. Python 3 is bytes and must be encoded.
        returns success (True) or failure (False)
        """
        self.logger.debug(u'called with:{}'.format(message))

        myErrorMessage = ''
        try:
            # if we're using debug playback mode we will write the panel message as INFO to the logs
            if self.plugin.isPlaybackCommunicationModeSet:
                self.logger.info('Simulate writing panel message:{}'.format(message))
                return True

            else:
                myErrorMessage = 'checking Python verion'
                if self.plugin.pythonVersion == 3:
                    myErrorMessage = 'encoding string to bytes'
                    panelMessageInBytes = message.encode("utf8")

                    self.logger.debug(u'attempting to write to the AlarmDecoder')
                    myErrorMessage = 'writing bytes to serial object'
                    serialObject.write(panelMessageInBytes)

                    self.logger.debug(u"wrote to AlarmDecoder (Python 3):{}".format(message))
                    self.logger.debug(u"wrote to AlarmDecoder (Python 3) bytes:{}".format(panelMessageInBytes))
                else:
                    myErrorMessage = 'writing string to serial object'
                    serialObject.write(message)
                    self.logger.debug(u"wrote to AlarmDecoder (Python 2):{}".format(message))

                return True

        except Exception as err:
            self.logger.error(
                u"Error writing to AlarmPanel:{} - error:{}".format(myErrorMessage, str(err)))
            return False

    def getURL(self):
        """
        returns the URL value from the plugin
        """
        self.logger.debug(u'called')
        return self.plugin.URL

    def getTimeout(self):
        """
        returns the value of the timeout constant k_SERIAL_TIMEOUT
        """
        self.logger.debug(u'called')
        return k_SERIAL_TIMEOUT

    def setSerialConnection(self, forceReset=False):
        """
        Sets the property "serialConnection" to a serial connection object to the AlarmDecoder
        or None if there is an error or if running in Playback debug mode.

        If parameter forceReset is provided and set to True it closes the serial connection if it exists
        and resets the property "serialConnection" to a new serial connection object to the AlarmDecoder
        or None if there is an error or if running in Playback debug mode. This method should be called
        with forceReset if the AlarmDecoder communication settings are changed.

        Returns True for success; or False for failure
        """
        self.logger.debug(u'called')

        try:
            # return True and set serialConnection to None if in Playback mode
            # unless the file has been read and then send a False
            if self.plugin.isPlaybackCommunicationModeSet:
                self.logger.debug(u'Panel message playback mode set - setting to serial connection to None')
                self.serialConnection = None

                # set the comm started flag to false unless the file exists
                # and we have not already read the entire file
                if self.__doesPlaybackFileExist():
                    if self.hasPlaybackFileBeenRead:
                        self.isCommStarted = False
                        return True
                    else:
                        self.isCommStarted = True
                        return True
                else:
                    self.isCommStarted = False
                    return False

            # if we're not forcing a reset (default is false)
            if not forceReset:

                # test the object first
                # if its not None assume its a serial object
                # TO DO: test for serial object vs. not None
                if self.serialConnection is not None:
                    self.logger.debug(u'serial connection is some object:{}'.format(self.serialConnection))

                    # if it is open we do nothing - we're all set
                    if self.serialConnection.is_open:
                        self.logger.debug(u'serial connection is open...')
                        # nothing more to do
                        self.isCommStarted = True
                        return True

            # else we are being asked to do a force reset
            else:
                # TO DO: test for serial object vs. not None
                if self.serialConnection is not None:
                    if self.serialConnection.is_open:
                        self.serialConnection.close()

            # if we get here we either have a None object or a closed serial
            # of we're forcing a reset which means a new serial object

            # start by changing the internal flag that comm is no longer set
            self.isCommStarted = False

            # get the URL for IP or Serial
            theURL = self.getURL()
            self.logger.info(u"attempting to connect to:{}".format(theURL))

            # attempt to create a new serial object and connect
            self.serialConnection = serial.serial_for_url(theURL, baudrate=115200)

            # set a timeout to not wait indefinitely on readline
            self.serialConnection.timeout = k_SERIAL_TIMEOUT

            # log and return success
            self.isCommStarted = True
            self.logger.info(u"connected to AlarmDecoder:{}".format(theURL))
            return True

        except Exception as err:
            self.logger.critical(u"Error establishing serial connection - error:{}".format(str(err)))
            self.serialConnection = None
            self.isCommStarted = False
            return False

    def setFirmware(self, firmwareVersion):
        """
        Set the property named 'firmwareVersion' of the firmware version supplied and logs to INFO if it changed.

        Returns True if changed; False otherwise
        """
        if (firmwareVersion != self.firmwareVersion) or self.plugin.showFirmwareVersionInLog:
            self.firmwareVersion = firmwareVersion
            self.logger.info("AlarmDecoder Firmware Version is: {}".format(firmwareVersion))
            # reset flag so we don't show the version message every time
            self.plugin.showFirmwareVersionInLog = False
            return True  # changed
        else:
            return False  # no change

    def process_KPM_BYPAS(self, kpmMsg):
        """
        Process KPM BYPAS messages we have to do the most processing. We look at both
        Process BYPAS bit: 0 = clear all BYPAS zones.
        Process BYPAS message string to add zones to BYPAS list.
        """
        self.logger.debug("called with:{}".format(kpmMsg.getMessageProperties()))

        try:
            # clear bypass zones if flag changed from 1 to 0
            if (kpmMsg.getKPMattr('ZONES_BYPASSED') == 0) and (self.lastApZonesBypassed == 1):
                self.logger.debug("zones bypassed keypad flag is now zero")
                self.lastApZonesBypassed = 0
                # Clear the bypass state of all zones
                for zone in self.listOfZonesBypassed:
                    myDevice = self.plugin.getDeviceForZoneNumber(zone)
                    myDevice.updateStateOnServer(key='bypassState', value=False)

                    # after setting bypass set the device state to itself (no change)
                    # to force display to change from the Bypass state
                    self.plugin.setDeviceState(myDevice, myDevice.displayStateValRaw)

                    self.logger.debug(
                        u"clearing bypass state for zone:{}, devid:{}".format(zone, myDevice.id))
                    self.logger.debug(u"zone:{}, data:{}".format(zone, self.plugin.zonesDict[zone]))

                # and now clear the list of bypassed zones
                self.listOfZonesBypassed.clear()

            # see if BYPAS was part of the message text and add it if it does not exist
            if (kpmMsg.getKPMattr('ZONES_BYPASSED') == 1) and kpmMsg.attr('isBypassZone'):
                # ensure its a valid zone code on the keypad message
                if kpmMsg.attr('isValidNumericCode'):

                    # ensure its a zone we know about in our Indigo devices
                    zone = kpmMsg.attr('zoneNumberAsInt')
                    myDevice = self.plugin.getDeviceForZoneNumberAsInt(zone)

                    if myDevice is not None:
                        # skip if we already know this zone is bypassed
                        if zone in self.listOfZonesBypassed:
                            pass
                        else:
                            self.listOfZonesBypassed.append(zone)
                            myDevice.updateStateOnServer(key='bypassState', value=True)

                            # after setting bypass set the device state to itself (no change)
                            # to force display to change from the Bypass state
                            self.plugin.setDeviceState(myDevice, myDevice.displayStateValRaw)
                    else:
                        self.logger.warning("Indigo device does not exist for zone:{}".format(zone))

        except Exception as err:
            self.logger.error("Error processing BYPASS message:{}".format(str(err)))

    def process_EXP_Message(self, messageObject):
        """
        For EXP messages we find the zone device and the keypad devices based on the parition of the
        zone device. Returns True is device was updated, False if it was not.
        """
        self.logger.debug("called with:{}".format(messageObject.getMessageProperties()))

        try:
            myDevice = self.plugin.getZoneDeviceForEXP(address=messageObject.attr(
                'zoneExpanderAddress'), channel=messageObject.attr('expanderChannel'))

            # make sure we have a good device
            if myDevice is None:
                return False

            # log some debug info about the device
            self.logger.debug("found EXP device id:{} name:{}".format(myDevice.id, myDevice.name))

            # get the zone number as a an int
            zoneNumber = self.plugin.getZoneNumberForDevice(myDevice)
            if zoneNumber is None:
                self.logger.warning("No device zone number found for EXP device name:{}".format(myDevice.name))
                return False

            # update the device if the message was valid
            if messageObject.attr('isFaulted') is None:
                self.logger.debug("fault setting not correct for EXP device")
                return False

            # update device state
            if messageObject.attr('isFaulted'):
                self.plugin.setDeviceState(myDevice, AD2USB_Constants.k_FAULT)
            else:
                self.plugin.setDeviceState(myDevice, AD2USB_Constants.k_CLEAR)

            # update the keypad?
            keypadDevice = self.plugin.getKeypadDeviceForDevice(myDevice)
            if keypadDevice is None:
                return False

            # get valid address from device
            keypadAddress = self.plugin.getKeypadAddressFromDevice(keypadDevice=keypadDevice)

            # if valid
            if keypadAddress is not None:

                # update the Zone Fault List on the keypad device
                if messageObject.attr('isFaulted'):
                    self.updateZoneFaultListForKeypad(keypad=keypadAddress, addZone=zoneNumber)
                    keypadDevice.updateStateOnServer(key='zoneFaultList', value=str(self.zoneStateDict[keypadAddress]))
                    # we do not update the keypad state
                    # self.plugin.setKeypadDeviceState(keypadDevice, AD2USB_Constants.k_PANEL_FAULT)
                else:
                    self.updateZoneFaultListForKeypad(keypad=keypadAddress, removeZone=zoneNumber)
                    keypadDevice.updateStateOnServer(key='zoneFaultList', value=str(self.zoneStateDict[keypadAddress]))
                    # we do not update the keypad state
                    # if len(self.zoneStateDict[keypadAddress]) == 0:
                    #   self.plugin.setKeypadDeviceState(keypadDevice, AD2USB_Constants.k_PANEL_READY)

        except Exception as err:
            self.logger.error("Error processing EXP message:{}".format(str(err)))

    def process_LRR_Message(self, messageObject):
        """
        For LRR messages we update all the possible keypad devices based on the parition provided
        by the LRR message. A parition of 0 = all partitions. We then call any triggers associated
        with the LRR events.
        """
        self.logger.debug("called with:{}".format(messageObject.getMessageProperties()))

        # EVENT DATA - Either the User Number who preformed the action or the zone that was bypassed.
        # PARTITION - The panel partition the event applies to. 0 indicates all partitions such as ACLOSS event.
        # EVENT TYPES - One of the following events. Note: the programming mode for enabling each type is also provided.
        # eg. !LRR:002,1,OPEN

        try:
            # look if new LRR message has a valid mapping first
            if messageObject.getMessageType() == 'LR2':
                if messageObject.getMessageAttribute('isMappedToEvent'):
                    # do nothing and process in the next section
                    pass

                else:
                    if self.plugin.logUnknownLRRMessages:
                        self.logger.warning("Unknown LRR Message - please post this message in User Forum \"Unknown LRR Messages\": {}".format(
                            messageObject.messageString))

                    # no need to process
                    return

            # message parsed:{'eventData': '008', 'partition': 1, 'eventType': 'ACLOSS', 'eventDataAsInt': 8, 'isKnownLRR': True}

            # get some shorter variable names from the message object
            partition = messageObject.getMessageAttribute('partition')
            eventType = messageObject.getMessageAttribute('eventType')
            user = ''
            zone = ''
            if messageObject.getMessageAttribute('isUserEvent'):
                user = messageObject.getMessageAttribute('eventData')
            elif messageObject.getMessageAttribute('isZoneEvent'):
                zone = messageObject.getMessageAttribute('eventData')

            # get a list of keypads for the partition
            keypadsToUpdate = []
            if messageObject.getMessageAttribute('isAllPartitions'):
                keypadsToUpdate = self.plugin.getAllKeypadDevices()
            else:
                oneKeypad = self.plugin.getKeypadDeviceForPartition(partition)
                if oneKeypad is not None:
                    keypadsToUpdate.append(oneKeypad)

            self.logger.debug('Will update:{} keypad devices'.format(len(keypadsToUpdate)))

            # update all the applicable keypads
            now = datetime.now()
            timeStamp = now.strftime("%Y-%m-%d %H:%M:%S")
            for oneKeypad in keypadsToUpdate:
                oneKeypad.updateStateOnServer(key='lastChgTo', value=eventType)
                oneKeypad.updateStateOnServer(key='lastChgAt', value=timeStamp)
                # will show user or blank if not a user event
                oneKeypad.updateStateOnServer(key='lastChgBy', value=user)
                # TO DO: Add Zone details to keypad state

                self.logger.debug('Updated keypad device:{} with partition number:{}'.format(oneKeypad.name, partition))

            # log event
            if self.plugin.logArmingEvents:
                if messageObject.getMessageAttribute('isUserEvent'):
                    self.logger.info("Alarm partition:{} set to:{} by:{}".format(partition, eventType, user))
                if messageObject.getMessageAttribute('isZoneEvent'):
                    self.logger.info("Alarm partition:{} zone:{} had event:{}".format(partition, zone, eventType))

            # now check to see if any triggers need to be called
            self.executeTrigger(partition, user, eventType)

        except Exception as err:
            self.logger.error(u"LRR Error:{}".format(str(err)))

    def __doesPlaybackFileExist(self):
        """
        Checks if Playback file exists.

        Returns True if exists; False otherwise.
        """
        if os.path.isfile(self.plugin.panelMessagePlaybackFilename):
            return True
        else:
            return False

    def updateZoneFaultListForKeypad(self, keypad=None, addZone=None, removeZone=None):
        """
        Adds or removes an element to the zoneStatDict property for a given keypad.
        Ensure the property is an array of integers that is sorted and unique.
        """
        # initialize the list for the keypad if needed
        if keypad not in self.zoneStateDict:
            self.zoneStateDict[keypad] = []

        # lets try to add first
        try:
            # skip if None
            if addZone is not None:
                # convert to an Int
                addAsInt = int(addZone)
                # don't add a zero or negative
                if addAsInt > 0:
                    self.zoneStateDict[keypad].append(addAsInt)

        except Exception as err:
            self.logger.warning("Unable to add zone to fault list:{}, msg:{}".format(addZone, str(err)))

        # next we we unique the list
        # initialize a null list
        unique_list = []

        # traverse for all elements
        for x in self.zoneStateDict[keypad]:
            # check if exists in unique_list or not
            if x not in unique_list:
                unique_list.append(x)

        # next lets try to remove
        try:
            # skip if None
            if removeZone is not None:
                # convert to an Int
                removeAsInt = int(removeZone)
                # only remove if it exists
                if removeAsInt in unique_list:
                    unique_list.remove(removeAsInt)

        except Exception as err:
            self.logger.warning("Unable to remove zone from fault list:{}, msg:{}".format(removeZone, str(err)))

        # replace the property with the sorted uniq list
        unique_list.sort()
        self.zoneStateDict[keypad] = unique_list.copy()

    def __convertToPaddedKeypadAddress(self, keypadAddressString=''):
        """
        Takes a string and returns a valid two-digit keypad address as a string. Will be
        zero-padded if < 10. Returns blank if not a valid number. Valid numbers are 1-99.
        """
        try:
            # test the empty string
            if keypadAddressString == '':
                return ''

            # attempt to convert to an integer
            keypadAsInt = int(keypadAddressString)

            if keypadAsInt > 0 and keypadAsInt < 10:
                return '0' + str(keypadAsInt)
            elif keypadAsInt < 100:
                return str(keypadAsInt)
            else:
                return ''

        except Exception as err:
            self.logger.debug("error converting keypad to zero-padded string:{}".format(str(err)))
            return ''

    def __flagToBoolean(self, flag=None, defaultValue=False):
        """
        Takes a flag or 1 or 0 and converts it to True or False. Returns defaultValue if flag is invalid.
        """
        if flag is None:
            return defaultValue

        if isinstance(flag, int):
            if flag == 1:
                return True
            elif flag == 0:
                return False
            else:
                return defaultValue

        else:
            return defaultValue

    def __convertUsersStringToList(self, name='', userString=''):
        """
        Takes a string or Indigo variable 'userString' and returns an array of integer that represent User Numbers
        """
        arrayOfUsers = []

        try:
            # strip whitespace
            userString = userString.strip()

            # is the userStringList a variable?
            # check if the pattern is valid variable
            if re.search(r'^%%v:\d+%%$', userString) is None:
                # its not a variable and we just use the value as passed
                usersValue = userString
            else:
                # it looks like a variable, check with the method that returns a tuple: Bool, String
                isVariableSub = self.plugin.substituteVariable(userString, True)
                # check the tuple value
                if isVariableSub[0]:
                    # if the tuple is true call the method again to get variables value
                    self.logger.debug('User is a variable:{}'.format(userString))
                    usersValue = self.plugin.substituteVariable(userString, False)
                    self.logger.info('Processing Trigger:{} - converted variable:{} to:{}'.format(name, userString, usersValue))
                else:
                    # unable to parse variable and we just use the value as passed
                    self.logger.error('Value from User variable:{} cannot be determined. Trigger will not be run.'.format(userString))
                    usersValue = ''

            # split the string on comma
            for oneUserString in usersValue.split(','):
                # try to convert to an integer
                oneUserInt = self.__getIntFromString(oneUserString)
                if oneUserInt is not None:
                    arrayOfUsers.append(oneUserInt)

        except Exception as err:
            self.logger.error("Error processing Trigger:{} Users value of:{}".format(name, userString))
            self.logger.error("Error message:{}".format(str(err)))
            return []

        return arrayOfUsers

    def __getIntFromString(self, intAsString=''):
        """
        Converts a string to an int. Returns None if the string is not a valid integer.
        """
        for c in intAsString:
            if c not in '0123456789':
                # return None if we find an invalid character
                return None
            else:
                pass

        # if we get here its contains valid int characters - but lets be extra safe
        try:
            x = int(intAsString)
            return x

        except Exception as err:
            self.logger.debug('Error converting:{} to integer - error:{}'.format(intAsString, str(err)))
            return None
