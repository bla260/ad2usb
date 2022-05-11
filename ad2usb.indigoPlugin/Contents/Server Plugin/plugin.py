#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# ad2usb Alarm Plugin
# Developed and copyright by Richard Perlman -- indigo AT perlman DOT com

# from berkinet import logger
# from indigoPluginUpdateChecker import updateChecker
# import inspect
import logging  # needed for CONSTANTS
import re
import time
import serial
import sys
import indigo   # Not needed. But it supresses lint errors
from ad2usb import ad2usb

################################################################################
# Globals
################################################################################
# Log levels dictionary and reverse dictionary name->number
kLoggingLevelNames = {'CRITICAL': 50, 'ERROR': 40, 'WARNING': 30, 'INFO': 20, 'DEBUG': 10}
kLoggingLevelNumbers = {50: 'CRITICAL', 40: 'ERROR', 30: 'WARNING', 20: 'INFO', 10: 'DEBUG'}

# Custom Zone State - see Devices.xml
kZoneStateDisplayValues = {'faulted': 'Fault', 'clear': 'Clear'}
k_CLEAR = 'clear'
k_FAULT = 'faulted'  # should convert to 'fault'

########################################################
# Support functions for building basic and advanced data structures
########################################################
# panel keypad devices


def addPanelDev(self, dev, mode, ad2usbKeyPadAddress):
    self.logger.debug(u"Called")
    self.logger.debug(u"received device:{}".format(dev))

    try:
        alarmPartition = dev.pluginProps['panelPartitionNumber']
    except:
        alarmPartition = "1"
        self.logger.error(u"partition number not found for keypad device:{} - assigning partition 1".format(dev.name))
        self.logger.error(u"please reconfigure the keypad device to resolve this problem")

    try:
        alarmPartitionAddress = dev.pluginProps['panelKeypadAddress']
    except:
        alarmPartitionAddress = ad2usbKeyPadAddress
        # TO DO: review this log
        self.logger.error(
            u"alarm panel keypad address not found for keypad device:{} - assigning address:{}.".format(alarmPartition, dev.name))
        self.logger.error(u"reconfigure the keypad device to resolve this problem")

    self.panelsDict[alarmPartitionAddress] = {'devId': dev.id, 'name': dev.name, 'partition': alarmPartition}
    self.logger.debug(u"added address to partition record:{}".format(self.panelsDict[alarmPartitionAddress]))

    # If advanced mode, add a reverse lookup: partition to keypad address
    if mode == 'advanced':
        self.partition2address[alarmPartition] = {'devId': dev.id, 'name': dev.name, 'address': alarmPartitionAddress}
        self.logger.debug(u"added partition to address record:{}".format(self.partition2address[alarmPartition]))

    self.logger.debug(u"completed")


########################################################
# Zone Group devices
def addGroupDev(self, dev):
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


########################################################
# Build/Modify device property dictionaries
########################################################
# for basic mode
def basicBuildDevDict(self, dev, funct, ad2usbKeyPadAddress):
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
            addPanelDev(self, dev, 'basic', ad2usbKeyPadAddress)

        elif dev.deviceTypeId == 'zoneGroup':
            addGroupDev(self, dev)

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
            self.logger.debug(u"added record for device:{}, zone:{}".format(zoneName, zoneNumber))
            self.logger.debug(u"wrote record:{}".format(self.advZonesDict[zoneIndex]))

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
            self.logger.debug(u"deleted entry for zone number:{}, name:{}, type:{}".format(
                zoneNumber, zoneName, zoneType))

    self.logger.debug(u"completed")


