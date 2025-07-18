from __future__ import absolute_import, division, print_function, unicode_literals
import serial
import serial.tools.list_ports
import glob
import time
import threading
import os
import sys
import requests
from io import open ## for Python 2 & 3
from . import CanvasComm

import yaml
from dotenv import load_dotenv
env_path = os.path.abspath(".") + "/.env"
if os.path.abspath(".") is "/":
    env_path = "/home/pi/.env"
load_dotenv(env_path)
BASE_URL_API = os.getenv("DEV_BASE_URL_API", "api.canvas3d.io/")
from subprocess import call, check_output
try:
   from queue import Queue, Empty  ## for Python 3
except ImportError:
    from Queue import Queue, Empty  ## for Python 2
from . import constants

def getLog(msg, module='palette-2'):
    return '{ "msg": "' + str(msg) + '", "module": "' + str(module) +'" }'

class Omega():
    def __init__(self, plugin):
        self.logger = plugin.logger
        self._printer = plugin._printer
        self._printer_profile_manager = plugin._printer_profile_manager
        self._plugin_manager = plugin._plugin_manager
        self._identifier = plugin._identifier
        self._settings = plugin._settings
        self.ports = []
        self.ledThread = None
        self.isHubS = False

        self.writeQueue = Queue()

        self.resetVariables()
        self.resetConnection()

        # Tries to automatically connect to palette first
        if self._settings.get(["autoconnect"]):
            self.startConnectionThread()
        self.canvas_comm = CanvasComm.CanvasComm(plugin)

    def checkIfMosaicHub(self):
        return os.path.isdir(constants.TURQUOISE_PATH)

    def checkMosaicPluginsCompatibility(self):
        # this function will warn the user if they need to manually update their
        # other Mosaic plugins for python 3 compatibility
        if self.checkIfMosaicHub():
            plugins_to_update = []
            plugins_to_check = constants.MOSAIC_PYTHON_3_PLUGINS if self.isHubS else [constants.MOSAIC_PYTHON_3_PLUGINS[0]]
            for plugin in plugins_to_check:
                if self._plugin_manager.get_plugin_info(plugin["identifier"]):
                    name = self._plugin_manager.get_plugin_info(plugin["identifier"]).name
                    version = self._plugin_manager.get_plugin_info(plugin["identifier"]).version

                    if version < plugin["p3CompatibleVersion"]:
                        plugin_data = {
                            "name": name,
                            "url": plugin["url"],
                        }
                        plugins_to_update.append(plugin_data)

            if plugins_to_update:
                call(["sudo chown -R pi:pi /home/pi/OctoPrint/venv/lib/python2.7/site-packages/"], shell=True)
                self.updateUI({"command": "python3", "data": plugins_to_update})

    def checkLedScriptFlag(self):
        led_script_flag = "/home/pi/.mosaicdata/led_flag"
        return os.path.isfile(led_script_flag)

    def updateHubSLedScript(self):
        if self.isHubS and not self.checkLedScriptFlag():
            self.logger.info(getLog(getLog("Updating LED script")))
            updated_script_path = "/home/pi/OctoPrint/venv/lib/python2.7/site-packages/octoprint_palette2/led.py"
            led_script_path = "/home/pi/led.py"
            call(["cp %s %s" % (updated_script_path, led_script_path)], shell=True)
            script_flag_path = "/home/pi/.mosaicdata/led_flag"
            call(["touch %s" % script_flag_path], shell=True)
            self.logger.debug(getLog("LED script updated. Please restart the CANVAS Hub S"))

    def determineHubVersion(self):
        hub_file_path = os.path.expanduser('~') + "/.mosaicdata/canvas-hub-data.yml"
        if os.path.exists(hub_file_path):
            with open(hub_file_path, "r") as hub_data:
                hub_yaml = yaml.safe_load(hub_data)
            if 'canvas-hub' in hub_yaml and 'device' in hub_yaml["canvas-hub"]:
                model = hub_yaml["canvas-hub"]["device"]["model"]
                if model == 'mosaic-s':
                    return True
        return False

    def getAllPorts(self):
        baselist = []

        if 'win32' in sys.platform:
            # use windows com stuff
            self.logger.info(getLog("Using a windows machine"))
            for port in serial.tools.list_ports.grep('.*0403:6015.*'):
                self.logger.info(getLog("got port %s" % port.device))
                baselist.append(port.device)

        baselist = baselist \
            + glob.glob('/dev/serial/by-id/*FTDI*') \
            + glob.glob('/dev/*usbserial*') \

        baselist = self.getRealPaths(baselist)
        # get unique values only
        baselist = list(set(baselist))
        return baselist

    def displayPorts(self, condition):
        # only change settings if user is opening the list of ports
        if "opening" in condition:
            self._settings.set(["autoconnect"], False, force=True)
            self._settings.save(force=True)
            self.updateUI({"command": "autoConnect", "data": self._settings.get(["autoconnect"])})
        self.ports = self.getAllPorts()
        self.logger.info(getLog("All ports: %s" % self.ports))
        self.logger.info(getLog("Selected port: %s" % self._settings.get(["selectedPort"])))
        self.updateUI({"command": "ports", "data": self.ports})
        self.updateUI({"command": "selectedPort", "data": self._settings.get(["selectedPort"])})
        if not self.ports:
            raise Exception(constants.P2_CONNECTION["NO_SERIAL_PORTS_FOUND"])

    def getRealPaths(self, ports):
        self.logger.info(getLog("Paths: %s" % ports))
        for index, port in enumerate(ports):
            port = os.path.realpath(port)
            ports[index] = port
        return ports

    def isPrinterPort(self, selected_port):
        selected_port = os.path.realpath(selected_port)
        printer_port = self._printer.get_current_connection()[1]
        self.logger.info(getLog("Printer port: %s" % printer_port))
        # because ports usually have a second available one (.tty or .cu)
        printer_port_alt = ""
        if printer_port == None:
            return False
        else:
            if "tty." in printer_port:
                printer_port_alt = printer_port.replace("tty.", "cu.", 1)
            elif "cu." in printer_port:
                printer_port_alt = printer_port.replace("cu.", "tty.", 1)
            self.logger.info(getLog("Printer port alt: %s" % printer_port_alt))
            if selected_port == printer_port or selected_port == printer_port_alt:
                return True
            else:
                return False

    def connectOmega(self, port):
        if self.connected is False:
            self.ports = self.getAllPorts()
            self.logger.info(getLog("Potential ports: %s" % self.ports))
            if len(self.ports) > 0:
                # if manual port given, try that first
                if port:
                    self.logger.info(getLog("Attempting manually selected port"))
                    if not self.isPrinterPort(port):
                        self.attemptSerialConnection(port)
                    else:
                        self.updateUIAll()
                        raise Exception(constants.P2_CONNECTION["PRINTER_ON_CURRENT_PORT"])
                else:
                    # try the last successfully connected port first, if any
                    lastConnectedP2Port = self._settings.get(["selectedPort"])
                    if lastConnectedP2Port:
                        self.logger.info(getLog("Attempting last successfully connected port"))
                        self.attemptSerialConnection(lastConnectedP2Port)

                    # loop through all ports
                    for serialPort in self.ports:
                        if self.isPrinterPort(serialPort) or lastConnectedP2Port:
                            continue
                        if self.attemptSerialConnection(serialPort):
                            break
                if not self.connected:
                    self._settings.set(["selectedPort"], None, force=True)
                    self._settings.save(force=True)
                    self.updateUIAll()
                    raise Exception(constants.P2_CONNECTION["HEARTBEAT_CONNECT_FAILURE"])
                else:
                    self.canvas_comm.send_message({ 'connection': 'palette 2 connected',
                                                    'port': self._settings.get(["selectedPort"])
                                                    })
            else:
                self.updateUIAll()
                raise Exception(constants.P2_CONNECTION["NO_SERIAL_PORTS_FOUND"])
        else:
            self.updateUIAll()
            raise Exception(constants.P2_CONNECTION["ALREADY_CONNECTED"])

    def attemptSerialConnection(self, port):
        default_baudrate = self._settings.get(["baudrate"])
        second_baudrate = self.getSecondBaudrate(default_baudrate)
        baudrates = [default_baudrate, second_baudrate]
        for baudrate in baudrates:
            try:
                if self.tryHeartbeatBeforeConnect(port, baudrate):
                    break
            except Exception as e:
                self.logger.info(getLog(e))
        return self.connected

    def getSecondBaudrate(self, default_baudrate):
        if default_baudrate == 115200:
            return 250000
        elif default_baudrate == 250000:
            return 115200

    def tryHeartbeatBeforeConnect(self, port, baudrate):
        self.logger.info(getLog("Trying: port (%s) and baudrate (%s)" %(port, baudrate)))
        self.omegaSerial = serial.Serial(port, baudrate, timeout=0.5)
        self.startReadThread()
        self.startWriteThread()
        self.enqueueCmd("\n")
        self.enqueueCmd(constants.COMMANDS["HEARTBEAT"])

        timeout = 3
        timeout_start = time.time()
        # Wait for Palette to respond with a handshake within 3 seconds
        while time.time() < timeout_start + timeout:
            if self.heartbeat:
                self.connected = True
                self.logger.info(getLog("P2 plugin successfully connected to P2"))
                self._settings.set(["selectedPort"], port, force=True)
                self._settings.set(["baudrate"], baudrate, force=True)
                self._settings.save(force=True)
                self.enqueueCmd(constants.COMMANDS["GET_FIRMWARE_VERSION"])
                self.updateUI({"command": "selectedPort", "data": self._settings.get(["selectedPort"])})
                self.updateUIAll()
                return True
            else:
                time.sleep(0.01)
        if not self.heartbeat:
            self.resetOmega()
            self.logger.info(getLog("Not the %s baudrate" % baudrate))
            return False

    def tryHeartbeatBeforePrint(self):
        self.heartbeat = False
        self.enqueueCmd("\n")
        self.enqueueCmd(constants.COMMANDS["HEARTBEAT"])
        self.printHeartbeatCheck = "Checking"

    def setFilename(self, name):
        self.filename = name

    def startReadThread(self):
        if self.readThread is None:
            self.logger.info(getLog("Omega Read Thread: starting thread"))
            self.readThreadStop = False
            self.readThread = threading.Thread(
                target=self.omegaReadThread,
                args=(self.omegaSerial,)
            )
            self.readThread.daemon = True
            self.readThread.start()

    def startWriteThread(self):
        if self.writeThread is None:
            self.logger.info(getLog("Omega Write Thread: starting thread"))
            self.writeThreadStop = False
            self.writeThread = threading.Thread(
                target=self.omegaWriteThread,
                args=(self.omegaSerial,)
            )
            self.writeThread.daemon = True
            self.writeThread.start()

    def startConnectionThread(self):
        if self.connectionThread is None:
            self.logger.info(getLog("Omega Auto-Connect Thread: starting thread"))
            self.connectionThreadStop = False
            self.connectionThread = threading.Thread(
                target=self.omegaConnectionThread
            )
            self.connectionThread.daemon = True
            self.connectionThread.start()

    def stopReadThread(self):
        self.readThreadStop = True
        if self.readThread and threading.current_thread() != self.readThread:
            self.readThread.join()
        self.readThread = None

    def stopWriteThread(self):
        self.writeThreadStop = True
        if self.writeThread and threading.current_thread() != self.writeThread:
            self.writeThread.join()
        self.writeThread = None

    def stopConnectionThread(self):
        self.connectionThreadStop = True
        if self.connectionThread and threading.current_thread() != self.connectionThread:
            self.connectionThread.join()
        self.connectionThread = None

    def omegaReadThread(self, serialConnection):
        while self.readThreadStop is False:
            try:
                line = serialConnection.readline()
                if line:
                    line = line.decode().strip()
                    command = self.parseLine(line)
                    if command != None:
                        number = command["number"]
                        params = command["params"]
                        total_params = len(params)
                        if number != 99:
                            self.logger.info(getLog("Omega Read Thread: reading: %s" % line))
                        # only respond to these commands if a
                        # connected mode print (.mcf.gcode) is currently happening
                        if self.isConnectedMode:
                            if number == 20:
                                if total_params > 0:
                                    if params[0] == "D5":
                                        self.handleFirstTimePrint()
                                    else:
                                        self.handleP2RequestForMoreInfo(command)
                            elif number == 34:
                                if total_params == 1:
                                    # if reject ping
                                    if params[0] == "D0":
                                        self.handleRejectedPing()
                                elif total_params > 2:
                                    # if ping
                                    if params[0] == "D1":
                                        self.handlePing(command)
                                    # else pong
                                    elif params[0] == "D2":
                                        self.handlePong(command)
                            elif number == 40:
                                self.handleResumeRequest()
                            elif number == 88:
                                if total_params > 0:
                                    self.handleErrorDetected(command)
                            elif number == 97:
                                if total_params > 0:
                                    if params[0] == "U0":
                                        if total_params > 1:
                                            if params[1] == "D0":
                                                self.handleSpliceCompletion()
                                            elif params[1] == "D2":
                                                self.handlePrintCancelling()
                                            elif params[1] == "D3":
                                                self.handlePrintCancelled()
                                    elif params[0] == "U25":
                                        if total_params > 2:
                                            if params[1] == "D0":
                                                self.handleSpliceStart(command)
                                    elif params[0] == "U26":
                                        if total_params > 1:
                                            self.handleFilamentUsed(command)
                                    elif params[0] == "U39":
                                        if total_params == 1:
                                            self.handleLoadingOffsetStart()
                                        # positive integer
                                        elif "-" in params[1]:
                                            self.handleLoadingOffsetExtrude(command)
                                        # negative integer or 0
                                        elif "-" not in params[1]:
                                            self.handleLoadingOffsetCompletion(command)
                                    elif self.drivesInUse and params[0] == self.drivesInUse[0]:
                                        if total_params > 1 and params[1] == "D0":
                                            self.handleDrivesLoading()
                                    elif self.drivesInUse and params[0] == self.drivesInUse[-1]:
                                        if total_params > 1 and params[1] == "D1":
                                            self.handleFilamentOutgoingTube()
                            elif number == 100:
                                self.handlePauseRequest()
                            elif number == 102:
                                if total_params > 0:
                                    if params[0] == "D0":
                                        self.handleSmartLoadRequest()
                        # always respond to these commands
                        # even if a connected mode print is not currently happening
                        if number == 50:
                            if total_params > 0:
                                firmware_version = params[0].replace("D","")
                                if firmware_version >= "9.0.9":
                                    self.startHeartbeatThread()
                            else:
                                self.sendAllMCFFilenamesToOmega()
                        elif number == 53:
                            if total_params > 1:
                                if params[0] == "D1":
                                    self.handleStartPrintFromP2(command)
                        elif number == 97:
                                if total_params > 0:
                                    if params[0] == "U25":
                                        if total_params > 2:
                                            if params[1] == "D0":
                                                self.feedRateControlStart()
                                            elif params[1] == "D1":
                                                self.feedRateControlEnd()
            except Exception as e:
                # Something went wrong with the connection to Palette2
                self.logger.error(getLog("Palette 2 Read Thread error"))
                self.logger.error(getLog(str(e)))
                self.readThreadError = True
                break
        if self.readThreadError:
            self.disconnect()
            self.updateUI({"command": "alert", "data": "threadError"})

    def omegaWriteThread(self, serialConnection):
        while self.writeThreadStop is False:
            try:
                line = self.writeQueue.get(True, 0.5)
                if line:
                    self.lastCommandSent = line
                    line = line.strip()
                    if line and constants.COMMANDS["HEARTBEAT"] not in line:
                        self.logger.info(getLog("Omega Write Thread: sending: %s" % line))
                    serialConnection.write((line + "\n").encode())
                else:
                    self.logger.info(getLog("Line is NONE"))
            except Empty:
                pass
            except Exception as e:
                self.logger.info(getLog("Palette 2 Write Thread Error"))
                self.logger.info(getLog(e))

    def omegaConnectionThread(self):
        while self.connectionThreadStop is False:
            if self.connected is False and not self._printer.is_printing():
                try:
                    self.connectOmega("")
                except Exception as e:
                    self.logger.info(getLog(e))
            time.sleep(1)

    def startLedThread(self):
        self.logger.info(getLog('starting led thread'))
        if self.isHubS:
            print('is hub s')
            if self.ledThread is not None:
                print('led thread already running. stopping now.')
                self.stopLedThread()
            self.logger.info(getLog("Omega Led Thread: starting thread"))

            self.ledThreadStop = False
            self.ledThread = threading.Thread(target=self.omegaLedThread)
            self.ledThread.daemon = True
            self.ledThread.start()
            self.logger.info(getLog('led thread started'))

    def stopLedThread(self):
        if self.isHubS:
            self.ledThreadStop = True
            if self.ledThread and threading.current_thread() != self.ledThread:
                self.ledThread.join()
            self.ledThread = None

    def omegaLedThread(self):
        palette_flag_path = "/home/pi/.mosaicdata/palette_flag"
        printer_flag_path = "/home/pi/.mosaicdata/printer_flag"
        try:
            while not self.ledThreadStop:
                if self.connected:
                    if not os.path.exists(palette_flag_path):
                        call(["touch %s" % palette_flag_path], shell=True)
                else:
                    if os.path.exists(palette_flag_path):
                        call(["rm %s" % palette_flag_path], shell=True)
                if self._printer.get_state_id() in ["OPERATIONAL", "PRINTING", "PAUSED"]:
                    if not os.path.exists(printer_flag_path):
                        call(["touch %s" % printer_flag_path], shell=True)
                else:
                    if os.path.exists(printer_flag_path):
                        call(["rm %s" % printer_flag_path], shell=True)
                time.sleep(2)
        except Exception as e:
                self.logger.info(getLog("Palette 2 Led Thread Error"))
                self.logger.info(getLog(e))

    def startHeartbeatThread(self):
        if self.heartbeatThread is not None:
            self.stopHeartbeatThread()
        self.logger.info(getLog("Omega Heartbeat Thread: starting thread"))
        self.heartbeatThreadStop = False
        self.heartbeatSent = False
        self.heartbeatReceived = False
        self.heartbeatThread = threading.Thread(target=self.omegaHeartbeatThread)
        self.heartbeatThread.daemon = True
        self.heartbeatThread.start()

    def stopHeartbeatThread(self):
        self.heartbeatThreadStop = True
        if self.heartbeatThread and threading.current_thread() != self.heartbeatThread:
            self.heartbeatThread.join()
        self.heartbeatThread = None

    def omegaHeartbeatThread(self):
        try:
            while not self.heartbeatThreadStop:
                if not self.palette2SetupStarted and not self.actualPrintStarted:
                    if self.heartbeatSent and not self.heartbeatReceived:
                        self.logger.info(getLog("Did not receive heartbeat response"))
                        self.disconnect()
                        break
                    self.heartbeatSent = True
                    self.heartbeatReceived = False
                    self.enqueueCmd(constants.COMMANDS["HEARTBEAT"])
                time.sleep(2)
        except Exception as e:
                self.logger.info(getLog("Palette 2 Heartbeat Thread Error"))
                self.logger.info(getLog(e))

    def enqueueCmd(self, line):
        self.writeQueue.put(line)

    def cut(self):
        self.enqueueCmd(constants.COMMANDS["CUT"])

    def clear(self):
        for command in constants.COMMANDS["CLEAR"]:
            self.enqueueCmd(command)

    def cancel(self):
        self.enqueueCmd(constants.COMMANDS["CANCEL"])

    def getJobData(self):
        data = {}
        data["pings"] = self.pings
        data["pongs"] = self.pongs
        data["currentStatus"] = self.currentStatus
        data["totalSplices"] = self.msfNS
        data["currentSplice"] = self.currentSplice
        data["p2Connection"] = self.connected
        data["filamentLength"] = self.filamentLength
        data["amountLeftToExtrude"] = self.amountLeftToExtrude
        data["printPaused"] = self._printer.is_paused()
        data["isSplicing"] = self.isSplicing
        return data

    def updateUIAll(self):
        self.logger.info(getLog("Updating all UI variables"))
        self.updateUI({"command": "printHeartbeatCheck", "data": self.printHeartbeatCheck}, True)
        self.updateUI({"command": "pings", "data": self.pings}, True)
        self.updateUI({"command": "pongs", "data": self.pongs}, True)
        self.updateUI({"command": "actualPrintStarted", "data": self.actualPrintStarted}, True)
        self.updateUI({"command": "palette2SetupStarted", "data": self.palette2SetupStarted}, True)
        self.updateUI({"command": "firstTime", "data": self.firstTime}, True)
        self.updateUI({"command": "currentStatus", "data": self.currentStatus}, True)
        self.updateUI({"command": "totalSplices", "data": self.msfNS}, True)
        self.updateUI({"command": "currentSplice", "data": self.currentSplice}, True)
        self.updateUI({"command": "p2Connection", "data": self.connected}, True)
        self.updateUI({"command": "filamentLength", "data": self.filamentLength}, True)
        self.updateUI({"command": "amountLeftToExtrude", "data": self.amountLeftToExtrude}, True)
        self.updateUI({"command": "printPaused", "data": self._printer.is_paused()}, True)
        self.updateUI({"command": "ports", "data": self.getAllPorts()}, True)
        self.settingsUpdateUI()
        self.advancedUpdateUI()

    def updateUI(self, data, log=None):
        if not log:
            if data["command"] == "advanced":
                self.logger.info(getLog("Updating UI: %s" % data["subCommand"]))
            else:
                self.logger.info(getLog("Updating UI: %s" % data["command"]))
        self._plugin_manager.send_plugin_message(self._identifier, data)

    def settingsUpdateUI(self):
        self.updateUI({"command": "displaySetupAlerts", "data": self._settings.get(["palette2Alerts"])}, True)
        self.updateUI({"command": "autoStartAfterLoad", "data": self._settings.get(["autoStartAfterLoad"])}, True)
        self.updateUI({"command": "autoConnect", "data": self._settings.get(["autoconnect"])}, True)
        self.updateUI({"command": "advanced", "subCommand": "displayAdvancedOptions", "data": self._settings.get(["advancedOptions"])}, True)

    def sendNextData(self, dataNum):
        if dataNum == 0:
            try:
                self.logger.info(getLog("Sending header '%s' to P2" % self.sentCounter))
                self.enqueueCmd(self.header[self.sentCounter])
                self.sentCounter = self.sentCounter + 1
            except:
                self.logger.info(getLog("Incorrect header information: %s" % self.header))
                self.logger.info(getLog("Sent counter: %s" % self.sentCounter))
        elif dataNum == 1:
            try:
                self.logger.info(getLog("Sending splice '%s' info to P2" % self.spliceCounter))
                splice = self.splices[self.spliceCounter]
                cmdStr = "%s D%d D%s\n" % (constants.COMMANDS["SPLICE"], int(splice[0]), splice[1])
                self.enqueueCmd(cmdStr)
                self.spliceCounter = self.spliceCounter + 1
            except:
                self.logger.info(getLog("Incorrect splice information: %s" % self.splices))
                self.logger.info(getLog("Splice counter: %s" % self.spliceCounter))
        elif dataNum == 2:
            self.logger.info(getLog("Sending current ping '%s' to P2" % self.currentPingCmd))
            self.enqueueCmd(self.currentPingCmd)
        elif dataNum == 4:
            try:
                self.logger.info(getLog("Sending algo '%s' to P2" % self.algoCounter))
                self.enqueueCmd(self.algorithms[self.algoCounter])
                self.algoCounter = self.algoCounter + 1
            except:
                self.logger.info(getLog("Incorrect algo information: %s" % self.algorithms))
                self.logger.info(getLog("Algo counter: %s" % self.algoCounter))
        elif dataNum == 8:
            self.logger.info(getLog("Need to resend last line to P2"))
            self.enqueueCmd(self.lastCommandSent)

    def savePing(self, pingCmd):
        self.logger.info(getLog("Reached a ping in the gcode -- saving it"))
        self.currentPingCmd = pingCmd
        self.enqueueCmd(constants.COMMANDS["PING"])

    def resetConnection(self):
        self.logger.info(getLog("Resetting threads"))

        self.stopReadThread()
        self.stopWriteThread()
        self.stopAutoLoadThread()
        self.stopHeartbeatThread()
        if not self._settings.get(["autoconnect"]):
            self.stopConnectionThread()

        if self.omegaSerial:
            self.omegaSerial.close()
            self.omegaSerial = None
        self.connectionStop = False

        # clear command queue
        while not self.writeQueue.empty():
            self.writeQueue.get()

    def resetVariables(self):
        self.logger.info(getLog("Resetting all values"))
        self.omegaSerial = None
        self.sentCounter = 0
        self.algoCounter = 0
        self.spliceCounter = 0

        self.msfNS = 0
        self.msfNA = "0"
        self.nAlgorithms = 0
        self.currentSplice = 0
        self.header = [None] * 9
        self.splices = []
        self.algorithms = []
        self.filamentLength = 0
        self.currentStatus = ""
        self.drivesInUse = []
        self.amountLeftToExtrude = ""
        self.printPaused = False
        self.firstTime = False
        self.lastCommandSent = ""
        self.currentPingCmd = ""
        self.palette2SetupStarted = False
        self.allMCFFiles = []
        self.actualPrintStarted = False
        self.totalPings = 0
        self.pings = []
        self.pongs = []
        self.printHeartbeatCheck = ""
        self.cancelFromHub = False
        self.cancelFromP2 = False
        self.heartbeatSent = False
        self.heartbeatReceived = False

        self.filename = ""

        self.connected = False
        self.readThread = None
        self.writeThread = None
        self.readThreadError = None
        self.connectionThread = None
        self.heartbeatThread = None
        self.connectionStop = False
        self.heartbeat = False

        self.missedPings = 0
        self.advanced_reset_values()

        self.autoLoadThread = None
        self.isSplicing = False
        self.isConnectedMode = False

    def resetPrintValues(self):
        self.logger.info(getLog("Resetting all print values"))
        self.sentCounter = 0
        self.algoCounter = 0
        self.spliceCounter = 0

        self.msfNS = 0
        self.msfNA = "0"
        self.nAlgorithms = 0
        self.currentSplice = 0
        self.header = [None] * 9
        self.splices = []
        self.algorithms = []
        self.filamentLength = 0
        self.currentStatus = ""
        self.drivesInUse = []
        self.amountLeftToExtrude = ""
        self.printPaused = False
        self.firstTime = False
        self.lastCommandSent = ""
        self.currentPingCmd = ""
        self.palette2SetupStarted = False
        self.allMCFFiles = []
        self.actualPrintStarted = False
        self.totalPings = 0
        self.pings = []
        self.pongs = []
        self.printHeartbeatCheck = ""
        self.cancelFromHub = False
        self.cancelFromP2 = False
        self.heartbeatSent = False
        self.heartbeatReceived = False

        self.filename = ""

        self.missedPings = 0
        self.isSplicing = False
        self.isConnectedMode = True
        self.advanced_reset_print_values()

    def resetOmega(self):
        self.resetConnection()
        self.resetVariables()

    def shutdown(self):
        self.logger.info(getLog("Shutdown"))
        self.disconnect()
        self.stopLedThread()

    def disconnect(self):
        self.logger.info(getLog("Disconnecting from Palette 2"))
        self.resetOmega()
        self.updateUIAll()
        self.canvas_comm.send_message({'connection': 'palette 2 disconnected'})

    def initializePrintVariables(self):
        self.logger.info(getLog("PRINT STARTED P2"))
        self.resetPrintValues()
        self.tryHeartbeatBeforePrint()
        self.updateUIAll()
        self.printHeartbeatCheck = ""

    def gotOmegaCmd(self, cmd):
        if "O1" not in cmd:
            if "O21" in cmd:
                self.initializePrintVariables()
                self.logger.info(getLog("Starting Header Sequence"))
                self.header[0] = cmd
                self.logger.info(getLog("Header: Got Version: %s" % self.header[0]))
            elif "O22" in cmd:
                self.header[1] = cmd
                self.logger.info(getLog("Header: Got Printer Profile: %s" % self.header[1]))
            elif "O23" in cmd:
                self.header[2] = cmd
                self.logger.info(getLog("Header: Got Slicer Profile: %s" % self.header[2]))
            elif "O24" in cmd:
                self.header[3] = cmd
                self.logger.info(getLog("Header: Got PPM Adjustment: %s" % self.header[3]))
            elif "O25" in cmd:
                self.header[4] = cmd
                self.logger.info(getLog("Header: Got MU: %s" % self.header[4]))
                drives = self.header[4][4:].split(" ")
                for index, drive in enumerate(drives):
                    if not "D0" in drive:
                        if index == 0:
                            drives[index] = "U60"
                        elif index == 1:
                            drives[index] = "U61"
                        elif index == 2:
                            drives[index] = "U62"
                        elif index == 3:
                            drives[index] = "U63"
                self.drivesInUse = list(filter(lambda drive: drive != "D0", drives))
                self.logger.info(getLog("Drives in use: %s" % self.drivesInUse))
            elif "O26" in cmd:
                self.header[5] = cmd
                try:
                    self.msfNS = int(cmd[5:], 16)
                    self.logger.info(getLog("Header: Got NS: %s" % self.header[5]))
                    self.updateUI({"command": "totalSplices", "data": self.msfNS})
                except:
                    self.logger.info(getLog("NS information not properly formatted: %s" % cmd))
            elif "O27" in cmd:
                self.header[6] = cmd
                try:
                    self.totalPings = int(cmd[5:], 16)
                    self.logger.info(getLog("Header: Got NP: %s" % self.header[6]))
                    self.logger.info(getLog("TOTAL PINGS: %s" % self.totalPings))
                except:
                    self.logger.info(getLog("NP information not properly formatted: %s" % cmd))
            elif "O28" in cmd:
                self.header[7] = cmd
                try:
                    self.msfNA = cmd[5:]
                    self.nAlgorithms = int(self.msfNA, 16)
                    self.logger.info(getLog("Header: Got NA: %s" % self.header[7]))
                except:
                    self.logger.info(getLog("NA information not properly formatted: %s" % cmd))
            elif "O29" in cmd:
                self.header[8] = cmd
                self.logger.info(getLog("Header: Got NH: %s" % self.header[8]))
            elif "O30" in cmd:
                try:
                    splice = (int(cmd[5:6]), cmd[8:])
                    self.splices.append(splice)
                    self.logger.info(getLog("Got splice: drive: %s, dist: %s" % (splice[0],
                                                                               splice[1])))
                except:
                    self.logger.info(getLog("Splice information not properly formatted: %s" % cmd))
            elif "O32" in cmd:
                self.algorithms.append(cmd)
                self.logger.info(getLog("Got algorithm: %s" % cmd[4:]))
        elif "O1" in cmd:
            timeout = 4
            timeout_start = time.time()
            # Wait for Palette to respond with a handshake within 4 seconds
            while not self.heartbeat and time.time() < timeout_start + timeout:
                time.sleep(0.01)
            if self.heartbeat:
                self.logger.info(getLog("Palette did respond to %s" % constants.COMMANDS[
                    "HEARTBEAT"]))
                self.enqueueCmd(cmd)
                self.currentStatus = constants.STATUS["INITIALIZING"]
                self.palette2SetupStarted = True
                if self.heartbeatSent:
                    self.heartbeatReceived = True
                self.printHeartbeatCheck = "P2Responded"
                self.printPaused = True
                self.updateUI({"command": "currentStatus", "data": self.currentStatus})
                self.updateUI({"command": "palette2SetupStarted", "data": self.palette2SetupStarted})
                self.updateUI({"command": "printHeartbeatCheck", "data": self.printHeartbeatCheck})
                self.updateUI({"command": "printPaused", "data": self.printPaused})
                self.updateUI({"command": "advanced", "subCommand": "advancedStatus", "data": "Awaiting Update..."})
                self.printHeartbeatCheck = ""
                try:
                    filename = self._printer.get_current_job()["file"]["name"].replace(".mcf.gcode", "").strip()
                    self.setFilename(filename)
                except:
                    self.logger.info(getLog("Error getting filename"))
            else:
                self.logger.info(getLog("Palette did not respond to %s" % constants.COMMANDS[
                    "HEARTBEAT"]))
                self.printHeartbeatCheck = "P2NotConnected"
                self.updateUI({"command": "printHeartbeatCheck", "data": self.printHeartbeatCheck})
                self.disconnect()
                self.logger.info(getLog("NO P2 detected. Cancelling print"))
                self._printer.cancel_print()
        elif cmd == "O9":
            # reset values
            self.logger.info(getLog("Soft resetting P2: %s" % cmd))
            self.enqueueCmd(cmd)
        else:
            self.logger.info(getLog("Got another Omega command '%s'" % cmd))
            self.enqueueCmd(cmd)

    def changeAlertSettings(self, condition):
        self._settings.set(["palette2Alerts"], condition, force=True)
        self._settings.save(force=True)
        self.updateUI({"command": "displaySetupAlerts", "data": self._settings.get(["palette2Alerts"])})

    def changeAutoStartAfterLoad(self, condition):
        self._settings.set(["autoStartAfterLoad"], condition, force=True)
        self._settings.save(force=True)
        self.updateUI({"command": "autoStartAfterLoad", "data": self._settings.get(["autoStartAfterLoad"])})

    def sendAllMCFFilenamesToOmega(self):
        self.getAllMCFFilenames()
        for file in self.allMCFFiles:
            filename = file.replace(".mcf.gcode", "")
            self.enqueueCmd("%s D%s" % (constants.COMMANDS["FILENAME"], filename))
        self.enqueueCmd(constants.COMMANDS["FILENAMES_DONE"])

    def getAllMCFFilenames(self):
        self.allMCFFiles = []
        uploads_path = self._settings.global_get_basefolder("uploads")
        self.iterateThroughFolder(uploads_path, "")

    def iterateThroughFolder(self, folder_path, folder_name):
        for file in os.listdir(folder_path):
            file_path = os.path.join(folder_path, file)
            # If file is an .mcf.gcode file
            if os.path.isfile(file_path) and ".mcf.gcode" in file:
                if folder_name != "":
                    cumulative_folder_name = folder_name + "/" + file
                else:
                    cumulative_folder_name = file
                self.allMCFFiles.append(cumulative_folder_name)

    def startPrintFromP2(self, file):
        self.logger.info(getLog("Received start print command from P2"))
        self._printer.select_file(file, False, printAfterSelect=True)

    def sendErrorReport(self, error_number, description):
        self.logger.info(getLog("SENDING ERROR REPORT TO MOSAIC"))
        log_content = self.prepareErrorReport(error_number, description)

        hub_id, hub_token = self.getHubData()
        url = "https://" + BASE_URL_API + "hubs/" + hub_id + "/log"
        payload = {
            "log": log_content
        }
        authorization = "Bearer " + hub_token
        headers = {"Authorization": authorization}
        try:
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code >= 300:
                self.logger.info(getLog(response))
            else:
                self.logger.info(getLog("Email sent successfully"))
        except requests.exceptions.RequestException as e:
            self.logger.info(getLog(e))

    def prepareErrorReport(self, error_number, description):
        # error number
        output = "===== ERROR %s =====\n\n" % error_number

        # plugins + versions
        output += "=== PLUGINS ===\n"
        plugins = list(self._plugin_manager.plugins)
        for plugin in plugins:
            output += "%s: %s\n" % (plugin, self._plugin_manager.get_plugin_info(plugin).version)

        # Hub or DIY
        output += "\n=== TYPE ===\n"
        if self.checkIfMosaicHub():
            output += "CANVAS HUB\n"
        else:
            output += "DIY HUB\n"

        # description
        if description:
            output += "\n=== USER ADDITIONAL DESCRIPTION ===\n"
            output += description + "\n"

        output += "\n=== OCTOPRINT LOG ===\n"

        # OctoPrint log
        octoprint_log_path = os.path.expanduser('~') + "/.octoprint/logs/octoprint.log"
        octoprint_log = ""
        try:
            octoprint_log = check_output(["tail", "-n", "1000", octoprint_log_path]).decode()
        except Exception as e:
            self.logger.info(getLog(e))

        finalized_report = output + octoprint_log
        return finalized_report


    def startPrintFromHub(self):
        self.enqueueCmd(constants.COMMANDS["START_PRINT_HUB"])

    def getHubData(self):
        hub_file_path = os.path.expanduser('~') + "/.mosaicdata/canvas-hub-data.yml"

        with open(hub_file_path, "r") as hub_data:
            hub_yaml = yaml.safe_load(hub_data)

        hub_id = hub_yaml["canvas-hub"]["id"]
        hub_token = hub_yaml["canvas-hub"]["token"]

        return hub_id, hub_token

    def parseLine(self, line):
        # is the first character O?
        if line[0] == "O":
            tokens = [token.strip() for token in line.split(" ")]
            command_number = tokens[0]
            command_params = tokens[1:]

            # verify command number validity
            try:
                command_number = int(command_number[1:])
            except:
                # command should be a number, otherwise invalid command
                self.logger.info(getLog("%s is not a valid number: %s" % (command_number, line)))
                return None
            # verify tokens' validity
            if len(command_params) > 0:
                for param in command_params:
                    # params should start with D or U, otherwise invalid param
                    if param[0] != "D" and param[0] != "U":
                        self.logger.info(getLog("%s is not a valid parameter: %s" % (param, line)))
                        return None
            return {
                "number": command_number,
                "params": command_params
            }
        # otherwise, is this line the heartbeat response?
        elif line == "Connection Okay":
            self.heartbeat = True
            self.heartbeatReceived = True
            self.heartbeatSent = False
            return None
        else:
            # Invalid first character (IFC). Don't need to do anything, but log out for potential troubleshooting.
            self.logger.info(getLog("IFC: %s" % line))
            return None

    def feedRateControlStart(self):
        self.logger.info(getLog('SPLICE START'))
        self.isSplicing = True
        if self.feedRateControl:
            if (self.isConnectedMode and self.actualPrintStarted) or not self.isConnectedMode:
                advanced_status = 'Splice starting: speed -> SLOW (%s%%)' % self.feedRateSlowPct
                if self.isConnectedMode and self.actualPrintStarted:
                    advanced_status = 'Splice (%s) starting: speed -> SLOW (%s%%)' % (self.currentSplice, self.feedRateSlowPct)
                self.updateUI({"command": "advanced", "subCommand": "advancedStatus", "data": advanced_status})
                if self.feedRateSlowed:
                    # Feedrate already slowed, set it again to be safe.
                    try:
                        self.logger.info(getLog("ADVANCED: Feed-rate SLOW - ACTIVE* (%s)" % \
                                          self.feedRateSlowPct))
                        self._printer.commands('M220 S%s' % self.feedRateSlowPct)
                    except ValueError:
                        self.logger.info(getLog('ADVANCED: Unable to Update Feed-Rate -> SLOW :: '\
                                               + \
                                          str(ValueError)))
                else:
                    self.logger.info(getLog('ADVANCED: Feed-rate SLOW - ACTIVE (%s)' % \
                                      self.feedRateSlowPct))
                    try:
                        self._printer.commands('M220 S%s B' % self.feedRateSlowPct)
                        self.feedRateSlowed = True
                    except ValueError:
                        self.logger.info(getLog('ADVANCED: Unable to Update Feed-Rate -> SLOW :: '\
                                               + \
                                          str(ValueError)))
                self.updateUI({"command": "advanced", "subCommand": "feedRateSlowed", "data": self.feedRateSlowed}, True)


    def feedRateControlEnd(self):
        self.logger.info(getLog('SPLICE END'))
        self.isSplicing = False
        if self.feedRateControl:
            if (self.isConnectedMode and self.actualPrintStarted) or not self.isConnectedMode:
                advanced_status = 'Splice finished: speed -> NORMAL (%s%%)' % self.feedRateNormalPct
                if self.isConnectedMode and self.actualPrintStarted:
                    advanced_status = 'Splice (%s) finished: speed -> NORMAL (%s%%)' % (self.currentSplice, self.feedRateNormalPct)
                self.updateUI({"command": "advanced", "subCommand": "advancedStatus", "data": advanced_status})
                try:
                    self._printer.commands('M220 S%s' % self.feedRateNormalPct)
                    self.feedRateSlowed = False
                except ValueError:
                    self.logger.info(getLog('ADVANCED: Unable to Update Feed-Rate -> NORMAL :: ' + \
                                          str(
                        ValueError)))
                self.updateUI({"command": "advanced", "subCommand": "feedRateSlowed", "data": self.feedRateSlowed}, True)


    def sendPingToPrinter(self, ping_number, ping_percent):
        # filter out ping offset information
        if self.showPingOnPrinter:
            self.logger.info(getLog("ADVANCED: sending ping '%s' to printer" % ping_number))
            try:
                if ping_percent == "MISSED":
                    self._printer.commands("M117 Ping %s %s" % (ping_number, ping_percent))
                else:
                    self._printer.commands("M117 Ping %s %s%%" % (ping_number, ping_percent))
            except ValueError:
                self.logger.info(getLog("Printer cannot handle M117 commands."))

    def advanced_reset_values(self):
        self.feedRateControl = self._settings.get(["feedRateControl"])
        self.feedRateNormalPct = self._settings.get(["feedRateNormalPct"])
        self.feedRateSlowPct = self._settings.get(["feedRateSlowPct"])
        self.autoVariationCancelPing = self._settings.get(["autoVariationCancelPing"])
        self.showPingOnPrinter = self._settings.get(["showPingOnPrinter"])
        self.variationPct = self._settings.get(["variationPct"])
        self.variationPingStart = self._settings.get(["variationPingStart"])
        self.advanced_reset_print_values()

    def advanced_reset_print_values(self):
        self.autoLoadThread = None
        self.feedRateSlowed = False
        self.isAutoLoading = False

    def advancedUpdateUI(self):
        self.logger.info(getLog("ADVANCED UPDATE UI"))
        try:
            self.updateUI({"command": "advanced", "subCommand": "autoVariationCancelPing", "data": self._settings.get(["autoVariationCancelPing"])}, True)
            self.updateUI({"command": "advanced", "subCommand": "showPingOnPrinter", "data": self._settings.get(["showPingOnPrinter"])}, True)
            self.updateUI({"command": "advanced", "subCommand": "feedRateControl", "data": self._settings.get(["feedRateControl"])}, True)
            self.updateUI({"command": "advanced", "subCommand": "feedRateSlowed", "data": self.feedRateSlowed}, True)
            self.updateUI({"command": "advanced", "subCommand": "feedRateNormalPct", "data": self._settings.get(["feedRateNormalPct"])}, True)
            self.updateUI({"command": "advanced", "subCommand": "feedRateSlowPct", "data": self._settings.get(["feedRateSlowPct"])}, True)
            self.updateUI({"command": "advanced", "subCommand": "variationPct", "data": self._settings.get(["variationPct"])}, True)
            self.updateUI({"command": "advanced", "subCommand": "isAutoLoading", "data": self.isAutoLoading}, True)
        except Exception as e:
            self.logger.info(getLog(e))

    def changeAutoVariationCancelPing(self, condition):
        try:
            self._settings.set(["autoVariationCancelPing"], condition, force=True)
            self._settings.save(force=True)
            self.logger.info(getLog("ADVANCED: autoVariationCancelPing -> '%s' '%s'" % (condition,
                                                                                  self._settings.get(["autoVariationCancelPing"]))))
            self.autoVariationCancelPing = self._settings.get(["autoVariationCancelPing"])
        except Exception as e:
            self.logger.info(getLog(e))

    def changeShowPingOnPrinter(self, condition):
        try:
            self._settings.set(["showPingOnPrinter"], condition, force=True)
            self._settings.save(force=True)
            self.logger.info(getLog("ADVANCED: showPingOnPrinter -> '%s' '%s'" % (condition,
                                                                            self._settings.get([
                                                                                "showPingOnPrinter"]))))
            self.showPingOnPrinter = self._settings.get(["showPingOnPrinter"])
        except Exception as e:
            self.logger.info(getLog(e))

    def changeFeedRateControl(self, condition):
        try:
            self._settings.set(["feedRateControl"], condition, force=True)
            self._settings.save(force=True)
            self.logger.info(getLog("ADVANCED: feedRateControl -> '%s' '%s'" % (condition,
                                                                          self._settings.get([
                                                                              "feedRateControl"]))))
            self.feedRateControl = self._settings.get(["feedRateControl"])
        except Exception as e:
            self.logger.info(getLog(e))

    def changeFeedRateNormalPct(self, value):
        if self.isPositiveInteger(value):
            clean_value = int(value)
            advanced_status = ""
            if clean_value == self.feedRateNormalPct:
                self.logger.info(getLog("Normal Feed Rate Speed did not change. Do nothing"))
            elif clean_value > 200:
                self.logger.info(getLog("Cannot set normal feed rate above 200%."))
                advanced_status = 'Cannot set normal feed rate above 200%%. Keeping speed at (%s%%).' % self.feedRateNormalPct
                self.updateUI({"command": "advanced", "subCommand": "feedRateNormalPct", "data": self._settings.get(["feedRateNormalPct"])})
            else:
                try:
                    self._settings.set(["feedRateNormalPct"], clean_value)
                    self._settings.save(force=True)
                    self.logger.info(getLog("ADVANCED: feedRateNormalPct -> '%s' '%s'" % (
                        clean_value,
                                                                                    self._settings.get(["feedRateNormalPct"]))))
                    self.feedRateNormalPct = self._settings.get(["feedRateNormalPct"])
                    if self.isConnectedMode and not self.actualPrintStarted:
                        advanced_status = 'Normal feed rate set to %s%%. Awaiting start of print to apply...' % self.feedRateNormalPct
                    else:
                        if not self.feedRateSlowed:
                            self._printer.commands('M220 S%s' % self.feedRateNormalPct)
                            advanced_status = 'Not currently splicing: speed -> NORMAL (%s%%)' % self.feedRateNormalPct
                        else:
                            advanced_status = 'Normal feed rate set to %s%%. Awaiting end of current splice to apply...' % self.feedRateNormalPct
                except Exception as e:
                    self.logger.info(getLog(e))
            if advanced_status != "":
                self.updateUI({"command": "advanced", "subCommand": "advancedStatus", "data": advanced_status})
        else:
            self.logger.info(getLog("Not positive integer"))
            self.updateUI({"command": "advanced", "subCommand": "feedRateNormalPct", "data": self._settings.get(["feedRateNormalPct"])})


    def changeFeedRateSlowPct(self, value):
        if self.isPositiveInteger(value):
            clean_value = int(value)
            advanced_status = ""
            if clean_value == self.feedRateSlowPct:
                self.logger.info(getLog("Splice Feed Rate Speed did not change. Do nothing"))
            elif clean_value > 100:
                self.logger.info(getLog("Cannot set splicing feed rate above 100%."))
                advanced_status = 'Cannot set splicing feed rate above 100%%. Keeping speed at (%s%%).' % self.feedRateSlowPct
                self.updateUI({"command": "advanced", "subCommand": "feedRateSlowPct", "data": self._settings.get(["feedRateSlowPct"])})
            else:
                try:
                    self._settings.set(["feedRateSlowPct"], clean_value)
                    self._settings.save(force=True)
                    self.logger.info(getLog("ADVANCED: feedRateSlowPct -> '%s' '%s'" % (
                        clean_value,
                                                                                  self._settings.get(["feedRateSlowPct"]))))
                    self.feedRateSlowPct = self._settings.get(["feedRateSlowPct"])
                    if self.isConnectedMode and not self.actualPrintStarted:
                        advanced_status = 'Splicing feed rate set to %s%%. Awaiting start of print to apply...' % (self.feedRateSlowPct)
                    else:
                        if self.feedRateSlowed:
                            self._printer.commands('M220 S%s' % self.feedRateSlowPct)
                            if self.isConnectedMode:
                                advanced_status = 'Currently splicing (%s): speed -> SLOW (%s%%)' % (self.currentSplice, self.feedRateSlowPct)
                            else:
                                advanced_status = 'Currently splicing: speed -> SLOW (%s%%)' % self.feedRateSlowPct
                        else:
                            advanced_status = 'Splicing feed rate set to %s%%. Awaiting next splice to apply...' % (self.feedRateSlowPct)
                except Exception as e:
                    self.logger.info(getLog(e))
            if advanced_status != "":
                self.updateUI({"command": "advanced", "subCommand": "advancedStatus", "data": advanced_status})
        else:
            self.logger.info(getLog("Not positive integer"))
            self.updateUI({"command": "advanced", "subCommand": "feedRateSlowPct", "data": self._settings.get(["feedRateSlowPct"])})

    def changeVariationPct(self, value):
        if self.isPositiveInteger(value):
            clean_value = int(value)
            if clean_value == self.variationPct:
                self.logger.info(getLog("Variation percent did not change. Do nothing"))
            elif clean_value > 100:
                self.logger.info(getLog("Cannot set variation percent above 100%."))
                self.updateUI({"command": "advanced", "subCommand": "variationPct", "data": self._settings.get(["variationPct"])})
            else:
                try:
                    self._settings.set(["variationPct"], clean_value)
                    self._settings.save(force=True)
                    self.logger.info(getLog("ADVANCED: variationPct -> '%s' '%s'" % (clean_value,
                                                                               self._settings.get(["variationPct"]))))
                    self.variationPct = self._settings.get(["variationPct"])
                except Exception as e:
                    self.logger.info(getLog(e))
        else:
            self.logger.info(getLog("Not positive integer"))
            self.updateUI({"command": "advanced", "subCommand": "variationPct", "data": self._settings.get(["variationPct"])})

    def changeVariationPingStart(self, value):
        if self.isPositiveInteger(value):
            clean_value = int(value)
            if clean_value == self.variationPingStart:
                self.logger.info(getLog("Variation start ping did not change. Do nothing"))
            else:
                try:
                    self._settings.set(["variationPingStart"], clean_value)
                    self._settings.save(force=True)
                    self.logger.info(getLog("ADVANCED: variationPingStart -> '%s' '%s'" % (
                        clean_value,
                                                                                     self._settings.get(["variationPingStart"]))))
                    self.variationPingStart = self._settings.get(["variationPingStart"])
                except Exception as e:
                    self.logger.info(getLog(e))
        else:
            self.logger.info(getLog("Not positive integer"))
            self.updateUI({"command": "advanced", "subCommand": "variationPingStart", "data": self._settings.get(["variationPingStart"])})

    def advancedUpdateVariables(self):
        self.autoVariationCancelPing = self._settings.get(["autoVariationCancelPing"])
        self.showPingOnPrinter = self._settings.get(["showPingOnPrinter"])
        self.feedRateControl = self._settings.get(["feedRateControl"])
        self.feedRateNormalPct = self._settings.get(["feedRateNormalPct"])
        self.feedRateSlowPct = self._settings.get(["feedRateSlowPct"])
        self.variationPct = self._settings.get(["variationPct"])
        self.variationPingStart = self._settings.get(["variationPingStart"])
        self.advancedUpdateUI()

    def isPositiveInteger(self, value):
        try:
            return int(value) > 0
        except Exception as e:
            self.logger.info(getLog(e))
            return False

    def startAutoLoadThread(self):
        if self.autoLoadThread is not None:
            self.stopAutoLoadThread()

        self.logger.info(getLog("Starting AutoLoad Thread"))
        self.isAutoLoading = True
        self.updateUI({"command": "advanced", "subCommand": "isAutoLoading", "data": self.isAutoLoading})
        self.autoLoadThreadStop = False
        self.autoLoadThread = threading.Thread(target=self.omegaAutoLoadThread)
        self.autoLoadThread.daemon = True
        self.autoLoadThread.start()

    def stopAutoLoadThread(self):
        self.autoLoadThreadStop = True
        if self.autoLoadThread and threading.current_thread() != self.autoLoadThread:
            self.autoLoadThread.join()
        self.autoLoadThread = None

    def omegaAutoLoadThread(self):
        self._printer.extrude(0)
        self.autoLoadFilament(self.amountLeftToExtrude)

    def autoLoadFilament(self, amount_to_extrude):
        if not self.autoLoadThreadStop:
            self.logger.info(getLog("Amount to extrude: %s" % amount_to_extrude))

            if amount_to_extrude <= 0:
                self.isAutoLoading = False
                self.updateUI({"command": "advanced", "subCommand": "isAutoLoading", "data": self.isAutoLoading})
                return 0

            old_value = amount_to_extrude
            change_detected = False

            # if not splicing, send extrusion command to printer
            if not self.isSplicing:
                if amount_to_extrude > 70:
                    # do increments of 50mm for large loading offsets to minimize filament grinding, in case a splice occurs
                    self.logger.info(getLog("Amount above 70, sending 50 to printer."))
                    self._printer.extrude(50)
                elif amount_to_extrude > 5:
                    # half the amount to minimize risk of over-extrusion
                    self.logger.info(getLog("Amount above 5, sending half (%s) to printer." % (
                            amount_to_extrude / 2)))
                    self._printer.extrude(amount_to_extrude / 2)
                elif amount_to_extrude > 0:
                    self.logger.info(getLog("Amount 5 or below, sending %s to printer." % \
                                      amount_to_extrude))
                    self._printer.extrude(amount_to_extrude)

            timeout = 6
            timeout_start = time.time()
            # check for change in remaining offset value after extrusion command was sent to know if smart load is working
            while time.time() < timeout_start + timeout:
                if self.amountLeftToExtrude != old_value:
                    old_value = self.amountLeftToExtrude
                    change_detected = True
                    # reset timeout
                    timeout = 3
                    timeout_start = time.time()
                time.sleep(0.01)

            if change_detected:
                # wait for current splice to finish before recursively continuing smart loading
                if self.isSplicing:
                    self.logger.info(getLog("Palette 2 is currently splicing. Waiting for end of " \
                                       "splice before continuing..."))
                    while self.isSplicing:
                        time.sleep(1)
                    self.logger.info(getLog("Resuming smart load."))
                self.autoLoadFilament(self.amountLeftToExtrude)
            else:
                self.logger.info(getLog("Loading offset at %smm did not change within %s seconds. " \
                                  "Filament did not move. Must place filament again" % (
                    self.amountLeftToExtrude, timeout)))
                self.isAutoLoading = False
                self.updateUI({"command": "advanced", "subCommand": "isAutoLoading", "data": self.isAutoLoading})
                self.updateUI({"command": "alert", "data": "autoLoadIncomplete"})
                self.enqueueCmd(constants.COMMANDS["SMART_LOAD_STOP"])
                return None
        else:
            return None

    def downloadPingHistory(self):
        self.logger.info(getLog("DOWNLOADING PING HISTORY"))
        return self.getPingHistory(self.pings, self.filename)

    def getPingHistory(self, pings, filename):
        data = ""
        data = data + "%s\n\nPING            (%%)\n===================\n" % filename

        # write out each ping
        for ping in pings:
            ping_number = "Ping %s" % ping["number"]
            ping_percent = "%s%%" % ping["percent"]
            if ping["percent"] == "MISSED":
                ping_percent = ping["percent"]
            space_length = (len("===================") - len(ping_number) - len(ping_percent)) * " "
            data = data + "%s%s%s\n" % (ping_number, space_length, ping_percent)

        download_filename = filename + ".txt"
        return {"filename": download_filename, "data": data}

    def pingHistory(self):
        return self.pings

    def handleResumeRequest(self):
        if self.actualPrintStarted:
            self._printer.resume_print()
            self.printPaused = False
            self.updateUI({"command": "printPaused", "data": self.printPaused})
        else:
            if self.currentStatus == constants.STATUS["LOADING_EXTRUDER"]:
                self._printer.resume_print()
                self.printPaused = False
                self.currentStatus = constants.STATUS["PRINT_STARTED"]
                self.actualPrintStarted = True
                self.updateUI({"command": "currentStatus", "data": self.currentStatus})
                self.updateUI({"command": "actualPrintStarted", "data": self.actualPrintStarted})
                self.updateUI({"command": "printPaused", "data": self.printPaused})
                self.logger.info(getLog("Splices being prepared."))
                if not self._settings.get(["autoStartAfterLoad"]):
                    self.updateUI({"command": "alert", "data": "printStarted"})
                if not self.isSplicing:
                    self._printer.commands('M220 S%s' % self.feedRateNormalPct)
                    advanced_status = 'Not currently splicing: speed -> NORMAL (%s%%)' % self.feedRateNormalPct
                    self.updateUI({"command": "advanced", "subCommand": "advancedStatus", "data": advanced_status})

    def handlePing(self, command):
        try:
            percent = float(command["params"][1][1:])
            number = int(command["params"][2][1:], 16) + self.missedPings
            current = {"number": number, "percent": percent}
            self.pings.append(current)
            self.updateUI({"command": "pings", "data": self.pings})
            self.sendPingToPrinter(number, percent)
            self.handlePingVariation()
        except:
            self.logger.info(getLog("Ping number invalid: %s" % command))

    def handlePong(self, command):
        try:
            percent = float(command["params"][1][1:])
            number = int(command["params"][2][1:], 16)
            current = {"number": number, "percent": percent}
            self.pongs.append(current)
            self.updateUI({"command": "pongs", "data": self.pongs})
        except:
            self.logger.info(getLog("Pong number invalid: %s" % command))

    def handleRejectedPing(self):
        # as of P2 FW version 9.0.9, pings are no longer "rejected"
        # this method will be kept for backwards compatibility purposes
        self.logger.info(getLog("REJECTING PING"))
        self.missedPings = self.missedPings + 1
        current = {"number": len(self.pings) + 1, "percent": "MISSED"}
        self.pings.append(current)
        self.updateUI({"command": "pings", "data": self.pings})
        self.sendPingToPrinter(current["number"], current["percent"])

    def handleFirstTimePrint(self):
        self.logger.info(getLog("FIRST TIME USE WITH PALETTE"))
        self.firstTime = True
        self.updateUI({"command": "firstTime", "data": self.firstTime})

    def handleP2RequestForMoreInfo(self, command):
        try:
            param_1 = int(command["params"][0][1:])
            # send next line of data
            self.sendNextData(param_1)
        except:
            self.logger.info(getLog("Error occured with: %s" % command))

    def handleStartPrintFromP2(self, command):
        try:
            index_to_print = int(command["params"][1][1:], 16)
            self.allMCFFiles.reverse()
            file = self.allMCFFiles[index_to_print]
            self.startPrintFromP2(file)
        except:
            self.logger.info(getLog("Print from P2 command invalid: %s" % command))

    def handleErrorDetected(self, command):
        try:
            error = int(command["params"][0][1:], 16)
            self.logger.info(getLog("ERROR %d DETECTED" % error))
            if os.path.isdir(os.path.expanduser('~') + "/.mosaicdata/"):
                self._printer.cancel_print()
                self.updateUI({"command": "error", "data": error})
        except:
            self.logger.info(getLog("Error command invalid: %s" % command))

    def handleSpliceCompletion(self):
        self.currentStatus = constants.STATUS["SPLICES_DONE"]
        self.updateUI({"command": "currentStatus", "data": self.currentStatus})
        self.logger.info(getLog("Palette work is done."))

    def handlePrintCancelling(self):
        self.logger.info(getLog("P2 CANCELLING START"))
        if not self.cancelFromHub and not self.cancelFromP2:
            self.cancelFromP2 = True
            self._printer.cancel_print()
        self.currentStatus = constants.STATUS["CANCELLING"]
        self.updateUI({"command": "currentStatus", "data": self.currentStatus})
        self.updateUI({"command": "alert", "data": "cancelling"})

    def handlePrintCancelled(self):
        self.logger.info(getLog("P2 CANCELLING END"))
        self.currentStatus = constants.STATUS["CANCELLED"]
        self.updateUI({"command": "currentStatus", "data": self.currentStatus})
        self.updateUI({"command": "alert", "data": "cancelled"})
        self.cancelFromHub = False
        self.cancelFromP2 = False
        self.isConnectedMode = False

    def handleSpliceStart(self, command):
        try:
            self.currentSplice = int(command["params"][2][1:], 16)
            self.logger.info(getLog("Current splice: %s" % self.currentSplice))
            self.updateUI({"command": "currentSplice", "data": self.currentSplice})
        except:
            self.logger.info(getLog("Splice command invalid: %s" % command))

    def handleFilamentUsed(self, command):
        try:
            self.filamentLength = int(command["params"][1][1:], 16)
            self.logger.info(getLog("%smm used" % self.filamentLength))
            self.updateUI({"command": "filamentLength", "data": self.filamentLength})
        except:
            self.logger.info(getLog("Filament length update invalid: %s" % command))

    def handleLoadingOffsetStart(self):
        self.currentStatus = constants.STATUS["LOADING_EXTRUDER"]
        self.updateUI({"command": "alert", "data": "extruder"})
        self.updateUI({"command": "currentStatus", "data": self.currentStatus})
        self.logger.info(getLog("Filament must be loaded into extruder by user"))

    def handleLoadingOffsetExtrude(self, command):
        try:
            self.amountLeftToExtrude = int(command["params"][1][2:])
            self.logger.info(getLog("%s mm left to extrude." % self.amountLeftToExtrude))
            self.updateUI({"command": "amountLeftToExtrude", "data": self.amountLeftToExtrude})
        except:
            self.logger.info(getLog("Filament extrusion update invalid: %s" % command))

    def handleLoadingOffsetCompletion(self, command):
        # also handles cases of LO over-extrusion
        try:
            self.amountLeftToExtrude = int(command["params"][1][1:]) * -1
            self.logger.info(getLog("%s mm left to extrude." % self.amountLeftToExtrude))
            self.updateUI({"command": "amountLeftToExtrude", "data": self.amountLeftToExtrude})
        except:
            self.logger.info(getLog("Filament extrusion update invalid: %s" % command))
        if self.amountLeftToExtrude == 0:
            if not self.cancelFromHub and not self.cancelFromP2:
                if self.isAutoLoading:
                    while self.isAutoLoading:
                        time.sleep(0.01)
                    self.handleStartPrintAfterLoad()
                else:
                    self.handleStartPrintAfterLoad()

    def handleStartPrintAfterLoad(self):
        if self._settings.get(["autoStartAfterLoad"]):
            self.startPrintFromHub()
        self.updateUI({"command": "alert", "data": "startPrint"})

    def handleDrivesLoading(self):
        self.currentStatus = constants.STATUS["LOADING_DRIVES"]
        self.updateUI({"command": "currentStatus", "data": self.currentStatus})
        self.logger.info(getLog("STARTING TO LOAD FIRST DRIVE"))

    def handleFilamentOutgoingTube(self):
        self.currentStatus = constants.STATUS["LOADING_TUBE"]
        self.updateUI({"command": "currentStatus", "data": self.currentStatus})
        self.updateUI({"command": "alert", "data": "temperature"})
        self.logger.info(getLog("FINISHED LOADING LAST DRIVE"))

    def handlePauseRequest(self):
        self._printer.pause_print()
        self.printPaused = True
        self.updateUI({"command": "printPaused", "data": self.printPaused})

    def handleSmartLoadRequest(self):
        if not self.isAutoLoading:
            self.startAutoLoadThread()

    def handlePingVariation(self):
        if self.autoVariationCancelPing and len(self.pings) > self.variationPingStart:
            try:
                currentPing = self.pings[-1]["percent"]
                previousPing = self.pings[-2]["percent"]
                variation = abs(currentPing - previousPing)
                if variation > self.variationPct:
                    self.logger.info(getLog("Variation (%s%% - current: %s%% vs before: %s%%) is " \
                                      "significantly greater than %s%%. Cancelling print" % (
                        variation, currentPing, previousPing, self.variationPct)))
                    self.cancel()
            except Exception as e:
                self.logger.info(getLog(e))
