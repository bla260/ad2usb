#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# ad2usb Alarm Plugin
# Originally developed by Richard Perlman

import indigo  # Not really needed, but a specific import removes lint errors
from datetime import datetime
# import inspect
import re
import serial
import sys
import string
from string import atoi

kRespDecode = ['loop1', 'loop4', 'loop2', 'loop3', 'bit3', 'sup', 'bat', 'bit0']
kBin = ['0000', '0001', '0010', '0011', '0100', '0101', '0110', '0111', '1000',
                '1001', '1010', '1011', '1100', '1101', '1110', '1111']
kEventStateDict = ['OPEN', 'ARM_AWAY', 'ARM_STAY', 'ACLOSS', 'AC_RESTORE', 'LOWBAT',
                   'LOWBAT_RESTORE', 'RFLOWBAT', 'RFLOWBAT_RESTORE', 'TROUBLE',
                   'TROUBLE_RESTORE', 'ALARM_PANIC', 'ALARM_FIRE', 'ALARM_AUDIBLE',
                   'ALARM_SILENT', 'ALARM_ENTRY', 'ALARM_AUX', 'ALARM_PERIMETER', 'ALARM_TRIPPED']

################################################################################
# Globals
################################################################################


################################################################################
class ad2usb(object):
    ########################################
    def __init__(self, plugin):
        self.plugin = plugin

        # remove these lines with 1.6.2
        # self.log = self.plugin.log.log
        # self.logError = self.plugin.log.logError
        # self.logName = self.plugin.pluginDisplayName
        # self.errorLog = self.plugin.errorLog
        # self.debugLog = self.plugin.debugLog

        # use indigo built-in logger API as of 1.6.2
        self.logger = self.plugin.logger

        self.zoneListInit = False
        self.zoneStateDict = {}
        self.zoneBypassDict = {}
        self.lastApZonesBypassed = 0

        self.shutdown = False
        self.shutdownComplete = False

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
    def eventQueueManager(self, partition, user, event):
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
            if len(address) == 0:
                self.plugin.conn.write(panelMsg)
            else:
                if len(address) == 1:
                    address = "0" + address
                panelMsg = 'K' + address + str(panelMsg)
                self.plugin.conn.write(panelMsg)
                self.logger.info(u"sent panel message:{}".format(panelMsg))
        except Exception as err:
            self.logger.error(u"unable to write panel message:{}".format(panelMsg))
            self.logger.error(u"error message:{}, {}".format(str(err), sys.exc_info()[0]))

        self.logger.debug(u"completed")

    ########################################
    # Wireless zone state decode function for advanced mode
    def decodeState(self, zState):
        self.logger.debug(u"called with:{}".format(zState))

        zoneState = ''
        returnDict = {}

        for i in range(len(zState)):
            zoneState += kBin[atoi(zState[i], base=16)]

        for i in range(7, -1, -1):
            decodeVal = False
            if zoneState[i] == '1':
                decodeVal = True

            returnDict[kRespDecode[i]] = decodeVal

        self.logger.debug(u"returned:{}".format(returnDict))
        return returnDict

        self.logger.debug(u"completed")

    ########################################
    # Update zone groups, if we have any
    def updateZoneGroups(self, zoneIndex, zoneState):
        # TO DO:
        # New logic
        # loop thru Zone Group devices
        # if Zone Group contains the zone passed to this method
        #   get all zones for this zone group and their state as a dict
        #   set the dictionary value of this zone to the new zone state
        #   if any zones in the dict are faulted the Zone Group is faulted
        #   if none of the zones in the dict are faulted the Zone Group is clear

        self.logger.debug(u"called with zoneIndex:{}, zoneState:{}".format(zoneIndex, zoneState))

        if zoneIndex not in self.plugin.zone2zoneGroupDevDict:
            self.logger.debug(
                u"zoneIndex:{} not in a zoneGroup. No updates to any ZoneGroup is required.".format(zoneIndex))
            return

        # mark the Zone Group not faulted until we find any zone that is faulted
        isFaulted = False

        self.logger.debug(u"zoneIndex:{} is in these Zone Groups:{}".format(
            zoneIndex, self.plugin.zone2zoneGroupDevDict[zoneIndex]))
        # iterate thru all Zone Group devices
        for zoneGroupDev in self.plugin.zone2zoneGroupDevDict[zoneIndex]:
            # get the device object and its state: zoneState (faulted or Clear)
            groupZoneDevice = indigo.devices[int(zoneGroupDev)]
            groupState = groupZoneDevice.states['zoneState']
            self.logger.debug(u"Zone Group:{}, current displayState:{}".format(zoneGroupDev, groupState))

            self.logger.debug(u"Details of Zone Group - zoneGroupDev:{}".format(zoneGroupDev))
            self.logger.debug(u"BEFORE... zoneGroupDev:{}".format(self.plugin.zoneGroup2zoneDict[zoneGroupDev]))
            self.plugin.zoneGroup2zoneDict[zoneGroupDev][zoneIndex] = zoneState
            self.logger.debug(u"AFTER... zoneGroupDev:{}".format(self.plugin.zoneGroup2zoneDict[zoneGroupDev]))

            # iterate thru all the zones in the Zone Group
            for zone in self.plugin.zoneGroup2zoneDict[zoneGroupDev]:
                self.logger.debug(u"DETAIL... zone:{}, zoneGroupDev:{}".format(
                    zone, self.plugin.zoneGroup2zoneDict[zoneGroupDev][zone]))
                if self.plugin.zoneGroup2zoneDict[zoneGroupDev][zone] == 'Faulted':
                    isFaulted = True
                    break

            # currentState = groupZoneDevice.states.['displayState.ui']

            # if the Zone Group should be faulted and isn't...
            newGroupState = groupState
            if isFaulted and (groupState != 'faulted'):
                groupZoneDevice.updateStateOnServer(key='zoneState', value='faulted')
                groupZoneDevice.updateStateOnServer(key='displayState', value='faulted', uiValue=u'Fault')
                groupZoneDevice.updateStateOnServer(key='onOffState', value=True)
                newGroupState = 'faulted'
            else:  # We don't check on the current state, since all grouped zones must be clear if we got to this point
                groupZoneDevice.updateStateOnServer(key='zoneState', value='Clear')
                groupZoneDevice.updateStateOnServer(key='displayState', value='enabled', uiValue=u'Clear')
                groupZoneDevice.updateStateOnServer(key='onOffState', value=False)
                newGroupState = 'Clear'

            if groupState != newGroupState:
                if groupZoneDevice.pluginProps[u'zoneLogChanges']:
                    self.logger.info(u"Zone Group:{}, state changed from:{} to:{}".format(
                        groupZoneDevice.name, groupState, newGroupState))
                else:
                    self.logger.debug(u"Zone Group:{}, state changed from:{} to:{}".format(
                        groupZoneDevice.name, groupState, newGroupState))

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
                        indigoDevice.updateStateOnServer(key='zoneState', value='faulted')
                        indigoDevice.updateStateOnServer(key='onOffState', value=True)
                        indigoDevice.updateStateOnServer(key='displayState', value='faulted', uiValue=u'Fault')

                        # Maintain the zone fault state
                        self.zoneStateDict[panelKeypadAddress].append(int(zNumber))
                        self.zoneStateDict[panelKeypadAddress].sort()
                        panelDevice.updateStateOnServer(key='zoneFaultList', value=str(
                            self.zoneStateDict[panelKeypadAddress]))

                        stateMsg = 'Faulted'
                    elif zoneState == zoneOff:
                        self.logger.debug(u"zoneOff zoneNumber:{}, and States list:{}".format(
                            zNumber, self.zoneStateDict))
                        indigoDevice.updateStateOnServer(key='zoneState', value='Clear')
                        indigoDevice.updateStateOnServer(key='onOffState', value=False)
                        indigoDevice.updateStateOnServer(key='displayState', value='enabled', uiValue=u'Clear')

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
                        indigoDevice.updateStateOnServer(key='zoneState', value='faulted')
                        indigoDevice.updateStateOnServer(key='onOffState', value=True, uiValue=u'Fault')
                        indigoDevice.updateStateOnServer(key='displayState', value='faulted', uiValue=u'Fault')

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
                        indigoDevice.updateStateOnServer(key='zoneState', value='Clear')
                        indigoDevice.updateStateOnServer(key='onOffState', value=False, uiValue=u'Clear')
                        indigoDevice.updateStateOnServer(key='displayState', value='enabled', uiValue=u'Clear')

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
                        self.updateZoneGroups(zNumber, stateMsg)
                except Exception as err:
                    self.logger.error(u"updateZoneGroups Error:{}".format(str(err)))

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

        if zoneState == 'faulted':
            uiValue = 'Fault'
            displayStateValue = 'faulted'
            onOffStateValue = True
            self.zoneStateDict[panelKeypadAddress].append(int(zoneIndex))
            self.zoneStateDict[panelKeypadAddress].sort()
            self.logger.debug(u"faulted... state list:{}".format(self.zoneStateDict))
        else:
            uiValue = 'Clear'
            displayStateValue = 'enabled'
            onOffStateValue = False
            self.zoneStateDict[panelKeypadAddress].remove(int(zoneIndex))
            self.logger.debug(u"clear... State list:{}".format(self.zoneStateDict))

        indigoDevice.updateStateOnServer(key='zoneState', value=zoneState, uiValue=uiValue)
        indigoDevice.updateStateOnServer(key='displayState', value=displayStateValue, uiValue=uiValue)
        indigoDevice.updateStateOnServer(key='onOffState', value=onOffStateValue)
        panelDevice.updateStateOnServer(key='zoneFaultList', value=str(self.zoneStateDict[panelKeypadAddress]))

        if zoneState == 'faulted':
            zoneState = 'Faulted'

        try:
            self.updateZoneGroups(str(zoneIndex), zoneState)
        except Exception as err:
            self.logger.error(u"updateZoneGroups Error:{}".format(str(err)))

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

                self.updateIndigoBasicMode(zoneIndex, 'faulted', panelDevice)

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

                self.updateIndigoBasicMode(zoneIndex, 'Clear', panelDevice)

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

                self.updateIndigoBasicMode(zoneIndex, 'Clear', panelDevice)

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
        while self.shutdown is False:
            rawData = ""
            try:
                while len(rawData) == 0 and self.shutdown is False:
                    rawData = self.plugin.conn.readline()
                    if rawData == '':
                        if self.shutdown is False:
                            self.logger.error(u"AD2USB Connection Error")
                        return  # exit()
            except Exception as err:
                if self.shutdown is True:
                    self.logger.info(u"Connection Closed:")
                    self.shutdownComplete = True
                else:
                    self.logger.critical(u"Connection Error:{}".format(str(err)))
                exit()
            except:
                self.logger.critical(u"Connection Problem, plugin quitting")
                exit()

            self.logger.debug(u"Read ad2usb message:{}".format(repr(rawData)))

            # write the message to the panel log too if panel logging is enabled
            if self.plugin.isPanelLoggingEnabled:
                self.plugin.panelLogger.info(u"{}".format(rawData.rstrip()))

            # Start by checking if this message is "Press * for faults"
            try:
                if len(rawData) > 0 and rawData[0] == "[":  # A valid panel message
                    self.logger.debug(u"raw zone type is:{}".format(rawData[0:4]))

                    # First split the message into parts and see if we need to send a * to get the faults
                    splitMsg = re.split('[\[\],]', rawData)
                    msgText = splitMsg[7]
                    if string.find(msgText, ' * ') >= 0:
                        self.logger.debug(u"Received a Press * message:{}".format(rawData))
                        self.plugin.conn.write('*')
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
                            self.logger.debug(u"Panel Message: Before:{}, Current:{}".format(rawData, lastPanelMsg))
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

                                        self.eventQueueManager(partition, user, function)
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
                                    for zone in self.zoneBypassDict:
                                        bZoneData = self.plugin.zonesDict[int(zone)]
                                        bZDevid = bZoneData['devId']
                                        bIndigoDevice = indigo.devices[bZDevid]
                                        bIndigoDevice.updateStateOnServer(key='bypassState', value=False)
                                        bIndigoDevice.updateStateOnServer(
                                            key='displayState', value="enabled", uiValue="Clear")
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
                                    self.zoneBypassDict[bMsgZoneNum] = {True}
                                    self.logger.info(
                                        u"Alarm zone number:{}, name:{} has been bypassed".format(bMsgZoneNum, zName))
                                    self.lastApZonesBypassed = apZonesBypassed
                                    indigoDevice.updateStateOnServer(key='bypassState', value=True)
                                    indigoDevice.updateStateOnServer(
                                        key='displayState', value="bypass", uiValue="bypass")
                                    # indigoDevice.setErrorStateOnServer(u'bypass')

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

                            self.eventQueueManager(partition, user, function)
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

        self.client_socket.close()
        self.logger.debug(u"completed")

   ########################################
   # Get things rolling
    def startComm(self, ad2usbIsAdvanced, ad2usbCommType, ad2usbAddress, ad2usbPort, ad2usbSerialPort):
        self.logger.debug(u"called")
        self.logger.debug(u"isAdvanced:{}, commType:{}, address:{}, port:{}, serialPort:{}".format(
            ad2usbIsAdvanced, ad2usbCommType, ad2usbAddress, ad2usbPort, ad2usbSerialPort))

        self.logger.debug(u"Read alarm status dict:{}".format(self.plugin.ALARM_STATUS))
        self.logger.debug(u"Loading zonesDict")

        for zone in sorted(self.plugin.zonesDict):
            self.logger.debug(u"...Index:{}, Data:{}".format(zone, self.plugin.zonesDict[zone]))

        self.shutdown is False
        lostConnCount = 0
        # firstTry = True

        while self.shutdown is False:
            if ad2usbCommType == 'IP':
                HOST = ad2usbAddress
                PORT = ad2usbPort
                theURL = 'socket://' + HOST + ':' + PORT
                self.logger.debug(u"the url is:{}".format(theURL))
            else:
                theURL = ad2usbSerialPort
                self.logger.debug(u"the serial port is:{}".format(theURL))

            try:
                self.logger.info(u"attempting to connect to:{}".format(theURL))
                self.plugin.conn = serial.serial_for_url(theURL, baudrate=115200)
                self.plugin.conn.timeout = None
                lostConnCount = 0
                self.plugin.serialOpen = True

                self.logger.info(u"connected to AlarmDecoder")
                self.panelMsgRead(ad2usbIsAdvanced)

                self.logger.info(u"returned from panelMessageRead")

            except Exception as err:
                self.logger.error(u"could not connect to AlarmDecoder at:{}".format(theURL))
                self.logger.error(u"error message:{}".format(str(err)))

            if not self.shutdown:
                lostConnCount += 1
                if lostConnCount < 3:
                    retryTime = 10
                    retryText = '10 seconds'
                elif lostConnCount < 13:
                    retryTime = 30
                    retryText = '30 seconds'
                elif lostConnCount < 23:
                    retryTime = 300
                    retryText = '5 minutes'
                else:
                    retryTime = 1800
                    retryText = '30 minutes'

                self.logger.error(u"failed connection to:{}".format(theURL))
                self.logger.error(u"will retry in:{}".format(retryText))

                retryTime = retryTime * 2  # check every 0.5 seconds
                while retryTime > 0 and not self.shutdown:
                    self.plugin.sleep(0.5)
                    retryTime -= 1

        self.logger.debug(u"completed")

   ########################################
    def stopComm(self):
        self.logger.debug(u"Called")
        self.shutdown = True

        if self.shutdownComplete is False:
            try:
                self.logger.info(u"attempting to close connection...")
                self.plugin.conn.close()
                self.logger.info(u"connection closed")
            except Exception as err:
                self.logger.error(u"Error while closing connection on line {}".format(sys.exc_info()[-1].tb_lineno))
                self.logger.error(u"Error:{}".format(str(err)))