################################################################################
# Now, Let's get started...
################################################################################
class Plugin(indigo.PluginBase):
    ########################################
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        # replaced with standard logger - remove these lines in 1.6.2
        # self.log = logger(self)
        # self.logName = pluginDisplayName
        # self.pluginDisplayName = pluginDisplayName

        # assume some logger exists
        self.logger.debug(u"called with id:{}, name:{}, version:{}".format(pluginId, pluginDisplayName, pluginVersion))
        self.logger.debug(u"preferences:{}".format(pluginPrefs))

        # init the ad2usb object first
        self.ad2usb = ad2usb(self)

        # call method to upgrade (if needed) and set preferences
        # need to do this before any logging to set logging levels
        self.__setPreferences(pluginPrefs)

        # set logging levels
        self.__setLoggingLevels()

        # if the preferences are set to log panel messages initialize the log file
        if self.isPanelLoggingEnabled is True:
            self.logger.info("Panel logging is enabled")
            self.__initPanelLogging()

        # init other properties
        self.ad2usbRestart = False
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

        try:
            self.pythonVersion = sys.version_info.major
        except Exception as err:
            self.logger.warning(u"Unable to determine Python version 2 or 3; assuming 2. Error:{}".format(str(err)))
            self.pythonVersion = 2

        # adding new logging object introduced in API 2.0
        self.logger.info(u"completed")

     ########################################
    def __del__(self):
        indigo.PluginBase.__del__(self)

    ########################################################
    # plugin startup (initialization) and shutdown
    ########################################################
    def startup(self):
        self.logger.debug(u"called")

        self.ALARM_STATUS = {'000': 'Fault', '001': 'armedStay', '010': 'armedAway', '100': 'ready'}
        self.zonesDict = {}
        self.advZonesDict = {}

        mode = 'Basic'
        if self.ad2usbIsAdvanced:
            mode = 'Advanced'

        # TO DO:
        # get the firmware version and log it
        # get the current configuration of the board and log it and change the preferences

        self.logger.info(u"Plugin startup completed. Ready to open link to the ad2usb in {} mode.".format(mode))

    ########################################################
    def shutdown(self):
        self.logger.debug(u"Called")

        self.ad2usb.stopComm()

        self.logger.info(u"completed")

    ########################################################
    # device setup/shutdown Calls from Indigo
    ########################################################
    def deviceStartComm(self, dev):
        self.logger.debug(u"called with Name:{}, id:{}, TypeId:{}, clearAllOnRestart:{}".format(
            dev.name, dev.id, dev.deviceTypeId, self.clearAllOnRestart))

        # Always load the basic Dict because we need a zone number to device lookup in advanced mode too.
        basicBuildDevDict(self, dev, 'add', self.ad2usbKeyPadAddress)

        if self.ad2usbIsAdvanced:
            advancedBuildDevDict(self, dev, 'add', self.ad2usbKeyPadAddress)

        # migrate state from old displayState to zoneState
        if (dev.deviceTypeId == 'zoneGroup'):
            if dev.displayStateId == 'displayState':
                # refresh from updated Devices.xml
                self.logger.info(u"Upgrading states on device:{}".format(dev.name))
                self.logger.debug(u"current device:{}".format(dev))
                dev.stateListOrDisplayStateIdChanged()
                self.setDeviceState(dev, k_CLEAR)
                self.logger.debug(u"revised device:{}".format(dev))

        # new method to start the device
        if (dev.deviceTypeId == 'zoneGroup'):
            if dev.displayStateValRaw == "" or self.clearAllOnRestart:
                self.setDeviceState(dev, k_CLEAR)

        # For new devices (Those whose state or dsplayState = "") set them to Clear/off
        if (dev.deviceTypeId == 'alarmZone'):
            if dev.states['zoneState'] == "" or dev.states['displayState'] == "" or self.clearAllOnRestart:
                dev.updateStateOnServer(key='zoneState', value='Clear', uiValue='Clear')
                dev.updateStateOnServer(key='displayState', value='enabled', uiValue='Clear')

        self.logger.info(u"device comm start completed for {}".format(dev.name))

    ########################################################
    def deviceStopComm(self, dev):
        self.logger.info(u"called with Name:{}, id:{}, TypeId:{}".format(dev.name, dev.id, dev.deviceTypeId))

        # We always load the basic Dict because we need a zone number to device lookup in advanced mode too.
        try:
            basicBuildDevDict(self, dev, 'del')
        except Exception as err:
            self.logger.error(u"basicBuildDevDict error: {}".format(err))

        if self.ad2usbIsAdvanced:
            try:
                advancedBuildDevDict(self, dev, 'del')
            except Exception as err:
                self.logger.error(u"advancedBuildDevDict error: {}".format(err))

        self.logger.info(u"device comm stop completed for {}".format(dev.name))

    ########################################################
    # start/stop/restart Calls from Indigo
    ########################################################
    def runConcurrentThread(self):
        self.logger.info(u"Called")

        try:
            self.ad2usb.startComm(self.ad2usbIsAdvanced, self.ad2usbCommType,
                                  self.ad2usbAddress, self.ad2usbPort, self.ad2usbSerialPort)
            self.logger.info(u"ad2usb communication closed")
        except Exception as err:
            self.logger.error(u"startComm error: {}".format(err))

            # TO DO: not sure ad2usbRestart is used - remove?
            if self.ad2usbRestart:
                self.logger.info(u"Process completed, Restarting")
            else:
                self.logger.info(u"Process completed, Restarting")
            return

        # In case we are restarting after a config change, we should just start again
        if self.ad2usbRestart:
            self.ad2usbRestart = False
            # self.log = logger(self)
            self.ad2usb.startComm(self.ad2usbIsAdvanced, self.ad2usbCommType,
                                  self.ad2usbAddress, self.ad2usbPort, self.ad2usbSerialPort)

        self.logger.info(u"completed")

    ########################################################
    def stopConcurrentThread(self):
        self.logger.debug(u"Called")

        self.ad2usb.stopComm()

        self.logger.info(u"completed")

    ########################################################
    def restart(self):
        self.logger.debug(u"Called")

        # TO DO: remove some of these log entry once startComm and stopComm has logging
        self.logger.info(u"Stopping")

        self.ad2usb.stopComm()
        self.sleep(5)

        self.logger.info(u"Starting")
        self.ad2usb.startComm(self.ad2usbIsAdvanced, self.ad2usbCommType,
                              self.ad2usbAddress, self.ad2usbPort, self.ad2usbSerialPort)

        self.logger.info(u"completed")

    ########################################################
    # Action callbacks
    ########################################################
    def virtZoneManage(self, pluginAction):
        self.logger.info(u"Called")
        self.logger.debug(u"Received: {}".format(pluginAction))

        devId = pluginAction.deviceId
        virtDevice = indigo.devices[devId]
        virtZoneNumber = virtDevice.pluginProps['zoneNumber']

        action = pluginAction.props['virtualAction']
        panelMsg = 'L' + virtZoneNumber + action + '\r'
        self.logger.debug(u"Sending panel message: {}".format(panelMsg))
        self.ad2usb.panelMsgWrite(panelMsg)

        # TO DO: remove this an log success within panelMsgWrite
        self.logger.debug(u"Sent panel message: {}".format(panelMsg))

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
                # TO DO: check we can pass a dictionary or indigo dictionary to the logger
                self.logger.debug(u"Clear - state list: {}".format(self.ad2usb.zoneStateDict))
            elif action == '1':   # Fault
                uiValue = 'Fault'
                displayStateValue = 'faulted'
                zoneState = 'faulted'
                self.ad2usb.zoneStateDict[panelKeypadAddress].append(int(virtZoneNumber))
                self.ad2usb.zoneStateDict[panelKeypadAddress].sort()
                self.logger.debug(u"Fault - state list: {}".format(self.ad2usb.zoneStateDict))
            elif action == '2':   # Trouble
                uiValue = 'Trouble'
                displayStateValue = 'trouble'
                self.ad2usb.zoneStateDict[panelKeypadAddress].append(int(virtZoneNumber))
                self.ad2usb.zoneStateDict[panelKeypadAddress].sort()
                self.logger.debug(u"Trouble - state list: {}".format(self.ad2usb.zoneStateDict))
            else:
                # ERROR
                pass

            virtDevice.updateStateOnServer(key='zoneState', value=zoneState, uiValue=uiValue)
            virtDevice.updateStateOnServer(key='displayState', value=displayStateValue, uiValue=uiValue)
            panelDevice.updateStateOnServer(key='zoneFaultList', value=str(
                self.ad2usb.zoneStateDict[panelKeypadAddress]))

        self.logger.info(u"completed")

    ########################################################
    def panelMsgWrite(self, pluginAction):
        self.logger.info(u"Called")
        self.logger.debug(u"Received: {}".format(pluginAction))

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

        self.logger.debug(u"Created panel message: {}".format(panelMsg))

        self.ad2usb.panelMsgWrite(panelMsg, address)

        self.logger.debug(u"Sent panel message: {}".format(panelMsg))

        self.logger.debug(u"completed")

    ########################################################
    def panelQuckArmWrite(self, pluginAction):
        self.logger.info(u"Called")
        self.logger.debug(u"Received: {}".format(pluginAction))

        if pluginAction.props['keypadAddress'] == '':
            address = self.ad2usbKeyPadAddress
        else:
            address = pluginAction.props['keypadAddress']

        panelMsg = pluginAction.props['armingCode']

        self.logger.debug(u"Created panel message: {}".format(panelMsg))

        self.ad2usb.panelMsgWrite(panelMsg, address)

        self.logger.debug(u"completed")

    ########################################################
    def forceZoneStateChange(self, pluginAction):
        self.logger.info(u"Called")
        self.logger.debug(u"Received: {}".format(pluginAction))

        zoneDevice = indigo.devices[int(pluginAction.props['zoneDevice'])]

        if pluginAction.props['zoneState'] == 'clear':
            zoneDevice.updateStateOnServer(key='displayState', value='enabled', uiValue=u'Clear')
            zoneDevice.updateStateOnServer(key='zoneState', value='Clear')
        else:
            zoneDevice.updateStateOnServer(key='zoneState', value='faulted', uiValue=u'Fault')
            zoneDevice.updateStateOnServer(key='displayState', value='faulted', uiValue=u'Fault')

        self.logger.debug(u"completed")

    ########################################################
    # Functions for configuration dialogs
    ########################################################

    ########################################################
    # Let us know the operating mode inside of a device configuration window
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

        if UserCancelled is False:
            if (self.ad2usbIsAdvanced != valuesDict['isAdvanced']) or (self.ad2usbCommType != valuesDict['ad2usbCommType']):
                self.logger.info(u"The configuration changes require a plugin restart. Restarting now...")

                # TO DO: replace this with self.restart()
                thisPlugin = indigo.server.getPlugin("com.berkinet.ad2usb")
                try:
                    thisPlugin.restart(waitUntilDone=False)
                except Exception:
                    pass   # Hide any shutdown errors

            else:
                self.logger.info(u"Updated configuration values: {}".format(valuesDict))

                self.ad2usbCommType = valuesDict['ad2usbCommType']
                if self.ad2usbCommType == 'IP':
                    self.ad2usbAddress = valuesDict["ad2usbAddress"]
                    self.ad2usbPort = valuesDict["ad2usbPort"]
                else:
                    self.ad2usbSerialPort = valuesDict["ad2usbSerialPort"]

                self.logUnknownDevices = valuesDict["logUnknownDevices"]

                self.ad2usbIsAdvanced = valuesDict["isAdvanced"]
                self.logArmingEvents = valuesDict["logArmingEvents"]
                self.clearAllOnRestart = valuesDict["restartClear"]
                self.numPartitions = int(valuesDict.get("panelPartitionCount", '1'))

                self.ad2usbKeyPadAddress = valuesDict.get("ad2usbKeyPadAddress")

                self.indigoLoggingLevel = valuesDict.get("indigoLoggingLevel", logging.INFO)
                self.pluginLoggingLevel = valuesDict.get("pluginLoggingLevel", logging.INFO)
                self.isPanelLoggingEnabled = valuesDict.get("isPanelLoggingEnabled", False)

                # reset the logging levels
                self.__setLoggingLevels()

            self.logger.info(u"Plugin preferences have been updated")
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
            prId = "com.berkinet.ad2usb"

            # TO DO: replace prId with a variable filter
            for dev in indigo.devices.iter(prId):
                # self.numPartitions == 1:
                # TO DO: this code prevents replacing the keypad address with an empty one unless it was already empty
                # but why is it in the for loop?
                if valuesDict[u'panelKeypadAddress'] == '' and valuesDict[u'panelPartitionNumber'] == '1':
                    valuesDict[u'panelKeypadAddress'] = self.ad2usbKeyPadAddress

                if dev.deviceTypeId == 'ad2usbInterface' and dev.configured:
                    try:
                        if valuesDict[u'panelPartitionNumber'] == dev.pluginProps[u'panelPartitionNumber'] and dev.id != devId:
                            errorMsgDict[u'panelPartitionNumber'] = 'Found an existing panel device for the same parttion.\nOnly one panel device per partition is allowed.'
                            errorMsgDict[u'showAlertText'] = '-> Found an existing panel device for the same partition.\nOnly one panel device per partition is allowed.'
                            self.logger.error(u"Only one panel device per partition is allowed")
                            areErrors = True
                    except:
                        valuesDict[u'panelPartitionNumber'] = "1"

                    try:
                        if valuesDict[u'panelKeypadAddress'] == dev.pluginProps[u'panelKeypadAddress'] and dev.id != devId:
                            errorMsgDict[u'panelKeypadAddress'] = 'Found an existing panel device with the same keypad address.\nOnly one panel device per address is allowed.'
                            errorMsgDict[u'showAlertText'] = '-> Found an existing panel device with the same keypad address.\nOnly one panel device per address is allowed.'
                            self.logger.error(u"Only one panel device per address is allowed.")
                            areErrors = True
                    except:
                        valuesDict[u'panelKeypadAddress'] = self.ad2usbKeyPadAddress

                    if int(valuesDict['panelPartitionNumber']) > self.numPartitions:
                        errorMsgDict[u'panelPartitionNumber'] = 'Partition number selected greater than configured partitions.'
                        errorMsgDict[u'showAlertText'] = '-> Partition number selected greater than configured partitions.'

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
        self.logger.debug(u"called with:{}".format(valuesDict))

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

            self.logger.info(u"validation: ad2usb config string is:{}".format(cString))

            # figure out the url for communications with the ad2usb board
            if valuesDict['ad2usbCommType'] == 'IP':
                theURL = 'socket://' + valuesDict['ad2usbAddress'] + ':' + valuesDict['ad2usbPort']
                self.logger.info(u"validation: the url is:{}".format(theURL))

                # Communication validation test and board config
                self.logger.info(u"Attempting to connect to AlarmDecoder at:{}".format(theURL))
                alarmDecoderConnectionStatus = u"connecting"
                try:
                    testSocket = serial.serial_for_url(theURL, baudrate=115200)
                    self.logger.info(u"connected to AlarmDecoder")

                    alarmDecoderConnectionStatus = u"writing configuring"
                    self.logger.info(u"starting AlarmDecoder configuration")
                    self.logger.debug(u"configurations settings:{}".format(repr(cString)))
                    testSocket.write(cString)

                    # time.sleep(1)
                    # testSocket.write(cString2)

                    alarmDecoderConnectionStatus = u"closing connection"
                    self.logger.info(u"finished AlarmDecoder configuration")
                    testSocket.close()
                    self.logger.info(u"closed connection to AlarmDecoder")
                except Exception as err:
                    errorMsgDict = indigo.Dict()
                    errorMsgDict[u'ad2usbAddress'] = u"Could not open connection to the IP Address and Port entered. " + \
                        str(err)
                    self.logger.critical(u"AlarmDecoder connection failed when {} with error:{}".format(
                        alarmDecoderConnectionStatus, str(err)))
                    return (False, valuesDict, errorMsgDict)
        else:
            self.logger.info(u"validation: no test for USB device:{}".format(valuesDict['ad2usbAddress']))

        # User choices look good, so return True (client will then close the dialog window).
        self.logger.debug(u"completed")

        return (True, valuesDict)

    ########################################################
    def validateEventConfigUi(self, valuesDict, typeId, devId):
        self.logger.debug(u"Called")
        self.logger.debug(u"received: typeId:{} devId:{} valuesDict:{}".format(typeId, devId, valuesDict))

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
            self.logger.error(u"completed with errors")
            return (False, valuesDict, errorMsgDict)
        else:
            self.logger.info(u"Event id:{} validation completed".format(devId))
            return (True, valuesDict)

    ########################################################
    # Confg callback methods
    ########################################################
    def ConfigButtonPressed(self, valuesDict):
        self.logger.debug(u"Called")
        self.logger.debug(u"Received: {}".format(valuesDict))

        # figure out the url for communications with the ad2usb board
        if valuesDict['ad2usbCommType'] == 'IP':
            theURL = 'socket://' + valuesDict['ad2usbAddress'] + ':' + valuesDict['ad2usbPort']
        else:
            theURL = valuesDict['ad2usbSerialPort']

        self.logger.debug(u"the url is:{}".format(theURL))

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
                # TO DO: change logging to better track connection failures
                self.logger.debug(u"created new connection")

                linesRead = 0
                testSocket.write('C\r')
                while linesRead < 5:
                    adRead = ""
                    # adRead = testSocket.readline(eol='\n')
                    adRead = testSocket.readline()

                    if len(adRead) > 8 and adRead[0:8] == '!CONFIG>':
                        linesRead = 5
                        msg = adRead[8:-2]
                        valuesDict['msgControl'] = '1'

                    self.logger.debug(u"readline:{}, {}".format(str(adRead), str(linesRead)))
                    linesRead += 1

                if testSocket.isOpen():
                    testSocket.close()
            except Exception as err:
                if testSocket.isOpen():
                    testSocket.close()
                valuesDict['msgControl'] = '2'
                self.logger.error(u"config read connection failed: the url was:{} error:{}".format(theURL, str(err)))
                return valuesDict

        self.logger.debug(u"the raw config is:{}".format(msg))
        adConfig = re.split('&', msg)
        self.logger.debug(u"the split config is:{}".format(adConfig))

        confItem = re.split('=', adConfig[0])

        # Check that we got a valid config back from the ad2usb.  Maybe the firmware is too old.
        if len(confItem) < 2:
            valuesDict['msgControl'] = '3'
            self.logger.debug(u"Completed with invalid config")
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

            self.logger.debug(u"Completed with valid config")

            return valuesDict

    ########################################################
    # ConfiguUI callbacks from Actions and Devices
    def getPartitionList(self, filter="", valuesDict=None, typeId="", targetId=0):
        self.logger.debug(u"Called")

        myArray = []

        for panelKeypadAddress in self.panelsDict:
            partition = self.panelsDict[panelKeypadAddress]['partition']
            myArray.append((panelKeypadAddress, partition))

        self.logger.debug(u"Returned myArray:{}".format(myArray))
        self.logger.debug(u"Completed with valid config")

        return myArray

    ########################################################
    def getZoneList(self,  filter="", valuesDict=None, typeId="", targetId=0):
        self.logger.debug(u"Called")

        myArray = []

        for device in sorted(indigo.devices):
            if device.deviceTypeId == 'alarmZone':
                myArray.append((device.id, device.name))

        self.logger.debug(u"Returned myArray:{}".format(myArray))
        self.logger.debug(u"completed")

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

    def getAllZoneGroups(self):
        """
        returns an array of device.id [integer] for all Zone Group devices
        """
        self.logger.debug(u"called")

        zoneGroups = []

        try:
            # all devices
            for device in indigo.devices.iter("self"):
                # just the Zone Groups
                if device.deviceTypeId == 'zoneGroup':
                    zoneGroups.append(device.id)

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

        self.logger.debug(u"called with device id:{}".format(zoneGroupDeviceId))

        try:
            # get the Zone Group device provided
            device = indigo.devices[zoneGroupDeviceId]
            # check if we have the proptery
            if 'zoneDeviceList' in device.pluginProps.keys():
                # return if it is a list
                zoneList = device.pluginProps['zoneDeviceList']
                if isinstance(zoneList, list):
                    return zoneList
                else:
                    return []
            else:
                return []

        except Exception as err:
            self.logger.error(u"error retrieving Zones for Zone Groups:{} from Indigo, msg:{}".format(
                zoneGroupDeviceId, str(err)))

            # return an empty dictionary
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

    def getDeviceIdForZoneNumber(self, forZoneNumber=''):
        """
        returns the device.id (integer) for the Zone Number (Address) provided or 0 if not found

        **parameters**:
        forZoneNumber -- an string that is the Zone Number (Address)
        """

        self.logger.debug(u"called with zone number:{}".format(forZoneNumber))

        try:
            for device in indigo.devices.iter("self"):
                if device.deviceTypeId == 'alarmZone' or device.deviceTypeId == 'alarmZoneVirtual':
                    zoneNumber = device.pluginProps.get('zoneNumber', "NONE")
                    if zoneNumber == forZoneNumber:
                        return device.id

            # did not find device
            self.logger.error(u"Unable to find device id for zone number:{}".format(forZoneNumber))
            return 0

        except Exception as err:
            self.logger.error("Error trying to get device id for zone number:{}, error:{}".format(
                forZoneNumber, str(err)))
            return 0

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
            device = indigo.devices[forDeviceId]
            self.logger.debug(u"found device id:{}".format(forDeviceId))
            if 'zoneState' in device.pluginProps['states'].keys():
                zoneState = device.pluginProps['states']['zoneState']
                self.logger.debug(u"found zoneState:{} in device:{}".format(zoneState, device.name))
                return zoneState

            # did not find state
            self.logger.error(u"Unable to get Zone State for device:{} ({})".format(device.name, forDeviceId))
            return 'NOT_FOUND'

        except Exception as err:
            self.logger.error("Error trying to get zone state for device id:{}, error:{}".format(forDeviceId, str(err)))
            return 'ERROR'

    def updateAllZoneGroups(self):
        """
        updates all the applicable Zone Groups when a Zone changes. call this method after an alarm zone state update
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
                        if zoneState == k_FAULT:
                            zoneGroupIsFaulted = True
                            self.logger.debug(u"zone group:{} will be faulted".format(zoneGroupDevice.name))
                            break

                # determine the new zone group state
                newZoneGroupZoneState = k_CLEAR
                if zoneGroupIsFaulted:
                    newZoneGroupZoneState = k_FAULT

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

    def setDeviceState(self, forDevice, newState='NONE'):
        """
        updates the indio.device for a given device object (indigo.device) and new state (string)
        the state is the key - not the value in the Devices.xml

        **parameters**:
        forDevice -- a valid indigo.device object
        newState -- a string for the new state value - use k-constant
        """
        self.logger.debug(u"called with name:{}, id:{}, new state:{}".format(forDevice.name, forDevice.id, newState))

        try:
            if newState == k_CLEAR:
                forDevice.updateStateOnServer(key='zoneState', value=k_CLEAR)
                forDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
                # TO DO: consider removing on/off state
                forDevice.updateStateOnServer(key='onOffState', value=True)
            elif newState == k_FAULT:
                forDevice.updateStateOnServer(key='zoneState', value=k_FAULT)
                forDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
                # TO DO: consider removing on/off state
                forDevice.updateStateOnServer(key='onOffState', value=True)
            else:
                self.logger.error(u"Unable to set device name:{}, id:{}, to state:{}".format(
                    forDevice.name, forDevice.id, newState))

        except Exception as err:
            self.logger.error(u"Unable to set device:{}, to state:{}, error:{}".format(forDevice, newState, str(err)))

    ########################################
    # Indigo Event Triggers: Start and Stop
    ########################################
    def triggerStartProcessing(self, trigger):
        self.logger.info(u"called for trigger:{}".format(trigger.name))
        self.logger.debug(u"received trigger:{}".format(trigger))
        self.logger.debug(u"starting trigger dict:{}".format(self.triggerDict))

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
                self.logger.error(u"Error:{}".format(err))
        else:
            try:
                if event not in self.triggerDict:
                    self.triggerDict[event] = {}
                self.triggerDict[event][partition] = tid
            except Exception as err:
                self.logger.error(u"Error:{}".format(err))

        self.logger.debug(u"updated triggerDict:{}".format(self.triggerDict))
        self.logger.debug(u"completed")

    ########################################
    def triggerStopProcessing(self, trigger):
        self.logger.debug(u"called for trigger:{}".format(trigger.name))
        self.logger.debug(u"Received trigger:{}".format(trigger.name))

        event = trigger.pluginProps['indigoTrigger'][0]

        if event in self.triggerDict:
            self.logger.debug(u"trigger:{} found".format(trigger.name))
            del self.triggerDict[event]

        self.logger.debug(u"trigger:{} deleted".format(trigger.name))
        self.logger.debug(u"Completed")

    ########################################
    # def triggerUpdated(self, origDev, newDev):
    #   self.log.log(4, u"<<-- entering triggerUpdated: %s" % origDev.name)
    #   self.triggerStopProcessing(origDev)
    #   self.triggerStartProcessing(newDev)

    def __initPanelLogging(self):
        try:
            # setup a new logger
            panelLogger = logging.getLogger("panelMessageLog")
            self.logger.debug("panel logger created")

            # determine the filename from Indigo paths
            panelFileName = indigo.server.getLogsFolderPath(pluginId=self.pluginId) + "/" + "panelMessages.log"
            self.logger.info('set panel message log filename to: %s', panelFileName)

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
            self.error("unable to configure panel logging. disabling.")
            self.error("error msg:{}".format(str(err)))
            # turn off panel logging regardless of the preferences
            self.isPanelLoggingEnabled = False

    def __setPreferences(self, pluginPrefs):
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
        if pluginPrefs.get("indigoLoggingLevel", "9999") not in kLoggingLevelNames.keys():
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
        if pluginPrefs.get("pluginLoggingLevel", "9999") not in kLoggingLevelNames.keys():
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
        # since log settings are migrated or set to a default don't need
        # to deal with those
        self.ad2usbAddress = pluginPrefs.get("ad2usbAddress", '127.0.0.1')
        self.ad2usbPort = pluginPrefs.get("ad2usbPort")
        self.ad2usbSerialPort = pluginPrefs.get("ad2usbSerialPort")
        self.ad2usbCommType = pluginPrefs.get('ad2usbCommType')

        self.logUnknownDevices = pluginPrefs.get("logUnknownDevices", False)

        self.ad2usbIsAdvanced = pluginPrefs.get("isAdvanced")
        self.logArmingEvents = pluginPrefs.get("logArmingEvents")
        self.clearAllOnRestart = pluginPrefs.get("restartClear", False)
        self.numPartitions = int(pluginPrefs.get("panelPartitionCount", '1'))

        self.ad2usbKeyPadAddress = pluginPrefs.get("ad2usbKeyPadAddress")

        self.indigoLoggingLevel = pluginPrefs.get("indigoLoggingLevel", "INFO")  # 20 = INFO
        self.pluginLoggingLevel = pluginPrefs.get("pluginLoggingLevel", "INFO")  # 20 = INFO
        self.isPanelLoggingEnabled = pluginPrefs.get("isPanelLoggingEnabled", False)

    def __setLoggingLevels(self):
        # check for valid logging level first
        # we're using level names as strings in the PluginConfig.xml and logging uses integers
        if self.indigoLoggingLevel in kLoggingLevelNames.keys():
            self.indigo_log_handler.setLevel(kLoggingLevelNames[self.indigoLoggingLevel])
            self.logger.info(u"Indigo logging level set to:{} ({})".format(
                self.indigoLoggingLevel, kLoggingLevelNames[self.indigoLoggingLevel]))
        else:
            self.indigo_log_handler.setLevel(logging.INFO)
            self.logger.error(u"Invalid Indigo logging level:{} - setting level to INFO".format(self.indigoLoggingLevel))

        if self.pluginLoggingLevel in kLoggingLevelNames.keys():
            self.plugin_file_handler.setLevel(kLoggingLevelNames[self.pluginLoggingLevel])
            self.logger.info(u"Plugin logging level set to:{} ({})".format(
                self.pluginLoggingLevel, kLoggingLevelNames[self.pluginLoggingLevel]))
        else:
            self.plugin_file_handler.setLevel(logging.INFO)
            self.logger.error(
                u"Invalid pluging logging level:{} - setting level to INFO".format(self.pluginLoggingLevel))
