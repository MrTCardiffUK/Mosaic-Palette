# coding=utf-8
from __future__ import absolute_import, division, print_function, unicode_literals

import octoprint.plugin
import octoprint.filemanager
import flask
import requests
import os.path
from distutils.version import LooseVersion
from . import constants
from . import Omega
from subprocess import call
import logging

def getLog(msg, module='init palette-2'):
    return '{ "msg": "' + msg + '", "module": "' + module +'" }'

class P2PluginVersionChecker:
    def __init__(self):
        pass

    def get_latest(self, target, check, full_data=False, online=True):
        resp = requests.get(constants.GET_RELEASES_URL)
        version_data = resp.json()
        latest_version_info = version_data[0]
        version = latest_version_info['name']
        current_version = check.get("current")
        information = dict(
            local=dict(
                name=current_version,
                value=current_version,
            ),
            remote=dict(
                name=version,
                value=version
            )
        )
        needs_update = LooseVersion(current_version) < LooseVersion(version)
        return information, not needs_update


class P2Plugin(octoprint.plugin.StartupPlugin,
               octoprint.plugin.TemplatePlugin,
               octoprint.plugin.SettingsPlugin,
               octoprint.plugin.AssetPlugin,
               octoprint.plugin.SimpleApiPlugin,
               octoprint.plugin.EventHandlerPlugin,
               octoprint.plugin.ShutdownPlugin):

    def get_sorting_key(self, context):
        if context == "StartupPlugin.on_after_startup":
            return 1
        return None

    def on_after_startup(self):
        mosaic_log = os.path.join(self._settings.getBaseFolder('logs'), 'mosaic.log')
        self.logger = self._setup_logger("palette-2", mosaic_log)
        self.logger.info(getLog('---------- Starting Palette 2 Plugin ----------'))
        self.logger.info(getLog("%s Plugin STARTED" % self._plugin_info))
        if os.path.isdir("/home/pi/OctoPrint/venv/lib/python2.7/site-packages/Canvas-0.1.0-py2.7.egg-info/") and os.path.isdir("/home/pi/.mosaicdata/turquoise/"):
            call(["sudo rm -rf /home/pi/OctoPrint/venv/lib/python2.7/site-packages/Canvas-0.1.0-py2.7.egg-info/"], shell=True)
            call(["sudo chown -R pi:pi /home/pi/OctoPrint/venv/lib/python2.7/site-packages/"], shell=True)
        self.palette = Omega.Omega(self)
        self.palette.isHubS = self.palette.determineHubVersion()
        self.palette.startLedThread()
        self.palette.ports = self.palette.getAllPorts()
        self.palette.updateHubSLedScript()

    def get_settings_defaults(self):
        return dict(autoconnect=False,
                    palette2Alerts=True,
                    baudrate=115200,
                    selectedPort=None,
                    advancedOptions=False,
                    feedRateControl=False,
                    feedRateNormalPct=100,
                    feedRateSlowPct=75,
                    autoVariationCancelPing=False,
                    variationPct=8,
                    variationPingStart=1,
                    showPingOnPrinter=False,
                    autoStartAfterLoad=False,
                    )

    def get_template_configs(self):
        return [
            dict(type="navbar", custom_bindings=False),
            dict(type="settings", custom_bindings=False)
        ]

    def get_assets(self):
        return dict(
            js=["js/palette2.js", "js/utils/alerts.js", "js/utils/ui.js"],
            css=["css/palette2.css"],
            less=["less/palette2.less"]
        )

    def get_api_commands(self):
        return dict(
            clearPalette2=[],
            connectOmega=["port"],
            disconnectPalette2=[],
            sendCutCmd=[],
            uiUpdate=[],
            changeAlertSettings=["condition"],
            displayPorts=["condition"],
            sendErrorReport=["errorNumber", "description"],
            startPrint=[],
            changeAutoVariationCancelPing=["condition"],
            changeVariationPct=["value"],
            changeVariationPingStart=["value"],
            changeShowPingOnPrinter=["condition"],
            changeFeedRateControl=["condition"],
            changeFeedRateNormalPct=["value"],
            changeFeedRateSlowPct=["value"],
            startAutoLoad=[],
            downloadPingHistory=[],
            getPingHistory=[],
            getJobData=[],
            changeAutoStartAfterLoad=["condition"]
        )

    def on_api_command(self, command, payload):
        self.logger.info(getLog("Got a command: '%s'" % command))
        try:
            data = None
            if command == "connectOmega":
                self.palette.connectOmega(payload["port"])
            elif command == "disconnectPalette2":
                self.palette.disconnect()
            elif command == "sendCutCmd":
                self.palette.cut()
            elif command == "clearPalette2":
                self.palette.clear()
            elif command == "uiUpdate":
                self.palette.updateUIAll()
            elif command == "changeAlertSettings":
                self.palette.changeAlertSettings(payload["condition"])
            elif command == "displayPorts":
                self.palette.displayPorts(payload["condition"])
            elif command == "sendErrorReport":
                self.palette.sendErrorReport(payload["errorNumber"], payload["description"])
            elif command == "startPrint":
                self.palette.startPrintFromHub()
            elif command == "startAutoLoad":
                self.palette.startAutoLoadThread()
                self.palette.enqueueCmd(constants.COMMANDS["SMART_LOAD_START"])
            elif command == "changeAutoVariationCancelPing":
                self.palette.changeAutoVariationCancelPing(payload["condition"])
            elif command == "changeVariationPct":
                self.palette.changeVariationPct(payload["value"])
            elif command == "changeVariationPingStart":
                self.palette.changeVariationPingStart(payload["value"])
            elif command == "changeShowPingOnPrinter":
                self.palette.changeShowPingOnPrinter(payload["condition"])
            elif command == "changeFeedRateControl":
                self.palette.changeFeedRateControl(payload["condition"])
            elif command == "changeFeedRateNormalPct":
                self.palette.changeFeedRateNormalPct(payload["value"])
            elif command == "changeFeedRateSlowPct":
                self.palette.changeFeedRateSlowPct(payload["value"])
            elif command == "downloadPingHistory":
                data = self.palette.downloadPingHistory()
            elif command == "getPingHistory":
                data = self.palette.pingHistory()
            elif command == "getJobData":
                data = self.palette.getJobData()
            elif command == "changeAutoStartAfterLoad":
                data = self.palette.changeAutoStartAfterLoad(payload["condition"])
            response = "POST request (%s) successful" % command
            return flask.jsonify(response=response, data=data, status=constants.HTTP["SUCCESS"]), constants.HTTP["SUCCESS"]
        except Exception as e:
            error = str(e)
            self.logger.error(getLog("Exception message: %s" % str(e)))
            return flask.jsonify(error=error, status=constants.HTTP["FAILURE"]), constants.HTTP["FAILURE"]

    def on_event(self, event, payload):
        try:
            if "ClientOpened" in event:
                self.palette.updateUIAll()
                self.palette.checkMosaicPluginsCompatibility()
            elif "PrintPaused" in event:
                if ".mcf.gcode" in payload["name"]:
                    self.palette.printPaused = True
                    self.palette.updateUI({"command": "printPaused", "data": self.palette.printPaused})
            elif "PrintResumed" in event:
                if ".mcf.gcode" in payload["name"]:
                    self.palette.palette2SetupStarted = False
                    self.palette.updateUI({"command": "palette2SetupStarted", "data": self.palette.palette2SetupStarted})
                    self.palette.printPaused = False
                    self.palette.updateUI({"command": "printPaused", "data": self.palette.printPaused})
            elif "PrintDone" in event:
                if ".mcf.gcode" in payload["name"]:
                    self.palette.isConnectedMode = False
                    self.palette.actualPrintStarted = False
                    self.palette.updateUI({"command": "actualPrintStarted", "data": self.palette.actualPrintStarted})
            elif "PrintFailed" in event:
                if ".mcf.gcode" in payload["name"]:
                    self.palette.actualPrintStarted = False
                    self.palette.updateUI({"command": "actualPrintStarted", "data": self.palette.actualPrintStarted})
            elif "PrintCancelled" in event:
                if ".mcf.gcode" in payload["name"] and self.palette.connected:
                    self.palette.actualPrintStarted = False
                    self.palette.updateUI({"command": "actualPrintStarted", "data": self.palette.actualPrintStarted})
                    if not self.palette.cancelFromP2:
                        self.logger.info(getLog("Cancelling print from Hub"))
                        self.palette.cancelFromHub = True
                        self.palette.cancel()
                    else:
                        self.logger.info(getLog("Cancel already done from P2."))
            elif "FileAdded" in event:
                self.palette.getAllMCFFilenames()
            elif "FileRemoved" in event:
                self.palette.getAllMCFFilenames()
            elif "SettingsUpdated" in event:
                self.palette.settingsUpdateUI()
                if not self._settings.get(["advancedOptions"]):
                    self.palette.changeAutoVariationCancelPing(False)
                    self.palette.changeShowPingOnPrinter(False)
                    self.palette.changeFeedRateControl(False)
                self.palette.advancedUpdateVariables()
                if self._settings.get(["autoconnect"]):
                    self.palette.startConnectionThread()
                else:
                    self.palette.stopConnectionThread()
        except Exception as e:
            self.logger.error(getLog(e))

    def on_shutdown(self):
        self.palette.shutdown()

    def sending_gcode(self, comm_instance, phase, cmd, cmd_type, gcode, subcode=None, tags=None):
        if cmd is not None and len(cmd) > 1:
            # pings in GCODE
            if constants.COMMANDS["PING"] in cmd:
                self.palette.savePing(cmd.strip())
                return "G4 P10",
            # header information
            elif 'O' in cmd[0]:
                self.palette.gotOmegaCmd(cmd)
                return None,
            # pause print locally
            elif 'M0' in cmd[0:2]:
                self.palette.printPaused = True
                self.palette.updateUI({"command": "printPaused", "data": self.palette.printPaused})
                return None,
                # return gcode

    def support_msf_machinecode(*args, **kwargs):
        return dict(
            machinecode=dict(
                msf=["msf"]
            )
        )

    def get_update_information(self):
        # Define the configuration for your plugin to use with the Software Update
        # Plugin here. See https://github.com/foosel/OctoPrint/wiki/Plugin:-Software-Update
        # for details.
        return dict(
            palette2=dict(
                displayName="Palette 2 Plugin",
                displayVersion=self._plugin_version,
                current=self._plugin_version,
                type="python_checker",
                python_checker=P2PluginVersionChecker(),
                pip=constants.RELEASE_ZIP_URL
            )
        )

    def _setup_logger(self, name, log_file, level=logging.DEBUG):
        formatter = logging.Formatter(
            fmt='{ "product": "canvas-hub", "datetime": "%(asctime)s.%(msecs)03dZ", "plugin": "%('
                'name)s", '
                '"type": "%(levelname)s", "details": %(message)s }', datefmt='%Y-%m-%dT%H:%M:%S')
        handler = logging.FileHandler(log_file)
        handler.setFormatter(formatter)
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.addHandler(handler)
        return logger


__plugin_name__ = "Palette 2"
__plugin_description__ = "A plugin to handle communication with Palette 2"
__plugin_pythoncompat__ = ">=2.7,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = P2Plugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.comm.protocol.gcode.sending": __plugin_implementation__.sending_gcode,
        "octoprint.filemanager.extension_tree":  __plugin_implementation__.support_msf_machinecode,
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
