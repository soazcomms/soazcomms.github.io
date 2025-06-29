import sys, os.path
import socket, errno, psutil
import time, datetime
from dateutil.relativedelta import relativedelta
import pytz
import numpy as np
from argparse import ArgumentParser


parser = ArgumentParser()
parser.add_argument("obs_code", default="648",
                    help="SQM location (MPC codes for the telescope).  "
                         "Possible values: 648, G96, V06, V00")
parser.add_argument("-t_interval", "--t_interval", dest="t_interval", default=60,
                    type=int, help="Time interval [s] between measurements.  Default is 60 seconds.")
parser.add_argument("-nbr_measurements", "--nbr_measurements", dest="nbr_measurements", default=-1,
                    type=int, help="Number of measurements.  Default is -1, which means that an "
                                   "infinite number of measurements are taken.")
parser.add_argument("-SB_min", "--SB_min", dest="SB_min", default=0.0,
                    type=float, help="The brightest sky brightness value [mag/arcsec2] that should "
                                     "be added to the data file.  Default is 0.0 mag/arcsec2.")
parser.add_argument("-dir_logs", "--dir_logs", dest="dir_logs", default="",
                    help="Directory where the log files should be saved.  Default is 'SQM/logs/'.")
args = parser.parse_args()


# Filenames according to the IDA standards.
flag_IDA_standard_filename = False


# ***************************************
# ***  Check, if instance is running  ***
# ***************************************

# If no other instance of this program is running then return 0.
# If another instance of this program is running then check that it has a status
# of 'running' or 'sleeping' and return it's process ID.  If it has any other status
# then try to kill it and return 0.  - A. R. Gibbs
def AlreadyRunning():
    iRet = 0
    iMyPID = os.getpid()
    lMyCmd = psutil.Process (iMyPID).cmdline()

    # Look for another process like this one that isn't this one.
    for oProc in psutil.process_iter():
        try:  # Added by H. Groeller, otherwise it crashes when debugging.
            l = oProc.cmdline()

            if l == lMyCmd and not oProc.pid == iMyPID:
                # If it's running  or sleeping then done.
                s = oProc.status()

                if s in ['running', 'sleeping']:
                    iRet = oProc.pid
                    break

                # Else try killing it.
                else:
                    t_check = datetime.datetime.now().replace(microsecond=0).isoformat()
                    print(f"{t_check} - Already running as process {oProc.pid} but it has "
                          f"status '{s}' so killing it.")
                    try:
                        oProc.kill()
                    except:
                        pass

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    return iRet


# ***************************************************************
# ***  Data acquisition routine for single stationary SQM-LE  ***
# ***************************************************************

# ------------------------
# ---  get_SQM_data()  ---
# ------------------------
# Procedure for sending rx, cx and ix requests
def get_SQM_data(sqmcommand):
    # Define the expected lengths for SQM commands.
    if sqmcommand == b'rx':
        # The "Reading" request "rx" or "Rx" commands the SQM-LE to provide the current
        # darkness value as well as all variables used to generate that result.
        strlen = 55
    elif sqmcommand == b'ix':
        # Unit information command "ix" provides details about the software in the
        # micro-controller.
        strlen = 37
    elif sqmcommand == b'cx':
        # The calibration information request "cx" returns all data about the specific
        # light sensor in the unit required to calculate a reading.
        strlen = 56
    else:
        strlen = 265

    msg = ''

    # Define thet socket instance.
    #   AF_INET ... refers to the address-family ipv4.
    #   SOCK_STREAM ... means connection-oriented TCP protocol.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        # Connecting to the SQM
        s.connect((SQM_url, SQM_port))

    except OSError as err:
        # Error codes for different OS taken from
        # https://aakinshin.net/posts/how-socket-error-codes-depend-on-runtime-and-operating-system/
        #
        # ENETUNREACH  ...  Network is unreachable
        #    Errno = 101 (Linux) and 51 (macOS)
        # ECONNREFUSED  ...  Connection refused
        #    Errno = 111 (Linux) and 61 (macOS)
        # ETIMEDOUT  ...  Operation timed out
        #    Errno = 110 (Linux) and 60 (macOS)
        # EHOSTDOWN  ...  Host is down
        #    Errno = 112 (Linux) and 64 (macOS)
        if err.errno == errno.ENETUNREACH or \
                err.errno == errno.ECONNREFUSED or \
                err.errno == errno.ETIMEDOUT or \
                err.errno == errno.EHOSTDOWN:
            print("  " + datetime.datetime.now().isoformat() + " - " + errno.errorcode[err.errno])
            print("    OS error: {0}".format(err))

            logfile = open(file_log_month, 'a')
            logfile.write("  " + datetime.datetime.now().isoformat() +
                          " - " + errno.errorcode[err.errno] + "\n")
            logfile.write("    OS error: {0}\n".format(err))
            logfile.close()
        else:
            print("  " + datetime.datetime.now().isoformat() + " - " + errno.errorcode[err.errno])
            print("    Unknown OSError number: {0}".format(err))

            logfile = open(file_log_month, 'a')
            logfile.write("  " + datetime.datetime.now().isoformat() +
                          " - " + errno.errorcode[err.errno] + "\n")
            logfile.write("    Unknown OSError number: {0}\n".format(err))
            logfile.close()

        msg = "OS error: {0}".format(err)

    # Catch all exceptions that are not OSError exceptions.
    except:
        err = sys.exc_info()[1]

        print("  " + datetime.datetime.now().isoformat() + " - " + errno.errorcode[err.errno])
        print("    Unexpected error: {0}".format(err))

        logfile = open(file_log_month, 'a')
        logfile.write("  " + datetime.datetime.now().isoformat() +
                      " - " + errno.errorcode[err.errno] + "\n")
        logfile.write("    Unexpected error: {0}\n".format(err))
        logfile.close()

        msg = "Unexpected error: {0}".format(err)

    if msg == '':
        # Request data from the SQM.
        s.send(sqmcommand)

        # Need this loop, because after sending the command, it takes a few milliseconds
        # to get the respond back from the SQM.
        # If no data is sent back yet, the respond is an empty byte string b''.
        recv_str = b''

        while len(msg) < strlen:
            # Receiving response from SQM.
            recv_str = s.recv(strlen - len(msg))

            if recv_str == '':
                print("Received a non-byte empty string from the SQM.")

                logfile = open(file_log_month, 'a')
                logfile.write("  " + datetime.datetime.now().isoformat() + " - No respond from the SQM\n")
                logfile.close()

                msg = "error: no respond from the SQM"
                if sqmcommand == b'rx':
                    # If rx sent and SQM responded, get current time
                    t_now_UTC = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)

                    return msg, t_now_UTC
                else:
                    return msg

            msg = msg + recv_str.decode()

    # Close the socket so that other programs can access the SQM-LE.
    #    Note: Only one connection can be made to the SQM-LE at a time. Therefore
    #    leaving a connection open constantly prevents other connections from being
    #    made.
    s.close()

    if sqmcommand == b'rx':
        # If rx sent and SQM responded, get current time
        t_now_UTC = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)

        return msg, t_now_UTC
    else:
        return msg


