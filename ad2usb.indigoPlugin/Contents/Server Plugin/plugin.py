#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# ad2usb Alarm Plugin
# Developed and copyright by Richard Perlman -- indigo AT perlman DOT com

from berkinet import logger
# from indigoPluginUpdateChecker import updateChecker
import inspect
import re
import time
import serial
import sys
import indigo   # Not needed. But it supresses lint errors
from ad2usb import ad2usb

################################################################################
# Globals
################################################################################


########################################################
# Support functions for building basic and advanced data structures
########################################################
# panel keypad devices
def addPanelDev(self, dev, mode, ad2usbKeyPadAddress):
    funcName = inspect.stack()[0][3]
    dbFlg = False
    self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)
    self.log.log(4, dbFlg, "%s: received device:\n%s\n" % (funcName, dev), self.logName)

    try:
        alarmPartition = dev.pluginProps['panelPartitionNumber']
    except:
        alarmPartition = "1"
        self.log.logError("%s: Partition number not found for keypad device '%s' Assigning partition 1.\nPlease reconfigure the keypad device to resolve this problem." % (
            funcName, dev.name), self.logName)

    try:
        alarmPartitionAddress = dev.pluginProps['panelKeypadAddress']
    except:
        alarmPartitionAddress = ad2usbKeyPadAddress
        self.log.logError("%s: Panel Keypad Address not found for keypad device '%s' Assigning address %s.\nPlease reconfigure the keypad device to resolve this problem." % (
            funcName, alarmPartition, dev.name), self.logName)

    self.panelsDict[alarmPartitionAddress] = {'devId': dev.id, 'name': dev.name, 'partition': alarmPartition}
    self.log.log(3, dbFlg, "%s: Added address to partition record:%s" %
                 (funcName, self.panelsDict[alarmPartitionAddress]), self.logName)

    # If advanced mode, add a reverse lookup: partition to keypad address
    if mode == 'advanced':
        self.partition2address[alarmPartition] = {'devId': dev.id, 'name': dev.name, 'address': alarmPartitionAddress}
        self.log.log(3, dbFlg, "%s: Added partition to address record:%s" %
                     (funcName, self.partition2address[alarmPartition]), self.logName)

    self.log.log(3, dbFlg, "%s completed" % (funcName), self.logName)


########################################################
# Zone Group devices
def addGroupDev(self, dev):
    funcName = inspect.stack()[0][3]
    dbFlg = False
    self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)
    self.log.log(4, dbFlg, "%s: received device:\n%s\n" % (funcName, dev), self.logName)

    zoneDeviceList = dev.pluginProps[u'zoneDeviceList']
    zoneLogChanges = dev.pluginProps[u'zoneLogChanges']
    self.log.log(3, dbFlg, "%s: Received: zoneDevceList:%s, zoneLogChanges:%s" %
                 (funcName, zoneDeviceList, zoneLogChanges), self.logName)

    try:
        for zone in zoneDeviceList:
            self.log.log(3, dbFlg, "%s:        Found:%s" % (funcName, zone), self.logName)
            # Create a zone number to zoneGroup device table
            if zone in self.zone2zoneGroupDevDict:
                self.log.log(3, dbFlg, "%s:IF        got here for:%s, %s" %
                             (funcName, zone, self.zone2zoneGroupDevDict[zone]), self.logName)
                self.zone2zoneGroupDevDict[zone].append(int(dev.id))
            else:
                self.log.log(3, dbFlg, "%s:IF NOT       got here for:%s" % (funcName, zone), self.logName)
                self.zone2zoneGroupDevDict[zone] = []
                self.zone2zoneGroupDevDict[zone].append(int(dev.id))

             # Create a zoneGroup device to zone state table
            if dev.id in self.zoneGroup2zoneDict:
                self.zoneGroup2zoneDict[dev.id][zone] = 'Clear'
            else:
                self.zoneGroup2zoneDict[dev.id] = {}
                self.zoneGroup2zoneDict[dev.id][zone] = 'Clear'

        self.log.log(3, dbFlg, "%s:        Returned zone2zoneGroupDevDict:%s" %
                     (funcName, self.zone2zoneGroupDevDict), self.logName)
        self.log.log(3, dbFlg, "%s:        Returned zoneGroup2zoneDict:%s" %
                     (funcName, self.zoneGroup2zoneDict), self.logName)
    except Exception as err:
        self.log.logError("%s: Error adding group zone device:%s" % (funcName, str(err)), self.logName)

     # for zone in self.zone2zoneGroupDevDict:
     #     self.log.log(0, dbFlg, "%s:zone2zoneGroupDevDict       Found:%s, %s" % (funcName, zone, self.zone2zoneGroupDevDict[zone]), self.logName)

     # for zone in self.zoneGroup2zoneDict:
     #     self.log.log(0, dbFlg, "%s:zoneGroup2zoneDict        Found:%s, %s" % (funcName, zone, self.zoneGroup2zoneDict[zone]), self.logName)


