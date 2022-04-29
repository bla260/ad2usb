#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# ad2usb Alarm Plugin
# Developed and copyright by Richard Perlman -- indigo AT perlman DOT com

import indigo  # Not really needed, but a specific import removes lint errors
from datetime import datetime
import inspect
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

        self.log = self.plugin.log.log
        self.logError = self.plugin.log.logError
        self.logName = self.plugin.pluginDisplayName

        self.errorLog = self.plugin.errorLog
        self.debugLog = self.plugin.debugLog
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
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log(2, dbFlg, "%s Called" % (funcName), self.logName)

        bits = ''
        for i in range(len(s)):
            bits += kBin[int(s[i], base=16)]

        self.log(3, dbFlg, "%s: Keypad address bit map:%s" % (funcName, bits), self.logName)
        return bits

    ########################################
    # Event queue management and trigger initiation
    def eventQueueManager(self, partition, user, event):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log(2, dbFlg, "%s Called" % (funcName), self.logName)
        self.log(3, dbFlg, "%s: Received: partition:%s, user:%s, event:%s" %
                 (funcName, partition, user, event), self.logName)

        if event in self.plugin.triggerDict:
            self.log(3, dbFlg, "%s: Found event trigger:%s" % (funcName, self.plugin.triggerDict[event]), self.logName)
            try:
                if self.plugin.triggerDict[event][partition]:
                    # We have a winner
                    indigo.trigger.execute(int(self.plugin.triggerDict[event][partition]))
                    self.log(3, dbFlg, "%s: Matched event trigger:%s" %
                             (funcName, self.plugin.triggerDict[event][partition]), self.logName)
            except:
                pass
        if isinstance(user, int):
            user = str(int(user))  # get rid of the leading zeroes
            if user in self.plugin.triggerDict:
                self.log(3, dbFlg, "%s: Found user trigger:%s" %
                         (funcName, self.plugin.triggerDict[user]), self.logName)
                try:
                    if self.plugin.triggerDict[user][partition]:
                        if self.plugin.triggerDict[user][partition]['event'] == event:
                            # We have a winner
                            indigo.trigger.execute(int(self.plugin.triggerDict[user][partition]['tid']))
                            self.log(3, dbFlg, "%s: Matched user trigger:%s" %
                                     (funcName, self.plugin.triggerDict[user][partition]), self.logName)
                except:
                    pass

        self.log(2, dbFlg, "%s Completed" % (funcName), self.logName)

    ########################################
    # Write arbitrary messages to the panel
    def panelMsgWrite(self, panelMsg, address=''):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log(2, dbFlg, "%s Called" % (funcName), self.logName)
        self.log(3, dbFlg, "%s: Received msg:%s for address:%s" % (funcName, panelMsg, address), self.logName)

        try:
            if len(address) == 0:
                self.plugin.conn.write(panelMsg)
            else:
                if len(address) == 1:
                    address = "0" + address
                panelMsg = 'K' + address + str(panelMsg)
                self.plugin.conn.write(panelMsg)
        except Exception as err:
            self.logError("%s: Unable to write panel message:%s" % (funcName, panelMsg), self.logName)
            self.logError("%s: The error message was: %s, %s" % (funcName, str(err), sys.exc_info()[0]), self.logName)

        self.log(2, dbFlg, "%s Completed" % (funcName), self.logName)

    ########################################
    # Wireless zone state decode function for advanced mode
    def decodeState(self, zState):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log(2, dbFlg, "%s Called" % (funcName), self.logName)
        self.log(3, dbFlg, "%s: Received:%s" % (funcName, zState), self.logName)

        zoneState = ''
        returnDict = {}

        for i in range(len(zState)):
            zoneState += kBin[atoi(zState[i], base=16)]

        for i in range(7, -1, -1):
            decodeVal = False
            if zoneState[i] == '1':
                decodeVal = True

            returnDict[kRespDecode[i]] = decodeVal

        self.log(3, dbFlg, "%s: Returned:%s" % (funcName, returnDict), self.logName)

        return returnDict

    ########################################
    # Update zone groups, if we have any
    def updateZoneGroups(self, zoneIndex, zoneState):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log(2, dbFlg, "%s Called" % (funcName), self.logName)
        self.log(3, dbFlg, "%s: Received zoneIndex:%s, zoneState:%s" % (funcName, zoneIndex, zoneState), self.logName)

        if zoneIndex not in self.plugin.zone2zoneGroupDevDict:
            self.log(2, dbFlg, "%s: zoneIndex not in a zoneGroup" % (funcName), self.logName)
            return

        isFaulted = False

        self.log(2, dbFlg, "%s: zoneIndex:%s contains:%s" %
                 (funcName, zoneIndex, self.plugin.zone2zoneGroupDevDict[zoneIndex]), self.logName)
        for zoneGroupDev in self.plugin.zone2zoneGroupDevDict[zoneIndex]:
            groupZoneDevice = indigo.devices[int(zoneGroupDev)]
            groupState = groupZoneDevice.states['zoneState']
            self.log(3, dbFlg, "%s: zoneGroupDev:%s" % (funcName, zoneGroupDev), self.logName)
            self.log(3, dbFlg, "%s: BEFORE... zoneGroupDev:%s" %
                     (funcName, self.plugin.zoneGroup2zoneDict[zoneGroupDev]), self.logName)
            self.plugin.zoneGroup2zoneDict[zoneGroupDev][zoneIndex] = zoneState
            self.log(3, dbFlg, "%s: AFTER... zoneGroupDev:%s" %
                     (funcName, self.plugin.zoneGroup2zoneDict[zoneGroupDev]), self.logName)
            for zone in self.plugin.zoneGroup2zoneDict[zoneGroupDev]:
                self.log(2, dbFlg, "%s: DETAIL... zone:%s, zoneGroupDev:%s" %
                         (funcName, zone, self.plugin.zoneGroup2zoneDict[zoneGroupDev][zone]), self.logName)
                if self.plugin.zoneGroup2zoneDict[zoneGroupDev][zone] == 'Faulted':
                    isFaulted = True
                    break

            currentState = groupZoneDevice.states['displayState.ui']

            if isFaulted and currentState != 'Fault':
                groupZoneDevice.updateStateOnServer(key='zoneState', value='faulted')
                groupZoneDevice.updateStateOnServer(key='displayState', value='faulted', uiValue=u'Fault')
                groupZoneDevice.updateStateOnServer(key='onOffState', value=True)
                stateMsg = 'Faulted'
            else:  # We don't check on the current state, since all grouped zones must be clear if we got to this point
                groupZoneDevice.updateStateOnServer(key='zoneState', value='Clear')
                groupZoneDevice.updateStateOnServer(key='displayState', value='enabled', uiValue=u'Clear')
                groupZoneDevice.updateStateOnServer(key='onOffState', value=False)
                stateMsg = 'Clear'

            if groupZoneDevice.pluginProps[u'zoneLogChanges']:
                if groupState != stateMsg:
                    self.log(0, dbFlg, "Zone Group: %s, state changed to: (%s)" %
                             (groupZoneDevice.name, stateMsg), self.logName)

        self.log(2, dbFlg, "Zone Group: %s, state was:%s, and now is: (%s)" %
                 (groupZoneDevice.name, zoneState, stateMsg), self.logName)
        self.log(2, dbFlg, "%s Completed" % (funcName), self.logName)

    ########################################
    # Read the zone messages in advanced mode
    def advancedReadZoneMessage(self, rawData):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log(2, dbFlg, "%s Called" % (funcName), self.logName)
        self.log(3, dbFlg, "%s: Received:%s:" % (funcName, rawData), self.logName)

        validDev = False
        supervisionMessage = False

        if not self.zoneListInit:
            for address in self.plugin.panelsDict:
                self.zoneStateDict[address] = []
            self.zoneListInit = True

        if rawData[1:4] == 'REL' or rawData[1:4] == 'EXP' or rawData[1:4] == 'RFX':   # a relay, expander module or RF zone event
            splitMsg = re.split('[!:,]', rawData)
            zoneDevType = splitMsg[1]
            self.log(3, dbFlg, "%s: Zone type is:%s" % (funcName, zoneDevType), self.logName)

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
                self.log(3, dbFlg, "%s: Zone index is:%s" % (funcName, zoneIndex), self.logName)
            # For RF zones the index in the device's unique serial number
            else:
                zoneIndex = splitMsg[2]
                zoneState = splitMsg[3][0:2]  # Lose the \r

            try:    # Lookup the zoneIndex in the zone device dictionary
                # and setup some variables to process the zone data
                zoneData = self.plugin.advZonesDict[zoneIndex]
                self.log(3, dbFlg, "%s: Read zoneData:%s" % (funcName, zoneData), self.logName)
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

                self.log(3, dbFlg, "%s: Found zone info: zType=%s, zDevId=%s, zBoard=%s, zDevice=%s, zNumber=%s, zLastState=%s, zName=%s, zPartition=%s." % (
                    funcName, zType, zDevId, zBoard, zDevice, zNumber, zLastState, zName, zPartition), self.logName)
                self.log(3, dbFlg, "%s: found panel info: DB%s, dev=%s" %
                         (funcName, self.plugin.partition2address[zPartition], panelDevice), self.logName)

                self.log(3, dbFlg, "%s: Indigo Device found:%s" % (funcName, zName), self.logName)
                validDev = True

            except Exception as err:  # An unrecognized device
                if self.plugin.logUnknownDevices:
                    self.logError("%s: Error:%s\nMessage from unrecognized Zone device: %s" %
                                  (funcName, err, rawData), self.logName)

            # We'll start with RELay & EXPander Zones since they are treated alike
            if validDev:
                if zType == 'REL' or zType == 'EXP':  # For Relay (on-board) and Expander zones
                    self.log(3, dbFlg, "%s: Ready to update Indigo REL & EXP" % (funcName), self.logName)
                    if zoneState == zoneOn:
                        self.log(3, dbFlg, "%s: zoneOn zoneNumber:%s, and States list:%s" %
                                 (funcName, zNumber, self.zoneStateDict), self.logName)
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
                        self.log(3, dbFlg, "%s: zoneOff zoneNumber:%s, and States list:%s" %
                                 (funcName, zNumber, self.zoneStateDict), self.logName)
                        indigoDevice.updateStateOnServer(key='zoneState', value='Clear')
                        indigoDevice.updateStateOnServer(key='onOffState', value=False)
                        indigoDevice.updateStateOnServer(key='displayState', value='enabled', uiValue=u'Clear')

                        # Maintain the zone fault state
                        try:
                            self.zoneStateDict[panelKeypadAddress].remove(int(zNumber))
                        except:
                            self.logError("%s: Unable to update state table for zone %s, address %s." %
                                          (funcName, zNumber, panelKeypadAddress), self.logName)
                        panelDevice.updateStateOnServer(key='zoneFaultList', value=str(
                            self.zoneStateDict[panelKeypadAddress]))

                        stateMsg = 'Clear'
                    else:
                        self.logError("%s: Zone %s %s has an UNKNOWN ZONE STATE: %s" %
                                      (funcName, zNumber, zName, rawData), self.logName)

                elif zType == 'RFX':  # for RF zones
                    self.log(3, dbFlg, "%s: Ready to update Indigo RFX (Wireless)" % (funcName), self.logName)

                    wirelessLoop = 'loop' + str(int(zDevice))  # remove any leading zeros
                    zoneStateDict = self.decodeState(zoneState)
                    if indigoDevice.pluginProps['zoneInvertSense']:
                        if zoneStateDict[wirelessLoop]:
                            zoneStateDict[wirelessLoop] = False
                        elif not zoneStateDict[wirelessLoop]:
                            zoneStateDict[wirelessLoop] = True
                        else:
                            self.logError("%s: State: %s not found in %s" %
                                          (funcName, zoneState, self.plugin.advZonesDict[zoneIndex]), self.logName)

                    if zoneStateDict[wirelessLoop]:
                        self.log(3, dbFlg, "%s: zoneOn zoneNumber:%s, and States list:%s" %
                                 (funcName, zNumber, self.zoneStateDict), self.logName)
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
                        self.log(3, dbFlg, "%s: zoneOff zoneNumber:%s, and States list:%s" %
                                 (funcName, zNumber, self.zoneStateDict), self.logName)
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
                        self.logError("%s: State: %s not found in %s" %
                                      (funcName, zoneState, self.plugin.advZonesDict[zoneIndex]), self.logName)

                    if zoneStateDict['sup']:
                        supervisionMessage = True
                        if zLogSupervision:  # make sure we want this logged
                            self.log(0, dbFlg, "Zone: %s supervision received. (%s)" %
                                     (zName, rawData[1:-2]), self.logName)
                            # Add update here to save last supervised to zone states

                else:  # An unrecognized message type
                    self.logError("%s: Unrecognized message type for received data: %s" %
                                  (funcName, rawData), self.logName)

                # If we are supposed to log zone changes, this is where we do it (unless this was a supervision message)
                if zLogChanges and not supervisionMessage:
                    self.log(3, dbFlg, "Zone: %s - %s state changed to: (%s)" %
                             (zNumber, zName, stateMsg), self.logName)

                try:
                    if not supervisionMessage:
                        self.updateZoneGroups(zNumber, stateMsg)
                except Exception as err:
                    self.logError("%s: updateZoneGroups Error: %s" % (funcName, str(err)), self.logName)

        else:
            if rawData[0:8] != '!setting' and rawData[0:7] != '!CONFIG' and rawData[0:2] != '!>' and rawData[0:4] != '!KPE' and rawData[0:8] != '!Sending':
                self.logError("%s: Unknown message received:%s" % (funcName, rawData), self.logName)

        self.log(2, dbFlg, "%s Completed" % (funcName), self.logName)

    ########################################
    # update Indigo on device state changes
    def updateIndigoBasicMode(self, zoneIndex, zoneState, panelDevice):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log(2, dbFlg, "%s Called" % (funcName), self.logName)
        self.log(3, dbFlg, "%s: Received index:%s, state:%s" % (funcName, zoneIndex, zoneState), self.logName)
        self.log(3, dbFlg, "%s: Zone index is:%s" % (funcName, zoneIndex), self.logName)

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
        self.log(3, dbFlg, "%s: Got address:%s" % (funcName, panelKeypadAddress), self.logName)

        if zoneState == 'faulted':
            uiValue = 'Fault'
            displayStateValue = 'faulted'
            onOffStateValue = True
            self.zoneStateDict[panelKeypadAddress].append(int(zoneIndex))
            self.zoneStateDict[panelKeypadAddress].sort()
            self.log(3, dbFlg, "%s: Faulted... State list:%s" % (funcName, self.zoneStateDict), self.logName)
        else:
            uiValue = 'Clear'
            displayStateValue = 'enabled'
            onOffStateValue = False
            self.zoneStateDict[panelKeypadAddress].remove(int(zoneIndex))
            self.log(3, dbFlg, "%s: Clear... State list:%s" % (funcName, self.zoneStateDict), self.logName)

        indigoDevice.updateStateOnServer(key='zoneState', value=zoneState, uiValue=uiValue)
        indigoDevice.updateStateOnServer(key='displayState', value=displayStateValue, uiValue=uiValue)
        indigoDevice.updateStateOnServer(key='onOffState', value=onOffStateValue)
        panelDevice.updateStateOnServer(key='zoneFaultList', value=str(self.zoneStateDict[panelKeypadAddress]))

        if zoneState == 'faulted':
            zoneState = 'Faulted'

        try:
            self.updateZoneGroups(str(zoneIndex), zoneState)
        except Exception as err:
            self.logError("%s: updateZoneGroups Error: %s" % (funcName, str(err)), self.logName)

        # If we are supposed to log zone changes, this is where we do it (unless this was a supervision message)
        if zLogChanges:
            self.log(0, dbFlg, "Zone: %s - %s state changed to: (%s)" % (zoneIndex, zName, zoneState), self.logName)

    ########################################
    # Read the zone messages in basic mode
    # Special thanks to Sean Mathews of Nu Tech Software Solutions
    # (and the developer of the ad2usb) for this great algorithm for
    # tracking zone states without zone restore messages or timers.

    def basicReadZoneMessage(self, rawData, msgBitMap, msgZoneNum, msgText, msgKey, panelDevice):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log(2, dbFlg, "%s Called" % (funcName), self.logName)
        self.log(3, dbFlg, "%s: Received rawData:%s, msgBitMap:%s, msgZoneNum:%s, msgText:%s, msgKey:%s" %
                 (funcName, rawData, msgBitMap, msgZoneNum, msgText, msgKey), self.logName)

        systemReady = False
        if msgBitMap[0] == '1':
            systemReady = True

        zoneFault = False
        if msgKey == 'FAULT':
            zoneFault = True

        self.log(3, dbFlg, "%s: Ready:%s, Fault:%s" % (funcName, systemReady, zoneFault), self.logName)

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
                self.log(3, dbFlg, "%s: Found zone: %d in the list at pos: %d" %
                         (funcName, msgZoneNum, newZonePos), self.logName)

            except:
                # If it failed, we need to insert the zone into the list
                # and sort the list
                self.plugin.faultList.append(msgZoneNum)
                self.plugin.faultList.sort()
                newZonePos = self.plugin.faultList.index(msgZoneNum)

                zoneIndex = msgZoneNum

                self.updateIndigoBasicMode(zoneIndex, 'faulted', panelDevice)

                self.log(3, dbFlg, "%s: Created new in the list, zone: %d at pos: %d" %
                         (funcName, msgZoneNum, newZonePos), self.logName)

            # Now that we are sure the zone is in the list, we can continue
            # Find the position of the last zone
            try:
                oldZonePos = self.plugin.faultList.index(self.plugin.lastZoneFaulted)
            except:
                oldZonePos = 0

            self.log(3, dbFlg, "%s: Last zone: %s, pos in the list: %d" %
                     (funcName, self.plugin.lastZoneFaulted, oldZonePos), self.logName)

            if msgZoneNum == self.plugin.lastZoneFaulted:
                for zoneCheck in range(newZonePos + 1, len(self.plugin.faultList)):
                    removeList.append(self.plugin.faultList[zoneCheck])
                    self.log(3, dbFlg, "%s: a) ZoneCheck: %d, pos %d" %
                             (funcName, self.plugin.faultList[zoneCheck], zoneCheck), self.logName)
                for zoneCheck in range(0, newZonePos):
                    removeList.append(self.plugin.faultList[zoneCheck])
                    self.log(3, dbFlg, "%s: b) ZoneCheck: %d, pos %d" %
                             (funcName, self.plugin.faultList[zoneCheck], zoneCheck), self.logName)
            elif msgZoneNum > self.plugin.lastZoneFaulted:
                for zoneCheck in range(oldZonePos + 1, newZonePos):
                    removeList.append(self.plugin.faultList[zoneCheck])
                    self.log(3, dbFlg, "%s: c) ZoneCheck: %d, pos %d" %
                             (funcName, self.plugin.faultList[zoneCheck], zoneCheck), self.logName)
            elif msgZoneNum < self.plugin.lastZoneFaulted:
                for zoneCheck in range(oldZonePos + 1, len(self.plugin.faultList)):
                    removeList.append(self.plugin.faultList[zoneCheck])
                    self.log(3, dbFlg, "%s: d) ZoneCheck: %d, pos %d" %
                             (funcName, self.plugin.faultList[zoneCheck], zoneCheck), self.logName)
                for zoneCheck in range(0, newZonePos):   # Changed to end at new pos instead of new pos -1
                    removeList.append(self.plugin.faultList[zoneCheck])
                    self.log(3, dbFlg, "%s: e) ZoneCheck: %d, pos %d" %
                             (funcName, self.plugin.faultList[zoneCheck], zoneCheck), self.logName)

            removeList = sorted(removeList, reverse=True)

            for clearZone in removeList:
                remZonePos = self.plugin.faultList.index(clearZone)
                self.log(3, dbFlg, "%s: Deleting zone:%d, at pos:%d" %
                         (funcName, self.plugin.faultList[remZonePos], remZonePos), self.logName)

                zoneIndex = self.plugin.faultList[remZonePos]

                self.updateIndigoBasicMode(zoneIndex, 'Clear', panelDevice)

                del self.plugin.faultList[remZonePos]

            self.plugin.lastZoneFaulted = msgZoneNum
        else:  # systemReady is true
            self.log(3, dbFlg, "%s: %d zones cleared. List was: %s" %
                     (funcName, len(self.plugin.faultList), self.plugin.faultList), self.logName)

            while len(self.plugin.faultList) > 0:
                remZonePos = len(self.plugin.faultList) - 1

                self.log(3, dbFlg, "%s: Deleting zone:%d, at pos:%d" %
                         (funcName, self.plugin.faultList[remZonePos], remZonePos), self.logName)
                self.log(3, dbFlg, "%s: Deleting position:%d" % (funcName, remZonePos), self.logName)

                zoneIndex = self.plugin.faultList[remZonePos]

                self.updateIndigoBasicMode(zoneIndex, 'Clear', panelDevice)

                del self.plugin.faultList[remZonePos]

        self.log(3, dbFlg, "%s: Ready: %s, Fault:%s, Zone:%d --" %
                 (funcName, systemReady, zoneFault, msgZoneNum), self.logName)
        self.log(3, dbFlg, "%s: The List:%s" % (funcName, self.plugin.faultList), self.logName)

        self.log(2, dbFlg, "%s Completed" % (funcName), self.logName)

    ########################################
    # Read the panel message stream
    #
    def panelMsgRead(self, ad2usbIsAdvanced):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log(2, dbFlg, "%s Called" % (funcName), self.logName)
        self.log(3, dbFlg, "%s: isAdvanced:%s" % (funcName, ad2usbIsAdvanced), self.logName)

        lastPanelMsg = ""
        while self.shutdown is False:
            rawData = ""
            try:
                while len(rawData) == 0 and self.shutdown is False:
                    rawData = self.plugin.conn.readline()
                    if rawData == '':
                        if self.shutdown is False:
                            self.logError("%s: AD2USB Connection Error" % (funcName), self.logName)
                        return  # exit()
            except Exception as err:
                if self.shutdown is True:
                    self.log(0, dbFlg, "%s: Connection Closed:" % (funcName), self.logName)
                    self.shutdownComplete = True
                else:
                    ("%s: Connection Error:%s" % (funcName, str(err)), self.logName)
                exit()
            except:
                self.logError("%s: Connection Problem, plugin quitting" % (funcName), self.logName)
                exit()

            self.log(4, dbFlg, "%s: Read ad2usb message:\n%s" % (funcName, repr(rawData)), self.logName)

            # Start by checking if this message is "Press * for faults"
            try:
                if len(rawData) > 0 and rawData[0] == "[":  # A valid panel message
                    self.log(3, dbFlg, "%s: raw zone type is:%s" % (funcName, rawData[0:4]), self.logName)

                    # First split the message into parts and see if we need to send a * to get the faults
                    splitMsg = re.split('[\[\],]', rawData)
                    msgText = splitMsg[7]
                    if string.find(msgText, ' * ') >= 0:
                        self.log(3, dbFlg, "%s: Received a Press * message:%s" % (funcName, rawData), self.logName)
                        self.plugin.conn.write('*')
                        # That's all we need to do for this messsage

                    elif rawData[30:38] == '00000000':
                        self.log(3, dbFlg, "%s: System Message: we passed on this one" % (funcName), self.logName)
                        pass  # Ignore system messages (no keypad address)

                    else:
                        # Get a list of keypad addresses this message was sent to
                        readThisMessage = False
                        foundAddress = False
                        lastAddress = ''
                        try:
                            if self.plugin.numPartitions == 1:                          # only 1 partition, we don't care about keypad addresses
                                panelKeypadAddress = str(self.plugin.ad2usbKeyPadAddress)
                                foundKeypadAddress = panelKeypadAddress
                                readThisMessage = True
                            else:
                                # The msg sub-string with the keypad addresses (in hex)
                                keypadAddressField = rawData[30:38]
                                # Convert the address field to a binary string
                                addrHex = self.hex2bin(keypadAddressField)
                                self.log(3, dbFlg, "%s: addrHex:%s" % (funcName, addrHex), self.logName)
                                for panelKeypadAddress in self.plugin.panelsDict:       # loop through the keypad device dict
                                    bitPosition = -1  # reset this each pass through the loop
                                    panelAddress = -1  # reset this each pass through the loop
                                    panelAddress = int(panelKeypadAddress)
                                    self.log(3, dbFlg, "%s: panelAddress:%s" % (funcName, panelAddress), self.logName)
                                    # determine the bit position for the current address
                                    bitPosition = 8 - (panelAddress % 8) + int(panelAddress / 8) * 8
                                    self.log(3, dbFlg, "%s: bitPosition:%s, bit at bitPosition:%s" %
                                             (funcName, bitPosition, addrHex[bitPosition-1]), self.logName)
                                    if addrHex[bitPosition-1] == '1':                   # See if we have a one in our slot
                                        self.log(3, dbFlg, "%s:  matched key=%s" %
                                                 (funcName, panelKeypadAddress), self.logName)
                                        foundKeypadAddress = panelKeypadAddress
                                        readThisMessage = True   # Yes, we can read this message
                                        if foundAddress:
                                            self.logError("%s: More than one matching keypad address. previous:%s, current:%s" % (
                                                funcName, lastAddress, panelKeypadAddress), self.logName)
                                        foundAddress = True
                                        lastAddress = panelKeypadAddress

                        except Exception as e:
                            self.logError("%s: Keypad Address Error = %s. Data: keypadAddressField=%s, panelAddress=%s, bitPosition=%s" % (
                                funcName, e, keypadAddressField, panelAddress, bitPosition), self.logName)

                        if readThisMessage:
                            # Now look to see if the message has changed since the last one we processed
                            self.log(3, dbFlg, "%s: Panel Message: Before:=%s, Current=%s" %
                                     (funcName, rawData, lastPanelMsg), self.logName)
                            # If it hasn't, start again
                            if rawData == lastPanelMsg:  # The alarm status has not changed
                                self.debugLog("no panel status change")
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

                                self.log(3, dbFlg, "%s: Panel message:%s" % (funcName, panelFlags), self.logName)

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
                                self.log(3, dbFlg, "%s: Found dev: %s, id:%s" %
                                         (funcName, panelDevice.name, panelDevice.id), self.logName)

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
                                        self.log(0, dbFlg, "Alarm tripped by zone: %s" %
                                                 (funcName, apAlarmedZone), self.logName)
                                    else:
                                        self.log(3, dbFlg, "Fire Alarm tripped by zone: %s" %
                                                 (funcName, apAlarmedZone), self.logName)

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
                                        self.log(3, dbFlg, "%s: Alarm Tripped :%s, partition:%s, function:%s" %
                                                 (funcName, user, partition, function), self.logName)

                                        panelDevice.updateStateOnServer(key='lastChgBy', value=user)
                                        panelDevice.updateStateOnServer(key='lastChgTo', value=function)
                                        panelDevice.updateStateOnServer(key='lastChgAt', value=timeStamp)
                                        if self.plugin.logArmingEvents:
                                            self.log(0, dbFlg, "Alarm partition %s set to %s caused/entered by %s." %
                                                     (partition, function, user), self.logName)

                                        self.eventQueueManager(partition, user, function)
                                except Exception as err:
                                    self.errorLog('ALARM TRIPPED: %s' % (str(err)))

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

                            self.log(3, dbFlg, "%s: current:%s, last %s" %
                                     (funcName, apZonesBypassed, self.lastApZonesBypassed), self.logName)

                            # Manage bypassed zones
                            if apZonesBypassed != self.lastApZonesBypassed:
                                self.log(4, dbFlg, "GOT HERE 1 %s: current:%s, last %s" %
                                         (funcName, apZonesBypassed, self.lastApZonesBypassed), self.logName)
                                # There has been a change is the bypass list
                                if apZonesBypassed == "0":
                                    self.log(4, dbFlg, "%s GOT HERE 2" % (funcName), self.logName)
                                    self.lastApZonesBypassed = apZonesBypassed
                                    # Clear the bypass state of all zones
                                    for zone in self.zoneBypassDict:
                                        bZoneData = self.plugin.zonesDict[int(zone)]
                                        bZDevid = bZoneData['devId']
                                        bIndigoDevice = indigo.devices[bZDevid]
                                        bIndigoDevice.updateStateOnServer(key='bypassState', value=False)
                                        bIndigoDevice.updateStateOnServer(
                                            key='displayState', value="enabled", uiValue="Clear")
                                        self.log(3, dbFlg, "%s Clearing bypass state for zone %s, devid %s" %
                                                 (funcName, zone, bZDevid), self.logName)
                                        self.log(4, dbFlg, "%s: \tIndex:%s, Data: %s" %
                                                 (funcName, zone, self.plugin.zonesDict[zone]), self.logName)
                                    # and now clear the list of bypassed zones
                                    self.zoneBypassDict.clear()

                            if apZonesBypassed == "1" and msgKey == "BYPAS" and realZone is True:
                                # A zone has been bypassed.
                                if bMsgZoneNum in self.zoneBypassDict:
                                    self.log(3, dbFlg, "%s: Zone bypass state for zone number %s zone name %s already recorded" % (
                                        funcName, bMsgZoneNum, zName), self.logName)
                                else:
                                    self.zoneBypassDict[bMsgZoneNum] = {True}
                                    self.log(0, dbFlg, "%s: Zone number %s zone name %s has been bypassed" %
                                             (funcName, bMsgZoneNum, zName), self.logName)
                                    self.lastApZonesBypassed = apZonesBypassed
                                    indigoDevice.updateStateOnServer(key='bypassState', value=True)
                                    indigoDevice.updateStateOnServer(
                                        key='displayState', value="bypass", uiValue="bypass")
                                    #indigoDevice.setErrorStateOnServer(u'bypass')

                            # OK, Now let's see if we have a zone event
                            if not ad2usbIsAdvanced and len(self.plugin.zonesDict) > 0:
                                self.debugLog('calling basic')
                                self.debugLog('Zone:%s, Key:%s' % (msgZoneNum, msgKey))

                                if msgKey == "FAULT" or apReadyMode == '1':
                                    self.log(3, dbFlg, "%s: Ready to call basic msg handler" % (funcName), self.logName)
                                    self.basicReadZoneMessage(rawData, msgBitMap, msgZoneNum,
                                                              msgText, msgKey, panelDevice)

                elif rawData[1:9] == u'SER2SOCK' or len(rawData) == 0:
                    self.log(3, dbFlg, "%s: SER2SOCK connection or null Message: we passed on this one" %
                             (funcName), self.logName)
                    pass  # Ignore system messages

                elif rawData[1:4] == 'LRR':   # panel state information  - mostly for events
                    self.log(3, dbFlg, "%s: Processing LRR Message:%s, logging option:%s" %
                             (funcName, rawData, self.plugin.logArmingEvents), self.logName)
                    # EVENT DATA - Either the User Number who preformed the action or the zone that was bypassed.
                    # PARTITION - The panel partition the event applies to. 0 indicates all partitions such as ACLOSS event.
                    # EVENT TYPES - One of the following events. Note: the programming mode for enabling each type is also provided.
                    # eg. !LRR:002,1,OPEN

                    try:
                        self.log(3, dbFlg, "%s: Processing LRR Message:%s, logging option:%s" %
                                 (funcName, rawData, self.plugin.logArmingEvents), self.logName)
                        splitMsg = re.split('[!:,]', rawData)
                        user = splitMsg[2]
                        partition = splitMsg[3]
                        function = splitMsg[4]
                        function = function[0:-2]  # lose the newline

                        if function in kEventStateDict:
                            self.log(3, dbFlg, "%s: LRR Decode- user:%s, partition:%s, function:%s" %
                                     (funcName, user, partition, function), self.logName)
                            now = datetime.now()
                            timeStamp = now.strftime("%Y-%m-%d %H:%M:%S")

                            panelDevice = indigo.devices[self.plugin.panelsDict[foundKeypadAddress]['devId']]
                            # panelDevice = indigo.devices[self.plugin.partition2address[partition]['devId']]
                            panelDevice.updateStateOnServer(key='lastChgBy', value=user)
                            panelDevice.updateStateOnServer(key='lastChgTo', value=function)
                            panelDevice.updateStateOnServer(key='lastChgAt', value=timeStamp)
                            if self.plugin.logArmingEvents:
                                self.log(0, dbFlg, "Alarm partition %s set to %s caused/entered by %s." %
                                         (partition, function, user), self.logName)

                            self.eventQueueManager(partition, user, function)
                    except Exception as err:
                        self.logError("%s: LRR Error:%s" % (funcName, str(err)), self.logName)

                else:
                    # We check the length of self.plugin.zonesDict so we will not try to update zones if none exist
                    # and then call the advanced mode handler.
                    # it is Ok that we skipped the panel update code, we'll catch that on the full ad2usb message

                    if ad2usbIsAdvanced and len(self.plugin.zonesDict) > 0 and rawData[1:4] != "AUI":
                        self.log(3, dbFlg, "%s: Calling advanced for:%s" % (funcName, rawData[1:4]), self.logName)
                        self.advancedReadZoneMessage(rawData)  # indigoDevice, panelKeypadAddress)

                self.log(2, dbFlg, "%s: panelMsgRead End" % (funcName), self.logName)

            except Exception as err:
                self.logError('Error on line {}'.format(sys.exc_info()[-1].tb_lineno), self.logName)
                self.logError("%s: Error: %s" % (funcName, str(err)), self.logName)

        self.client_socket.close()
        self.log(2, dbFlg, "%s Completed" % (funcName), self.logName)

   ########################################
   # Get things rolling
    def startComm(self, ad2usbIsAdvanced, ad2usbCommType, ad2usbAddress, ad2usbPort, ad2usbSerialPort):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log(2, dbFlg, "%s Called" % (funcName), self.logName)
        self.log(3, dbFlg, "%s: isAdvanced:%s, commType:%s, address:%s, port:%s, serialPort:%s" %
                 (funcName, ad2usbIsAdvanced, ad2usbCommType, ad2usbAddress, ad2usbPort, ad2usbSerialPort), self.logName)

        self.log(3, dbFlg, "%s: Read alarm status dict:%s" % (funcName, self.plugin.ALARM_STATUS), self.logName)
        self.log(3, dbFlg, "%s: Loading zonesDict" % (funcName), self.logName)

        for zone in sorted(self.plugin.zonesDict):
            self.log(4, dbFlg, "%s: \tIndex:%s, Data: %s" % (funcName, zone, self.plugin.zonesDict[zone]), self.logName)

        self.shutdown is False
        lostConnCount = 0
        # firstTry = True

        while self.shutdown is False:
            if ad2usbCommType == 'IP':
                HOST = ad2usbAddress
                PORT = ad2usbPort
                theURL = 'socket://' + HOST + ':' + PORT
                self.log(4, dbFlg, "%s: \tthe url is:%s" % (funcName, theURL), self.logName)
            else:
                theURL = ad2usbSerialPort
                self.log(4, dbFlg, "%s: \tthe serial port is:%s" % (funcName, theURL), self.logName)

            try:
                self.plugin.conn = serial.serial_for_url(theURL, baudrate=115200)
                self.plugin.conn.timeout = None
                lostConnCount = 0
                self.log(1, dbFlg, "ad2usb opened for communication at %s" % (theURL), self.logName)
                self.plugin.serialOpen = True
                self.panelMsgRead(ad2usbIsAdvanced)
                self.log(3, dbFlg, "%s: Returned from panelMessageRead()" % (funcName), self.logName)
            except Exception as err:
                self.logError("%s: Could not open connection to the IP Address and Port entered %s" %
                              (funcName, theURL), self.logName)
                self.logError("           The error message was: %s" % (str(err)), self.logName)

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

                self.logError("%s: Failed connection to %s. Will retry in %s\n" %
                              (funcName, theURL, retryText), self.logName)

                retryTime = retryTime * 2  # check every 0.5 seconds
                while retryTime > 0 and not self.shutdown:
                    self.plugin.sleep(0.5)
                    retryTime -= 1

        self.log(0, dbFlg, "%s Completed" % (funcName), self.logName)

   ########################################
    def stopComm(self):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log(3, dbFlg, "%s Called" % (funcName), self.logName)
        self.shutdown = True

        if self.shutdownComplete is False:
            try:
                self.log(3, dbFlg, "%s Started" % (funcName), self.logName)
                self.plugin.conn.close()
            except Exception as err:
                self.logError('Error on line {}'.format(sys.exc_info()[-1].tb_lineno), self.logName)
                self.logError("%s: Error: %s" % (funcName, str(err)), self.logName)