# ---------------------------
# ---  format_data_str()  ---
# ---------------------------
# Data line formatting
def format_data_str():
    # Convert the UTC and local time, when the measurement was taken, into a string.
    t_UTC = t_now_UTC.strftime("%Y-%m-%dT%H:%M:%S.") + \
               (('{0:06d}').format(t_now_UTC.microsecond))[:3] + ';'
    t_local = t_now_local.strftime("%Y-%m-%dT%H:%M:%S.") + \
               (('{0:06d}').format(t_now_UTC.microsecond))[:3] + ';'

    # Extract the data from the received string.

    # Temperature measured at light sensor in degrees C.
    #   - Leading space for positive value.
    #   - Leading negative sign (-) for negative value.
    temperature = '%.1f;' % np.float64(rxstr[48:54])
    # Period of sensor in counts.
    #   - Counts occur at a rate of 460.8 kHz (14.7456MHz/32).
    counts = '%s;' % int(rxstr[23:33])
    # Frequency of sensor in Hz.
    frequence = '%i;' % int(rxstr[10:20])
    # Sky brightness value in mag/arcsec2.
    #   - Leading space for positive value.
    #   - Leading negative sign (-) for negative value.
    #   - A reading of 0.00m means that the light at the sensor has reached the upper
    #     brightness limit of the unit.
    sky_brightness = '%.2f' % np.float64(rxstr[2:8])

    return t_UTC + t_local + temperature + counts + frequence + sky_brightness + '\r\n'


