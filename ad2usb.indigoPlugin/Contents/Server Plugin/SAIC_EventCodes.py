# Two parts to this data structure - dictionary:
#
# First part is a mapping from newer firmware 2.2a.8.8 LRR messages to older 2.2a.6
#
# Second part is from APPENDIX C: EVENT CODES in SIA DC-05-1999.09
# fields are key=code, [ event, data type: zone or user ]
#
# 100 - ALARMS
# 200 - SUPERVISORY
# 300 - TROUBLES
# 400 - OPEN/CLOSE REMOTE ACCESS
# 500 - BYPASSES/DISABLES
# 600 - TEST/MISC
#
# Event qualifiers
# 1 = New Event or Opening (Open = Disarm)
# 3 = New Restore or Closing (Close = The manual or automatic arming of a security system.)
# 6 = Previously reported condition still present (Status report)
#
######################################
#
# Mapping to old LRR messages / 19 Events
# ? = just a guess for now
#
# 8 are mapped below:
# OPEN - 1,441 and 1,408
# ARM_AWAY - 3,408 - Quick mode
# ARM_STAY - 3,441
# ACLOSS - 1,301  # this trouble report is randomized with up to a (4) hour delay from initial power loss
# AC_RESTORE - 3,301
# LOWBAT - 1,302 (Panel)
# LOWBAT_RESTORE - 3,302 (Panel)
# ALARM_ENTRY - 1,134
#
# 11 are still not verified:
# RFLOWBAT - ? - 1,384
# RFLOWBAT_RESTORE - ? - 3,384
# TROUBLE - ? - 1,300
# TROUBLE_RESTORE - ? - 3,300
#
# ALARM_PANIC - ? - 1,120
# ALARM_FIRE - ? - 1,110
# ALARM_AUDIBLE - ? _ 1,123
# ALARM_SILENT - ? - 1,122
# ALARM_AUX - ?
# ALARM_PERIMETER - ? - 1,131
# ALARM_TRIPPED - N/A - this is a keypad change event
#
##################################
# ARM_STAY then alarm tripped from entry testing
# 1. 3,441 - ARM STAY enabled
# 2. 1,134 - Entry/Exit zone alarm started
# 3. 1,406 - User Cancel
# 4. 1,441 - OPEN (Disarmed)
# 5. 3,134 - Entry/Exit zone alarm restored
#
##################################
# ARM_AWAY Quick Arm then alarm tripped by motion testing
# 1. 3,408 - ARM AWAY
# 2. 3,459 - Recent Close(?)
# 3. 1,401 - O/C by User
# 4. 1,132 - Interior Zone Alarm
# 5. 1,406 - User Cancel
# 6. 3,132 - Interior Zone Alarm
#
######################################
# No Events defined
# BYPASS - 1,570 - enable bypass
# NBG_ZONE_ALARM - 1,150
#
# Mapping to old LRR messages and Events
# map the code to a valid Event - the events were defined as old LRR message types
# the current plugin only uses 19 events
# ALARM_AUX - not sure what codes
# ALARM_TRIPPED - N/A
# 11 codes below - these are just guesses
#
# '110': {'3': 'ALARM_FIRE'},
# '120': {'3': 'ALARM_PANIC'},
# '122': {'3': 'ALARM_SILENT'},
# '123': {'3': 'ALARM_AUDIBLE'},
# '131': {'3': 'ALARM_PERIMETER'},
# '300': {'1': 'TROUBLE', '3': 'TROUBLE_RESTORE'},
# '384': {'1': 'RFLOWBAT', '3': 'RFLOWBAT_RESTORE'},
#
# Map codes to Plugin Events
# Not all Plugin Events defined in Plugin - for future use
cid_code_to_event = {
    '110': {'1': 'ALARM_FIRE'},  # not verified
    '120': {'1': 'ALARM_PANIC'},  # not verified
    '122': {'1': 'ALARM_SILENT'},  # not verified
    '123': {'1': 'ALARM_AUDIBLE'},  # not verified
    '131': {'1': 'ALARM_PERIMETER'},  # not verified
    '132': {'1': 'ALARM_INTERIOR'},  # verified and added this as new event in 3.3.0
    '134': {'1': 'ALARM_ENTRY'},  # verified
    '150': {'1': 'NBG_ZONE_ALARM', '3': 'NBG_ZONE_CLEAR'},  # 24 Hour Non-Burglary zone
    '301': {'1': 'ACLOSS', '3': 'AC_RESTORE'},  # verified
    '302': {'1': 'LOWBAT', '3': 'LOWBAT_RESTORE'},  # verified
    '383': {'1': 'TROUBLE', '3': 'TROUBLE_RESTORE'},  # verified - this is a CHECK on keypad
    '384': {'1': 'RFLOWBAT', '3': 'RFLOWBAT_RESTORE'}, # not verified - an educated guess
    '401': {'1': 'OPEN'},  # verified DISARM Away
    '406': {'1': 'CANCEL'},  # zone alarm cancelled by user
    '408': {'3': 'ARM_AWAY'},  # verified
    '441': {'3': 'ARM_STAY', '1': 'OPEN'},  # verified
    '459': {'3': 'RECENT_CLOSE'},  # verified but may not be useful
    '570': {'1': 'BYPASS_ON', '3': 'BYPASS_OFF'},  # bypass
    '602': {'1': 'PERIODIC_TEST'}
}