########################################################
# Build/Modify device property dictionaries
########################################################
# for basic mode
def basicBuildDevDict(self, dev, funct, ad2usbKeyPadAddress):
    funcName = inspect.stack()[0][3]
    dbFlg = False
    self.log.log(2, dbFlg, "%s Called for function:%s" % (funcName, funct), self.logName)
    self.log.log(4, dbFlg, "%s: received device:\n%s\n" % (funcName, dev), self.logName)

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
            self.log.log(3, dbFlg, "%s: Added record for Device:%s, Zone:%s" %
                         (funcName, zoneName, zoneNumber), self.logName)
            self.log.log(3, dbFlg, "%s: Wrote record:%s" % (funcName, self.zonesDict[zoneIndex]), self.logName)

        elif dev.deviceTypeId == 'ad2usbInterface':
            addPanelDev(self, dev, 'basic', ad2usbKeyPadAddress)

        elif dev.deviceTypeId == 'zoneGroup':
            addGroupDev(self, dev)

     # This block is for deleting zones
    elif funct == 'del':
        if dev.deviceTypeId == 'alarmZone':
            zoneNumber = int(dev.pluginProps['zoneNumber'])
            zoneName = dev.name

            del self.zonesDict[zoneNumber]
            self.log.log(3, dbFlg, "%s: Deleted entry for Zone number:%s, Zone name:%s" %
                         (funcName, zoneNumber, zoneName), self.logName)

    self.log.log(3, dbFlg, "%s completed" % (funcName), self.logName)


# For advanced mode
def advancedBuildDevDict(self, dev, funct, ad2usbKeyPadAddress):
    funcName = inspect.stack()[0][3]
    dbFlg = False
    self.log.log(2, dbFlg, "%s Called for devce:%s,  Type:%s, function:%s" %
                 (funcName, dev.name, dev.deviceTypeId, funct), self.logName)
    self.log.log(4, dbFlg, "%s: received device:\n%s\n" % (funcName, dev), self.logName)

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
            zoneLogSupervision = dev.pluginProps['logSupervision']
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
            self.log.log(3, dbFlg, "%s: Added record for Device:%s, Zone:%s" %
                         (funcName, zoneName, zoneNumber), self.logName)
            self.log.log(3, dbFlg, "%s: Wrote record:%s" % (funcName, self.advZonesDict[zoneIndex]), self.logName)

        elif dev.deviceTypeId == 'ad2usbInterface':
            addPanelDev(self, dev, 'advanced', ad2usbKeyPadAddress)

        elif dev.deviceTypeId == 'zoneGroup':
            addGroupDev(self, dev)

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
            self.log.log(3, dbFlg, "%s: Deleted entry for Zone number:%s, Zone name:%s, Zone type:%s" %
                         (funcName, zoneNumber, zoneName, zoneType), self.logName)

    self.log.log(3, dbFlg, "%s completed" % (funcName), self.logName)


