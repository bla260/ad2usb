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

# Custom Zone State - see Devices.xml
kZoneStateDisplayValues = {'faulted': 'Fault', 'Clear': 'Clear'}
k_CLEAR = 'Clear'  # key: Clear, value: Clear - should convert key to 'clear'
k_FAULT = 'faulted'  # key: faulted, value: Fault - should convert to 'fault'

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
        self.zoneBypassDict = {}  # dict with key of zone number as int, values are True
        self.lastApZonesBypassed = 0

        self.stopReadingMessages = False
        self.shutdownComplete = False

        # set the debug panel playback file
        self.playbackLastLineNumberRead = 0  # tracks the current line
        self.playbackSleepTime = 3  # 5 seconds sleep between each message
        self.hasPlaybackFileBeenRead = False  # flag to set after reading file

        # set the firmware to unknown and the serial connection to None
        self.firmwareVersion = ''
        self.serialConnection = None
        self.isCommStarted = False  # this property is set in newStartComm

        # this code executes before runConcurrentThread so no open reading is happening
        # send a VER and CONFIG message and read the output
        if self.newStartComm():
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

        if event in self.plugin.triggerDict:
            self.logger.debug(u"found event trigger:{}".format(self.plugin.triggerDict[event]))
            try:
                if self.plugin.triggerDict[event][partition]:
                    # We have a winner
                    indigo.trigger.execute(int(self.plugin.triggerDict[event][partition]))
                    self.logger.debug(u"matched event trigger:{}".format(self.plugin.triggerDict[event][partition]))
            except:
                pass
        if isinstance(user, int):
            user = str(int(user))  # get rid of the leading zeroes
            if user in self.plugin.triggerDict:
                self.logger.debug(u"found user trigger:{}".format(self.plugin.triggerDict[user]))
                try:
                    if self.plugin.triggerDict[user][partition]:
                        if self.plugin.triggerDict[user][partition]['event'] == event:
                            # We have a winner
                            indigo.trigger.execute(int(self.plugin.triggerDict[user][partition]['tid']))
                            self.logger.debug(u"matched user trigger:{}".format(
                                self.plugin.triggerDict[user][partition]))
                except:
                    pass

        self.logger.debug(u"completed")

    ########################################
    # Write arbitrary messages to the panel
    def panelMsgWrite(self, panelMsg, address=''):
        self.logger.debug(u"called with msg:{} for address:{}".format(panelMsg, address))

        try:
            # if no keypad address specified no need to prefix the message with K##
            if len(address) == 0:
                self.panelWriteWrapper(self.serialConnection, panelMsg)
            else:
                if len(address) == 1:
                    address = "0" + address
                panelMsg = 'K' + address + str(panelMsg)
                self.panelWriteWrapper(self.serialConnection, panelMsg)
                self.logger.info(u"sent panel message:{}".format(panelMsg))
        except Exception as err:
            self.logger.error(u"unable to write panel message:{}".format(panelMsg))
            self.logger.error(u"error message:{}, {}".format(str(err), sys.exc_info()[0]))

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
            for address in self.plugin.panelsDict:
                self.zoneStateDict[address] = []
            self.zoneListInit = True

        if rawData[1:4] == 'REL' or rawData[1:4] == 'EXP' or rawData[1:4] == 'RFX':   # a relay, expander module or RF zone event
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

                # Now we get some information about the partition, like the keypad address and the panel device
                panelDevId = self.plugin.partition2address[zPartition]['devId']
                panelDevice = indigo.devices[panelDevId]
                panelKeypadAddress = panelDevice.pluginProps['panelKeypadAddress']

                self.logger.debug(u"found zone info: zType={}, zDevId={}, zBoard={}, zDevice={}, zNumber={}, zLastState={}, zName={}, zPartition={}".format(
                    zType, zDevId, zBoard, zDevice, zNumber, zLastState, zName, zPartition))
                self.logger.debug(u"found panel info: DB:{}, dev={}".format(
                    self.plugin.partition2address[zPartition], panelDevice))

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
                        self.plugin.setDeviceState(indigoDevice, k_FAULT)

                        # Maintain the zone fault state
                        self.zoneStateDict[panelKeypadAddress].append(int(zNumber))
                        self.zoneStateDict[panelKeypadAddress].sort()
                        panelDevice.updateStateOnServer(key='zoneFaultList', value=str(
                            self.zoneStateDict[panelKeypadAddress]))

                        stateMsg = 'Faulted'
                    elif zoneState == zoneOff:
                        self.logger.debug(u"zoneOff zoneNumber:{}, and States list:{}".format(
                            zNumber, self.zoneStateDict))
                        self.plugin.setDeviceState(indigoDevice, k_CLEAR)

                        # Maintain the zone fault state
                        try:
                            self.zoneStateDict[panelKeypadAddress].remove(int(zNumber))
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
                    zoneStateDict = self.decodeState(zoneState)
                    if indigoDevice.pluginProps['zoneInvertSense']:
                        if zoneStateDict[wirelessLoop]:
                            zoneStateDict[wirelessLoop] = False
                        elif not zoneStateDict[wirelessLoop]:
                            zoneStateDict[wirelessLoop] = True
                        else:
                            self.logger.error(u"State:{} not found in:{}".format(
                                zoneState, self.plugin.advZonesDict[zoneIndex]))

                    if zoneStateDict[wirelessLoop]:
                        self.logger.debug(u"zoneOn zoneNumber:{}, and States list:{}".format(
                            zNumber, self.zoneStateDict))
                        self.plugin.setDeviceState(indigoDevice, k_FAULT)

                        # Maintain the zone fault state
                        try:
                            self.zoneStateDict[panelKeypadAddress].append(int(zNumber))
                            self.zoneStateDict[panelKeypadAddress].sort()
                            panelDevice.updateStateOnServer(key='zoneFaultList', value=str(
                                self.zoneStateDict[panelKeypadAddress]))
                        except:
                            pass  # probably a non-numeric zone

                        stateMsg = 'Faulted'
                    elif not zoneStateDict[wirelessLoop]:
                        self.logger.debug(u"zoneOff zoneNumber:{}, and States list:{}".format(
                            zNumber, self.zoneStateDict))
                        self.plugin.setDeviceState(indigoDevice, k_CLEAR)

                        # Maintain the zone fault state
                        try:
                            self.zoneStateDict[panelKeypadAddress].remove(int(zNumber))
                            panelDevice.updateStateOnServer(key='zoneFaultList', value=str(
                                self.zoneStateDict[panelKeypadAddress]))
                        except:
                            pass  # probably a non-numeric zone

                        stateMsg = 'Clear'
                    else:
                        self.logger.error(u"State:{} not found in:{}".format(
                            zoneState, self.plugin.advZonesDict[zoneIndex]))

                    if zoneStateDict['sup']:
                        supervisionMessage = True
                        if zLogSupervision:  # make sure we want this logged
                            self.logger.info(u"Zone:{} supervision received. ({})".format(zName, rawData[1:-2]))
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
            if rawData[0:8] != '!setting' and rawData[0:7] != '!CONFIG' and rawData[0:2] != '!>' and rawData[0:4] != '!KPE' and rawData[0:8] != '!Sending':
                self.logger.error(u"Unknown message received:{}".format(rawData))

        self.logger.debug(u"completed")

    ########################################
    # update Indigo on device state changes
    def updateIndigoBasicMode(self, zoneIndex, zoneState, panelDevice):
        self.logger.debug(u"called with index:{}, state:{}, panel:{}".format(zoneIndex, zoneState, panelDevice))

        if not self.zoneListInit:
            for address in self.plugin.panelsDict:
                self.zoneStateDict[address] = []
            self.zoneListInit = True

        zoneData = self.plugin.zonesDict[zoneIndex]
        zDevId = zoneData['devId']
        zLogChanges = zoneData['logChanges']
        zName = zoneData['name']
        indigoDevice = indigo.devices[zDevId]

        panelKeypadAddress = panelDevice.pluginProps['panelKeypadAddress']
        self.logger.debug(u"got address:{}".format(panelKeypadAddress))

        if zoneState == k_FAULT:
            self.zoneStateDict[panelKeypadAddress].append(int(zoneIndex))
            self.zoneStateDict[panelKeypadAddress].sort()
            self.logger.debug(u"faulted... state list:{}".format(self.zoneStateDict))
        else:
            self.zoneStateDict[panelKeypadAddress].remove(int(zoneIndex))
            self.logger.debug(u"clear... State list:{}".format(self.zoneStateDict))

        # update the device state
        self.plugin.setDeviceState(indigoDevice, zoneState)

        # update the panel device state info
        panelDevice.updateStateOnServer(key='zoneFaultList', value=str(self.zoneStateDict[panelKeypadAddress]))

        try:
            # now that zones have been updated we can refresh the zone groups
            self.plugin.updateAllZoneGroups()
        except Exception as err:
            self.logger.error(u"updateAllZoneGroups error:{}".format(str(err)))

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

                self.updateIndigoBasicMode(zoneIndex, k_FAULT, panelDevice)

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

                self.updateIndigoBasicMode(zoneIndex, k_CLEAR, panelDevice)

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

                self.updateIndigoBasicMode(zoneIndex, k_CLEAR, panelDevice)

                del self.plugin.faultList[remZonePos]

        self.logger.debug(u"Ready:{}, Fault:{}, Zone:{}".format(systemReady, zoneFault, msgZoneNum))
        self.logger.debug(u"The List:{}".format(self.plugin.faultList))

        self.logger.debug(u"completed")

    ########################################
    # Read the panel message stream
    #
    def panelMsgRead(self, ad2usbIsAdvanced):
        self.logger.debug(u"called")
        self.logger.debug(u"isAdvanced:{}".format(ad2usbIsAdvanced))

        lastPanelMsg = ""
        while self.stopReadingMessages is False:
            doNotProcessThisMessage = False  # default to process every message
            rawData = ""
            try:
                while (len(rawData) == 0) and (self.stopReadingMessages is False):
                    # this should read one line and block while waiting for another line
                    rawData = self.panelReadWrapper(self.serialConnection)

                    # ############## New Message Parser ########################
                    #
                    # added this code to begin to test the message Object
                    newMessageObject = AlarmDecoder.Message(rawData, self.firmwareVersion, self.logger)

                    # process select messages
                    if newMessageObject.isValidMessage:
                        if (newMessageObject.messageType == 'CONFIG') and newMessageObject.needsProcessing:
                            self.plugin.hasAlarmDecoderConfigBeenRead = True
                            self.processAlarmDecoderConfigString(
                                newMessageObject.getMessageAttribute('configMessageString'))

                        elif (newMessageObject.messageType == 'VER') and newMessageObject.needsProcessing:
                            self.setFirmware(newMessageObject.firmwareVersion)

                        elif (newMessageObject.messageType == 'AUI') and newMessageObject.needsProcessing:
                            pass

                        else:
                            pass

                    else:
                        self.logger.warning("Unable able to parse message:{}".format(
                            newMessageObject.invalidReason))

                    #
                    #
                    # ############## End New Message Parser ########################

                    # TO DO: this shouldn't happen
                    if rawData == '':
                        doNotProcessThisMessage = True
                        if self.stopReadingMessages is False:
                            self.logger.error(u"AD2USB Connection/Read Error")

            except Exception as err:
                # don't process any message we had an error reading
                doNotProcessThisMessage = True
                self.logger.error(u"Error reading AlarmDecoder message - error:{}".format(str(err)))
                self.logger.error(u"Error reading AlarmDecoder message - raw data is:{}".format(rawData))

                if self.stopReadingMessages is True:
                    self.logger.info(u"Stop reading messages has been set")
                    self.shutdownComplete = True
                else:
                    self.logger.error(u"Will try next message")

            # message Read was successful - log it
            self.logger.debug(u"Read ad2usb message:{}".format(repr(rawData)))

            # write the message to the panel log too if panel logging is enabled
            if self.plugin.isPanelLoggingEnabled:
                self.plugin.panelLogger.info(u"{}".format(rawData.rstrip()))

            #
            # Process Message Section
            #

            # if we don't want to process this message go back to top of while loop
            if doNotProcessThisMessage:
                continue

            # Start processing the message
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
                                for panelKeypadAddress in self.plugin.panelsDict:       # loop through the keypad device dict
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
                                apACPower = panelFlags[8]
                                apChimeMode = panelFlags[9]
                                apAlarmOccurred = panelFlags[10]
                                apAlarmBellOn = panelFlags[11]
                                apBatteryLow = panelFlags[12]
                                apFireAlarm = panelFlags[14]
                                apCheckZones = panelFlags[15]

                                self.logger.debug(u"Panel message:{}".format(panelFlags))

                                # self.ALARM_STATUS = {'000': 'Fault', '001': 'armedStay', '010': 'armedAway', '100': 'ready'}
                                panelTxtStatus = self.plugin.ALARM_STATUS[panelBitStatus]
                                if panelTxtStatus == 'ready':
                                    displayState = 'enabled'
                                    displayStateUi = 'Ready'
                                elif panelTxtStatus == 'Fault':
                                    displayState = 'faulted'
                                    displayStateUi = 'Fault'
                                else:
                                    displayState = panelTxtStatus
                                    displayStateUi = panelTxtStatus

                                lastPanelMsg = rawData
                                panelDevice = indigo.devices[self.plugin.panelsDict[foundKeypadAddress]['devId']]
                                self.logger.debug(u"Found dev:{}, id:{}".format(panelDevice.name, panelDevice.id))

                                # panelDevice = indigo.devices[self.plugin.alarmDevId]
                                panelDevice.updateStateOnServer(key='LCDLine1', value=rawData[61:77])
                                panelDevice.updateStateOnServer(key='LCDLine2', value=rawData[77:93])
                                panelDevice.updateStateOnServer(key='panelState', value=panelTxtStatus)
                                panelDevice.updateStateOnServer(
                                    key='displayState', value=displayState, uiValue=displayStateUi)
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
                            msgZoneNum = int(splitMsg[3])
                            realZone = False
                            try:
                                bMsgZoneNum = int(msgText[7:9])
                                realZone = True
                            except:
                                pass
                                # 0fc = comm failure; 0f* = Field?
                                # self.logError("%s: Panel reports: %s" % (funcName, msgText), self.logName)

                            msgKey = msgText[1:6]
                            self.logger.debug(u"msgKey is:{}, msgTxt is:{}".format(msgKey, msgText))
                            if msgZoneNum in self.plugin.zonesDict:  # avoid issues with count down timers on arm
                                zoneData = self.plugin.zonesDict[int(msgZoneNum)]
                                zDevId = zoneData['devId']
                                #zLogChanges = zoneData['logChanges']
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
                                    for zone in self.zoneBypassDict.keys():
                                        bZoneData = self.plugin.zonesDict[int(zone)]
                                        bZDevid = bZoneData['devId']
                                        bIndigoDevice = indigo.devices[bZDevid]
                                        bIndigoDevice.updateStateOnServer(key='bypassState', value=False)

                                        # after setting bypass set the device state to itself (no change)
                                        # to for force display to account for bypass state change
                                        self.plugin.setDeviceState(bIndigoDevice, bIndigoDevice.displayStateValRaw)

                                        self.logger.debug(
                                            u"clearing bypass state for zone:{}, devid:{}".format(zone, bZDevid))
                                        self.logger.debug(u"zone:{}, data:{}".format(zone, self.plugin.zonesDict[zone]))

                                    # and now clear the list of bypassed zones
                                    self.zoneBypassDict.clear()

                            if apZonesBypassed == "1" and msgKey == "BYPAS" and realZone is True:
                                # A zone has been bypassed.
                                if bMsgZoneNum in self.zoneBypassDict:
                                    self.logger.debug(
                                        u"zone bypass state zone:{}, name:{} already recorded".format(bMsgZoneNum, zName))
                                else:
                                    self.zoneBypassDict[bMsgZoneNum] = True
                                    self.logger.info(
                                        u"Alarm zone number:{}, name:{} has been bypassed".format(bMsgZoneNum, zName))
                                    self.lastApZonesBypassed = apZonesBypassed
                                    indigoDevice.updateStateOnServer(key='bypassState', value=True)

                                    # after setting bypass set the device state to itself (no change)
                                    # to for force display to account for bypass state change
                                    self.plugin.setDeviceState(indigoDevice, indigoDevice.displayStateValRaw)

                            # OK, Now let's see if we have a zone event
                            if not ad2usbIsAdvanced and len(self.plugin.zonesDict) > 0:
                                self.logger.debug(u'calling basic')
                                self.logger.debug(u'Zone:{}, Key:{}'.format(msgZoneNum, msgKey))

                                if msgKey == "FAULT" or apReadyMode == '1':
                                    self.logger.debug(u"ready to call basic msg handler")
                                    self.basicReadZoneMessage(rawData, msgBitMap, msgZoneNum,
                                                              msgText, msgKey, panelDevice)

                elif rawData[1:9] == u'SER2SOCK' or len(rawData) == 0:
                    # ignore system messages
                    self.logger.debug(u"SER2SOCK connection or null message - do nothing")
                    pass

                elif rawData[1:4] == 'LRR':   # panel state information  - mostly for events
                    self.logger.debug(u"Processing LRR Message:{}, logging option:{}".format(
                        rawData, self.plugin.logArmingEvents))
                    # EVENT DATA - Either the User Number who preformed the action or the zone that was bypassed.
                    # PARTITION - The panel partition the event applies to. 0 indicates all partitions such as ACLOSS event.
                    # EVENT TYPES - One of the following events. Note: the programming mode for enabling each type is also provided.
                    # eg. !LRR:002,1,OPEN

                    try:
                        self.logger.debug(u"Processing LRR Message:{}, logging option:{}".format(
                            rawData, self.plugin.logArmingEvents))
                        splitMsg = re.split('[!:,]', rawData)
                        user = splitMsg[2]
                        partition = splitMsg[3]
                        function = splitMsg[4]
                        function = function[0:-2]  # lose the newline

                        if function in kEventStateDict:
                            self.logger.debug(
                                u"LRR Decode - user:{}, partition:{}, function:{}".format(user, partition, function))
                            now = datetime.now()
                            timeStamp = now.strftime("%Y-%m-%d %H:%M:%S")

                            panelDevice = indigo.devices[self.plugin.panelsDict[foundKeypadAddress]['devId']]
                            # panelDevice = indigo.devices[self.plugin.partition2address[partition]['devId']]
                            panelDevice.updateStateOnServer(key='lastChgBy', value=user)
                            panelDevice.updateStateOnServer(key='lastChgTo', value=function)
                            panelDevice.updateStateOnServer(key='lastChgAt', value=timeStamp)
                            if self.plugin.logArmingEvents:
                                self.logger.info(
                                    u"Alarm partition {} set to {} caused/entered by {}".format(partition, function, user))

                            self.executeTrigger(partition, user, function)
                    except Exception as err:
                        self.logger.error(u"LRR Error:{}".format(str(err)))

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

        self.logger.info(u"AlarmDecoder message reading stopped")
        self.logger.debug(u"completed")

    ########################################
    # Get things rolling
    # TO DO: remove this - not called
    def old_startComm(self, ad2usbIsAdvanced, ad2usbCommType, ad2usbAddress, ad2usbPort, ad2usbSerialPort):
        self.logger.debug(u"called")
        self.logger.debug(u"isAdvanced:{}, commType:{}, address:{}, port:{}, serialPort:{}".format(
            ad2usbIsAdvanced, ad2usbCommType, ad2usbAddress, ad2usbPort, ad2usbSerialPort))

        self.logger.debug(u"Read alarm status dict:{}".format(self.plugin.ALARM_STATUS))
        self.logger.debug(u"Loading zonesDict")

        for zone in sorted(self.plugin.zonesDict):
            self.logger.debug(u"...Index:{}, Data:{}".format(zone, self.plugin.zonesDict[zone]))

        self.stopReadingMessages is False
        retryCount = 0
        # firstTry = True

        # TO DO: convert to use setURL and integrate with stop/start/restart
        while self.stopReadingMessages is False:

            # set the serial connection property - will open if needed
            if self.setSerialConnection():
                try:
                    if self.plugin.isPlaybackCommunicationModeSet:
                        # read a test/debug file of panel messages
                        # it doesn't matter what the connection object is so long as it exists
                        self.logger.info('In Playback debug mode - no connection created...')
                    else:
                        self.logger.info(u"connected to AlarmDecoder")

                    self.panelMsgRead(ad2usbIsAdvanced)
                    self.logger.info(u"returned from panelMessageRead")

                except Exception as err:
                    self.logger.error(u"Error in old_startComm shutdown loop - message:{}".format(str(err)))

            else:
                self.logger.error(u"Error setting serial connection...")
                # retry 3 times for 10 seconds (30 sec)
                # then 3 times for 30 seconds (total of 2 mins)
                # then 3 times for 5 minutes (total of 17 mins)
                # then 3 times for 30 minutes (total of 1 hour and 47 mins)
                retryCount += 1
                if retryCount <= 3:
                    sleepTime = 10
                    self.logger.warning(u"trying serial connection again in {} seconds...".format(sleepTime))
                    time.sleep(sleepTime)
                elif (retryCount > 3) and (retryCount <= 6):
                    sleepTime = 30
                    self.logger.warning(u"trying serial connection again in {} seconds...".format(sleepTime))
                    time.sleep(sleepTime)
                elif (retryCount > 6) and (retryCount <= 9):
                    sleepTime = 5
                    self.logger.error(u"trying serial connection again in {} minutes...".format(sleepTime))
                    time.sleep(sleepTime * 60)
                elif (retryCount > 9) and (retryCount <= 12):
                    sleepTime = 30
                    self.logger.error(u"trying serial connection again in {} minutes...".format(sleepTime))
                    time.sleep(sleepTime * 60)
                elif retryCount > 12:
                    self.logger.critical(
                        'Failed to connect to AlarmDecoder after several attempts. Check connection to AlarmDecoder')
                    self.stopReadingMessages = True

        self.logger.debug(u"completed")

    def newStartComm(self):
        """
        Initiates serial port open call and send C and V commands and read CONFIG and VER

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
            verReadSuccess = False
            configReadSuccess = False

            # try to open the serial connection
            # TO DO: put send and read of V and CONFIG into 2 methods
            if self.setSerialConnection():
                self.logger.info(u"AlarmDecoder communication started...")

                if self.sendAlarmDecoderVersionCommand():
                    # run a loop loking for VER message, max 10 times
                    maxReadLines = 10
                    ignoredMessageCount = 0
                    while (maxReadLines > 0):
                        messageString = self.panelReadWrapper(self.serialConnection)
                        # count down from 10 to 1
                        maxReadLines = maxReadLines - 1
                        # create an object
                        messageObject = AlarmDecoder.Message(messageString)
                        if messageObject.messageType == 'VER':
                            self.setFirmware(messageObject.firmwareVersion)
                            self.logger.info(u"AlarmDecoder firmware version is:{}".format(self.firmwareVersion))
                            verReadSuccess = True
                        else:
                            ignoredMessageCount += 1

                    self.logger.info("Ignored {} messages reading VER".format(ignoredMessageCount))

                if self.sendAlarmDecoderConfigCommand():
                    # run a loop loking for CONFIG message, max 10 times
                    maxReadLines = 10
                    ignoredMessageCount = 0
                    while (maxReadLines > 0):
                        messageString = self.panelReadWrapper(self.serialConnection)
                        # count down from 10 to 1
                        maxReadLines = maxReadLines - 1
                        # create an object
                        messageObject = AlarmDecoder.Message(messageString, self.firmwareVersion)
                        if messageObject.messageType == 'CONFIG':
                            configString = messageObject.getMessageAttribute('configMessageString')
                            self.processAlarmDecoderConfigString(configString)
                            self.logger.info(u"AlarmDecoder config string is:{}".format(configString))
                            self.logger.info(u"AlarmDecoder config settings are:{}".format(
                                self.plugin.configSettings))
                            configReadSuccess = True
                        else:
                            ignoredMessageCount += 1

                    self.logger.info("Ignored {} messages reading CONFIG".format(ignoredMessageCount))

            if verReadSuccess and configReadSuccess:
                self.logger.info(u"AlarmDecoder communication startup completed successfully")

                # TO DO: remove this? ported this log from old startComm
                for zone in sorted(self.plugin.zonesDict):
                    self.logger.debug(u"...Index:{}, Data:{}".format(zone, self.plugin.zonesDict[zone]))

                self.isCommStarted = True
                return True
            else:
                if not configReadSuccess:
                    self.logger.error(u"Unable to read AlarmDecoder CONFIG")
                if not verReadSuccess:
                    self.logger.error(u"Unable to read AlarmDecoder VERSION")

                self.isCommStarted = False
                return False

        except Exception as err:
            self.logger.error(u"Unable to open serial connection and read CONFIG and VER - error:{}".format(str(err)))
            self.isCommStarted = False
            return False

    ########################################
    def stopComm(self):
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

            # set a flag that we reset when CONFIG message is read
            self.plugin.hasAlarmDecoderConfigBeenRead = False

            # don't run if in playback mode
            if self.plugin.isPlaybackCommunicationModeSet:
                self.logger.debug(u'Panel Message Playback Set - cannot send AlarmDecoder CONFIG command')
                return False

            if (self.plugin.ad2usbCommType == 'IP') or (self.plugin.ad2usbCommType == 'USB'):

                self.logger.debug(u'attempting to get serial connection')
                if (self.setSerialConnection()) and (self.serialConnection is not None):
                    self.logger.debug(u"established connection to send CONFIG command")
                    # change the timeout for this command
                    self.serialConnection.timeout = 2

                    # send message to AlarmDecoder
                    configCommand = kADCommands['CONFIG']
                    self.logger.debug(u'attempting to send CONFIG command:{} to AlarmDecoder'.format(configCommand))
                    self.panelWriteWrapper(self.serialConnection, configCommand)
                    self.logger.debug(u'sent CONFIG command to AlarmDecoder')

                    # reset the timeout to None
                    self.serialConnection.timeout = None
                    self.logger.debug(u'reset timeout back to None')
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

            # open a new connection as the URL could have changed
            self.logger.debug(u'attempting to get serial connection...')
            if self.setSerialConnection():

                self.logger.debug(u'attempting to set new timeout...')
                self.serialConnection.timeout = 2
                self.logger.debug(u"new timeout set...")

                verCommand = kADCommands['VER']
                self.logger.debug(u'attempting to send VER command:{} to AlarmDecoder'.format(verCommand))
                self.panelWriteWrapper(self.serialConnection, verCommand)
                self.logger.debug(u"VER command sent...")

                self.serialConnection.timeout = None
                self.logger.debug(u"timeout reset to None...")

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
                        self.logger.debug('setting timeout...')
                        self.serialConnection.timeout = 2
                        if self.panelWriteWrapper(self.serialConnection, configString):
                            self.logger.debug(u'AlarmDecoder CONFIG written successfully')
                            self.logger.debug('resetting timeout...')
                            self.serialConnection.timeout = None
                            return True
                        else:
                            self.logger.error(u'AlarmDecoder CONFIG write failed')
                            self.logger.debug('resetting timeout...')
                            self.serialConnection.timeout = None
                            return False
                    else:
                        self.logger.warning(u'AlarmDecoder CONFIG settings to write was empty')
                        return True

                else:
                    self.logger.error(u'Unable to get serial connection to write AlarmDecoder CONFIG')
                    return False

            else:
                self.logger.debug(
                    u'commType is not IP or USB:{} - cannot write to AlarmDecoder - returning False'.format(self.plugin.ad2usbCommType))
                return False

        except Exception as err:
            self.logger.error(
                u"reading AlarmDecoder configuration failed: URL:{}, CONFIG string:{}, error:{}".format(self.getURL(), configString, str(err)))
            return False

    def processAlarmDecoderConfigString(self, configString):
        """
        parses a valid AlarmDecoder CONFIG string (from the device) and sets the keys and values
        of the plugin property 'configSettings' to the CONFIG string keys and values

        **parameter:**
        configString -- the CONFIG string from the AlarmDecoder
        """

        self.logger.debug(u"called with:{}".format(configString))

        try:
            # log the old settings
            self.logger.debug(u"prior configSettings were:{}".format(self.plugin.configSettings))

            # we only set new settings at end in case there is an error
            newConfigSettings = {}

            configItems = re.split('&', configString)

            for oneConfig in configItems:
                configParam = re.split('=', oneConfig)

                # skip parameters we don't manage
                if (configParam[0] == 'CONFIGBITS') or (configParam[0] == 'MASK') or (configParam[0] == 'MASK'):
                    pass
                else:
                    newConfigSettings[configParam[0]] = configParam[1]

            self.plugin.configSettings = {}
            self.plugin.configSettings = newConfigSettings.copy()
            self.logger.debug(u"updated configSettings are:{}".format(self.plugin.configSettings))

        except Exception as err:
            # no changes are made to configSettings dictionary
            self.logger.error('Error processing CONFIG string:{} - error:{}'.format(configString, str(err)))
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

                        # else process it
                        else:
                            # split on the "|" and strip the whitespace from the message part of the file
                            lineItems = re.split(r'\|', line)
                            playbackCurrentMessage = lineItems[1].strip()
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
        this is a wrapper to support Python 2 and 3 serial communications. Python 2 is a string. Python 3 is bytes and must be decoded.
        returns a string of the message read or empty string if there are any errors
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

                    self.logger.debug(u'attempting to write from the AlarmDecoder')
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

            # set a timeout to wait indefinitley on readline
            self.serialConnection.timeout = None

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
        Set the property of the firmware version supplied and logs to INFO if it changed.

        Returns True if changed; False otherwise
        """
        if firmwareVersion != self.firmwareVersion:
            self.firmwareVersion = firmwareVersion
            self.logger.info("AlarmDecoder Firmware Version is:{}".format(firmwareVersion))
            return True  # changed
        else:
            return False  # no change

    def __doesPlaybackFileExist(self):
        """
        Checks if Playback file exists.

        Returns True if exists; False otherwise.
        """
        if os.path.isfile(self.plugin.panelMessagePlaybackFilename):
            return True
        else:
            return False