# the authoritative code list
kCODE = {'100': ['Medical', 'zone'],
         '101': ['Personal Emergency', 'zone'],
         '102': ['Fail to report in', 'zone'],
         '110': ['Fire', 'zone'],
         '111': ['Smoke', 'zone'],
         '112': ['Combustion', 'zone'],
         '113': ['Water flow', 'zone'],
         '114': ['Heat', 'zone'],
         '115': ['Pull Station', 'zone'],
         '116': ['Duct', 'zone'],
         '117': ['Flame', 'zone'],
         '118': ['Near Alarm', 'zone'],
         '120': ['Panic', 'zone'],
         '121': ['Duress', 'user'],
         '122': ['Silent', 'zone'],
         '123': ['Audible', 'zone'],
         '124': ['Duress - Access granted', 'zone'],
         '125': ['Duress - Egress granted', 'zone'],
         '130': ['Burglary', 'zone'],
         '131': ['Perimeter', 'zone'],
         '132': ['Interior', 'zone'],
         '133': ['24 Hour (Safe)', 'zone'],
         '134': ['Entry/Exit', 'zone'],
         '135': ['Day/night', 'zone'],
         '136': ['Outdoor', 'zone'],
         '137': ['Tamper', 'zone'],
         '138': ['Near alarm', 'zone'],
         '139': ['Intrusion Verifier', 'zone'],
         '140': ['General Alarm', 'zone'],
         '141': ['Polling loop open', 'zone'],
         '142': ['Polling loop short', 'zone'],
         '143': ['Expansion module failure', 'zone'],
         '144': ['Sensor tamper', 'zone'],
         '145': ['Expansion module tamper', 'zone'],
         '146': ['Silent Burglary', 'zone'],
         '147': ['Sensor Supervision Failure', 'zone'],
         '150': ['24 Hour Non-Burglary', 'zone'],
         '151': ['Gas detected', 'zone'],
         '152': ['Refrigeration', 'zone'],
         '153': ['Loss of heat', 'zone'],
         '154': ['Water Leakage', 'zone'],
         '155': ['Foil Break', 'zone'],
         '156': ['Day Trouble', 'zone'],
         '157': ['Low bottled gas level', 'zone'],
         '158': ['High temp', 'zone'],
         '159': ['Low temp', 'zone'],
         '160': ['24 Hour Non-Burglary', 'zone'],
         '161': ['Loss of air flow', 'zone'],
         '162': ['Carbon Monoxide detected', 'zone'],
         '163': ['Tank level', 'zone'],
         '200': ['Fire Supervisory', 'zone'],
         '201': ['Low water pressure', 'zone'],
         '202': ['Low CO2', 'zone'],
         '203': ['Gate valve sensor', 'zone'],
         '204': ['Low water level', 'zone'],
         '205': ['Pump activated', 'zone'],
         '206': ['Pump failure', 'zone'],
         '210': ['Fire Supervisory', 'zone'],
         '300': ['System Trouble', 'zone'],
         '301': ['AC Loss', 'zone'],
         '302': ['Low system battery', 'zone'],
         '303': ['RAM Checksum bad', 'zone'],
         '304': ['ROM checksum bad', 'zone'],
         '305': ['System reset', 'zone'],
         '306': ['Panel programming changed', 'zone'],
         '307': ['Self-test failure', 'zone'],
         '308': ['System shutdown', 'zone'],
         '309': ['Battery test failure', 'zone'],
         '310': ['Ground fault', 'zone'],
         '311': ['Battery Missing/Dead', 'zone'],
         '312': ['Power Supply Overcurrent', 'zone'],
         '313': ['Engineer Reset', 'user'],
         '320': ['Sounder/Relay', 'zone'],
         '321': ['Bell 1', 'zone'],
         '322': ['Bell 2', 'zone'],
         '323': ['Alarm relay', 'zone'],
         '324': ['Trouble relay', 'zone'],
         '325': ['Reversing relay', 'zone'],
         '326': ['Notification Appliance Ckt. # 3', 'zone'],
         '327': ['Notification Appliance Ckt. #4', 'zone'],
         '330': ['System Peripheral trouble', 'zone'],
         '331': ['Polling loop open', 'zone'],
         '332': ['Polling loop short', 'zone'],
         '333': ['Expansion module failure', 'zone'],
         '334': ['Repeater failure', 'zone'],
         '335': ['Local printer out of paper', 'zone'],
         '336': ['Local printer failure', 'zone'],
         '337': ['Exp. Module DC Loss', 'zone'],
         '338': ['Exp. Module Low Batt.', 'zone'],
         '339': ['Exp. Module Reset', 'zone'],
         '340': ['System Peripheral trouble', 'zone'],
         '341': ['Exp. Module Tamper', 'zone'],
         '342': ['Exp. Module AC Loss', 'zone'],
         '343': ['Exp. Module self-test fail', 'zone'],
         '344': ['RF Receiver Jam Detect', 'zone'],
         '350': ['Communication trouble', 'zone'],
         '351': ['Telco 1 fault', 'zone'],
         '352': ['Telco 2 fault', 'zone'],
         '353': ['Long Range Radio xmitter fault', 'zone'],
         '354': ['Failure to communicate event', 'zone'],
         '355': ['Loss of Radio supervision', 'zone'],
         '356': ['Loss of central polling', 'zone'],
         '357': ['Long Range Radio VSWR problem', 'zone'],
         '360': ['Communication trouble', 'zone'],
         '370': ['Protection loop', 'zone'],
         '371': ['Protection loop open', 'zone'],
         '372': ['Protection loop short', 'zone'],
         '373': ['Fire trouble', 'zone'],
         '374': ['Exit error alarm (zone)', 'zone'],
         '375': ['Panic zone trouble', 'zone'],
         '376': ['Hold-up zone trouble', 'zone'],
         '377': ['Swinger Trouble', 'zone'],
         '378': ['Cross-zone Trouble', 'zone'],
         '380': ['Sensor trouble', 'zone'],
         '381': ['Loss of supervision - RF', 'zone'],
         '382': ['Loss of supervision - RPM', 'zone'],
         '383': ['Sensor tamper', 'zone'],
         '384': ['RF low battery', 'zone'],
         '385': ['Smoke detector Hi sensitivity', 'zone'],
         '386': ['Smoke detector Low sensitivity', 'zone'],
         '387': ['Intrusion detector Hi sensitivity', 'zone'],
         '388': ['Intrusion detector Low sensitivity', 'zone'],
         '389': ['Sensor self-test failure', 'zone'],
         '391': ['Sensor Watch trouble', 'zone'],
         '392': ['Drift Compensation Error', 'zone'],
         '393': ['Maintenance Alert', 'zone'],
         '400': ['Open/Close', 'user'],
         '401': ['O/C by user', 'user'],
         '402': ['Group O/C', 'user'],
         '403': ['Automatic O/C', 'user'],
         '404': ['Late to O/C (Note: use 453, 454 instead )', 'user'],
         '405': ['Deferred O/C (Obsolete- do not use )', 'user'],
         '406': ['Cancel', 'user'],
         '407': ['Remote arm/disarm', 'user'],
         '408': ['Quick arm', 'user'],
         '409': ['Keyswitch O/C', 'user'],
         '440': ['Open/Close', 'user'],
         '441': ['Armed STAY', 'user'],
         '442': ['Keyswitch Armed STAY', 'user'],
         '450': ['Exception O/C', 'user'],
         '451': ['Early O/C', 'user'],
         '452': ['Late O/C', 'user'],
         '453': ['Failed to Open', 'user'],
         '454': ['Failed to Close', 'user'],
         '455': ['Auto-arm Failed', 'user'],
         '456': ['Partial Arm', 'user'],
         '457': ['Exit Error (user)', 'user'],
         '458': ['User on Premises', 'user'],
         '459': ['Recent Close', 'user'],
         '461': ['Wrong Code Entry', 'zone'],
         '462': ['Legal Code Entry', 'user'],
         '463': ['Re-arm after Alarm', 'user'],
         '464': ['Auto-arm Time Extended', 'user'],
         '465': ['Panic Alarm Reset', 'zone'],
         '466': ['Service On/Off Premises', 'user'],
         '410': ['Remote Access', 'zone'],
         '411': ['Callback request made', 'user'],
         '412': ['Successful download/access', 'user'],
         '413': ['Unsuccessful access', 'user'],
         '414': ['System shutdown command received', 'user'],
         '415': ['Dialer shutdown command received', 'user'],
         '416': ['Successful Upload', 'zone'],
         '420': ['Access Control', 'zone'],
         '421': ['Access denied', 'user'],
         '422': ['Access report by user', 'user'],
         '423': ['Forced Access', 'zone'],
         '424': ['Egress Denied', 'user'],
         '425': ['Egress Granted', 'user'],
         '426': ['Access Door propped open', 'zone'],
         '427': ['Access point Door Status Monitor trouble', 'zone'],
         '428': ['Access point Request To Exit trouble', 'zone'],
         '429': ['Access program mode entry', 'user'],
         '430': ['Access program mode exit', 'user'],
         '431': ['Access threat level change', 'user'],
         '432': ['Access relay/trigger fail', 'zone'],
         '433': ['Access RTE shunt', 'zone'],
         '434': ['Access DSM shunt', 'zone'],
         '500': ['System Disables', 'zone'],
         '501': ['Access reader disable', 'zone'],
         '510': ['System Disables', 'zone'],
         '520': ['Sounder/Relay Disable', 'zone'],
         '521': ['Bell 1 disable', 'zone'],
         '522': ['Bell 2 disable', 'zone'],
         '523': ['Alarm relay disable', 'zone'],
         '524': ['Trouble relay disable', 'zone'],
         '525': ['Reversing relay disable', 'zone'],
         '526': ['Notification Appliance Ckt. # 3 disable', 'zone'],
         '527': ['Notification Appliance Ckt. # 4 disable', 'zone'],
         '530': ['System Peripheral Disables', 'zone'],
         '531': ['Module Added', 'zone'],
         '532': ['Module Removed', 'zone'],
         '540': ['System Peripheral Disables', 'zone'],
         '550': ['Communication Disables', 'zone'],
         '551': ['Dialer disabled', 'zone'],
         '552': ['Radio transmitter disabled', 'zone'],
         '553': ['Remote Upload/Download disabled', 'zone'],
         '560': ['Communication Disables', 'zone'],
         '570': ['Zone/Sensor bypass', 'zone'],
         '571': ['Fire bypass', 'zone'],
         '572': ['24 Hour zone bypass', 'zone'],
         '573': ['Burg. Bypass', 'zone'],
         '574': ['Group bypass', 'user'],
         '575': ['Swinger bypass', 'zone'],
         '576': ['Access zone shunt', 'zone'],
         '577': ['Access point bypass', 'zone'],
         '600': ['Test/Misc', 'zone'],
         '601': ['Manual trigger test report', 'zone'],
         '602': ['Periodic test report', 'zone'],
         '603': ['Periodic RF transmission', 'zone'],
         '604': ['Fire test', 'user'],
         '605': ['Status report to follow', 'zone'],
         '606': ['Listen-in to follow', 'zone'],
         '607': ['Walk test mode', 'user'],
         '608': ['Periodic test - System Trouble Present', 'zone'],
         '609': ['Video Xmitter active', 'zone'],
         '610': ['Test/Misc', 'zone'],
         '611': ['Point tested OK', 'zone'],
         '612': ['Point not tested', 'zone'],
         '613': ['Intrusion Zone Walk Tested', 'zone'],
         '614': ['Fire Zone Walk Tested', 'zone'],
         '615': ['Panic Zone Walk Tested', 'zone'],
         '616': ['Service Request', 'zone'],
         '620': ['Event Log', 'zone'],
         '621': ['Event Log reset', 'zone'],
         '622': ['Event Log 50% full', 'zone'],
         '623': ['Event Log 90% full', 'zone'],
         '624': ['Event Log overflow', 'zone'],
         '625': ['Time/Date reset', 'user'],
         '626': ['Time/Date inaccurate', 'zone'],
         '627': ['Program mode entry', 'zone'],
         '628': ['Program mode exit', 'zone'],
         '629': ['32 Hour Event log marker', 'zone'],
         '630': ['Schedule change', 'zone'],
         '631': ['Exception schedule change', 'zone'],
         '632': ['Access schedule change', 'zone'],
         '640': ['Personnel Monitoriing', 'zone'],
         '641': ['Senior Watch Trouble Zone', 'zone'],
         '650': ['Misc', 'zone'],
         '651': ['Reserved for Ademco Use Zone', 'zone'],
         '642': ['Latch-key Supervision', 'user'],
         '652': ['Reserved for Ademco Use', 'user'],
         '653': ['Reserved for Ademco Use', 'user'],
         '654': ['System Inactivity', 'zone']
         }
