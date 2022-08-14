import re
import SAIC_EventCodes
import AD2USB_Constants

# valid AlarmDecoder MessageType regardless of firmware - used to establish valid message or not
kVALIDMESSAGEHEADERS = ['!>', '!CONFIG', '!AUI', '!CRC', '!EXP', '!ERR', '!KPE', '!KPM', '!LRR', '!REL', '!RFX', '!VER']

# we define internally our own message types that resemble the protocol
# note LRR and LR2 to address two different firmware versions
kVALIDMESSAGETYPES = ['PROMPT', 'CONFIG', 'AUI', 'CRC', 'EXP',
                      'ERR', 'KPE', 'KPM', 'LRR', 'LR2', 'REL', 'RFX', 'VER', 'UNK']

# valid AlarmDecoder capabilties
kCAPABILITIES = ['TX', 'RX', 'SM', 'VZ', 'RF', 'ZX', 'RE', 'AU', '3X', 'CG', 'DD',
                 'MF', 'LR', 'L2', 'KE', 'MK', 'CB', 'DS', 'ER', 'CR']

# define valid CONFIG setting we will store
kVALID_CONFIG_ITEMS = ['ADDRESS', 'EXP', 'REL', 'LRR', 'DEDUPLICATE']


class Message(object):
    """
    This object is initialized with a string from the AlarmDecoder and an optional but recommended firmware version.
    It will parse the message. You can then identify details about the message via properties and methods of the class.

    Common properties are:
    isValidMessage (boolean) - is this a valid AlarmDecoder message
    needsProcessing (boolean) - is this a message that needs to be processed
    messageType (char) - a 3 letter char that matches the AlarmDecoder protocol for message types
    """

    def __init__(self, messageString='', firmwareVersion='', logger=None):
        # init some internal properties first
        # a message can be valid but we don't process it - PROMPT, ERR, CRC, UNK
        self.isValidMessage = False
        self.invalidReason = ''
        self.needsProcessing = False
        self.messageType = 'UNK'
        self.messageString = ''

        # check for valid firmware and logger parameters
        if firmwareVersion == 'V2.2a.6':
            self.firmwareVersion = firmwareVersion
        elif firmwareVersion == 'V2.2a.8.8':
            self.firmwareVersion = firmwareVersion

        elif firmwareVersion == '':
            self.isValidMessage = False
            self.needsProcessing = False
            self.invalidReason = 'firmware not provided'
        else:
            self.isValidMessage = False
            self.needsProcessing = False
            self.invalidReason = 'Invalid firmware detected:{}. Only V2.2a.6 or V2.2a.8.8 are supported.'.format(
                firmwareVersion)

        # check for logger parameters
        if logger is None:
            self.isValidMessage = False
            self.invalidReason = 'logger not provided in AlarmDecoderMessage(__init__)'
            return
        else:
            self.logger = logger

        # Message Types
        # Informational: !AUI, !CRC, !ERR, !EXP, !KPE, !KPM, !LRR, !REL, !RFX, !VER]
        # Prompts: !>
        # All others are Keypad = but keypad starts with [ or !KPM
        try:
            self.messageString = messageString.rstrip()
            self.messageDetails = {}

            self.logger.debug('received message:{}'.format(self.messageString))

            if len(messageString) > 0:
                self.__processMessage()

        except Exception as err:
            self.logger.warning('cannot read message:{} - error:{}'.format(messageString, str(err)))
            self.isValidMessage = False
            self.invalidReason = 'message could not be read'
            self.needsProcessing = False
            self.messageType = 'UNK'

    def __processMessage(self):

        # order these by most common messages for some efficiency
        if ((self.messageString[0:4] == '!KPM') or (self.messageString[0:1] == '[')):
            self.isValidMessage = True
            self.messageType = 'KPM'
            self.logger.debug('read {} message type - starting parsing'.format(self.messageType))
            self.parseMessage_KPM()

        elif self.messageString[0:7] == '!CONFIG':
            self.isValidMessage = True
            self.messageType = 'CONFIG'
            self.logger.debug('read {} message type - starting parsing'.format(self.messageType))
            self.parseMessage_CONFIG()

        elif self.messageString[0:4] == '!VER':
            self.isValidMessage = True
            self.messageType = 'VER'
            self.logger.debug('read {} message type - starting parsing'.format(self.messageType))
            self.parseMessage_VER()

        elif (self.messageString[0:2] == '!>'):
            self.isValidMessage = True
            self.messageType = 'PROMPT'
            self.needsProcessing = False
            self.logger.debug('read {} message type - no parsing needed'.format(self.messageType))

        elif self.messageString[0:4] == '!AUI':
            self.isValidMessage = True
            self.messageType = 'AUI'
            self.logger.debug('read {} message type - starting parsing'.format(self.messageType))
            self.parseMessage_AUI()

        elif self.messageString[0:4] == '!RFX':
            self.isValidMessage = True
            self.messageType = 'RFX'
            self.logger.debug('read {} message type - starting parsing'.format(self.messageType))
            self.parseMessage_RFX()

        elif self.messageString[0:4] == '!EXP':
            self.isValidMessage = True
            self.messageType = 'EXP'
            self.logger.debug('read {} message type - starting parsing'.format(self.messageType))
            self.parseMessage_EXP()

        elif self.messageString[0:4] == '!REL':
            self.isValidMessage = True
            self.messageType = 'REL'
            self.logger.debug('read {} message type - starting parsing'.format(self.messageType))
            self.parseMessage_REL()

        elif self.messageString[0:4] == '!LRR':
            if self.firmwareVersion == 'V2.2a.8.8':
                self.isValidMessage = True
                self.messageType = 'LR2'
                self.logger.debug(
                    'read {} ({}) message type - starting parsing'.format(self.messageType, self.firmwareVersion))
                self.parseMessage_LR2()
            elif self.firmwareVersion == 'V2.2a.6':
                self.isValidMessage = True
                self.messageType = 'LRR'
                self.logger.debug(
                    'read {} ({}) message type - starting parsing'.format(self.messageType, self.firmwareVersion))
                self.parseMessage_LRR()
            elif self.firmwareVersion == '':
                self.logger.warning(
                    'cannot read {} message type - firmware version not read from AlarmDecoder yet'.format(self.messageType))
                self.setMessageToInvalid('Unidentified firmware')
            else:
                # need firmware version to process LRR
                self.logger.error(
                    'Cannot read {} message type - unsupported firmware version:{}. Only V2.2a.6 or V2.2a.8.8 versions are supported.'.format(self.messageType, self.firmwareVersion))
                self.setMessageToInvalid('Unsupported firmware')

        elif (self.messageString[0:8] == '!Sending') or (self.messageString[0:8] == '!setting') or (self.messageString[0:8] == '!Reading') or (self.messageString[0:5] == '!UART'):
            self.isValidMessage = True
            self.messageType = 'PROMPT'
            self.needsProcessing = False
            self.logger.debug('read {} message type - no parsing needed'.format(self.messageType))

        elif self.messageString[0:4] == '!KPE':
            self.isValidMessage = True
            self.messageType = 'KPE'
            self.needsProcessing = False
            self.logger.debug('read {} message type - no parsing'.format(self.messageType))

        elif self.messageString[0:4] == '!ERR':
            self.isValidMessage = True
            self.messageType = 'ERR'
            self.logger.debug('read {} message type - starting parsing'.format(self.messageType))
            self.parseMessage_ERR()

        elif self.messageString[0:4] == '!CRC':
            self.isValidMessage = True
            self.messageType = 'CRC'
            self.needsProcessing = False
            self.logger.debug('read {} message type - starting parsing'.format(self.messageType))

        else:
            self.isValidMessage = False
            self.messageType = 'UNK'
            self.needsProcessing = False
            self.logger.warning('Unknown message type:{} - skipping'.format(self.messageString))

    def parseMessage_KPM(self):
        """
        This parses the keypad message starting with !KPM of simply ']'. Example:

        01234567890123456789012345678901234567890123456789012345678901234567890
        [00110011000000003A--],010,[f70700000010808c18020000000000],"ARMED ***STAY** ZONE BYPASSED "

        There are 4 main parts to the message. Each becomes a property. Additional properties are created too.

        **properties created:**
        bitField (string) - bit string - see below (part 1)
        numericCode (string) - typically represents zero-padded base-10 integer (part 2)
        rawData (string) - the raw data of message (part 3)
        alphanumericKeypadMessage (string) (part 4)

        **additional properties created:**
        isSystemMessage (boolean) - keypad message if this is a System Message
        zoneNumberAsInt (int) - conversion of the numericCode (part 2) to an integer for the zone number
        isValidNumericCode (boolean) - sometimes numericCode may not be base 10 number (see NuTech docs)
                in this case we consider it a bad keypad message
        isBypassZone (boolean) - if message text start with BYPAS
        keypadDestinations (array of int) - the list of keypads this message is intended for
        keypadFlags (dictionary) - a dictionary with the following keys created based on bitField above.
                most are 0 or 1; except BEEPS (int), ERROR_REPORT (?), and ADEMCO_OR_DSC ("A or "D")
                READY, ARMED_AWAY, ARMED_HOME, BACKLIGHT, PGM_MODE, BEEPS, ZONES_BYPASSED, AC_ON,
                CHIME_MODE, ALARM_OCCURRED, ALARM_BELL_ON, BATTERY_LOW, ARMED_INSTANT, FIRE,
                CHECK_ZONE, ARMED_STAY_NIGHT, ERROR_REPORT, ADEMCO_OR_DSC
        """

        # return if not a KPM message
        if self.messageType != 'KPM':
            self.setMessageToInvalid('not a KPM message type')
            return

        try:
            # strip the !KPM: if it exists
            if self.messageString[:5] == '!KPM:':
                kpmMessage = self.messageString[5:]
            # if no !KPM header we expect first character to be '['
            elif self.messageString[0] == '[':
                kpmMessage = self.messageString
            # if not !KPM or '[' we don't have KPM message
            else:
                self.logger.warning('!KPM or [ not found at start of message:{}'.format(self.messageString))
                self.setMessageToInvalid('!KPM or [ not found at start of message')
                return

            # we now have a good KPM message so lets parse it
            # init the properites
            self.messageDetails['KPM'] = {}
            self.messageDetails['KPM']['isValidNumericCode'] = False
            self.messageDetails['KPM']['panelState'] = AD2USB_Constants.k_PANEL_UNK

            # text of message
            self.messageDetails['KPM']['isBypassZone'] = False
            self.messageDetails['KPM']['isPressForFaultMessage'] = False
            self.messageDetails['KPM']['isAlarmTripped'] = False
            self.messageDetails['KPM']['isCountdown'] = False
            self.messageDetails['KPM']['isFault'] = False
            self.messageDetails['KPM']['doesMessageContainZoneNumber'] = False
            self.messageDetails['KPM']['doesMessageZoneMatchNumericCode'] = False

            # split the message on comma
            kpmItems = re.split(',', kpmMessage)
            self.messageDetails['KPM']['bitField'] = kpmItems[0]
            self.messageDetails['KPM']['numericCode'] = kpmItems[1]
            self.messageDetails['KPM']['rawData'] = kpmItems[2]
            self.messageDetails['KPM']['alphanumericKeypadMessage'] = kpmItems[3]

            # process the bits - skipping the first char '['
            # char 0 = '[', char 1-20 = data, char 21 = ']'
            self.messageDetails['KPM']['keypadFlags'] = self.getKPMKeypadData(
                self.messageDetails['KPM']['bitField'][1:21])

            # get a zone number as int
            # if it contains non 0-9 is may be an ECP bus failure
            zoneAsInt = self.__getIntFromString(self.messageDetails['KPM']['numericCode'])
            if zoneAsInt is None:
                self.messageDetails['KPM']['isValidNumericCode'] = False
                self.messageDetails['KPM']['zoneNumberAsInt'] = 0  # should never be used
            else:
                self.messageDetails['KPM']['isValidNumericCode'] = True
                self.messageDetails['KPM']['zoneNumberAsInt'] = zoneAsInt

            # get keypad mask and determine if its a system message
            keypadMask = self.messageString[30:38]
            self.logger.debug('keypad bitmask is:{}'.format(keypadMask))
            if keypadMask == '0000000':
                self.messageDetails['KPM']['isSystemMessage'] = True
            else:
                self.messageDetails['KPM']['isSystemMessage'] = False

            # process the bitmask of the keypadMask for keypad destinations 0-31
            # we do this in pairs given how the data is structured per NuTech docs
            # byte 1:0-7, 2:8-15, 3:16-23, 4:24-31
            self.messageDetails['KPM']['keypadDestinations'] = []

            # we can loop thru the 4 pairs of 2 x hex digits and check the masks
            for hexPair in range(0, 4):
                # string is start of h*2, end h*2 + 2 = 0:2, 2:4, 4:6, 6:8
                keyPadHexPairAsString = keypadMask[hexPair*2:hexPair*2+2]
                # self.logger.debug('keypad bitmask:{} is:{}'.format(hexPair + 1, keyPadHexPairAsString))
                # HEX 0 and 1 - keypads 0-7, 8-15, 16-23, 24-31
                for i in range(0, 8):
                    if self.__getBitFromHexString(keyPadHexPairAsString, i) == 1:
                        # if true append the integer value to the array
                        # bit number to add = k * 8 - 0, 8, 16, 24
                        self.messageDetails['KPM']['keypadDestinations'].append(i+hexPair*8)

            # ##########
            # parse the alphanumeric message for certain cases
            # akm = alphanumericKeypadMessage
            akm = self.messageDetails['KPM']['alphanumericKeypadMessage']

            # Hit * for faults
            if " * " in akm:
                self.messageDetails['KPM']['isPressForFaultMessage'] = True

            # DISARM - Alarm Tripped
            elif akm[1:14] == "DISARM SYSTEM":
                self.messageDetails['KPM']['isAlarmTripped'] = True

            # BYPAS
            elif akm[1:6] == "BYPAS":
                # zoneNumberAsInt has bypassed zone details
                self.messageDetails['KPM']['isBypassZone'] = True
                zoneAsInt = self.__getIntFromString(akm[7:9])
                if zoneAsInt is None:
                    self.messageDetails['KPM']['doesMessageContainZoneNumber'] = False
                    self.messageDetails['KPM']['zoneFromMessage'] = None
                else:
                    self.messageDetails['KPM']['doesMessageContainZoneNumber'] = False
                    self.messageDetails['KPM']['zoneFromMessage'] = zoneAsInt

                # check if zone number in message text = numericCode field
                if self.messageDetails['KPM']['zoneFromMessage'] == self.messageDetails['KPM']['zoneNumberAsInt']:
                    self.messageDetails['KPM']['doesMessageZoneMatchNumericCode'] = True

            # ARMED .. May Exit Countdown
            elif ("ARMED" in akm) and ("Exit Now" in akm):
                self.messageDetails['KPM']['isCountdown'] = True
                self.messageDetails['KPM']['countdownTimeRemaining'] = self.messageDetails['KPM']['zoneNumberAsInt']

            # FAULT
            elif akm[1:6] == "FAULT":
                # zoneNumberAsInt has bypassed zone details
                self.messageDetails['KPM']['isFault'] = True
                zoneAsInt = self.__getIntFromString(akm[7:9])
                if zoneAsInt is None:
                    self.messageDetails['KPM']['doesMessageContainZoneNumber'] = False
                    self.messageDetails['KPM']['zoneFromMessage'] = None
                else:
                    self.messageDetails['KPM']['doesMessageContainZoneNumber'] = False
                    self.messageDetails['KPM']['zoneFromMessage'] = zoneAsInt

                # check if zone number in message text = numericCode field
                if self.messageDetails['KPM']['zoneFromMessage'] == self.messageDetails['KPM']['zoneNumberAsInt']:
                    self.messageDetails['KPM']['doesMessageZoneMatchNumericCode'] = True

            #
            # ########## END

            # determine the panel state
            if (self.getKPMattr(flag='READY') == 1) and (self.getKPMattr(flag='ARMED_AWAY') == 0) and (self.getKPMattr(flag='ARMED_HOME') == 0):
                self.messageDetails['KPM']['panelState'] = AD2USB_Constants.k_PANEL_READY

            elif (self.getKPMattr(flag='READY') == 0) and (self.getKPMattr(flag='ARMED_AWAY') == 1):

                # MAX
                if self.getKPMattr(flag='ARMED_INSTANT') == 1:
                    self.messageDetails['KPM']['panelState'] = AD2USB_Constants.k_PANEL_ARMED_MAX

                # AWAY
                else:
                    self.messageDetails['KPM']['panelState'] = AD2USB_Constants.k_PANEL_ARMED_AWAY

            elif (self.getKPMattr(flag='READY') == 0) and (self.getKPMattr(flag='ARMED_HOME') == 1):

                # INSTANT
                if (self.getKPMattr(flag='ARMED_INSTANT') == 1) and (self.getKPMattr(flag='ARMED_STAY_NIGHT') == 0):
                    self.messageDetails['KPM']['panelState'] = AD2USB_Constants.k_PANEL_ARMED_INSTANT

                # NIGHT STAY
                elif (self.getKPMattr(flag='ARMED_INSTANT') == 0) and (self.getKPMattr(flag='ARMED_STAY_NIGHT') == 1):
                    self.messageDetails['KPM']['panelState'] = AD2USB_Constants.k_PANEL_ARMED_NIGHT_STAY

                # STAY
                else:
                    self.messageDetails['KPM']['panelState'] = AD2USB_Constants.k_PANEL_ARMED_STAY

            elif (self.getKPMattr(flag='READY') == 0) and (self.getKPMattr(flag='ARMED_AWAY') == 0) and (self.getKPMattr(flag='ARMED_HOME') == 0):
                # this is a fault
                # first 3 bits are zero: READY = 0, AWAY = 0, HOME = 0
                # unless not a numeric in which case it is an error
                if self.messageDetails['KPM']['isValidNumericCode']:
                    self.messageDetails['KPM']['panelState'] = AD2USB_Constants.k_PANEL_FAULT
                else:
                    self.messageDetails['KPM']['panelState'] = AD2USB_Constants.k_PANEL_ERROR

            else:
                # we have an error or unknown
                self.messageDetails['KPM']['panelState'] = AD2USB_Constants.k_PANEL_UNK

            self.needsProcessing = True
            self.logger.debug('KPM message parsed:{}'.format(self.messageDetails['KPM']))

        except Exception as err:
            self.setMessageToInvalid('error processing KPM message')
            self.logger.warning('error processing KPM message:{} - error:{}'.format(self.messageString, str(err)))

    def getKPMKeypadData(self, bitString):
        """
        Take an string of 20 chars and returns a dictionary of elements set to value represeted by the bit

        **parameters**
        bitString (string) - a string of 20 chars - mostly 0 and 1 but some are characters
        """

        # Example: [1000000100000000----]
        # 1 = READY                           10 = ALARM OCCURRED STICKY BIT (cleared 2nd disarm)
        # 2 = ARMED AWAY  <*                  11 = ALARM BELL (cleared 1st disarm)
        # 3 = ARMED HOME  <*                  12 = BATTERY LOW
        # 4 = BACK LIGHT                      13 = ENTRY DELAY OFF (ARMED INSTANT/MAX) <*
        # 5 = Programming Mode                14 = FIRE ALARM
        # 6 = Beep 1-7 ( 3 = beep 3 times )   15 = CHECK ZONE - TROUBLE
        # 7 = A ZONE OR ZONES ARE BYPASSED    16 = PERIMETER ONLY (ARMED STAY/NIGHT)
        # 8 = AC Power                        17 = System specific error report
        # 9 = CHIME MODE                      18 = Ademco or DSC Mode A or D
        #                                     19 - 20 Unused
        # NOTE: V2.2a.6 has 17-20 unused
        # NOTE: V2.2a.8 has 19-20 unused

        # process 18 of the 20 bits by reading the string left to right
        # we use an ordered array here to create the dictionary items
        bitFieldNames = ['READY', 'ARMED_AWAY', 'ARMED_HOME', 'BACKLIGHT', 'PGM_MODE',
                         'BEEPS', 'ZONES_BYPASSED', 'AC_ON', 'CHIME_MODE', 'ALARM_OCCURRED',
                         'ALARM_BELL_ON', 'BATTERY_LOW', 'ARMED_INSTANT', 'FIRE', 'CHECK_ZONE',
                         'ARMED_STAY_NIGHT', 'ERROR_REPORT', 'ADEMCO_OR_DSC']

        # initialize return value dictionary with None for each item
        returnDictionary = {}
        for item in bitFieldNames:
            returnDictionary[item] = None

        # transform all the bitfields into a dictionary with int or char values
        # the bitString is 1 to N; bit the key from the array is i-1
        i = 1
        for bit in bitString:
            # skip if we exceed the number of array bit field name items
            if (i <= len(bitFieldNames)):
                # value may be an int or char
                if bit in '0123456789':
                    # make it an int - usually 0 or 1
                    returnDictionary[bitFieldNames[i-1]] = int(bit)
                else:
                    # keep it a string
                    returnDictionary[bitFieldNames[i-1]] = bit

            # increment the bitsField array counter
            i = i + 1

        return returnDictionary

    def parseMessage_VER(self):
        """
        Parses the VER message type.
        Example: !VER:ffffffff,V2.2a.8.2,TX;RX;SM;VZ;RF;ZX;RE;AU;3X;CG;DD;MF;LR;KE;MK;CB;DS;ER

        **properties created:**
        serialNumber (string)
        firmwareVersion (string) (can be used to call AlarmDecoderMessage)
        capabilities (dictionary) - dictionary with a capability and True as the value
        """
        # return if not a VER message
        if self.messageType != 'VER':
            self.setMessageToInvalid('not a VER message type')
            return

        try:
            self.messageDetails['VER'] = {}
            self.messageDetails['VER']['serialNumber'] = ''
            self.messageDetails['VER']['firmwareVersion'] = ''

            # set all possible capabilities to False
            # this allows us to check regardless of firmware version
            self.messageDetails['VER']['capabilties'] = {}
            for capability in kCAPABILITIES:
                self.messageDetails['VER']['capabilties'][capability] = False

            # strip first 5 chars from the message - !VER:
            versionMessage = self.messageString[5:]

            # serial, firmware, capabilties = split on comma
            versionMessageItems = re.split(',', versionMessage)
            self.serialNumber = versionMessageItems[0]
            self.firmwareVersion = versionMessageItems[1]
            capabiltiesString = versionMessageItems[2]

            # capabilties dict = split on semicolon and build a dict
            for capability in re.split(';', capabiltiesString):
                self.messageDetails['VER']['capabilties'][capability] = True

            self.needsProcessing = True
            self.logger.debug('VER message parsed:{}'.format(self.messageDetails['VER']))

        except Exception as err:
            self.setMessageToInvalid('error processing VER message')
            self.logger.warning('error processing VER message:{} - error:{}'.format(self.messageString, str(err)))

    def parseMessage_CONFIG(self):
        """
        Parses the CONFIG message type.
        Example: !CONFIG>ADDRESS=18&CONFIGBITS=ff00&LRR=N&EXP=NNNNN&REL=NNNN&MASK=ffffffff&DEDUPLICATE=N

        **properties created:**
        configMessageString - the part of the message after '!CONFIG>'
        keypadAddress - same as flag['ADDRESS']
        flags (dictionary) - with key values of: MODE, ADDRESS, CONFIGBITS, MASK, EXP, REL, LRR, DEDUPLICATE
        """
        # return if not a VER message
        if self.messageType != 'CONFIG':
            self.setMessageToInvalid('not a CONFIG message type')
            return

        try:
            self.messageDetails['CONFIG'] = {}
            self.messageDetails['CONFIG']['flags'] = {}
            self.messageDetails['CONFIG']['keypadAddress'] = ''

            # strip first 8 chars from the message - !CONFIG>
            configMessage = self.messageString[8:]
            self.messageDetails['CONFIG']['configMessageString'] = configMessage

            configItems = re.split('&', configMessage)

            for oneConfig in configItems:
                configParam = re.split('=', oneConfig)

                # only process parameters we manage so we never change them
                # see the constant kVALID_CONFIG_ITEMS at the top of this file
                if (configParam[0] in kVALID_CONFIG_ITEMS):
                    self.messageDetails['CONFIG']['flags'][configParam[0]] = configParam[1]
                # skip parameters we don't manage
                else:
                    pass

            # update keypad address property of the message object
            if 'ADDRESS' in self.messageDetails['CONFIG']['flags'].keys():
                self.messageDetails['CONFIG']['keypadAddress'] = self.messageDetails['CONFIG']['flags']['ADDRESS']

            self.needsProcessing = True
            self.logger.debug('CONFIG message parsed:{}'.format(self.messageDetails['CONFIG']))

        except Exception as err:
            self.setMessageToInvalid('error processing CONFIG message')
            self.logger.warning('error processing CONFIG message:{} - error:{}'.format(self.messageString, str(err)))

    def parseMessage_RFX(self):
        """
        Parses the RFX message type.
        Example: !RFX:0180036,80

        **properties created:**
        serialNumber (string) - the 7-digit serial number of the device the message originated from
        data (string) - data is an 8-bit hex message with several indicators. See below.
        bits (dictionary) - see below for keys - all are bolean:
            1 - UNK1 - Unknown - Seems that the loop indicators should be ignored if set.
            2 - LOWBAT - Low battery indication
            3 - SUP - Supervision required indication
            4 - UNK4 - Unknown
            5 - LOOP3 - Loop #3 indication
            6 - LOOP2 - Loop #2 indication
            7 - LOOP4 - Loop #4 indication
            8 - LOOP1 - Loop #1 indication

        For data - Please refer to the 5800 SERIES TRANSMITTER INPUT LOOP IDENTIFICATION section
        of your programming manual for what the loops relate to for your specific device
        """
        # double check the message type
        if self.messageType != 'RFX':
            self.setMessageToInvalid('not an RFX message')
            return

        try:
            self.messageDetails['RFX'] = {}
            self.messageDetails['RFX']['serialNumber'] = ''
            self.messageDetails['RFX']['data'] = ''
            self.messageDetails['RFX']['bits'] = {}

            # strip first 5 chars from the message - !RFX:
            messageText = self.messageString[5:]
            self.logger.debug('RFX message data items are:{}'.format(messageText))

            # serial number, data = split on comma
            messageItems = re.split(',', messageText)
            self.messageDetails['RFX']['serialNumber'] = messageItems[0]
            self.messageDetails['RFX']['data'] = messageItems[1]

            # convert data to an int value
            dataAsInt = self.__hexStringToInt(self.messageDetails['RFX']['data'])
            if dataAsInt is None:
                self.logger.warning(
                    'RFX parsing - data field is not a valid hex value in message:{}'.format(self.messageString))
                self.setMessageToInvalid('data field is not a valid hex value')
                return
            else:

                self.logger.debug('RFX message data value is:{}'.format(dataAsInt))
                # determine if its bit flags
                bitFlags = ['UNK1', 'LOWBAT', 'SUP', 'UNK4', 'LOOP3', 'LOOP2', 'LOOP4', 'LOOP1']
                for i in range(0, 8):
                    flagSet = self.__getBitFromInt(dataAsInt, i)
                    # self.logger.debug("data:{} ({}), bit:{} is set to:{}".format(self.messageDetails['RFX']['data'], dataAsInt, i, flagSet))
                    if flagSet == 1:
                        # if true set the flag to True
                        self.messageDetails['RFX']['bits'][bitFlags[i]] = True
                    else:
                        self.messageDetails['RFX']['bits'][bitFlags[i]] = False

                self.needsProcessing = True
                self.logger.debug('RFX message parsed:{}'.format(self.messageDetails['RFX']))

        except Exception as err:
            self.setMessageToInvalid('error parsing RFX message')
            self.logger.warning('error processing RFX message:{} - error:{}'.format(self.messageString, str(err)))

    def parseMessage_LRR(self):
        """
        Parses the older v2.2a.6 firmware LRR message type. See parseMessage_LR2 for newer format.
        Example: !LRR:012,1,ARM_STAY

        **properties created:**
        eventData (string) - either the user number of the person performing the action or the zone that was bypassed
        user (string) - if its a user event this is the same as eventData, blank otherwise
        partition (int) - the panel partition the event applies to; 0 indicates that it's destined for all partitions
        eventType (string) - see below for valid values:
        OPEN, ARM_AWAY, ARM_STAY, ACLOSS, AC_RESTORE, LOWBAT, LOWBAT_RESTORE, RFLOWBAT,
        RFLOWBAT_RESTORE, TROUBLE, TROUBLE_RESTORE', ALARM_PANIC, ALARM_FIRE, ALARM_AUDIBLE,
        ALARM_SILENT, ALARM_ENTRY, ALARM_AUX, ALARM_PERIMETER, ALARM_TRIPPED
        """
        if self.messageType != 'LRR':
            self.setMessageToInvalid('not an LRR message')
            return

        try:
            self.messageDetails['LRR'] = {}
            self.messageDetails['LRR']['eventData'] = ''
            self.messageDetails['LRR']['partition'] = 0
            self.messageDetails['LRR']['user'] = ''
            self.messageDetails['LRR']['eventType'] = ''
            self.messageDetails['LRR']['isUserEvent'] = False
            self.messageDetails['LRR']['isZoneEvent'] = False
            self.messageDetails['LRR']['isAllPartitions'] = False

            # strip first 5 chars from the message - !EXP:
            messageText = self.messageString[5:]

            # serial number, data = split on comma
            messageItems = re.split(',', messageText)
            self.messageDetails['LRR']['eventData'] = messageItems[0]
            self.messageDetails['LRR']['eventDataAsInt'] = int(messageItems[0])
            self.messageDetails['LRR']['partition'] = int(messageItems[1])
            self.messageDetails['LRR']['eventType'] = messageItems[2]

            # if parition == 0 then partition is ALL
            if self.messageDetails['LRR']['partition'] == 0:
                self.messageDetails['LRR']['isAllPartitions'] = True

            # determine valid event type and user vs. paritition event
            # triggers are currently: first 19 lines
            # added ALARM_RESTORE in 3.1.1 - not documented in AlarmDecoder protocol
            validLRREvents = {
                'OPEN': {'type': 'user', 'desc': 'Indicates that the alarm is disarmed'},
                'ARM_AWAY': {'type': 'user', 'desc': 'Indicates that the system was armed AWAY'},
                'ARM_STAY': {'type': 'user', 'desc': 'Indicates that the system was armed STAY'},
                'ACLOSS': {'type': 'zone', 'desc': 'Indicates that AC power was lost'},
                'AC_RESTORE': {'type': 'zone', 'desc': 'Indicates that AC power was restored'},
                'LOWBAT': {'type': 'zone', 'desc': 'Low battery indication'},
                'LOWBAT_RESTORE': {'type': 'zone', 'desc': 'Indicates that the low battery has been restored'},
                'RFLOWBAT': {'type': 'zone', 'desc': 'Low battery indication for the RF transmitter'},
                'RFLOWBAT_RESTORE': {'type': 'zone', 'desc': 'Indicates that the low battery on the RF transmitter has been restored.'},
                'TROUBLE': {'type': 'zone', 'desc': 'Indicates that a zone is reporting a tamper or failure'},
                'TROUBLE_RESTORE': {'type': 'zone', 'desc': 'Indicates that the trouble event was restored'},
                'ALARM_AUDIBLE': {'type': 'zone', 'desc': 'Indicates that an audible alarm is in progress'},
                'ALARM_AUX': {'type': 'zone', 'desc': 'Indicates that an auxiliary alarm type was triggered'},
                'ALARM_ENTRY': {'type': 'zone', 'desc': 'Indicates that there was an entry alarm'},
                'ALARM_FIRE': {'type': 'zone', 'desc': 'Indicates that there is a fire'},
                'ALARM_PANIC': {'type': 'zone', 'desc': 'Indicates that there is a panic'},
                'ALARM_PERIMETER': {'type': 'zone', 'desc': 'Indicates that there was a perimeter alarm'},
                'ALARM_SILENT': {'type': 'zone', 'desc': 'Indicates that there was a silent alarm'},
                'ALARM_TRIPPED': {'type': 'zone', 'desc': 'Alarm Tripped'},
                'ALARM_EXIT_ERROR': {'type': 'zone', 'desc': 'Indicates an error when a zone is not closed during arming'},
                'BYPASS': {'type': 'zone', 'desc': 'Indicates that a zone has been bypassed'},
                'BYPASS_RESTORE': {'type': 'zone', 'desc': 'Indicates that the bypassed zone was restored'},
                'CANCEL': {'type': 'user', 'desc': 'Indicates that the alarm was canceled after second disarm'},
                'TEST_CALL': {'type': 'zone', 'desc': 'Indicates a phone test when in testing mode'},
                'TEST_RESTORE': {'type': 'zone', 'desc': 'Indicates that a zone was restored in testing mode'},
                'RESTORE': {'type': 'zone', 'desc': 'Indicates that the alarm was restored'},
                'ALARM_RESTORE': {'type': 'zone', 'desc': 'Indicates that the alarm was restored'}
                }

            # build list of zone vs. user types
            LRRUserEvents = []
            LRRZoneEvents = []
            for oneType in validLRREvents.keys():
                if validLRREvents[oneType]['type'] == 'user':
                    LRRUserEvents.append(oneType)
                elif validLRREvents[oneType]['type'] == 'zone':
                    LRRZoneEvents.append(oneType)

            # check if it is a known LRR message event type
            if self.messageDetails['LRR']['eventType'] in validLRREvents.keys():
                self.messageDetails['LRR']['isKnownLRR'] = True
                self.needsProcessing = True

                # next determine if its a zone of user message
                if self.messageDetails['LRR']['eventType'] in LRRUserEvents:
                    self.messageDetails['LRR']['isUserEvent'] = True
                    self.messageDetails['LRR']['user'] = self.messageDetails['LRR']['eventData']
                elif self.messageDetails['LRR']['eventType'] in LRRZoneEvents:
                    self.messageDetails['LRR']['isZoneEvent'] = True

            else:
                self.logger.warning('Unknown LRR (v2.2a.6) eventType:{} message parsed:{}'.format(
                    self.messageDetails['LRR']['eventType'], self.messageDetails['LRR']))

                self.logger.warning('Post this messages in the Indigo User Forum')
                self.messageDetails['LRR']['isKnownLRR'] = False
                self.needsProcessing = False

            self.logger.debug('LRR (v2.2a.6) message parsed:{}'.format(self.messageDetails['LRR']))

        except Exception as err:
            self.setMessageToInvalid('error processing LRR message')
            self.logger.warning(
                'error processing LRR (v2.2a.6) message:{} - error:{}'.format(self.messageString, str(err)))

    def parseMessage_LR2(self):
        """
        Parses the newer v2.2a.8.8 firmware LRR message type. See parseMessage_LRR for older format.
        Example: !LRR:012,1,CID_1441,ff
        CID_QXYZ = "CID_", Event Qualifier (1 char), Event Code (3 char)

        **properties created:**
        eventData (string) - either the user number of the person performing the action or the zone that was bypassed
        partition (int) - the panel partition the event applies to; 0 indicates that it's destined for all partitions
        cid_message (string) - see below for valid values:
        report_code (string) - TBD (2 digit hex?)
        cid_event_qualifier (int) - 1 = New Event or Opening; 3 = New Restore or Closing; 6 = Previously reported condition still present (Status report)
        cid_event_code (string) - (3 Hex digits 0-9,B-F) Event codes are 3 hex digits and are broken down in classes by the first digit.
            100 Alarms
            200 Supervisory
            300 Troubles
            400 Open/Close REMOTE ACCESS
            500 Bypass/Disables
            600 TEST/MISC
        """
        if self.messageType != 'LR2':
            self.setMessageToInvalid('not an LR2 message')
            return

        try:
            progressMessage = 'started...'
            self.messageDetails['LR2'] = {}
            self.messageDetails['LR2']['eventData'] = ''
            self.messageDetails['LR2']['partition'] = 0
            self.messageDetails['LR2']['user'] = ''
            self.messageDetails['LR2']['eventType'] = ''
            self.messageDetails['LR2']['isUserEvent'] = False
            self.messageDetails['LR2']['isZoneEvent'] = False
            self.messageDetails['LR2']['isAllPartitions'] = False

            self.messageDetails['LR2']['cid_message'] = ''
            self.messageDetails['LR2']['report_code'] = ''

            self.messageDetails['LR2']['cid_event_qualifier'] = ''
            self.messageDetails['LR2']['cid_event_code'] = ''

            progressMessage = 'Values initialized'

            # strip first 5 chars from the message - !LRR:
            messageText = self.messageString[5:]
            progressMessage = 'LRR stripped'

            # eventData, partition, cid_message, report_code = split on comma
            messageItems = re.split(',', messageText)
            self.messageDetails['LR2']['eventData'] = messageItems[0]
            self.messageDetails['LR2']['partition'] = int(messageItems[1])
            self.messageDetails['LR2']['cid_message'] = messageItems[2]
            self.messageDetails['LR2']['report_code'] = messageItems[3]
            self.logger.debug("message split:{}".format(self.messageDetails))

            # if parition == 0 then partition is ALL
            if self.messageDetails['LR2']['partition'] == 0:
                self.messageDetails['LR2']['isAllPartitions'] = True

            progressMessage = 'Partitions checked'

            # additional parsing of CID string
            # check that it starts with CID_ chars 0-3
            # CID event qualifier is char 4
            # CID event code is chars 5-7
            if self.messageDetails['LR2']['cid_message'][0:4] == 'CID_':
                self.messageDetails['LR2']['cid_event_qualifier'] = self.messageDetails['LR2']['cid_message'][4]
                self.messageDetails['LR2']['cid_event_code'] = self.messageDetails['LR2']['cid_message'][5:8]
            else:
                self.setMessageToInvalid('CID string not found')
                self.logger.warning('LR2 message failed to parse - CID not found:{}'.format(self.messageDetails['LR2']))
                return

            progressMessage = 'CID portion parsed'

            # a 3 digit code ex: 570
            cid_code = self.messageDetails['LR2']['cid_event_code']
            cid_event_qualifier = self.messageDetails['LR2']['cid_event_qualifier']
            self.logger.debug("SAIC code:{} and qualifier:{}".format(cid_code, cid_event_qualifier))

            # check if code exists in SAIC_EventCodes file
            progressMessage = 'Checking code...'
            if cid_code in SAIC_EventCodes.kCODE:

                self.logger.debug("found valid SAIC code:{}".format(cid_code))
                self.messageDetails['LR2']['isKnownCode'] = True

                # event description from SIA DC-05-1999.09
                self.messageDetails['LR2']['cid_event_string'] = SAIC_EventCodes.kCODE[cid_code][0]
                progressMessage = 'description found'

                # check if zone or user event
                if SAIC_EventCodes.kCODE[cid_code][1] == 'user':
                    self.messageDetails['LR2']['userCode'] = int(self.messageDetails['LR2']['eventData'])
                    self.messageDetails['LR2']['isUserEvent'] = True
                    progressMessage = 'user event found'

                elif SAIC_EventCodes.kCODE[cid_code][1] == 'zone':
                    self.messageDetails['LR2']['zoneNumber'] = int(self.messageDetails['LR2']['eventData'])
                    self.messageDetails['LR2']['isZoneEvent'] = True
                    progressMessage = 'zone event found'

                else:
                    self.logger.error('Unable to find user or zone setting in SAIC message file:{}'.format(
                        SAIC_EventCodes.kCODE[cid_code]))
                    # return without processing messsage
                    self.setMessageToInvalid('Unable to find user or zone setting')
                    return

            else:
                self.logger.warning('Unknown LR2 (v2.2a.8.8) CID code:{} message parsed:{}'.format(
                    cid_code, self.messageDetails['LR2']))
                self.setMessageToInvalid('Code {} not found in SAIC List'.format(cid_code))
                return

            # if we made it here we have a valid and parsed LR2 message so log it
            self.logger.debug("valid LR2 message parsed:{}".format(self.messageDetails['LR2']))

            # map the code to a valid Event - the events were defined as old LRR message types
            # see the SAIC_EventCodes file for mapping
            # and set the event type property which matches Events.xml triggers
            if cid_code in SAIC_EventCodes.cid_code_to_event:
                if cid_event_qualifier in SAIC_EventCodes.cid_code_to_event[cid_code]:
                    self.messageDetails['LR2']['eventType'] = SAIC_EventCodes.cid_code_to_event[cid_code][cid_event_qualifier]
                    self.logger.debug("message:{},{} mapped to:{}".format(
                        cid_code, cid_event_qualifier, self.messageDetails['LR2']['eventType']))
                else:
                    # log that we don't have an event qualified mapping
                    self.logger.debug("LR2 message code found but event qualifier not mapped to event")
                    if self.logUnknownLRRMessages:
                        self.logger.info(
                            "Unknown LRR Message Event Qualifier for known Code:{}".format(self.messageString))

            else:
                # log that we don't have code a mapping
                self.logger.debug("LR2 message code not mapped to event")
                if self.logUnknownLRRMessages:
                    self.logger.info("Unknown LRR Message Code:{}".format(self.messageString))

            # pass back to process the message
            self.needsProcessing = True
            self.logger.debug('LRR (v2.2a.8.8) LR2 message parsed:{}'.format(self.messageDetails['LR2']))

        except Exception as err:
            self.setMessageToInvalid('error parsing LR2 message')
            self.logger.warning(
                'Error processing LRR/LR2 (v2.2a.8.8) after:{} - message:{} - error:{}'.format(progressMessage, self.messageString, str(err)))

    def parseMessage_AUI(self):
        """
        Parses the AUI message type.
        Example: !AUI:126600000000656c02456cf5ec01017f0002

        **properties created:**
        data (string) - large binary blob that's destined for a graphical panel
        """
        try:
            if self.messageType != 'AUI':
                self.setMessageToInvalid('not an AUI message')
                return

            # else its and AUI message
            self.messageDetails['AUI'] = {}
            self.messageDetails['AUI']['data'] = ''

            # strip first 5 chars from the message - !AUI:
            self.messageDetails['AUI']['data'] = self.messageString[5:]

            self.needsProcessing = True
            self.logger.debug('AUI message parsed:{}'.format(self.messageDetails['AUI']))

        except Exception as err:
            self.setMessageToInvalid('error parsing AUI message')
            self.logger.warning('error processing AUI message:{} - error:{}'.format(self.messageString, str(err)))

    def parseMessage_EXP(self):
        """
        Parses the EXP message type.
        Example: !EXP:07,01,00

        **properties created:**
        zoneExpanderAddress (string) - the address that the zone expander occupies
        expanderChannel (string) - the channel generating the message
        data (string) - 00 and 01 indicate that the zone is restored and faulted, respectively
        isFaulted - True or False
        """
        if self.messageType == 'EXP':
            try:
                self.messageDetails['EXP'] = {}
                self.messageDetails['EXP']['zoneExpanderAddress'] = ''
                self.messageDetails['EXP']['expanderChannel'] = ''
                self.messageDetails['EXP']['data'] = ''
                self.messageDetails['EXP']['isFaulted'] = None

                # strip first 5 chars from the message - !EXP:
                messageText = self.messageString[5:]

                # zone expander address, channel, data = split on comma
                messageItems = re.split(',', messageText)
                self.messageDetails['EXP']['zoneExpanderAddress'] = messageItems[0]
                self.messageDetails['EXP']['expanderChannel'] = messageItems[1]
                self.messageDetails['EXP']['data'] = messageItems[2]

                # determine if its faulted
                if self.messageDetails['EXP']['data'] == '01':
                    self.messageDetails['EXP']['isFaulted'] = True
                elif self.messageDetails['EXP']['data'] == '00':
                    self.messageDetails['EXP']['isFaulted'] = False
                else:
                    self.messageDetails['EXP']['isFaulted'] = None

                self.needsProcessing = True
                self.logger.debug('EXP message parsed:{}'.format(self.messageDetails['EXP']))

            except Exception as err:
                self.setMessageToInvalid('error parsing EXP message')
                self.logger.warning('error processing EXP message:{} - error:{}'.format(self.messageString, str(err)))

    def parseMessage_REL(self):
        """
        Parses the REL message type.
        Example: !REL:12,01,00

        **properties created:**
        relayExpanderAddress (string) - the address that the relay expander occupies
        expanderChannel (string) - the channel generating the message
        data (string) - 00 and 01 indicate that the relay is opened and closed, respectively
        isOpen - True or False
        """
        if self.messageType == 'REL':
            try:
                self.messageDetails['REL'] = {}
                self.messageDetails['REL']['relayExpanderAddress'] = ''
                self.messageDetails['REL']['expanderChannel'] = ''
                self.messageDetails['REL']['data'] = ''
                self.messageDetails['REL']['isOpen'] = None

                # strip first 5 chars from the message - !EXP:
                messageText = self.messageString[5:]

                # zone expander address, channel, data = split on comma
                messageItems = re.split(',', messageText)
                self.messageDetails['REL']['relayExpanderAddress'] = messageItems[0]
                self.messageDetails['REL']['expanderChannel'] = messageItems[1]
                self.messageDetails['REL']['data'] = messageItems[2]

                # determine if its faulted
                if self.messageDetails['REL']['data'] == '00':
                    self.messageDetails['REL']['isOpen'] = True
                elif self.messageDetails['REL']['data'] == '01':
                    self.messageDetails['REL']['isOpen'] = False
                else:
                    self.messageDetails['REL']['isOpen'] = None

                self.needsProcessing = True
                self.logger.debug('REL message parsed:{}'.format(self.messageDetails['REL']))

            except Exception as err:
                self.setMessageToInvalid('error parsing REL message')
                self.logger.warning('error processing REL message:{} - error:{}'.format(self.messageString, str(err)))

    def parseMessage_ERR(self):
        """
        Parses the ERR message type.
        Example: !ERR:4,4,4

        **properties created:**
        errorCount (int) - a count of the errors reported by the AlarmDecoder
        errorsDetails (array of string) - a list of errors in string array format
        hasError (boolean) - True if an error was detected; False otherwise
        """
        if self.messageType != 'ERR':
            self.setMessageToInvalid('not an ERR message')
            return

        try:
            self.messageDetails['ERR'] = {}
            self.messageDetails['ERR']['errorsDetails'] = []
            self.messageDetails['ERR']['errorCount'] = 0
            self.messageDetails['ERR']['hasError'] = False

            # strip first 5 chars from the message - !ERR:
            messageText = self.messageString[5:]

            # check for no errors first
            if messageText == '0':
                self.messageDetails['ERR']['errorsDetails'] = []
                self.messageDetails['ERR']['errorCount'] = 0
                self.messageDetails['ERR']['hasError'] = False
            else:
                # we should have an array of errors
                messageItems = re.split(',', messageText)
                self.messageDetails['ERR']['errorsDetails'] = messageItems

                # get the count of errors
                self.messageDetails['ERR']['errorCount'] = len(messageItems)

                # test each error - if any are non-zero we have an error
                for anError in messageItems:
                    if anError != '0':
                        self.messageDetails['ERR']['hasError'] = True

            self.needsProcessing = True
            self.logger.debug('ERR message parsed:{}'.format(self.messageDetails['ERR']))

        except Exception as err:
            self.setMessageToInvalid('error parsing ERR message')
            self.logger.warning('error processing ERR message:{} - error:{}'.format(self.messageString, str(err)))

    def getMessageProperties(self):
        """
        returns a dictionary of the message properties
        """
        if self.messageType in self.messageDetails.keys():
            return self.messageDetails[self.messageType]
        else:
            return None

    def getMessageAttribute(self, attributeName=''):
        """
        returns a message properties (attribute)

        **parameters:**
        attributeName - name of the property you want to get
        """
        try:
            if attributeName in self.messageDetails[self.messageType]:
                return self.messageDetails[self.messageType][attributeName]
            else:
                return None

        except Exception as err:
            self.logger.error("Unable to retrieve panel message attribute:{}, error msg:{}".format(
                attributeName, str(err)))
            return None

    def getKPMattr(self, flag=''):
        """
        Returns the flag value from the Keypad Message Bit Field.
        Valid flags are: READY, ARMED_AWAY, ARMED_HOME, BACKLIGHT, PGM_MODE,
        BEEPS, ZONES_BYPASSED, AC_ON, CHIME_MODE, ALARM_OCCURRED,
        ALARM_BELL_ON, BATTERY_LOW, ARMED_INSTANT, FIRE, CHECK_ZONE,
        ARMED_STAY_NIGHT, ERROR_REPORT, ADEMCO_OR_DSC
        """

        if self.messageType == 'KPM':
            if flag in self.messageDetails['KPM']['keypadFlags'].keys():
                return self.messageDetails['KPM']['keypadFlags'][flag]
            else:
                return None
        else:
            return None

    def attr(self, attributeName=''):
        """
        Short name version for getMessageAttribute() method.
        """
        return self.getMessageAttribute(attributeName)

    def setMessageToInvalid(self, reason='reason not provided'):
        """
        sets attributes to ensure the caller knows the message is invalid
        """
        self.isValidMessage = False
        self.invalidReason = reason
        self.needsProcessing = False

    def __hexStringToInt(self, hexString=''):
        # see if its valid
        for s in hexString.lower():
            if s not in '0123456789abcdef':
                return None

        # append the hex prefix to the string
        hexString = '0x' + hexString.lower()

        # return it as an integer
        return int(hexString, 16)

    def __getBitFromInt(self, value=0, bitIndex=0):
        """
        Takes value (int) and bitIndex (int) and returns 1 if the bitIndex of value (in binary) is 1, 0 otherwise
        """
        # self.logger.debug("call with value:{}, bitIndex:{}".format(value, bitIndex))
        return (value >> bitIndex) & 1

    def __getBitFromHexString(self, hexString='', bitIndex=0):
        """
        Takes hexString (string) and bitIndex (int) and returns 1 if the bitIndex of value (in binary) is 1, 0 otherwise
        NOTE: it will return 0 for an invalid hexString
        """
        # self.logger.debug("call with value:{}, bitIndex:{}".format(value, bitIndex))
        value = self.__hexStringToInt(hexString)
        if value is None:
            return 0
        else:
            return (value >> bitIndex) & 1

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

        # if we get here its contains valid int characters - but lets be crazy safe
        try:
            x = int(intAsString)
            return x

        except Exception as err:
            self.logger.debug('Error converting:{} to integer - error:{}'.format(intAsString, str(err)))
            return None