# -----------------------
# ---  create_file()  ---
# -----------------------
# Procedure for creating new file, requires an existing .inp input file. Also creates
# a log file recording the time for last acquisition.
#
# The data files are generated according to the "Definition of the community standard
# for skyglow observations" of the IDA
#   https://www.darksky.org/wp-content/uploads/bsk-pdf-manager/47_SKYGLOW_DEFINITIONS.PDF
def create_file(filename_data):
    logfile = open(file_log_month, 'a')
    # if len(filename_data.split(os.sep)[-1].split('_')) == 3:
    # First boolean expression is to check when using the IDA standards for naming the
    # files and the second one is when not using the IDA standard.
    if len(filename_data.split(os.sep)[-1].split('_')) == 3 or \
            len(filename_data.split(os.sep)[-1].split('_')[-1].split('-')) == 3:
        print('\n---  Daily data file: ' + filename_data.split(os.sep)[-1] + '  ---')
        print('  Started creating @ ' + t_create_file_local.strftime("%Y-%m-%dT%H:%M:%S.") +
              (('{0:06d}').format(t_create_file_local.microsecond))[:3] + '\n')
        # logfile.write('\n\n---  Daily data file for ' +
        #               t_create_file_local.strftime("%Y-%m-%dT%H:%M:%S") + '  ---\n')
        logfile.write('\n\n---  Daily data file: ' + filename_data.split(os.sep)[-1] + '  ---\n')
        logfile.write('  Started creating @ ' + t_create_file_local.strftime("%Y-%m-%dT%H:%M:%S.") +
                      (('{0:06d}').format(t_create_file_local.microsecond))[:3] + '\n\n')
    else:
        print('\n===  Monthly data file: ' + filename_data.split(os.sep)[-1] + '  ===')
        print('  Started creating @ ' + t_create_file_local.strftime("%Y-%m-%dT%H:%M:%S.") +
              (('{0:06d}').format(t_create_file_local.microsecond))[:3] + '\n')
        # logfile.write('\n\n===  Monthly data file for ' + str(t_create_file_local.year) + \
        #               '-%02i' % t_create_file_local.month + '  ===\n')
        logfile.write('\n\n===  Monthly data file: ' + filename_data.split(os.sep)[-1] + '  ===\n')
        logfile.write('  Started creating @ ' + t_create_file_local.strftime("%Y-%m-%dT%H:%M:%S.") +
                      (('{0:06d}').format(t_create_file_local.microsecond))[:3] + '\n\n')
    logfile.close()

    # Send the information command.
    print("  Sending 'ix' command ...")
    logfile = open(file_log_month, 'a')
    logfile.write("  Sending 'ix' command ...\n")
    logfile.close()

    ixstr = get_SQM_data(b'ix')

    print("    'ix' response: " + repr(ixstr))
    logfile = open(file_log_month, 'a')
    logfile.write("    'ix' response: " + repr(ixstr) + "\n")
    logfile.close()

    # if ixstr.find('error') > 0:
    if (ixstr.find('error') > 0) or (ixstr[:1] != 'i'):
        print("      -->  Trying to reconnect and sending the 'ix' command ...")
        logfile = open(file_log_month, 'a')
        logfile.write("      -->  Trying to reconnect and sending the 'ix' command ...\n")
        logfile.close()

        ix_err = True

        # Wait 1 minute, before trying again to connect and send the 'ix' command.
        time.sleep(60)

        while ix_err:
            ixstr = get_SQM_data(b'ix')

            print("    'ix' response: " + repr(ixstr))
            logfile = open(file_log_month, 'a')
            logfile.write("    'ix' response: " + repr(ixstr) + "\n")
            logfile.close()

            # if ixstr.find('error') > 0:
            if (ixstr.find('error') > 0) or (ixstr[:1] != 'i'):
                print("      -->  Trying to reconnect and sending the 'ix' command ...")
                logfile = open(file_log_month, 'a')
                logfile.write("      -->  Trying to reconnect and sending the 'ix' command ...\n")
                logfile.close()

                ix_err = True

                # Wait 1 minute, before trying again to connect and send the 'ix' command.
                time.sleep(60)
            else:
                print("    -->  Could connect again and received 'ix' response.\n")
                logfile = open(file_log_month, 'a')
                logfile.write("    -->  could connect again and received 'ix' response.\n")
                logfile.close()

                ix_err = False
    else:
        print("    -->  Received 'ix' response.")
        logfile = open(file_log_month, 'a')
        logfile.write("    -->  Received 'ix' response.\n")
        logfile.close()

    # Send the calibration command.
    print("  Sending 'cx' command ...")
    logfile = open(file_log_month, 'a')
    logfile.write("  Sending 'cx' command ...\n")
    logfile.close()

    cxstr = get_SQM_data(b'cx')

    print("    'cx' response: " + repr(cxstr))
    logfile = open(file_log_month, 'a')
    logfile.write("    'cx' response: " + repr(cxstr) + "\n")
    logfile.close()

    # if cxstr.find('error') > 0:
    if (cxstr.find('error') > 0) or (cxstr[:1] != 'c'):
        print("      -->  Trying to reconnect and sending the 'cx' command ...")
        logfile = open(file_log_month, 'a')
        logfile.write("      -->  Trying to reconnect and sending the 'cx' command ...\n")
        logfile.close()

        cx_err = True

        # Wait 1 minute, before trying again to connect and send the 'cx' command.
        time.sleep(60)

        while cx_err:
            cxstr = get_SQM_data(b'cx')

            print("    'cx' response: " + repr(cxstr))
            logfile = open(file_log_month, 'a')
            logfile.write("    'cx' response: " + repr(cxstr) + "\n")
            logfile.close()

            # if cxstr.find('error') > 0:
            if (cxstr.find('error') > 0) or (cxstr[:1] != 'c'):
                print("      -->  Trying to reconnect and sending the 'cx' command ...")
                logfile = open(file_log_month, 'a')
                logfile.write("      -->  Trying to reconnect and sending the 'cx' command ...\n")
                logfile.close()

                cx_err = True

                # Wait 1 minute, before trying again to connect and send the 'cx' command.
                time.sleep(60)
            else:
                print("    -->  Could connect again and received 'cx' response.")
                logfile = open(file_log_month, 'a')
                logfile.write("    -->  could connect again and received 'cx' response.\n")
                logfile.close()

                cx_err = False
    else:
        print("    -->  Received 'cx' response.")
        logfile = open(file_log_month, 'a')
        logfile.write("    -->  Received 'cx' response.\n")
        logfile.close()

    # Send the request for data command.
    print("  Sending 'rx' test command ...")
    logfile = open(file_log_month, 'a')
    logfile.write("  Sending 'rx' test command ...\n")
    logfile.close()

    rxstr, t_dummy = get_SQM_data(b'rx')

    print("    'rx' response: " + repr(rxstr))
    logfile = open(file_log_month, 'a')
    logfile.write("    'rx' response: " + repr(rxstr) + "\n")
    logfile.close()

    # if rxstr.find('error') > 0:
    if (rxstr.find('error') > 0) or (rxstr[:1] != 'r'):
        print("      -->  Trying to reconnect and sending the 'rx' command ...")
        logfile = open(file_log_month, 'a')
        logfile.write("      -->  Trying to reconnect and sending the 'rx' command ...\n")
        logfile.close()

        rx_err = True

        # Wait 1 minute, before trying again to connect and send the 'rx' command.
        time.sleep(60)

        while rx_err:
            rxstr, t_dummy = get_SQM_data(b'rx')

            print("    'rx' response: " + repr(rxstr))
            logfile = open(file_log_month, 'a')
            logfile.write("    'rx' response: " + repr(rxstr) + "\n")
            logfile.close()

            # if rxstr.find('error') > 0:
            if (rxstr.find('error') > 0) or (rxstr[:1] != 'r'):
                print("      -->  Trying to reconnect and sending the 'rx' command ...")
                logfile = open(file_log_month, 'a')
                logfile.write("      -->  Trying to reconnect and sending the 'rx' command ...\n")
                logfile.close()

                rx_err = True

                # Wait 1 minute, before trying again to connect and send the 'rx' command.
                time.sleep(60)
            else:
                print("    -->  Could connect again and received 'rx' response.\n")
                logfile = open(file_log_month, 'a')
                logfile.write("    -->  could connect again and received 'rx' response.\n")
                logfile.close()

                rx_err = False
    else:
        print("    -->  Received 'rx' response.")
        logfile = open(file_log_month, 'a')
        logfile.write("    -->  Received 'rx' response.\n")
        logfile.close()

    if len(filename_data.split(os.sep)[-1].split('_')) == 3:
        print("\n  Started creating daily data file ...")
        logfile = open(file_log_month, 'a')
        logfile.write("\n  Started creating daily data file ...\n")
        logfile.close()
    else:
        print("\n  Started creating monthly data file ...")
        logfile = open(file_log_month, 'a')
        logfile.write("\n  Started creating monthly data file ...\n")
        logfile.close()

    # Create the directory, in case it doesn't exist yet.
    if not os.path.exists(os.sep.join(filename_data.split(os.sep)[:-1])):
        os.makedirs(os.sep.join(filename_data.split(os.sep)[:-1]))

    # Create the daily data file.
    outfile = open(filename_data, 'w')
    # outfile.write('# Community Standard Skyglow Data Format 1.0\r\n')
    # outfile.write('# URL: https://www.darksky.org/wp-content/uploads/bsk-pdf-manager/47_SKYGLOW_DEFINITIONS.PDF\r\n')
    outfile.write('# Light Pollution Monitoring Data Format 1.0\r\n')
    outfile.write('# URL: http://www.darksky.org/measurements\r\n')
    outfile.write('# Number of header lines: 36\r\n')
    outfile.write('# This data is released under the following license: '
                  'ODbL 1.0 http://opendatacommons.org/licenses/odbl/summary/\r\n')
    outfile.write('# Device type: ' + lines[3] + '\r\n')
    outfile.write('# Instrument ID: ' + lines[4] + '\r\n')
    outfile.write('# Data supplier: ' + lines[5] + '\r\n')
    outfile.write('# Location name: ' + lines[6] + '\r\n')
    outfile.write('# Position (lat, lon, elev(m)): ' + lines[7] + '\r\n')
    outfile.write('# Local timezone: ' + lines[8] + '\r\n')
    outfile.write('# Time Synchronization: ' + lines[9] + '\r\n')
    outfile.write('# Moving / Stationary position: STATIONARY\r\n')
    outfile.write('# Moving / Fixed look direction: FIXED\r\n')
    outfile.write('# Number of channels: 1\r\n')
    outfile.write('# Filters per channel: ' + lines[10] + '\r\n')
    outfile.write('# Measurement direction per channel: ' + lines[11] + '\r\n')
    outfile.write('# Field of view (degrees): ' + lines[12] + '\r\n')
    outfile.write('# Number of fields per line: 6\r\n')
    outfile.write('# SQM serial number: ' + str(int(ixstr[29:37])) + '\r\n')
    outfile.write('# SQM hardware identity: \r\n')
    outfile.write('# SQM firmware version: ' + str(int(ixstr[2:10])) + '-' + str(int(ixstr[11:19])) + '-' + str(
        int(ixstr[20:28])) + '\r\n')
    outfile.write('# SQM cover offset value: ' + lines[13] + '\r\n')
    outfile.write('# SQM readout test ix: ' + ixstr + '\r\n')
    outfile.write('# SQM readout test rx: ' + rxstr + '\r\n')
    outfile.write('# SQM readout test cx: ' + cxstr + '\r\n')
    outfile.write('# Comment: ' + lines[14] + '\r\n')
    outfile.write('# Comment: ' + lines[15] + '\r\n')
    outfile.write('# Comment: ' + lines[16] + '\r\n')
    outfile.write('# Comment: ' + lines[17] + '\r\n')
    outfile.write('# Comment: ' + lines[18] + '\r\n')
    outfile.write('# blank line 31\r\n')
    outfile.write('# blank line 32\r\n')
    outfile.write('# blank line 33\r\n')
    outfile.write('# UTC Date & Time, Local Date & Time, Temperature, Counts, Frequency, MSAS\r\n')
    outfile.write('# YYYY-MM-DDTHH:mm:ss.fff;YYYY-MM-DDTHH:mm:ss.fff;Celsius;number;Hz;mag/arcsec^2\r\n')
    outfile.write('# END OF HEADER\r\n')
    outfile.close()

    # if len(filename_data.split(os.sep)[-1].split('_')) == 3:
    #     logfile.write("    -->  Finished (including the header).\n\n")
    # else:
    #     logfile.write("    -->  Finished (including the header).\n\n")
    print("    -->  Finished (including the header).")
    logfile = open(file_log_month, 'a')
    logfile.write("    -->  Finished (including the header).")
    logfile.close()


