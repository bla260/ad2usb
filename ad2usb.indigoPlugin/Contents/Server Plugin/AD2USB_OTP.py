import configparser
import os
import time

# OTP filenames
kOTP_CONFIG = "AD2USB_OTP.cfg"
kOTP_QRCODE = "AD2USB_OTP.png"

OTP_INSTALLED = False
QRCODE_INSTALLED = False
OTP_IMPORT_ERRORS = ''

# TO DO: clean this up
# import checks for optinal OTP capabilties
try:
    import pyotp
    OTP_INSTALLED = True

except Exception as err:
    OTP_IMPORT_ERRORS = "Unable to import 'pyotp' - " + format(str(err))

try:
    import qrcode
    QRCODE_INSTALLED = True

except Exception as err:
    OTP_IMPORT_ERRORS = OTP_IMPORT_ERRORS + "Unable to import 'qrcode' - " + format(str(err))


class OTP(object):
    """
    This object is initialized with a string that is the path to where the configuration file is stored.

    It has a variety of methods to manage the One-Time-Password (OTP) features. The basic usage is:

        x = OTP(folderPath='/X/Y/Z', logger=loggerObject)
        x.isValidOTP(otpCode)  # checks if the the OTP is valid True or False
        x.getCode()  # returns the code from the configuration file
        x.writeOTPConfigFiles()  # creates or updates the OTP configuration file and the QRCode image file
    """

    def __init__(self, folderPath='', logger=None, isEnabled=False):
        try:
            # set the properties from the folderPath
            self.__setProperties(folderPath, isEnabled)

            # check for logger parameters first
            if logger is None:
                # TO DO: add test that object is logging object
                # refuse to create object if no logger exists
                raise ValueError("logger parameter not provided or not a logger object.")
            else:
                # set the logger property
                self.logger = logger

        except Exception as err:
            raise ValueError("logger parameter not provided or not a logger object:{}".format(str(err)))

        # check if its enabled but module does not exist
        if isEnabled and (not OTP_INSTALLED):
            self.logger.warning(
                "OTP features require 'pyotp' module. Python3 Module pyotp was imported successully. OTP features are disabled. Use 'pip3 install pyotp' to install.")
            self.logger.error("Error:{}".format(OTP_IMPORT_ERRORS))

        # also check if its enabled and installed but the folder path is empty
        elif isEnabled and OTP_INSTALLED and (len(self.folderPath) == 0):
            self.logger.error(
                "OTP features require a folder path. OTP features are disabled. Use 'Configure' menu to set Folder Path.")
            self.logger.error("Folder Path:{}".format(folderPath))

        # this is for initial setup and first creation since closedPrefsConfigUi creates a new OTP object
        # check if enabled and has a valid Folder path but the config file does not exist
        elif isEnabled and OTP_INSTALLED and (len(self.folderPath) > 0) and (self.fileName is not None):
            # create file if it does not exists
            if not self.doesConfigFileExist():
                # if we're initializing the OTP object on startup or after changing Configure settings
                # and the file does not exist we will create it
                if self.writeOTPConfigFiles():
                    self.writeOTPQRCode()
                else:
                    self.logger.error("Unable to create the initial OTP configuration file.")

    def __setProperties(self, folderPath='', isEnabled=False):
        # is OTP and QR Code enabled
        # module must be installed and feature enabled in Configure
        self.isQRCodeEnabled = QRCODE_INSTALLED and isEnabled
        self.isOTPEnabled = OTP_INSTALLED and isEnabled

        # folder and file names
        self.folderPath = folderPath.strip()
        # only set filename if folder path is not empty
        if len(self.folderPath) > 0:
            self.fileName = self.folderPath + '/' + kOTP_CONFIG
            self.qrCodeFile = self.folderPath + '/' + kOTP_QRCODE
        else:
            self.fileName = None
            self.qrCodeFile = None

        # we store/cache key - but we do not store the alarm code in the object
        self.sharedkey = None

        # status
        self.fileHasBeenRead = False

        # OTP attempts
        self.previousOTPValues = []
        self.OTPAttempts = []

    def getSharedKey(self):
        """
        Returns the OTP Shared Key as a string if found in the config file or 'None' if the file cannot read or not found.
        """
        # if the key is None try to read the config file
        if self.sharedkey is None:
            wasReadSuccessful, key, blankCode = self.readOTPConfigFile(returnTheKey=True)
            # if we read the file successfully
            if wasReadSuccessful:
                # set the property/cache
                self.sharedkey = key
                # return the shared key
                return self.sharedkey
            else:
                # if we can't read the file return None
                return None
        else:
            # if the property/cached key is not None - return it - no need ot read file
            return self.sharedkey

    def getCode(self):
        """
        Returns the alarm panel code as a string if found in the config file or 'None' if not read or found.
        """
        # we don't store the code - so read the config file
        wasReadSuccessful, key, code = self.readOTPConfigFile(returnTheCode=True)
        # if we can read the file
        if wasReadSuccessful:
            # return the code
            return code
        else:
            # if we can't read the file return None
            return None

    def isOTPConfigFileValid(self):
        """
        Checks if the config file is valid before reading it. Returns True if it can be read,
        returns False if it cannot.
        """

        # test the file first
        try:
            # config path is blank
            if (self.folderPath == ''):
                self.logger.warning("OTP Configuration Folder not set. Use the 'Configure' menu to set.")
                return False

            # if the config path does exist
            if not os.path.exists(self.folderPath):
                self.logger.warning("OTP Configuration Folder does not exist")
                return False

            # if the config path is not a directory
            if not os.path.isdir(self.folderPath):
                self.logger.warning("OTP Configuration Folder is not a folder")
                return False

            # now test the file
            # if the file path does not exist
            if not os.path.exists(self.fileName):
                self.logger.warning(
                    "OTP Configuration file does not exist. Use the Plugin menu: 'Regenerate OTP Key' to create it.")
                return False

            # if the file is not readable
            if not os.access(self.fileName, os.R_OK):
                self.logger.warning(
                    "OTP Configuration file is not readable. Make sure it exists and the Indigo server application can read the file")
                return False

            # if we made it this far file is valid
            return True

        except Exception as err:
            self.logger.error("Error reading OTP Configuration file:{}".format(str(err)))
            self.logger.error("Check folder path in 'Configure' and consider regeneratin file")
            return False

    def readOTPConfigFile(self, returnTheCode=False, returnTheKey=False):
        """
        Reads the config file containing the shared key and the alarm panel code.

        Returns 3 values: Read Success/Fail (Boolean), KeyValue (String), and CodeValue(String).
        You must specify if you want the values returned by passing True to one or both of
        the parameters 'returnTheKey' and 'returnTheCode'.
        """

        # test the file first
        try:
            code = ''
            key = ''

            # check if file is valid
            if not self.isOTPConfigFileValid():
                return False, key, code

            # file is valid - continue
            # now parse the file
            config = configparser.ConfigParser()
            config.read(self.fileName)

            # read the sharedKey if we ask for it
            if returnTheKey:
                errorMessageKey = 'sharedkey'
                key = config['DEFAULT']['sharedkey']

            # read the code if we ask for it
            if returnTheCode:
                errorMessageKey = 'code'
                code = config['DEFAULT']['code']
                # success if asking for both code and key
                return True, key, code
            else:
                # success if asking only for key
                return True, key, code

        except (configparser.ParsingError, configparser.Error) as err:
            self.logger.warning("Unable to parse the OTP configuration file. Consider regenerating the file.")
            self.logger.warning("Error msg: {}".format(str(err)))
            return False, key, code

        except configparser.MissingSectionHeaderError as err:
            self.logger.warning(
                "OTP configuration file missing DEFAULT section headers. Consider regenerating the file.")
            self.logger.warning("Error msg: {}".format(str(err)))
            return False, key, code

        except configparser.NoOptionError as err:
            self.logger.warning(
                "Unable to find {} option in DEFAULT section of the OTP configuration file. Consider regenerating the file.".format(errorMessageKey))
            self.logger.warning("Error msg: {}".format(str(err)))
            return False, key, code

        except Exception as err:
            self.logger.warning("Unable to process the OTP configuration file. Consider regenerating the file.")
            self.logger.warning("Error msg: {}".format(str(err)))
            return False, key, code

    def writeOTPConfigFiles(self):
        """
        Used to generate a new or update an existing OTP Configuration file. We always assume we are regenerating
        the key when using this method and a new shared key will always be created.
        """
        try:
            # create a new config parser object
            import configparser
            config = configparser.ConfigParser()

            configFileExists = self.doesConfigFileExist()

            # check if we're updating the file (it exists) or creating a new one
            if configFileExists:
                code = self.getCode()
                # if the objects code is not set = make it a default with a comment
                if code is None:
                    config['DEFAULT']['code'] = '1234 # replace with your Alarm Code'
                else:
                    config['DEFAULT']['code'] = code
                    code = ''  # clear the code
            else:
                # don't fetch code if file does not exists
                config['DEFAULT']['code'] = '1234 # replace with your Alarm Code'

            # generate a new valid random key
            config['DEFAULT']['sharedKey'] = self.__getNewSharedKey()

            # do not write the config file if the key did not change and the file already exists
            if (self.sharedkey == config['DEFAULT']['sharedKey']) and configFileExists:
                # key unchanged - do nothing
                self.logger.error("Shared key not updated. OTP configuration file:{} not change.".format(self.fileName))
                return False

            # check that the filename is valid
            if self.isWritableFile(filename=self.fileName):

                # log a message if we're creating the file
                if not configFileExists:
                    self.logger.info("OTP Config file:{} does not exist and will be created.".format(self.fileName))

                # write the file
                with open(self.fileName, 'w') as configfile:
                    config.write(configfile)

            # return success if we made it this far
            return True

        except Exception as err:
            self.logger.error("Error writing OTP Configuration file:{}. Error:{}".format(self.fileName, str(err)))
            return False

    def writeOTPQRCode(self):
        """
        Attempts to write a PNG image to the QRCODE file named 'AD2USB_OTP.png' in the user defined folder.
        Returns True if successful; False if not.
        """
        try:
            # check to see if QRCODE is enabled
            if not QRCODE_INSTALLED:
                self.logger.error(
                    "Unable to write QRCODE file:{} - required Python modules not installed: {}".format(self.qrCodeFile, OTP_IMPORT_ERRORS))
                return False

            # check if the PNG file is writeable
            if self.isWritableFile(filename=self.qrCodeFile):
                uri = self.__getURI()
                if len(uri) > 0:
                    img = qrcode.make(uri)
                    type(img)  # qrcode.image.pil.PilImage
                    # img.save(self.qrCodeFile)
                    self.logger.info("New QRCODE PNG file generated:{}".format(self.qrCodeFile))
                    return True
                else:
                    self.logger.error("Unable to write QRCODE file:{} - empty URI.")
                    return False
            else:
                self.logger.error("Unable to write QRCODE file:{} - not writable.".format(self.qrCodeFile))
                return False

        except Exception as err:
            self.logger.error("Error while writing QRCODE. Error:{}".format(str(err)))
            return False

        return True

    def isValidOTP(self, OTPValue):
        """
        Returns True is the OTPValue is valid based on the Shared Key. Returns False if it is not.
        """

        try:
            # check if pyotp is enabled
            if not OTP_INSTALLED:
                self.logger.warning("Unable to import 'pyotp'. OTP is not enabled and cannot be used.")
                return False

            # allow this number of attempts each 60 seconds
            numberOfAttemptsAllowed = 4

            # log the attempt as a timestamp and append it
            currentTime = time.time()
            self.OTPAttempts.append(currentTime)

            # purge all timestamps older than 60 seconds
            # we know we will always have at least one entry less than 60 since we just added it
            timeDelta = currentTime - self.OTPAttempts[0]
            while (timeDelta > 60.0):
                # remove the oldest element which was used to compute timeDelta
                self.OTPAttempts.pop(0)

                # get the next oldest time if there is another element in array
                if len(self.OTPAttempts) > 0:
                    timeDelta = currentTime - self.OTPAttempts[0]
                else:
                    timeDelta = 0  # no more elements left

            # if the number of attempts in 60 seconds > 4 attempts return False
            # this prevents brute force
            if len(self.OTPAttempts) > numberOfAttemptsAllowed:
                self.logger.warning("OTP attempts = {} within 60 seconds exceeds the limit of {}".format(
                    len(self.OTPAttempts), numberOfAttemptsAllowed))
                return False

            self.logger.debug("Number of attempts OK.")

            # look for invalid OTPValues
            if isinstance(OTPValue, str):
                self.logger.debug("String check OK.")
            else:
                self.logger.warning("OTP value is not a string")
                return False

            if OTPValue.isdigit():
                self.logger.debug("Digit check OK.")
            else:
                self.logger.warning("OTP value contains characters other than digits")
                return False

            if len(OTPValue) != 6:
                self.logger.warning("OTP value is not 6 digits")
                return False
            else:
                self.logger.debug("Length check OK.")

            # check for duplicate values used and manage a list of 100 previous
            if OTPValue in self.previousOTPValues:
                self.logger.warning("OTP value cannot be used more than once")
                return False

            self.logger.debug("Previous values check OK.")

            # get the expected OTP code
            totp = None  # initialize it
            sharedKey = self.getSharedKey()
            if sharedKey is not None:
                totp = pyotp.TOTP(sharedKey)
                sharedKey = ''
            else:
                self.logger.error("OTP shared key is not set in configuration file.")
                return False

            self.logger.debug("Get shared key successful.")

            # self.logger.info("Current OTP:{}".format(totp.now()))

            # finally check is the code is the right code
            if totp.verify(OTPValue):
                self.logger.info("OTP value valid")
                # add it to previous codes used - keeping only last 100 values
                self.previousOTPValues.append(OTPValue)
                if len(self.previousOTPValues) > 100:
                    self.previousOTPValues.pop(0)  # pop 0th element from list

                self.logger.debug("Appended to list - list size:{}".format(len(self.previousOTPValues)))

                return True

            else:
                self.logger.debug("OTP value invalid")
                return False

        except Exception as err:
            self.logger.error("Error validating OTP:{}".format(str(err)))
            return False

    def isValidFolder(self, folderToCheck=None):
        """
        If the optional 'FolderToCheck' parameter is not provided it checks the
        folderPath property set during initialization. Thus, this method can check the object's
        folder path or any other folder path by passing a value to 'FolderToCheck'.

        Returns a tuple of Boolen, Message. Returns True if the folder exists, is a folder,
        and is both readable and writeable. Returns False otherwise.
        """
        # clean up white space just in case
        if folderToCheck is None:
            pathToCheck = self.folderPath.strip()
        else:
            pathToCheck = folderToCheck.strip()

        # self.folderPath = self.folderPath.strip()

        # config path is blank
        if (pathToCheck == ''):
            return False, '''OTP Configuration Folder not set. Enter a valid folder path in the "OTP Configuration Folde" text field.'''

        # if the config path exists
        if not os.path.exists(pathToCheck):
            return False, f'''OTP Configuration Folder: "{pathToCheck}" does not exist. Use the 'Configure' menu to change or created the folder.'''

        # if the config path is a directory
        if not os.path.isdir(pathToCheck):
            return False, f'''OTP Configuration Folder: "{pathToCheck}" is not a folder.'''

        if not os.access(pathToCheck, os.W_OK):
            return False, f'''OTP Configuration Folder: "{pathToCheck}" is not writable.'''

        if not os.access(pathToCheck, os.R_OK):
            return False, f'''OTP Configuration Folder: "{pathToCheck}" is not readable.'''

        # if we made it this far assume its a valid folder
        return True, "folder is valid"

    def doesConfigFileExist(self):
        """
        Returns True if the filename defined in the property 'fileName' exists; returns False if file does not exist.
        """
        # check the file for readability
        # if the file path exists
        if self.fileName is None:
            return False

        if os.path.exists(self.fileName):
            return True
        else:
            return False

    def isReadableFile(self, silent=False):
        """
        Returns True if the filename exists and is readable; returns False if file does not exist or is not readable.
        """
        # check the file for readability
        # if the file path exists
        if self.fileName is None:
            return False

        if not os.path.exists(self.fileName):
            if not silent:
                self.logger.warning(
                    "OTP Configuration file does not exist. Use the Plugin menu: 'Regenerate OTP Key' to create it.")

            return False

        # if the file is readable
        if not os.access(self.fileName, os.R_OK):
            if not silent:
                self.logger.warning(
                    "OTP Configuration file is not readable. Make sure it exists and the Indigo server application can read the file")

            return False

        # if we made it this far assume its OK
        return True

    def isWritableFile(self, filename=None, silent=False):
        """
        Returns True if the filename if writable or does not exist; returns False if file exists and is not writable.
        """
        # test the file for writability
        if filename is None:
            return False

        # if the file does not exist assume its writable
        if not os.path.exists(filename):
            return True

        # if the file is writeable
        if not os.access(filename, os.W_OK):
            if not silent:
                self.logger.warning(
                    "OTP Configuration file:'{}' is not writeable. Make sure the Indigo server application can write to the the file.".format(filename))

            return False

        # if we made it this far assume its OK
        return True

    def __getURI(self):
        """
        Generates a URI from the Shared Key for the QRCODE image file.
        Returns URI as as string if successful; returns an empty string if not.
        """
        try:
            # check if pyotp installed and OTP is enabled
            if not OTP_INSTALLED:
                self.logger.warning("Unable to import 'pyotp'. OTP is not enabled and cannot be used.")
                return ''

            key = self.getSharedKey()
            uri = pyotp.totp.TOTP(key).provisioning_uri(name='AD2USB', issuer_name='AD2SUB Plugin')
            return uri

        except Exception as err:
            self.logger.error("Unable to generate QRCODE URI. Error:{}".format(str(err)))
            return ''

    def __getNewSharedKey(self):
        """
        Returns a new shared key with a new 32-character base32 secret, compatible with Google Authenticator
        and other OTP apps. Returns the current shared key if one cannot be generated.
        """
        try:
            # set a default
            oldKey = None
            # set it to the current key in case we have an error
            oldKey = self.sharedkey
            # check if pyotp installed
            if OTP_INSTALLED:
                newKey = pyotp.random_base32()
                return newKey
            else:
                self.logger.warning("Unable to import 'pyotp'. OTP is not installed and cannot be used.")
                return oldKey

        except Exception as err:
            self.logger.error(
                "Unable to generate new OTP Shared Key. Key will not be changed. Error:{}".format(str(err)))
            return oldKey
