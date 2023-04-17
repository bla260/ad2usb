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

#
# Panel States, Armed Mode, and HomeKit States
# ==================================|===================================|====================================
# panelState                        | armedMode                         | homeKitState
# ===============|==================|================|==================|====================|===============
# Value          | UI Display       | Value          | UI Display       | Value              | UI Display
# ===============|==================|================|==================|====================|===============
# ready          | Ready            | unArmed        | Not Armed        | disarmed (3)       | Disarmed
# Fault          | Fault            | unArmed        | Not Armed        | disarmed (3)       | Disarmed
# armedStay      | Armed Stay       | armedStay      | Armed Stay       | armedStay (0)      | Armed Stay
# armedNightStay | Armed Night Stay | armedNightStay | Armed Night Stay | armedNightStay (2) | Armed Night Stay
# armedAway      | Armed Away       | armedAway      | Armed Away       | armedAway (1)      | Armed Away
# armedInstant   | Armed Instant    | armedInstant   | Armed Instant    | armedStay (0)      | Armed Stay 
# armedMax       | Armed Max        | armedMax       | Armed Max        | armedAway (1)      | Armed Away
# error          | Error            | <any>          | <any>            | disarmed (3)       | Disarmed
# alarmOccured   | Alarm Occurred   | <any>          | <any>            | alarmOccured (4)   | Alarm Occurred
# alarmOn        | Alarm Sounding   | <any>          | <any>            | alarmOccured (4)   | Alarm Occurred
# ===============|==================|================|==================|====================|===============
#

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
k_PANEL_ALARM_OCCURRED = 'alarmOccured'
k_PANEL_ALARM_ON = 'alarmOn'

# HomeKit States Values (stored as strings in Panel Device State)
k_HK_ALARM_STAY_ARMED = k_PANEL_ARMED_STAY          # 0
k_HK_ALARM_AWAY_ARMED = k_PANEL_ARMED_AWAY          # 1
k_HK_ALARM_NIGHT_ARMED = k_PANEL_ARMED_NIGHT_STAY   # 2
k_HK_ALARM_DISARMED =  'disarmed'                   # 3
k_HK_ALARM_TRIGGERED = k_PANEL_ALARM_OCCURRED       # 4

# conversion from Panel State to HomeKit State
k_HOMEKIT_STATES = {
    k_PANEL_READY : k_HK_ALARM_DISARMED,
    k_PANEL_FAULT : k_HK_ALARM_DISARMED,
    k_PANEL_ARMED_STAY : k_HK_ALARM_STAY_ARMED,
    k_PANEL_ARMED_NIGHT_STAY : k_HK_ALARM_NIGHT_ARMED,
    k_PANEL_ARMED_INSTANT : k_HK_ALARM_STAY_ARMED,
    k_PANEL_ARMED_AWAY : k_HK_ALARM_AWAY_ARMED,
    k_PANEL_ARMED_MAX : k_HK_ALARM_AWAY_ARMED,
    k_PANEL_UNK : k_HK_ALARM_DISARMED,
    k_PANEL_ERROR : k_HK_ALARM_DISARMED,
    k_PANEL_ALARM_OCCURRED : k_HK_ALARM_TRIGGERED,
    k_PANEL_ALARM_ON : k_HK_ALARM_TRIGGERED
}

# set of states for ready/armed (green) icon
k_SENSOR_ON_ICON_STATES = { k_PANEL_READY, k_PANEL_ARMED_STAY, k_PANEL_ARMED_NIGHT_STAY,
                            k_PANEL_ARMED_INSTANT, k_PANEL_ARMED_AWAY, k_PANEL_ARMED_MAX }

# set of states for tripped (red) icon
k_SENSOR_TRIPPED_ICON_STATES = { k_PANEL_FAULT, k_PANEL_ALARM_OCCURRED, k_PANEL_ALARM_ON } 

# set of states for error (error) icon
k_SENSOR_ERROR_ICON_STATES = { k_PANEL_UNK, k_PANEL_ERROR } 

# UI values to display on state
k_PANEL_STATE_UI_VALUES = {k_PANEL_READY: 'Ready',
                           k_PANEL_FAULT: 'Fault',
                           k_PANEL_ARMED_STAY: 'Armed Stay',
                           k_PANEL_ARMED_NIGHT_STAY: 'Armed Night Stay',
                           k_PANEL_ARMED_INSTANT: 'Armed Instant',
                           k_PANEL_ARMED_AWAY: 'Armed Away',
                           k_PANEL_ARMED_MAX: 'Armed Max',
                           k_PANEL_UNK: 'Unknown',
                           k_PANEL_ERROR: 'Error',
                           k_PANEL_ALARM_OCCURRED : 'Alarm Occured',
                           k_PANEL_ALARM_ON : 'Alarm Sounding'}

# Code and HomeKit Settings Options
k_CODE_USE_VARIABLE = 'inVariable'
k_CODE_USE_OTP = 'inOTP'
k_CODE_USE_PREFS = 'inPrefs'

