################################################################################
# Globals
################################################################################
# Log levels dictionary and reverse dictionary name->number
kLoggingLevelNames = {'CRITICAL': 50, 'ERROR': 40, 'WARNING': 30, 'INFO': 20, 'DEBUG': 10}
kLoggingLevelNumbers = {50: 'CRITICAL', 40: 'ERROR', 30: 'WARNING', 20: 'INFO', 10: 'DEBUG'}

# Custom Zone State - see Devices.xml
k_CLEAR = 'Clear'  # key: Clear, value: Clear - should convert key to 'clear'
k_FAULT = 'faulted'  # key: faulted, value: Fault - should convert to 'fault'
k_ERROR = 'error'  # key: error, value: Error - also referred to as Trouble
k_BYPASS = 'bypass'
kZoneStateUIValues = {k_FAULT: 'Fault', k_CLEAR: 'Clear', k_ERROR: 'Error', k_BYPASS: 'Bypass'}

# Panel State constants
k_PANEL_READY = 'ready'
k_PANEL_FAULT = 'Fault'
k_PANEL_ARMED_STAY = 'armedStay'
k_PANEL_ARMED_NIGHT_STAY = 'armedNightStay'
k_PANEL_ARMED_INSTANT = 'armedInstant'
k_PANEL_ARMED_AWAY = 'armedAway'
k_PANEL_ARMED_MAX = 'armedMax'
k_PANEL_UNK = 'unknown'  # this is set before processing keypad message
k_PANEL_ERROR = 'error'  # key: error, value: Error - also referred to as Trouble

# these panel states all display the same icon
k_COMMON_STATES_DISPLAYS = [k_PANEL_READY, k_PANEL_ARMED_STAY, k_PANEL_ARMED_NIGHT_STAY,
                            k_PANEL_ARMED_INSTANT, k_PANEL_ARMED_AWAY, k_PANEL_ARMED_MAX]

kPanelStateUIValues = {k_PANEL_READY: 'Ready', k_PANEL_FAULT: 'Fault',
                       k_PANEL_ARMED_STAY: 'Armed Stay',
                       k_PANEL_ARMED_NIGHT_STAY: 'Armed Night Stay',
                       k_PANEL_ARMED_INSTANT: 'Armed Instant',
                       k_PANEL_ARMED_AWAY: 'Armed Away',
                       k_PANEL_ARMED_MAX: 'Armed Max',
                       k_PANEL_UNK: 'Unknown',
                       k_PANEL_ERROR: 'Error'}

# create a map of keypad bits to common keypad States
k_PANEL_BIT_MAP = {'000': k_PANEL_FAULT, '001': k_PANEL_ARMED_STAY, '010': k_PANEL_ARMED_AWAY, '100': k_PANEL_READY}
