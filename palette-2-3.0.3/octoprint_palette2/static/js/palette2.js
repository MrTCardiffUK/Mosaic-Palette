function OmegaViewModel(parameters) {
  var self = this;

  /* OTHER VIEWMODELS */
  self.settings = parameters[0];
  self.control = parameters[1];
  self.printerState = parameters[2];
  self.files = parameters[3];
  self.pluginManager = parameters[4];

  /* GLOBAL VARIABLES */
  self.notificationId = "";
  self.firstTime = false;
  self.actualPrintStarted = false;

  /* KNOCKOUT DATA-BINDINGS */
  // Plugin settings
  self.autoconnect = ko.observable(false);
  self.displaySetupAlerts = ko.observable(true);
  self.autoStartAfterLoad = ko.observable(false);
  self.advancedOptions = ko.observable();

  // Connection observables
  self.connected = ko.observable(false);
  self.connectionStateMsg = ko.computed(function () {
    if (self.connected()) {
      return "Connected";
    } else {
      return self.autoconnect() ? "Not Connected - Trying To Connect..." : "Not Connected";
    }
  });
  self.connectPaletteText = ko.computed(function () {
    return self.connected() ? "Connected" : "Connect to Palette 2";
  });
  self.disconnectPaletteText = ko.computed(function () {
    return self.connected() ? "Disconnect" : "Disconnected";
  });
  self.ports = ko.observableArray([]);
  self.selectedPort = ko.observable();

  // General status observables
  self.currentStatus = ko.observable();
  self.palette2SetupStarted = ko.observable();
  self.filaLength = ko.observable();
  self.filaLengthDisplay = ko.computed(function () {
    return (Number(self.filaLength()) / 1000.0).toFixed(2) + "m";
  });
  self.currentSplice = ko.observable();
  self.nSplices = ko.observable();
  self.totalSplicesDisplay = ko.computed(function () {
    return " / " + self.nSplices() + " Splices";
  });
  self.pings = ko.observableArray([]);
  self.pingsDisplay = ko.computed(function () {
    return self.pings().map(ping => {
      return {
        number: ping.number,
        percent: ping.percent !== "MISSED" ? `${ping.percent}%` : 'MISSED',
      };
    });
  });
  self.latestPing = ko.computed(function () {
    return self.pingsDisplay()[0] ? self.pingsDisplay()[0].number : 0;
  });
  self.latestPingPercent = ko.computed(function () {
    return self.pingsDisplay()[0] ? self.pingsDisplay()[0].percent : "%";
  });
  self.pongs = ko.observableArray([]);
  self.pongsDisplay = ko.computed(function () {
    return self.pongs().map(pong => {
      return {
        number: pong.number,
        percent: `${pong.percent}%`,
      };
    });
  });
  self.latestPong = ko.computed(function () {
    return self.pongsDisplay()[0] ? self.pongsDisplay()[0].number : 0;
  });
  self.latestPongPercent = ko.computed(function () {
    return self.pongsDisplay()[0] ? self.pongsDisplay()[0].percent : "%";
  });

  // Advanced options observables
  self.autoVariationCancelPing = ko.observable(true);
  self.variationPct = ko.observable(8);
  self.variationPingStart = ko.observable(1);
  self.variationPctStatus = ko.computed(function () {
    const variationPingStart = Number(self.variationPingStart());
    if (self.pings().length >= variationPingStart) {
      const variation = Number(self.variationPct());
      const upperBound = self.pings()[0].percent + variation;
      const lowerBound = self.pings()[0].percent - variation;
      return `An upcoming ping greater than ${upperBound}% or lower than ${lowerBound}% will cancel your print`;
    } else {
      return `Variation detection not started yet. Waiting for ping ${variationPingStart}...`
    }
  });
  self.showPingOnPrinter = ko.observable(true);
  self.feedRateControl = ko.observable(true);
  self.feedRateSlowed = ko.observable(false);
  self.feedRateSlowedText = ko.computed(function () {
    return self.feedRateSlowed() && self.printerState.isPrinting() ? "Yes" : "No";
  });
  self.feedRateNormalPct = ko.observable(100);
  self.feedRateSlowPct = ko.observable(50);
  self.feedRateStatus = ko.observable("Awaiting Update...");

  // Side notification list observables
  self.autoLoad = ko.observable(false);
  self.isAutoLoading = ko.observable(false);
  self.autoLoadButtonText = ko.computed(function () {
    return self.isAutoLoading() ? "Loading..." : "Smart Load";
  });
  self.amountLeftToExtrude = ko.observable();
  self.amountLeftToExtrudeText = ko.computed(function () {
    if (self.amountLeftToExtrude() > 0 || self.amountLeftToExtrude() < 0) {
      return `${self.amountLeftToExtrude()}mm`;
    } else if (self.amountLeftToExtrude() === 0) {
      return "Loading complete";
    } else {
      return "No loading offset detected";
    }
  });

  /* COMMUNICATION TO BACK-END FUNCTIONS */
  self.displayPorts = () => {
    const condition = $(".serial-ports-list").is(":visible") ? "closing" : "opening";
    const payload = {
      command: "displayPorts",
      condition: condition
    };
    self.ajaxRequest(payload).done(() => {
      self.settings.requestData();
      if (condition === "closing") {
        $(".serial-ports-list").hide(125);
      } else if (condition === "opening") {
        $(".serial-ports-list").toggle(125);
      }
    }).always(() => {
      if (self.ports().length === 0) {
        $(".serial-ports-list").hide(125);
        self.showAlert("noSerialPorts");
      }
    });
  };

  self.connectOmega = () => {
    Palette2UI.loadingOverlay(true, "connect");
    const condition = $(".serial-ports-list").is(":visible");
    const payload = {
      command: "connectOmega",
      port: condition ? self.selectedPort() || "" : ""
    }
    self.ajaxRequest(payload).fail(() => {
      if (self.ports().length === 0) {
        $(".serial-ports-list").hide(125);
        self.showAlert("noSerialPorts");
      } else {
        self.showAlert("cannotConnect");
      }
    }).always(value => {
      Palette2UI.loadingOverlay(false);
    });
  };

  self.disconnectPalette2 = () => {
    Palette2UI.loadingOverlay(true, "disconnect");
    self.connected(false);
    self.removeNotification();
    const payload = { command: "disconnectPalette2" };
    self.ajaxRequest(payload).always(value => {
      Palette2UI.loadingOverlay(false);
    });
  };

  self.changeAlertSettings = condition => {
    const payload = {
      command: "changeAlertSettings",
      condition: !condition
    };
    self.ajaxRequest(payload).then(() => {
      self.settings.requestData();
    });
  };

  self.changeAutoStartAfterLoad = condition => {
    const payload = {
      command: "changeAutoStartAfterLoad",
      condition: condition
    };
    self.ajaxRequest(payload).then(() => {
      self.settings.requestData();
    });
  };

  self.uiUpdate = () => {
    console.log("Requesting BE to update Palette2UI");
    const payload = { command: "uiUpdate" };
    self.ajaxRequest(payload);
  };

  self.sendCutCmd = () => {
    const payload = { command: "sendCutCmd" };
    self.ajaxRequest(payload);
  };

  self.sendClearOutCmd = () => {
    const payload = { command: "clearPalette2" };
    self.ajaxRequest(payload);
  };

  self.sendErrorReport = (errorNumber, description) => {
    const payload = {
      command: "sendErrorReport",
      errorNumber: errorNumber,
      description: description
    };
    self.ajaxRequest(payload);
  };

  self.startPrintFromHub = () => {
    const payload = { command: "startPrint" };
    self.ajaxRequest(payload);
  };

  self.downloadPingHistory = (data, event) => {
    event.stopPropagation();
    const payload = { command: "downloadPingHistory" }
    self.ajaxRequest(payload).then(result => {
      const filename = result.data.filename;
      const data = result.data.data;

      const blob = new Blob([data], { type: "text/plain" });
      if (window.navigator.msSaveOrOpenBlob) {
        window.navigator.msSaveBlob(blob, filename);
      } else {
        const elem = window.document.createElement("a");
        elem.href = window.URL.createObjectURL(blob);
        elem.download = filename;
        document.body.appendChild(elem);
        elem.click();
        elem.href = window.URL.revokeObjectURL(blob);
        document.body.removeChild(elem);
      }
    });
  };

  self.startAutoLoad = () => {
    const payload = { command: "startAutoLoad" };
    self.ajaxRequest(payload);
  };

  self.autoVariationCancelPing.subscribe(function () {
    const payload = {
      command: "changeAutoVariationCancelPing",
      condition: self.autoVariationCancelPing()
    };
    self.ajaxRequest(payload);
  });
  self.variationPct.subscribe(function () {
    const payload = {
      command: "changeVariationPct",
      value: self.variationPct()
    }
    self.ajaxRequest(payload);
  });
  self.variationPingStart.subscribe(function () {
    const payload = {
      command: "changeVariationPingStart",
      value: self.variationPingStart()
    }
    self.ajaxRequest(payload);
  });
  self.showPingOnPrinter.subscribe(function () {
    const payload = {
      command: "changeShowPingOnPrinter",
      condition: self.showPingOnPrinter()
    };
    self.ajaxRequest(payload);
  });
  self.feedRateControl.subscribe(function () {
    const payload = {
      command: "changeFeedRateControl",
      condition: self.feedRateControl()
    };
    self.ajaxRequest(payload);
  });
  self.feedRateNormalPct.subscribe(function () {
    const payload = {
      command: "changeFeedRateNormalPct",
      value: self.feedRateNormalPct()
    }
    self.ajaxRequest(payload);
  });
  self.feedRateSlowPct.subscribe(function () {
    const payload = {
      command: "changeFeedRateSlowPct",
      value: self.feedRateSlowPct()
    };
    self.ajaxRequest(payload);
  });

  self.ajaxRequest = payload => {
    return $.ajax({
      url: API_BASEURL + "plugin/palette2",
      type: "POST",
      dataType: "json",
      data: JSON.stringify(payload),
      contentType: "application/json; charset=UTF-8"
    });
  };

  self.handleAdvancedOptions = (subCommand, data) => {
    switch (subCommand) {
      case "displayAdvancedOptions":
        self.advancedOptions(data);
        break;
      case "feedRateControl":
        self.feedRateControl(data);
        break;
      case "feedRateSlowed":
        self.feedRateSlowed(data);
        break;
      case "autoVariationCancelPing":
        self.autoVariationCancelPing(data);
        break;
      case "variationPct":
        self.variationPct(data);
        break;
      case "variationPingStart":
        self.variationPingStart(data);
        break;
      case "showPingOnPrinter":
        self.showPingOnPrinter(data);
        break;
      case "feedRateNormalPct":
        self.feedRateNormalPct(data);
        break;
      case "feedRateSlowPct":
        self.feedRateSlowPct(data);
        break;
      case "advancedStatus":
        self.feedRateStatus(data);
        break;
      case "isAutoLoading":
        self.isAutoLoading(data);
        self.toggleSmallLoader();
        self.toggleAutoLoadText();
        break;
      default:
      //Do Nothing
    }
  };

  self.fromResponse = () => { };

  /* Palette2UI FUNCTIONS */

  self.checkIfCountdownExists = () => {
    if ($("body").find("#load-filament-notification").length === 0) {
      self.displayFilamentCountdown();
    }
  };

  self.smartLoadInfoListener = () => {
    $("body").find(".smart-load-icon").on("click", () => {
      self.toggleSmartLoadInfo();
    });
  };

  self.removePopupListener = () => {
    $(".remove-button").on("click", () => {
      self.removeNotification();
    });
  };

  self.autoLoadListener = () => {
    $(".autoload-button").on("click", () => {
      self.startAutoLoad();
    });
  };

  self.displayFilamentCountdown = () => {
    const notification = $(`
    <li id="load-filament-notification" class="popup-notification">
		  <i class="material-icons remove-button">clear</i>
		  <h6 class="load-filament-title">Remaining Length To Extrude:</h6>
      <div class="value-container">
        <span class="load-filament-value">${self.amountLeftToExtrudeText()}</span>
        <span class="small-loader-autoload"></span>
      </div>
      <div class="smart-load-container">
        <button class="btn btn-primary autoload-button">${self.autoLoadButtonText()}</button>
        <div class="smart-load-info-container">
          <i class="material-icons smart-load-icon">info_outline</i>
          <div class="smart-load-text" id="autoload-filament-text">
            <h6 class="smart-load-heading">Smart Loading makes starting a print easier</h6>
            <div class="smart-load-body"><p>Securely load your filament into your printer's extruder, insert the Outgoing Tube into the clip, then click "Smart Load". CANVAS Hub will automatically load the correct amount of filament into your printer and begin the print automatically.</p></div>
          </div>
        </div>
      </div>
    </li>`).hide();
    self.notificationId = "#load-filament-notification";
    $(".side-notifications-list").append(notification);

    self.smartLoadInfoListener();
    self.removePopupListener();
    self.autoLoadListener();
    self.toggleSmallLoader();
  };

  self.updateFilamentCountdown = firstValue => {
    if (self.amountLeftToExtrude() < 0) {
      Palette2UI.closeAlert();
      $(self.notificationId)
        .find(".load-filament-value")
        .addClass("negative-number");
    } else {
      $(self.notificationId)
        .find(".load-filament-value")
        .removeClass("negative-number");
    }
    if (firstValue) {
      $(self.notificationId)
        .fadeIn(200)
        .find(".load-filament-value")
        .text(`${self.amountLeftToExtrudeText()}`);
    } else {
      $(self.notificationId)
        .find(".load-filament-value")
        .text(`${self.amountLeftToExtrudeText()}`);
    }
  };

  self.removeNotification = () => {
    $(self.notificationId).fadeOut(500, function () {
      this.remove();
    });
  };

  self.showAlert = (command, condition) => {
    if (command === "temperature") {
      if (self.displaySetupAlerts()) {
        const base_url = window.location.origin;
        window.location.href = `${base_url}/#temp`;
        Palette2UI.temperatureHighlight();
        Palette2Alerts.preheatAlert();
      }
    } else if (command === "extruder") {
      if (self.displaySetupAlerts()) {
        const base_url = window.location.origin;
        window.location.href = `${base_url}/#control`;
        Palette2UI.extrusionHighlight();
        Palette2Alerts.extrusionAlert(self.firstTime);
      }
    } else if (command === "cancelling") {
      self.removeNotification();
      Palette2Alerts.printCancellingAlert();
    } else if (command === "printStarted") {
      // if user presses start from P2
      Palette2UI.closeAlert();
    } else if (command === "cancelled") {
      self.removeNotification();
      Palette2Alerts.printCancelledAlert();
    } else if (command === "startPrint") {
      $("body").on("click", "#swal2-p2-checkbox1", event => {
        self.changeAlertSettings(event.target.checked);
      });
      $("body").on("click", "#swal2-p2-checkbox2", event => {
        self.changeAutoStartAfterLoad(event.target.checked);
      });
      Palette2Alerts.readyToStartAlert(self.displaySetupAlerts(), self.autoStartAfterLoad()).then(result => {
        if (result.hasOwnProperty("value") && result.value === 'Start Print') {
          self.startPrintFromHub();
        }
      });
    } else if (command === "cannotConnect") {
      Palette2Alerts.cannotConnectAlert();
    } else if (command === "heartbeat") {
      Palette2UI.loadingOverlay(false);
      if (condition === "P2NotConnected") {
        Palette2Alerts.displayHeartbeatAlert();
      } else if (condition === "P2Responded") {
        Palette2Alerts.palette2PrintStartAlert()
      }
    } else if (command === "error") {
      Palette2Alerts.errorAlert(condition).then(result => {
        // if user clicks yes
        if (result.value) {
          Palette2Alerts.errorTextAlert().then(result => {
            if (result.dismiss === Swal.DismissReason.cancel) {
            } else {
              description = "";
              if (result.value) {
                description = result.value;
              }
              self.sendErrorReport(condition, description);
            }
          });
        }
        // if user clicks no
        else if (result.dismiss === Swal.DismissReason.cancel) {
        }
      });
    } else if (command === "noSerialPorts") {
      Palette2Alerts.noSerialPortsAlert();
    } else if (command === "turnOnP2") {
      Palette2Alerts.palette2NotConnectedAlert();
    } else if (command === "autoLoadIncomplete") {
      Palette2Alerts.autoLoadFailAlert();
    } else if (command === "threadError") {
      Palette2Alerts.P2SerialConnectionErrorAlert()
    }
  };

  self.toggleAdvancedOptionInfo = (data, event) => {
    const targetId = `#${event.target.nextElementSibling.id}`;
    if ($(`.advanced-info-text:not(${targetId})`).is(":visible")) {
      $(".advanced-info-text").hide(50);
    }
    $(targetId).toggle(50);
  };

  self.toggleSmartLoadInfo = (data, event) => {
    $(".smart-load-text").toggle(50);
  };

  self.toggleSmallLoader = () => {
    if (self.isAutoLoading()) {
      $(".small-loader-autoload").show();
    } else {
      $(".small-loader-autoload").fadeOut(200);
    }
  };

  self.toggleAutoLoadText = () => {
    if (self.isAutoLoading() || self.amountLeftToExtrude() <= 0 || self.firstTime) {
      $(self.notificationId)
        .find(".autoload-button")
        .text(`${self.autoLoadButtonText()}`)
        .attr("disabled", "disabled");
    } else {
      $(self.notificationId)
        .find(".autoload-button")
        .text(`${self.autoLoadButtonText()}`)
        .removeAttr("disabled");
    }
  };

  self.togglePingHistory = (data, event) => {
    if (self.pingsDisplay().length) {
      $(".ping-history").slideToggle();
    }
  };

  self.togglePongHistory = () => {
    if (self.pongsDisplay().length) {
      $(".pong-history").slideToggle();
    }
  };

  /* VIEWMODELS MODIFICATIONS FOR P2 PLUGIN */

  self.modifyPrinterStateVM = () => {
    self.printerState.enablePrint = ko.pureComputed(function () {
      if (self.printerState.filename() && self.printerState.filename().includes(".mcf.gcode")) {
        return (
          self.printerState.isOperational() &&
          self.printerState.isReady() &&
          !self.printerState.isPrinting() &&
          !self.printerState.isCancelling() &&
          !self.printerState.isPausing() &&
          self.printerState.loginState.isUser() &&
          self.printerState.filename() &&
          self.connected()
        );
      } else {
        return (
          self.printerState.isOperational() &&
          self.printerState.isReady() &&
          !self.printerState.isPrinting() &&
          !self.printerState.isCancelling() &&
          !self.printerState.isPausing() &&
          self.printerState.loginState.isUser() &&
          self.printerState.filename()
        );
      }
    });

    self.printerState.enablePause = ko.pureComputed(function () {
      if (
        self.printerState.filename() &&
        self.printerState.filename().includes(".mcf.gcode") &&
        self.palette2SetupStarted()
      ) {
        return false;
      } else {
        return (
          self.printerState.isOperational() &&
          (self.printerState.isPrinting() || self.printerState.isPaused()) &&
          !self.printerState.isCancelling() &&
          !self.printerState.isPausing() &&
          self.printerState.loginState.isUser()
        );
      }
    });
  };

  self.modifyFilesVM = () => {
    self.files.enablePrint = function (data) {
      if (data.name.includes(".mcf.gcode")) {
        return (
          self.files.loginState.isUser() &&
          self.files.isOperational() &&
          !(self.files.isPrinting() || self.files.isPaused() || self.files.isLoading()) &&
          self.connected()
        );
      } else {
        return (
          self.files.loginState.isUser() &&
          self.files.isOperational() &&
          !(self.files.isPrinting() || self.files.isPaused() || self.files.isLoading())
        );
      }
    };

    self.files.enableSelect = function (data, printAfterSelect) {
      if (
        data.name.includes(".mcf.gcode") &&
        self.files.isOperational() &&
        !(self.files.isPrinting() || self.files.isPaused() || self.files.isLoading())
      ) {
        return true && !self.files.listHelper.isSelected(data);
      } else {
        return self.files.enablePrint(data) && !self.files.listHelper.isSelected(data);
      }
    };
  };

  /* OCTOPRINT-SPECIFIC EVENT HANDLERS */

  self.onBeforeBinding = () => {
    self.uiUpdate();
    self.modifyPrinterStateVM();
    self.modifyFilesVM();

    self.currentSplice(0);
    self.nSplices(0);
    self.filaLength(0);
    self.connected(false);
  };

  self.onAfterBinding = () => {
    self.uiUpdate();
  };

  self.onEventFileSelected = payload => {
    if (payload.name.includes(".mcf.gcode") && !self.connected()) {
      self.showAlert("turnOnP2");
    }
  };

  self.onEventPrintStarted = payload => {
    if (payload.name.includes(".mcf.gcode")) {
      Palette2UI.loadingOverlay(false,"heartbeat");
      if (self.connected) {
        Palette2UI.loadingOverlay(false);
      } else {
        self.connectOmega();
      }
    }
  };

  self.onEventPrintCancelling = payload => {
    self.removeNotification();
  };

  self.onEventPrintCancelled = payload => {
    self.removeNotification();
  };

  self.onDataUpdaterPluginMessage = (pluginIdent, message) => {
    if (pluginIdent === "palette2") {
      if (message.command === "error") {
        self.showAlert("error", message.data);
      } else if (message.command === "printHeartbeatCheck") {
        if (message.data === "P2NotConnected") {
          const base_url = window.location.origin;
          window.location.href = `${base_url}/#tab_plugin_palette2`;
        }
        self.showAlert("heartbeat", message.data);
      } else if (message.command === "pings") {
        self.pings(message.data.reverse());
      } else if (message.command === "pongs") {
        self.pongs(message.data.reverse());
      } else if (message.command === "selectedPort") {
        self.selectedPort(message.data);
      } else if (message.command === "ports") {
        self.ports(message.data)
      } else if (message.command === "currentSplice") {
        self.currentSplice(message.data);
      } else if (message.command === "displaySetupAlerts") {
        self.displaySetupAlerts(message.data);
      } else if (message.command === "autoStartAfterLoad") {
        self.autoStartAfterLoad(message.data);
      } else if (message.command === "totalSplices") {
        self.nSplices(message.data);
      } else if (message.command === "p2Connection") {
        self.connected(message.data);
        if (self.connected() && !$(".serial-ports-list").is(":visible")) {
          $(".serial-ports-list").show(125);
        }
      } else if (message.command === "filamentLength") {
        self.filaLength(message.data);
      } else if (message.command === "currentStatus") {
        if (message.data && message.data !== self.currentStatus()) {
          self.currentStatus(message.data);
          if (self.currentStatus() === "Loading filament into extruder") {
            Palette2UI.addNotificationList();
            self.checkIfCountdownExists();
          } else if (self.currentStatus() === "Print started: preparing splices") {
            self.removeNotification();
          }
        } else if (!message.data) {
          self.currentStatus("No ongoing Palette 2 print");
        }
      } else if (message.command === "amountLeftToExtrude") {
        if (!self.actualPrintStarted) {
          self.amountLeftToExtrude(message.data);
          if (!$("#load-filament-notification").is(":visible")) {
            self.updateFilamentCountdown(true);
          } else if ($("#load-filament-notification").is(":visible")) {
            self.updateFilamentCountdown(false);
          }
        }
      } else if (message.command === "printPaused") {
        self.printPaused = message.data;
      } else if (message.command === "firstTime") {
        self.firstTime = message.data;
      } else if (message.command === "autoConnect") {
        self.autoconnect(message.data);
      } else if (message.command === "palette2SetupStarted") {
        self.palette2SetupStarted(message.data);
      } else if (message.command === "actualPrintStarted") {
        self.actualPrintStarted = message.data;
      } else if (message.command === "alert") {
        self.showAlert(message.data);
      } else if (message.command === "advanced") {
        self.handleAdvancedOptions(message.subCommand, message.data);
      } else if (message.command === "python3") {
        Palette2Alerts.python3CompatibilityAlert(message.data).then(result => {
          if (result.hasOwnProperty("value")) {
            const plugins = message.data;
            // initialize some global variables to keep track of update progress
            self.python3Update = true;
            self.pluginsUpdated = 0;
            self.pluginsToUpdateCount = plugins.length;

            plugins.forEach(plugin => {
              self.pluginManager.installPlugin(plugin.url);
            });
          }
        });
      }
    } else if (pluginIdent === "pluginmanager") {
      if (self.python3Update) {
        // hacky way to give user visual feedback that more than
        // one plugin is being installed at once via the plugin manager view model
        // this is done because the plugin manager view model is only designed to install
        // 1 plugin at a time
        if (message.type === "result") {
          self.pluginsUpdated++;
          if (self.pluginsUpdated === self.pluginsToUpdateCount) {
            self.python3Update = false;
            self.pluginManager.working(false); // set it to false just to be safe
          }
        } else if (message.type === "loglines") {
          if (self.pluginsUpdated < self.pluginsToUpdateCount) {
            self.pluginManager.working(true);
          }
        }
      }
    }
  };
}

/* ======================
  RUN
  ======================= */

$(function () {
  OCTOPRINT_VIEWMODELS.push({
    // This is the constructor to call for instantiating the plugin
    construct: OmegaViewModel,
    dependencies: ["settingsViewModel", "controlViewModel", "printerStateViewModel", "filesViewModel", "pluginManagerViewModel"],
    elements: ["#tab_plugin_palette2"]
  }); // This is a list of dependencies to inject into the plugin. The order will correspond to the "parameters" arguments above // Finally, this is the list of selectors for all elements we want this view model to be bound to.
});