# **************************
# ***  read_SQM_data.py  ***
# **************************

# Check if already running.
iPID = AlreadyRunning ()

t_check = datetime.datetime.now().replace(microsecond=0).isoformat()
if iPID:
    print(f"{t_check} - Already running as process {iPID}.  Exiting.")
else:
    print(f"{t_check} - Running as process {os.getpid ()}.")

    # Start the actual read_SQM_data code.

    print("\n***  SQM-%s  ***\n" % args.obs_code)
    print("  Time interval between measurements: %i s" % args.t_interval)
    if args.nbr_measurements == -1:
        print("  Number of measurements: infinite")
    else:
        print("  Number of measurements: %i" % args.nbr_measurements)
    print("  Sky brightness value > %.2f mag/arcsec2 are added to the data files." % args.SB_min)
    print("  Filenames according to the IDA standards: %s\n" % str(flag_IDA_standard_filename))

    # Get the absolute path to the current file.
#    dir_code = os.path.dirname(os.path.realpath(__file__)) + os.sep
    dir_code = 'DSNdata' + os.sep

    # Define the directories for daily and monthly log files.
    if args.dir_logs == '':
        dir_logs = dir_code + '..' + os.sep + 'logs' + os.sep + args.obs_code + os.sep
    else:
        if args.dir_logs[-1:] != '/' or args.dir_logs[-1:] != '\\':
            dir_logs = (os.path.normcase(args.dir_logs)) + os.path.normcase('/')
        else:
            dir_logs = os.path.normcase(args.dir_logs)

    if not os.path.exists(dir_logs):
        os.makedirs(dir_logs)

    # dir_logs_year = dir_logs + str(datetime.datetime.now().year) + os.sep
    # if not os.path.exists(dir_logs_year):
    #     os.makedirs(dir_logs_year)
    #
    # dir_logs_month = dir_logs_year + str(datetime.datetime.now().year) + \
    #                  '-%02i' % datetime.datetime.now().month + os.sep
    # if not os.path.exists(dir_logs_month):
    #     os.makedirs(dir_logs_month)


    # Get the number of measurements
    #   n = -1 ... infinite number of measurements
    n = args.nbr_measurements

    # Get the time interval [s] between measurements
    t_interval = args.t_interval

    # Get the brightest sky brightness value [mag/arcsec2] that should
    # be added to the data file.
    SB_min = args.SB_min


    # Read the settings in the parameter file (.inp)
    #
    # --Beginning of File--
    # [URL]:[TCP Port]
    # [Nr. of measurements(0 means infinite)]:[Measurement interval (integer seconds)]
    # [New file creation time (24 hours HH:MM)],[(u)TC or (l)ocal time]
    # [SQM model]
    # [Instrument ID]
    # [Location name]
    # [Latitude],[Longitude],[Elevation]
    # [IANA time zone]
    # [Time synchronization method]
    # [Optical filter used by SQM]
    # [Zenith angle],[Azimuth angle]
    # [Field of view]
    # [Housing attenuation in MPSAS]
    # [Comment line 1]
    # [Comment line 2]
    # [Comment line 3]
    # [Comment line 4]
    # [Comment line 5]
    # --End of File--

    file_parameter = open(dir_code + 'SQM-' + sys.argv[1] + '.inp', "r")
    lines = file_parameter.readlines()

    # Iterate through each line of the parameter file and get rid of any escpae characters
    # at the end of each line.
    for i in range(len(lines)):
        if lines[i][-2:] == '\r\n':
            lines[i] = lines[i][:-2]
        if lines[i][-1:] == '\n':
            lines[i] = lines[i][:-1]
        if lines[i][-1:] == '\r':
            lines[i] = lines[i][:-1]

    # Get the url and the port for the SQM.
    SQM_url = lines[0].split(':')[0]
    SQM_port = int(lines[0].split(':')[1])

    # # Get the number of measurements
    # #   n = 0 ... infinite number of measurements
    # n = int(lines[1].split(',')[0])
    # if n == 0:
    #     n -= 1
    #
    # # Get the time interval [s] between measurements
    # t_interval = int(lines[1].split(',')[1])
    #
    # # Get the brightest sky brightness value [mag/arcsec2] that should
    # # be added to the data file.
    # SB_min = 0.

    # Define the counter for the number of readings of the SQM.
    count_reading = 1 #0

    t_create_file_local = datetime.datetime.now().astimezone(pytz.timezone(lines[8]))

    # ***   Define needed directory and filenames   ***

    # ---   Define directories   ---
    #   Yearly directory ... for the log files and the monthly data files.
    #   Monthly directory ... for the daily data files.

    # # Check, if it's before or after noon on 01/01/year.
    # if t_create_file_local.day == 1 and t_create_file_local.month == 1 and  \
    #         t_create_file_local.time() < datetime.time(hour=12):
    #     # If it's before noon on Jan 1, decrease year by one year (still use the previous year).
    #     dir_logs_year = dir_logs + str((t_create_file_local - relativedelta(years=1)).year) + os.sep
    #     dir_logs_year = dir_logs + str((t_create_file_local - relativedelta(years=1)).year) + os.sep
    #     dir_logs_month = dir_logs_year + str((t_create_file_local - relativedelta(years=1)).year) + \
    #                      '-%02i' % (t_create_file_local - relativedelta(months=1)).month + os.sep
    # else:
    #     # If it's noon or after noon on Jan 1, use the current year.
    #     dir_logs_year = dir_logs + str(t_create_file_local.year) + os.sep
    #     dir_logs_month = dir_logs_year + str(t_create_file_local.year) + \
    #                      '-%02i' % t_create_file_local.month + os.sep

    # ---  UPDATED CODE  ---
    # Check, if it's before noon on the 1st of a month/year
    #   - If it's before, use the previous month to save the file.
    if t_create_file_local.day == 1 and t_create_file_local.time() < datetime.time(hour=12):
        # Check, if it's also January, then use the previous year too.
        if t_create_file_local.month == 1:
            # dir_logs_year = dir_logs + str((t_create_file_local - relativedelta(years=1)).year) + os.sep
            str_year = str((t_create_file_local - relativedelta(years=1)).year)
        else:
            # dir_logs_year = dir_logs + str(t_create_file_local.year) + os.sep
            str_year = str(t_create_file_local.year)

        dir_logs_year = dir_logs + str_year + os.sep
        dir_logs_month = dir_logs_year + str_year + \
                         '-%02i' % (t_create_file_local - relativedelta(months=1)).month + os.sep
    else:
        dir_logs_year = dir_logs + str(t_create_file_local.year) + os.sep
        dir_logs_month = dir_logs_year + str(t_create_file_local.year) + \
                         '-%02i' % t_create_file_local.month + os.sep
    # ---  END OF UPDATED CODE  ---


    # Create the directories, in case they don't exist yet.
    if not os.path.exists(dir_logs_year):
        os.makedirs(dir_logs_year)
    if not os.path.exists(dir_logs_month):
        os.makedirs(dir_logs_month)

    # ---   Define filenames   ---

    # Define the file name for the monthly log file.
    if t_create_file_local.day == 1 and t_create_file_local.time() < datetime.time(hour=12):
        file_log_month = dir_logs_year + lines[4] + '_' + \
                 (t_create_file_local - relativedelta(months=1)).strftime("%Y-%m") + '.log'
    else:
        file_log_month = dir_logs_year + lines[4] + '_' + \
                         t_create_file_local.strftime("%Y-%m") + '.log'

    # Define the file names for the daily and monthly data file.
    if t_create_file_local.day == 1 and t_create_file_local.time() < datetime.time(hour=12):
        file_data_month = dir_logs_year + lines[4] + '_' + \
                  (t_create_file_local - relativedelta(months=1)).strftime("%Y-%m") + '.dat'
    else:
        file_data_month = dir_logs_year + lines[4] + '_' + \
                          t_create_file_local.strftime("%Y-%m") + '.dat'

    if flag_IDA_standard_filename:
        file_data_day = dir_logs_month + t_create_file_local.strftime("%Y%m%d_%H%M%S") + \
                        '_' + lines[4] + '.dat'
    else:
        # Start a new daily data file after noon (12:00).
        if t_create_file_local.time() < datetime.time(hour=12):
            file_data_day = dir_logs_month + lines[4] + '_' + \
                    (t_create_file_local.date() - datetime.timedelta(days=1)).isoformat() + '.dat'
        else:
            file_data_day = dir_logs_month + lines[4] + '_' + \
                            t_create_file_local.date().isoformat() + '.dat'

    # Check, if a new monthly log and data file need to be created.
    if not os.path.isfile(file_log_month):
        # Create log file.
        print(lines[4] + " - Log File for " + t_create_file_local.strftime("%Y-%m"))
        print("------------------------------")

        logfile = open(file_log_month, 'w')
        logfile.write(lines[4] + " - Log File for " + t_create_file_local.strftime("%Y-%m") + '\n')
        logfile.write("------------------------------\n")
        logfile.close()

    if not os.path.isfile(file_data_month):
        # Create data file.
        create_file(file_data_month)

    # Define the time, when to start a new log file.
    t_create_new_log_file_local = \
        t_create_file_local.replace(day=1, hour=12, minute=0, second=0, microsecond=0)
    if (t_create_file_local.day > 1) or \
            (t_create_file_local.day == 1 and t_create_file_local.time() > datetime.time(hour=12)):
        t_create_new_log_file_local = t_create_new_log_file_local + relativedelta(months=1)


    # Check, if a new daily data file needs to be created.
    if not os.path.isfile(file_data_day):
        # print("\n---  New data file for " +
        #       t_create_file_local.isoformat() + "  ---")

        create_file(file_data_day)


    # In case the code had to restart, add the time, when it started again recording data.
    print("  " + datetime.datetime.now().isoformat() + " - Starting recording data ...")
    print("  Time interval between measurements: %i s" % args.t_interval)
    if args.nbr_measurements == -1:
        print("  Number of measurements: infinite")
    else:
        print("  Number of measurements: %i" % args.nbr_measurements)
    print("  Sky brightness value > %.2f mag/arcsec2 are added to the data files." % args.SB_min)
    print("  Filenames according to the IDA standards: %s\n" % str(flag_IDA_standard_filename))

    logfile = open(file_log_month, 'a')
    logfile.write("  " + datetime.datetime.now().isoformat() + " - Starting recording data ...\n")
    logfile.write("      Time interval between measurements: %i s\n" % args.t_interval)
    if args.nbr_measurements == -1:
        logfile.write("      Number of measurements: infinite\n")
    else:
        logfile.write("      Number of measurements: %i" % args.nbr_measurements)
    logfile.write("      Sky brightness value > %.2f mag/arcsec2 are added to the data files.\n" %
                  args.SB_min)
    logfile.write("      Filenames according to the IDA standards: %s\n\n" %
                  str(flag_IDA_standard_filename))
    logfile.close()


    # Define the time, when to start a new data file.
    t_create_new_file_local = \
        t_create_file_local.replace(hour=12, minute=0, second=0, microsecond=0)
    if t_create_file_local.time() > datetime.time(hour=12, minute=0, second=0, microsecond=0):
        t_create_new_file_local = t_create_new_file_local + relativedelta(days=1)

    # Wait until a multiple of the time interval is reached to start recording.  This helps
    # when comparing different SQMs, because the data are recorded at the same time.
    print("Waiting for a multiple of the time interval to start recording data ...\n")
    # while datetime.datetime.now().second != 0:
    while datetime.datetime.now().second % t_interval != 0:
        time.sleep(0.001)

    print("Started recording data ...\n")
    logfile = open(file_log_month, 'a')
    logfile.write("    Started recording data @ " +
                  datetime.datetime.now().replace(microsecond=0).isoformat() + "\n\n")
    logfile.close()

    while n != 0:
        # Need this time to determine the waiting time for the next data acquiring.
        t_timing = datetime.datetime.now().replace(microsecond=0)

        # Read data from the SQM.
        rxstr, t_now_UTC = get_SQM_data(b'rx')

        # Check, if the SQM responded with an error.  If error occurred, reset the SQM
        # connection.
        if rxstr.find('error') > 0:
            # Since the connection is getting closed and started, when acquiring data, no
            # need to reset the connection to the SQM.
            print("      -->  Trying to reconnect and to acquire data ...")
            logfile = open(file_log_month, 'a')
            logfile.write("      -->  Trying to reconnect and to acquire data ...\n")
            logfile.close()

            # Wait 1 minute, before trying again to connect and send the 'rx' command.
            time.sleep(60)

            # Wait until a multiple of the time interval is reached to start recording.
            # This helps when comparing different SQMs, because the data are recorded at
            # the same time.
            while datetime.datetime.now().second % t_interval != 0:
                time.sleep(0.001)

            continue

        # Only add sky brightness data to the data file when it's higher than
        # the given max brightness value.
        if np.float64(rxstr[2:8]) <= SB_min:
            # Wait until a multiple of the time interval is reached to start recording.
            # This helps when comparing different SQMs, because the data are recorded at
            # the same time.
            while datetime.datetime.now().second % t_interval != 0:
                time.sleep(0.001)

            continue

        # count_reading = count_reading + 1

        # Convert the time of recording (t_now) from UTC to the local time zone.
        t_now_local = t_now_UTC.astimezone(pytz.timezone(lines[8]))

        recorded_data = format_data_str()

        # Check, if a new daily data file has to be created.
        if t_now_local > t_create_new_file_local:
            # print("\n---  New data file for " +
            #       t_create_file_local.date().isoformat() + "  ---")

            t_create_file_local = datetime.datetime.now().astimezone(pytz.timezone(lines[8]))

            # Define the time, when to start a new data file.
            t_create_new_file_local = \
                t_create_file_local.replace(hour=12, minute=0, second=0, microsecond=0) + \
                relativedelta(days=1)

            # Define the monthly directory for the daily data files.
            # # Check, if it's before or after noon on 01/01/year.
            # if t_create_file_local.day == 1 and t_create_file_local.month == 1 and \
            #         t_create_file_local.time() < datetime.time(hour=12):
            #     # If it's before noon on Jan 1, decrease year by one year (still use the previous year).
            #     dir_logs_year = dir_logs + str((t_create_file_local - relativedelta(years=1)).year) + os.sep
            #     dir_logs_month = dir_logs_year + str((t_create_file_local - relativedelta(years=1)).year) + \
            #                      '-%02i' % (t_create_file_local - relativedelta(months=1)).month + os.sep
            # else:
            #     # If it's noon or after noon on Jan 1, use the current year.
            #     dir_logs_year = dir_logs + str(t_create_file_local.year) + os.sep
            #     dir_logs_month = dir_logs_year + str(t_create_file_local.year) + \
            #                      '-%02i' % t_create_file_local.month + os.sep

            # ---  UPDATED CODE  ---
            # Check, if it's before noon on the 1st of a month/year
            #   - If it's before, use the previous month to save the file.
            if t_create_file_local.day == 1 and t_create_file_local.time() < datetime.time(hour=12):
                # Check, if it's also January, then use the previous year too.
                if t_create_file_local.month == 1:
                    # dir_logs_year = dir_logs + str((t_create_file_local - relativedelta(years=1)).year) + os.sep
                    str_year = str((t_create_file_local - relativedelta(years=1)).year)
                else:
                    # dir_logs_year = dir_logs + str(t_create_file_local.year) + os.sep
                    str_year = str(t_create_file_local.year)

                dir_logs_year = dir_logs + str_year + os.sep
                dir_logs_month = dir_logs_year + str_year + \
                                 '-%02i' % (t_create_file_local - relativedelta(months=1)).month + os.sep
            else:
                dir_logs_year = dir_logs + str(t_create_file_local.year) + os.sep
                dir_logs_month = dir_logs_year + str(t_create_file_local.year) + \
                                 '-%02i' % t_create_file_local.month + os.sep
            # ---  END OF UPDATED CODE  ---


            # Define the file name for the daily data file.
            if flag_IDA_standard_filename:
                file_data_day = dir_logs_month + \
                                t_create_file_local.strftime("%Y%m%d_%H%M%S") + '_' + \
                                lines[4] + '.dat'
            else:
                file_data_day = dir_logs_month + lines[4] + '_' + \
                                t_create_file_local.date().isoformat() + '.dat'

            create_file(file_data_day)

            print("  " + datetime.datetime.now().isoformat() + " - Starting recording data ...")
            print("  Time interval between measurements: %i s" % args.t_interval)
            if args.nbr_measurements == -1:
                print("  Number of measurements: infinite")
            else:
                print("  Number of measurements: %i" % args.nbr_measurements)
            print("  Sky brightness value > %.2f mag/arcsec2 are added to the data files." % args.SB_min)
            print("  Filenames according to the IDA standards: %s\n" % str(flag_IDA_standard_filename))

            logfile = open(file_log_month, 'a')
            logfile.write("  " + datetime.datetime.now().isoformat() +
                          " - Starting recording data ...\n")
            logfile.write("      Time interval between measurements: %i s\n" % args.t_interval)
            if args.nbr_measurements == -1:
                logfile.write("      Number of measurements: infinite\n")
            else:
                logfile.write("      Number of measurements: %i\n" % args.nbr_measurements)
            logfile.write("      Sky brightness value > %.2f mag/arcsec2 are added to the data files.\n" %
                          args.SB_min)
            logfile.write("      Filenames according to the IDA standards: %s\n\n" %
                          str(flag_IDA_standard_filename))
            logfile.close()

            print("Started recording data ...\n")
            logfile = open(file_log_month, 'a')
            logfile.write("    Started recording data @ " +
                          datetime.datetime.now().replace(microsecond=0).isoformat() + "\n\n")
            logfile.close()

            # Reset the counter for the number of readings of the SQM, everytime a new file
            # is created.  Thus, each file (each day) starts to count with 1.
            count_reading = 1

            # Add the last recorded data to the new file.  Otherwise, this
            # data would get lost.
            # count_reading = 1

            print("%4i  " % count_reading + recorded_data.replace('\r','').replace('\n',''))

            outfile = open(file_data_day, 'a')
            outfile.write(recorded_data)
            outfile.close()

            # # Reset the counter for the number of readings of the SQM, everytime a new file
            # # is created.  Thus, each file (each day) starts to count with 0.
            # count_reading = 0
        else:
            print("%4i  " % count_reading + recorded_data.replace('\r','').replace('\n',''))

            outfile = open(file_data_day, 'a')
            outfile.write(recorded_data)
            outfile.close()

        # Check, if a new monthly log and data file has to be created.
        if t_now_local > t_create_new_log_file_local:
            # Define the annual directory for the monthly data and log files.
            # # Check, if it's before or after noon on 01/01/year.
            # if t_create_file_local.day == 1 and t_create_file_local.month == 1 and \
            #         t_create_file_local.time() < datetime.time(hour=12):
            #     # If it's before noon on Jan 1, decrease year by one year (still use the previous year).
            #     dir_logs_year = dir_logs + str((t_create_file_local - relativedelta(years=1)).year) + os.sep
            # else:
            #     # If it's noon or after noon on Jan 1, use the current year.
            #     dir_logs_year = dir_logs + str(t_create_file_local.year) + os.sep

            # ---  UPDATED CODE  ---
            # Check, if it's before noon on the 1st of a month/year
            #   - If it's before, use the previous month to save the file.
            if t_create_file_local.day == 1 and t_create_file_local.time() < datetime.time(hour=12):
                # Check, if it's also January, then use the previous year too.
                if t_create_file_local.month == 1:
                    # dir_logs_year = dir_logs + str((t_create_file_local - relativedelta(years=1)).year) + os.sep
                    str_year = str((t_create_file_local - relativedelta(years=1)).year)
                else:
                    # dir_logs_year = dir_logs + str(t_create_file_local.year) + os.sep
                    str_year = str(t_create_file_local.year)

                dir_logs_year = dir_logs + str_year + os.sep
            else:
                dir_logs_year = dir_logs + str(t_create_file_local.year) + os.sep
            # ---  END OF UPDATED CODE  ---


            # Define the file name for the monthly log file.
            # file_log_month = dir_logs_year + lines[4] + '_' + \
            #                  str(t_now_local.year) + \
            #                  '-%02i' % t_now_local.month + '.log'
            file_log_month = dir_logs_year + lines[4] + '_' + t_now_local.strftime("%Y-%m") + '.log'

            # Define the file name for the monthly data file.
            # file_data_month = dir_logs_year + lines[4] + '_' + \
            #                   str(t_now_local.year) + \
            #                   '-%02i' % t_now_local.month + '.dat'
            file_data_month = dir_logs_year + lines[4] + '_' + t_now_local.strftime("%Y-%m") + '.dat'

            # Define the time, when to start a new log file.
            t_create_new_log_file_local = \
                t_now_local.replace(day=1, hour=12, minute=0, second=0, microsecond=0) + \
                relativedelta(months=1)

            # Create the directory, in case it doesn't exist yet.
            if not os.path.exists(os.sep.join(file_log_month.split(os.sep)[:-1])):
                os.makedirs(os.sep.join(file_log_month.split(os.sep)[:-1]))

            # Create log file.
            print(lines[4] + " - Log File for " + t_now_local.strftime("%Y-%m"))
            print("------------------------------")

            logfile = open(file_log_month, 'w')
            logfile.write(lines[4] + " - Log File for " + t_now_local.strftime("%Y-%m") + "\n")
            logfile.write("------------------------------\n")
            logfile.close()

            # Create data file.
            create_file(file_data_month)

            # Add the last recorded data to the new file.  Otherwise, this
            # data would get lost.
            outfile = open(file_data_month, 'a')
            outfile.write(recorded_data)
            outfile.close()
        else:
            outfile = open(file_data_month, 'a')
            outfile.write(recorded_data)
            outfile.close()

        count_reading = count_reading + 1

        # Wait the time interval before start acquiring the next data.
        if n > 0:
            n -= 1
            while (datetime.datetime.now().astimezone(pytz.utc)).replace(microsecond=0) - \
                    t_timing < datetime.timedelta(seconds=t_interval):
                time.sleep(0.001)
        if n < 0:
            # while datetime.datetime.now().astimezone(pytz.utc) - t_now_UTC < \
            while datetime.datetime.now() - t_timing < \
                    datetime.timedelta(seconds=t_interval):
                time.sleep(0.001)