################################################################################
# Now, Let's get started...
################################################################################
class Plugin(indigo.PluginBase):
    ########################################
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        self.log = logger(self)
        self.logName = pluginDisplayName
        self.pluginDisplayName = pluginDisplayName
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)

        # removing these since version check now provided by Indigo
        # self.updater = updateChecker(self, pluginId)
        # self.updater.checkVersionPoll()

        self.ad2usb = ad2usb(self)
        self.logUnknownDevices = pluginPrefs.get("logUnknownDevices", False)
        self.ad2usbAddress = pluginPrefs.get("ad2usbAddress", '127.0.0.1')
        self.ad2usbPort = pluginPrefs.get("ad2usbPort")
        self.ad2usbSerialPort = pluginPrefs.get("ad2usbSerialPort")
        self.ad2usbIsAdvanced = pluginPrefs.get("isAdvanced")
        self.ad2usbCommType = pluginPrefs.get('ad2usbCommType')
        self.ad2usbRestart = False
        self.clearAllOnRestart = pluginPrefs.get("restartClear", False)
        self.numPartitions = int(pluginPrefs.get("panelPartitionCount", '1'))
        self.ad2usbKeyPadAddress = pluginPrefs.get("ad2usbKeyPadAddress")
        self.logArmingEvents = pluginPrefs.get("logArmingEvents")
        self.faultList = []
        self.lastZoneFaulted = 0
        self.zonesDict = {}
        self.advZonesDict = {}
        self.panelsDict = {}
        self.virtualDict = {}
        self.zoneGroup2zoneDict = {}
        self.zone2zoneGroupDevDict = {}
        self.partition2address = {}
        self.triggerDict = {}
        self.conn = ''
        self.pluginDisplayName = pluginDisplayName
        self.pluginPrefs = pluginPrefs

        self.log.log(3, dbFlg, "%s Completed" % (funcName), self.logName)

     ########################################
    def __del__(self):
        indigo.PluginBase.__del__(self)

    ########################################################
    # plugin startup (initialization) and shutdown
    ########################################################
    def startup(self):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)

        self.ALARM_STATUS = {'000': 'Fault', '001': 'armedStay', '010': 'armedAway', '100': 'ready'}
        self.zonesDict = {}
        self.advZonesDict = {}

        mode = 'Basic'
        if self.ad2usbIsAdvanced:
            mode = 'Advanced'

        self.log.log(0, dbFlg, "Plugin setup completed. Ready to open link to the ad2usb in %s mode." %
                     (mode), self.logName)

        self.log.log(3, dbFlg, "%s completed" % (funcName), self.logName)

    ########################################################
    def shutdown(self):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)

        self.ad2usb.stopComm()
        self.log.log(3, dbFlg, "%s completed" % (funcName), self.logName)

    ########################################################
    # device setup/shutdown Calls from Indigo
    ########################################################
    def deviceStartComm(self, dev):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)
        self.log.log(3, dbFlg, "%s: devName:%s, devId:%s, devTypeId:%s, clearAllOnRestart:%s" %
                     (funcName, dev.name, dev.id, dev.deviceTypeId, self.clearAllOnRestart), self.logName)

        # Always load the basic Dict because we need a zone number to device lookup in advanced mode too.
        basicBuildDevDict(self, dev, 'add', self.ad2usbKeyPadAddress)

        if self.ad2usbIsAdvanced:
            advancedBuildDevDict(self, dev, 'add', self.ad2usbKeyPadAddress)

         # For new devices (Those whose state or dsplayState = "") set them to Clear/off
        if dev.deviceTypeId == 'alarmZone':
            if dev.states['zoneState'] == "" or dev.states['displayState'] == "" or self.clearAllOnRestart:
                dev.updateStateOnServer(key='zoneState', value='Clear', uiValue='Clear')
                dev.updateStateOnServer(key='displayState', value='enabled', uiValue='Clear')

        self.log.log(3, dbFlg, "%s completed" % (funcName), self.logName)

    ########################################################
    def deviceStopComm(self, dev):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)
        self.log.log(3, dbFlg, "%s: devName:%s, devId:%s, devTypeId:%s" %
                     (funcName, dev.name, dev.id, dev.deviceTypeId), self.logName)

        # We always load the basic Dict because we need a zone number to device lookup in advanced mode too.
        try:
            basicBuildDevDict(self, dev, 'del')
        except:
            pass

        if self.ad2usbIsAdvanced:
            try:
                advancedBuildDevDict(self, dev, 'del')
            except:
                pass

        self.log.log(3, dbFlg, "%s completed" % (funcName), self.logName)

    ########################################################
    # start/stop/restart Calls from Indigo
    ########################################################
    def runConcurrentThread(self):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)

        try:
            self.ad2usb.startComm(self.ad2usbIsAdvanced, self.ad2usbCommType,
                                  self.ad2usbAddress, self.ad2usbPort, self.ad2usbSerialPort)
            self.log.log(0, dbFlg, "ad2usb communication closed", self.logName)
        except:
            if self.ad2usbRestart:
                self.log.log(0, dbFlg, "%s Process completed, Restarting" % (funcName), self.logName)
            else:
                self.log.log(0, dbFlg, "%s Process completed, Restarting" % (funcName), self.logName)
            return

        # In case we are restarting after a config change, we should just start again
        if self.ad2usbRestart:
            self.ad2usbRestart = False
            self.log = logger(self)
            self.ad2usb.startComm(self.ad2usbIsAdvanced, self.ad2usbCommType,
                                  self.ad2usbAddress, self.ad2usbPort, self.ad2usbSerialPort)

        self.log.log(3, dbFlg, "%s completed" % (funcName), self.logName)

    ########################################################
    def stopConcurrentThread(self):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(3, dbFlg, "%s Called" % (funcName), self.logName)

        self.ad2usb.stopComm()

        self.log.log(3, dbFlg, "%s completed" % (funcName), self.logName)

    ########################################################
    def restart(self):
        funcName = inspect.stack()[0][3]
        dbFlg = True
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)

        self.log.log(2, dbFlg, "%s: Stopping" % (funcName), self.logName)
        self.ad2usb.stopComm()
        self.sleep(5)
        self.log.log(2, dbFlg, "%s: Starting" % (funcName), self.logName)
        self.ad2usb.startComm(self.ad2usbIsAdvanced, self.ad2usbCommType,
                              self.ad2usbAddress, self.ad2usbPort, self.ad2usbSerialPort)

        self.log.log(3, dbFlg, "%s completed" % (funcName), self.logName)

    ########################################################
    # Action callbacks
    ########################################################
    def virtZoneManage(self, pluginAction):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)
        self.log.log(3, dbFlg, "%s: Received:%s" % (funcName, pluginAction), self.logName)

        devId = pluginAction.deviceId
        virtDevice = indigo.devices[devId]
        virtZoneNumber = virtDevice.pluginProps['zoneNumber']

        action = pluginAction.props['virtualAction']
        panelMsg = 'L' + virtZoneNumber + action + '\r'
        self.ad2usb.panelMsgWrite(panelMsg)

        self.log.log(3, dbFlg, "%s: Sent message:%s" % (funcName, panelMsg), self.logName)

        if self.ad2usbIsAdvanced:
            virtPartition = virtDevice.pluginProps['vZonePartitionNumber']
            panelDevice = indigo.devices[self.partition2address[virtPartition]['devId']]
            panelKeypadAddress = panelDevice.pluginProps['panelKeypadAddress']
            # Update device UI States
            # This shouldn't be necessary, but the AD2USB doesn't send EXP messages for virtual zones
            if action == '0':   # Clear
                uiValue = 'Clear'
                zoneState = 'Clear'
                displayStateValue = 'enabled'
                try:   # In case someone tries to set a clear zone to clear
                    self.ad2usb.zoneStateDict[panelKeypadAddress].remove(int(virtZoneNumber))
                except:
                    pass
                self.log.log(3, dbFlg, "%s: Clear - state list:%s" %
                             (funcName, self.ad2usb.zoneStateDict), self.logName)
            elif action == '1':   # Fault
                uiValue = 'Fault'
                displayStateValue = 'faulted'
                zoneState = 'faulted'
                self.ad2usb.zoneStateDict[panelKeypadAddress].append(int(virtZoneNumber))
                self.ad2usb.zoneStateDict[panelKeypadAddress].sort()
                self.log.log(3, dbFlg, "%s: Fault - state list:%s" %
                             (funcName, self.ad2usb.zoneStateDict), self.logName)
            elif action == '2':   # Trouble
                uiValue = 'Trouble'
                displayStateValue = 'trouble'
                self.ad2usb.zoneStateDict[panelKeypadAddress].append(int(virtZoneNumber))
                self.ad2usb.zoneStateDict[panelKeypadAddress].sort()
                self.log.log(3, dbFlg, "%s: Trouble - state list:%s" %
                             (funcName, self.ad2usb.zoneStateDict), self.logName)
            else:
                # ERROR
                pass

            virtDevice.updateStateOnServer(key='zoneState', value=zoneState, uiValue=uiValue)
            virtDevice.updateStateOnServer(key='displayState', value=displayStateValue, uiValue=uiValue)
            panelDevice.updateStateOnServer(key='zoneFaultList', value=str(
                self.ad2usb.zoneStateDict[panelKeypadAddress]))

        self.log.log(3, dbFlg, "%s completed" % (funcName), self.logName)

    ########################################################
    def panelMsgWrite(self, pluginAction):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)
        self.log.log(3, dbFlg, "%s: Received:%s" % (funcName, pluginAction), self.logName)

        if pluginAction.props['keypadAddress'] == '':
            address = self.ad2usbKeyPadAddress
        else:
            address = pluginAction.props['keypadAddress']

        panelMsg = pluginAction.props['panelMessage']
        if panelMsg == 'F1' or panelMsg == 'f1':
            panelMsg = chr(1) + chr(1) + chr(1)
        elif panelMsg == 'F2' or panelMsg == 'f2':
            panelMsg = chr(2) + chr(2) + chr(2)
        elif panelMsg == 'F3' or panelMsg == 'f3':
            panelMsg = chr(3) + chr(3) + chr(3)
        elif panelMsg == 'F4' or panelMsg == 'f4':
            panelMsg = chr(4) + chr(4) + chr(4)

        self.log.log(3, dbFlg, "%s: Created message:%s" % (funcName, panelMsg), self.logName)

        self.ad2usb.panelMsgWrite(panelMsg, address)

        self.log.log(3, dbFlg, "%s completed" % (funcName), self.logName)

    ########################################################
    def panelQuckArmWrite(self, pluginAction):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)
        self.log.log(3, dbFlg, "%s: Received:%s" % (funcName, pluginAction), self.logName)

        if pluginAction.props['keypadAddress'] == '':
            address = self.ad2usbKeyPadAddress
        else:
            address = pluginAction.props['keypadAddress']
        panelMsg = pluginAction.props['armingCode']

        self.log.log(3, dbFlg, "%s: Created message:%s" % (funcName, panelMsg), self.logName)

        self.ad2usb.panelMsgWrite(panelMsg, address)

        self.log.log(3, dbFlg, "%s completed" % (funcName), self.logName)

    ########################################################
    def forceZoneStateChange(self, pluginAction):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)
        self.log.log(3, dbFlg, "%s: Received: %s" % (funcName, pluginAction), self.logName)

        zoneDevice = indigo.devices[int(pluginAction.props['zoneDevice'])]

        if pluginAction.props['zoneState'] == 'clear':
            zoneDevice.updateStateOnServer(key='displayState', value='enabled', uiValue=u'Clear')
            zoneDevice.updateStateOnServer(key='zoneState', value='Clear')
        else:
            zoneDevice.updateStateOnServer(key='zoneState', value='faulted', uiValue=u'Fault')
            zoneDevice.updateStateOnServer(key='displayState', value='faulted', uiValue=u'Fault')

        self.log.log(3, dbFlg, "%s completed" % (funcName), self.logName)

    ########################################################
    # Functions for configuration dialogs
    ########################################################

    ########################################################
    # Let us know the operating mode inside of a device configuration window
    def getDeviceConfigUiValues(self, pluginProps, typeId, devId):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)

        valuesDict = pluginProps
        errorMsgDict = indigo.Dict()

        # Override the device ConfigUI isAdvanced value here with the global value:
        valuesDict["isAdvanced"] = self.pluginPrefs["isAdvanced"]
        valuesDict["numPartitions"] = self.numPartitions

        self.log.log(3, dbFlg, "%s completed" % (funcName), self.logName)

        return (valuesDict, errorMsgDict)

    ########################################
    def closedPrefsConfigUi(self, valuesDict, UserCancelled):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)

        if UserCancelled is False:
            if (self.ad2usbIsAdvanced != valuesDict['isAdvanced']) or (self.ad2usbCommType != valuesDict['ad2usbCommType']):
                self.log.log(0, dbFlg, "The configuration changes require a plugin reload. Reloading now...", self.logName)
                thisPlugin = indigo.server.getPlugin("com.berkinet.ad2usb")
                try:
                    thisPlugin.restart(waitUntilDone=False)
                except:
                    pass   # Hide any shutdown errors
            else:
                self.log = logger(self)
                self.log.log(4, dbFlg, "%s: Read valuesDict:%s" % (funcName, valuesDict), self.logName)
                self.ad2usbCommType = valuesDict['ad2usbCommType']
                if self.ad2usbCommType == 'IP':
                    self.ad2usbAddress = valuesDict["ad2usbAddress"]
                    self.ad2usbPort = valuesDict["ad2usbPort"]
                else:
                    self.ad2usbSerialPort = valuesDict["ad2usbSerialPort"]

                self.ad2usbIsAdvanced = valuesDict["isAdvanced"]
                self.logUnknownDevices = valuesDict["logUnknownDevices"]
                self.clearAllOnRestart = valuesDict["restartClear"]

            self.log.log(0, dbFlg, "Plugin preferences have been updated", self.logName)
            self.log.log(3, dbFlg, "%s completed" % (funcName), self.logName)

    ########################################################
    # Validation methods
    ########################################################
    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)
        self.log.log(3, dbFlg, "%s: received:\n>>valuesDict\n%s\n>>typeId\n%s\n>>devId\n%s\n" %
                     (funcName, valuesDict, typeId, devId), self.logName)

        errorMsgDict = indigo.Dict()
        areErrors = False

        if typeId == 'ad2usbInterface':
            prId = "com.berkinet.ad2usb"

            for dev in indigo.devices.iter(prId):
                # self.numPartitions == 1:
                if valuesDict[u'panelKeypadAddress'] == '' and valuesDict[u'panelPartitionNumber'] == '1':
                    valuesDict[u'panelKeypadAddress'] = self.ad2usbKeyPadAddress

                if dev.deviceTypeId == 'ad2usbInterface' and dev.configured:
                    try:
                        if valuesDict[u'panelPartitionNumber'] == dev.pluginProps[u'panelPartitionNumber'] and dev.id != devId:
                            errorMsgDict[u'panelPartitionNumber'] = 'Found an existing panel device for the same parttion.\nOnly one panel device per partition is allowed.'
                            errorMsgDict[u'showAlertText'] = '-> Found an existing panel device for the same partition.\nOnly one panel device per partition is allowed.'
                            self.log.logError(
                                "%s: -> Found an existing panel device for the same partition.\nOnly one panel device per partition is allowed." % (funcName), self.logName)
                            areErrors = True
                    except:
                        valuesDict[u'panelPartitionNumber'] = "1"

                    try:
                        if valuesDict[u'panelKeypadAddress'] == dev.pluginProps[u'panelKeypadAddress'] and dev.id != devId:
                            errorMsgDict[u'panelKeypadAddress'] = 'Found an existing panel device with the same keypad address.\nOnly one panel device per address is allowed.'
                            errorMsgDict[u'showAlertText'] = '-> Found an existing panel device with the same keypad address.\nOnly one panel device per address is allowed.'
                            self.log.logError(
                                "%s: -> Found an existing panel device with the same keypad address.\nOnly one panel device per address is allowed." % (funcName), self.logName)
                            areErrors = True
                    except:
                        valuesDict[u'panelKeypadAddress'] = self.ad2usbKeyPadAddress

                    if int(valuesDict['panelPartitionNumber']) > self.numPartitions:
                        errorMsgDict[u'panelPartitionNumber'] = 'Partition number selected greater than configured partitions.'
                        errorMsgDict[u'showAlertText'] = '-> Partition number selected greater than configured partitions.'
                        self.log.logError(
                            "%s: -> Partition number selected greater than configured partitions." % (funcName), self.logName)
                        areErrors = True

            valuesDict[u'address'] = 'Keypad ' + valuesDict[u'panelKeypadAddress']

        elif typeId == 'alarmZone' or typeId == 'alarmZoneVirtual':
            self.log.log(3, dbFlg, "%s:  Option alarmZone/alarmZoneVirtual." % (funcName), self.logName)
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

        self.log.log(3, dbFlg, "%s:  returned:%s" % (funcName, valuesDict), self.logName)

        if areErrors:
            self.log.log(3, dbFlg, "%s Completed - With errors" % (funcName), self.logName)
            return (False, valuesDict, errorMsgDict)
        else:
            self.log.log(3, dbFlg, "%s Completed - No errors" % (funcName), self.logName)
            return (True, valuesDict)

    ########################################################
    def validatePrefsConfigUi(self, valuesDict):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)
        self.log.log(3, dbFlg, "%s: Received: %s" % (funcName, valuesDict), self.logName)

        # Build the ad2usb board configuration string
        # The keypad address is required. Without it we cannot continue
        if valuesDict['msgControl'] == '2':
            errorMsgDict = indigo.Dict()
            errorMsgDict[u'ad2usbCommType'] = u"IP Address or USB device Invalid. "
            return (False, valuesDict, errorMsgDict)

        elif valuesDict['msgControl'] == '1':
            if len(valuesDict['ad2usbKeyPadAddress']) > 0:
                cAddress = 'ADDRESS=' + valuesDict['ad2usbKeyPadAddress']
            else:
                errorMsgDict = indigo.Dict()
                errorMsgDict[u'ad2usbKeyPadAddress'] = u"A valid keypad address is required"
                return (False, valuesDict, errorMsgDict)

             # virtual zone expanders
            zxCount = 0
            zx1 = 'n'
            if valuesDict['ad2usbExpander_1']:
                zx1 = 'Y'
                zxCount += 1
            zx2 = 'n'
            if valuesDict['ad2usbExpander_2']:
                zx2 = 'Y'
                zxCount += 1
            zx3 = 'n'
            if valuesDict['ad2usbExpander_3']:
                zx3 = 'Y'
                zxCount += 1
            zx4 = 'n'
            if valuesDict['ad2usbExpander_4']:
                zx4 = 'Y'
                zxCount += 1
            zx5 = 'n'
            if valuesDict['ad2usbExpander_5']:
                zx5 = 'Y'
                zxCount += 1
            cZoneExpander = '&EXP=' + zx1 + zx2 + zx3 + zx4 + zx5

            if zxCount > 2:
                errorMsgDict = indigo.Dict()
                errorMsgDict[u'ad2usbExpander_1'] = u"A maximum of 2 virtual zone expanders are allowed"
                return (False, valuesDict, errorMsgDict)

             # virtual relays
            vr1 = 'n'
            if valuesDict['ad2usbVirtRelay_1']:
                vr1 = 'Y'
            vr2 = 'n'
            if valuesDict['ad2usbVirtRelay_2']:
                vr2 = 'Y'
            vr3 = 'n'
            if valuesDict['ad2usbVirtRelay_3']:
                vr3 = 'Y'
            vr4 = 'n'
            if valuesDict['ad2usbVirtRelay_4']:
                vr4 = 'Y'
            cRelays = '&REL=' + vr1 + vr2 + vr3 + vr4

            # LRR
            cLrr = '&LRR=N'
            if valuesDict['ad2usbLrr']:
                cLrr = '&LRR=Y'
             # Deduplicate
            cDedup = '&DEDUPLICATE=N'
            if valuesDict['ad2usbDeduplicate'] is True:
                cDedup = '&DEDUPLICATE=Y'

             # Now put it all together
            cString = 'C' + cAddress + cZoneExpander + cRelays + cLrr + cDedup + '\r'
            # cString2 = 'C' + cLrr + cDedup + '\r'   # Work-around for ad2usb bug

            self.log.log(3, dbFlg, "%s: validation: ad2usb config string is:%s" % (funcName, cString), self.logName)

            # figure out the url for communications with the ad2usb board
            if valuesDict['ad2usbCommType'] == 'IP':
                theURL = 'socket://' + valuesDict['ad2usbAddress'] + ':' + valuesDict['ad2usbPort']
                self.log.log(3, dbFlg, "%s: Validation: the url is:%s" % (funcName, theURL), self.logName)

                # Communication validation test and board config
                try:
                    testSocket = serial.serial_for_url(theURL, baudrate=115200)
                    # self.log.log(3, dbFlg, "%s: Starting config write with:\n%s: and\n%s" % (funcName, repr(cString), repr(cString2)), self.logName)
                    self.log.log(3, dbFlg, "%s: Starting config write with:\n%s:" %
                                 (funcName, repr(cString)), self.logName)
                    testSocket.write(cString)
                    #time.sleep(1)
                    #testSocket.write(cString2)
                    self.log.log(3, dbFlg, "%s: validation: ad2usb config string is: %s" %
                                 (funcName, cString), self.logName)
                    testSocket.close()
                    self.log.log(3, dbFlg, "%s: Completed config write" % (funcName), self.logName)
                except Exception as err:
                    errorMsgDict = indigo.Dict()
                    errorMsgDict[u'ad2usbAddress'] = u"Could not open connection to the IP Address and Port entered. " + \
                        str(err)
                    self.log.logError("%s: Test connection failed: the url was:%s. err=%s" %
                                      (funcName, theURL, str(err)), self.logName)
                    return (False, valuesDict, errorMsgDict)
        else:
            self.log.log(3, dbFlg, "%s: Validation: no test for USB device %s" %
                         (funcName, valuesDict['ad2usbAddress']), self.logName)

         # User choices look good, so return True (client will then close the dialog window).
        self.log.log(3, dbFlg, "%s completed" % (funcName), self.logName)

        return (True, valuesDict)

    ########################################################
    def validateEventConfigUi(self, valuesDict, typeId, devId):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)
        self.log.log(3, dbFlg, "%s: received:\n>>valuesDict\n%s\n>>typeId\n%s\n>>devId\n%s\n" %
                     (funcName, valuesDict, typeId, devId), self.logName)

        errorMsgDict = indigo.Dict()
        areErrors = False

        if typeId == 'userEvents':
            try:
                # foo = str(int(valuesDict[u'userNumber']))  # Throw an error if not an int
                valuesDict[u'userNumber'] = str(valuesDict[u'userNumber'])
            except:
                errorMsgDict[u'userNumber'] = 'User number must be an integer.'
                valuesDict[u'userNumber'] = 'User number must be an integer.'
                areErrors = True

        if areErrors:
            self.log.log(3, dbFlg, "%s Completed - With errors" % (funcName), self.logName)
            return (False, valuesDict, errorMsgDict)
        else:
            self.log.log(3, dbFlg, "%s Completed - No errors" % (funcName), self.logName)
            return (True, valuesDict)

    ########################################################
    # Confg callback methods
    ########################################################
    def ConfigButtonPressed(self, valuesDict):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)
        self.log.log(4, dbFlg, "%s: Received: %s" % (funcName, valuesDict), self.logName)

        # figure out the url for communications with the ad2usb board
        if valuesDict['ad2usbCommType'] == 'IP':
            theURL = 'socket://' + valuesDict['ad2usbAddress'] + ':' + valuesDict['ad2usbPort']
            self.log.log(4, dbFlg, "%s: the url is:%s" % (funcName, theURL), self.logName)
        else:
            theURL = valuesDict['ad2usbSerialPort']
            self.log.log(4, dbFlg, "%s:  the url is:%s" % (funcName, theURL), self.logName)

         # Communication validation test and board config
        linesRead = 0
        msg = ""
        adConfig = ""
        adRead = "nothing"

        if valuesDict['ad2usbCommType'] == 'USB':
            valuesDict['msgControl'] = '3'
            return valuesDict
        else:
            try:
                testSocket = serial.serial_for_url(theURL, baudrate=115200)
                testSocket.timeout = 2
                self.log.log(4, dbFlg, "%s: created new connection" % (funcName), self.logName)

                linesRead = 0
                testSocket.write('C\r')
                while linesRead < 5:
                    adRead = ""
                    #adRead = testSocket.readline(eol='\n')
                    adRead = testSocket.readline()

                    if len(adRead) > 8 and adRead[0:8] == '!CONFIG>':
                        linesRead = 5
                        msg = adRead[8:-2]
                        valuesDict['msgControl'] = '1'

                    self.log.log(4, dbFlg, "%s: readline:%s, %s" %
                                 ((funcName, str(adRead), str(linesRead))), self.logName)
                    linesRead += 1

                if testSocket.isOpen():
                    testSocket.close()
            except Exception as err:
                if testSocket.isOpen():
                    testSocket.close()
                valuesDict['msgControl'] = '2'
                self.log.logError("%s: config read connection failed: the url was:%s. err=%s" %
                                  (funcName, theURL, str(err)), self.logName)
                return valuesDict

        self.log.log(4, dbFlg, "%s: the raw config is:%s" % (funcName, msg), self.logName)
        adConfig = re.split('&', msg)
        self.log.log(4, dbFlg, "%s:  the split config is:%s" % (funcName, adConfig), self.logName)

        confItem = re.split('=', adConfig[0])

        # Check that we got a valid config back from the ad2usb.  Maybe the firmware is too old.
        if len(confItem) < 2:
            valuesDict['msgControl'] = '3'
            self.log.log(3, dbFlg, "%s Completed with invalid config" % (funcName), self.logName)
            return valuesDict
        else:
            valuesDict['ad2usbKeyPadAddress'] = confItem[1]

            confItem = re.split('=', adConfig[2])
            valuesDict['ad2usbLrr'] = confItem[1]

            confItem = re.split('=', adConfig[3])
            adExp = confItem[1]

            valuesDict['ad2usbExpander_1'] = adExp[0:1]
            valuesDict['ad2usbExpander_2'] = adExp[1:2]
            valuesDict['ad2usbExpander_3'] = adExp[2:3]
            valuesDict['ad2usbExpander_4'] = adExp[3:4]
            valuesDict['ad2usbExpander_5'] = adExp[4:5]

            confItem = re.split('=', adConfig[4])
            adRel = confItem[1]
            valuesDict['ad2usbVirtRelay_1'] = adRel[0:1]
            valuesDict['ad2usbVirtRelay_2'] = adRel[1:2]
            valuesDict['ad2usbVirtRelay_3'] = adRel[2:3]
            valuesDict['ad2usbVirtRelay_4'] = adRel[3:4]

            confItem = re.split('=', adConfig[6])
            valuesDict['ad2usbDeduplicate'] = confItem[1]

            self.log.log(3, dbFlg, "%s Completed with valid config" % (funcName), self.logName)

            return valuesDict

    ########################################################
    # ConfiguUI callbacks from Actions and Devices
    def getPartitionList(self, filter="", valuesDict=None, typeId="", targetId=0):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)

        myArray = []

        for panelKeypadAddress in self.panelsDict:
            partition = self.panelsDict[panelKeypadAddress]['partition']
            myArray.append((panelKeypadAddress, partition))

        self.log.log(4, dbFlg, "%s: Returned myArray:%s" % (funcName, myArray), self.logName)
        self.log.log(3, dbFlg, "%s Completed with valid config" % (funcName), self.logName)

        return myArray

    ########################################################
    def getZoneList(self,  filter="", valuesDict=None, typeId="", targetId=0):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)

        myArray = []

        for device in sorted(indigo.devices):
            if device.deviceTypeId == 'alarmZone':
                myArray.append((device.id, device.name))

        self.log.log(4, dbFlg, "%s: Returned myArray:%s" % (funcName, myArray), self.logName)
        self.log.log(3, dbFlg, "%s completed" % (funcName), self.logName)

        return myArray

    ########################################################
    # Functon for getZoneDevList to sort the zone list on zone number
    def asint(self, s):
        try:
            return int(s), ''
        except ValueError:
            return sys.maxint, s

    ########################################################
    def getZoneDevList(self,  filter="", valuesDict=None, typeId="", targetId=0):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s Called" % (funcName), self.logName)

        myArray = []
        tempDict = {}

        #for device in sorted(indigo.devices.iter("self")):
        for device in indigo.devices.iter("self"):
            if device.deviceTypeId == 'alarmZone' or device.deviceTypeId == 'alarmZoneVirtual':
                zoneNumber = device.pluginProps['zoneNumber']
                if len(zoneNumber) == 1:
                    zoneNumber = '0' + zoneNumber
                value = zoneNumber + ' - ' + device.name
                tempDict[zoneNumber] = value

        self.log.log(4, dbFlg, "%s:  tempDict:%s" % (funcName, tempDict), self.logName)
        # Take the dict of zone numbers and names and turn it into a numerically sorted list
        sortedlist = [(k, tempDict[k]) for k in sorted(tempDict, key=self.asint)]
        self.log.log(3, dbFlg, "%s:  sortedlist:%s" % (funcName, sortedlist), self.logName)
        for key in sortedlist:
            self.log.log(3, dbFlg, "%s:  zone tupple: %s" % (funcName, key), self.logName)
            try:
                foo = int(key[0])  # Force an error if the key is non-numeric
                foo = foo  # Get rid of the stupid lintv error
                myArray.append(key)
            except:
                pass

        self.log.log(3, dbFlg, "%s: Returned myArray:%s" % (funcName, myArray), self.logName)
        self.log.log(3, dbFlg, "%s completed" % (funcName), self.logName)

        return myArray

    ########################################
    # Indigo Event Triggers: Start and Stop
    #

    ########################################
    def triggerStartProcessing(self, trigger):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s called for trigger %s" % (funcName, trigger.name), self.logName)
        self.log.log(4, dbFlg, "%s: Received trigger:%s" % (funcName, trigger), self.logName)
        self.log.log(4, dbFlg, "%s: Starting trigger dict:%s" % (funcName, self.triggerDict), self.logName)

        event = trigger.pluginProps['indigoTrigger'][0]
        partition = trigger.pluginProps['panelPartitionNumber']
        tid = trigger.id

        try:
            user = trigger.pluginProps['userNumber']
        except:
            user = False

        if user:
            try:
                if user not in self.triggerDict:
                    self.triggerDict[user] = {}
                self.triggerDict[user][partition] = {'tid': tid, 'event': event}
            except Exception as err:
                self.log.logError("%s: Error:%s" % (funcName, err), self.logName)
        else:
            try:
                if event not in self.triggerDict:
                    self.triggerDict[event] = {}
                self.triggerDict[event][partition] = tid
            except Exception as err:
                self.log.logError("%s: Error:%s" % (funcName, err), self.logName)

        self.log.log(2, dbFlg, "%s updated triggerDict:%s" % (funcName, self.triggerDict), self.logName)
        self.log.log(2, dbFlg, "%s: Completed" % (funcName), self.logName)

    ########################################
    def triggerStopProcessing(self, trigger):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.log.log(2, dbFlg, "%s called for trigger %s" % (funcName, trigger.name), self.logName)
        self.log.log(4, dbFlg, "%s: Received trigger:%s" % (funcName, trigger), self.logName)

        event = trigger.pluginProps['indigoTrigger'][0]

        if event in self.triggerDict:
            self.log.log(2, dbFlg, "%s trigger %s found" % (funcName, trigger.name), self.logName)
            del self.triggerDict[event]

        self.log.log(2, dbFlg, "%s trigger %s deleted" % (funcName, trigger.name), self.logName)
        self.log.log(2, dbFlg, "%s: Completed" % (funcName), self.logName)

    ########################################
    # def triggerUpdated(self, origDev, newDev):
    #   self.log.log(4, u"<<-- entering triggerUpdated: %s" % origDev.name)
    #   self.triggerStopProcessing(origDev)
    #   self.triggerStartProcessing(newDev)
