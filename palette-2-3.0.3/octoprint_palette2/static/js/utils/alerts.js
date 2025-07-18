if (!document.getElementById("sweetalert2-styling")) {
  let link = document.createElement("link");
  link.id = "sweetalert2-styling";
  link.href = "https://cdnjs.cloudflare.com/ajax/libs/limonte-sweetalert2/7.29.0/sweetalert2.min.css";
  link.rel = "stylesheet";
  document.head.appendChild(link);
}
if (!document.getElementById("sweetalert2-script")) {
  let script = document.createElement("script");
  script.id = "sweetalert2-script";
  script.src = "https://cdnjs.cloudflare.com/ajax/libs/limonte-sweetalert2/7.29.0/sweetalert2.min.js";
  document.head.appendChild(script);
}

const Palette2Alerts = {
  cannotConnectAlert: () => {
    return swal({
      title: "Could not connect to Palette 2",
      text: `Please make sure Palette 2 is turned on and try manual port selection if problems persist. Please wait 5 seconds before trying again.`,
      type: "error"
    });
  },
  palette2PrintStartAlert: () => {
    return swal({
      title: "You are about to print with Palette 2",
      text:
        "Your print will temporarily be paused. This is normal - please follow the instructions on Palette 2's screen. The print will resume automatically once everything is ready.",
      type: "info"
    });
  },
  preheatAlert: () => {
    return swal({
      title: "Pre-heat your printer",
      text:
        "Palette 2 is now making filament. In the meantime, please pre-heat your printer using the controls in the Temperature Tab.",
      type: "info"
    });
  },
  extrusionAlert: firstTime => {
    let text = `Use the "Extrude" button in the Controls tab or the "Smart Load" button in the loading notification to drive filament into the extruder. If using "Smart Load", please place the filament at a proper angle to be inserted into the extruder before loading.`;
    if (firstTime) {
      text = `Use the "Extrude" button in the Controls tab to drive filament into the extruder until you see the desired color. To accurately load, we recommend setting the extrusion amount to a low number.`;
    }
    return swal({
      title: "Follow instructions on Palette 2 ",
      text: text,
      type: "info"
    });
  },
  printCancellingAlert: () => {
    return swal({
      title: "Palette 2: Print cancelling",
      text: `Please remove filament from the extruder and from Palette 2.`,
      type: "info"
    });
  },
  printCancelledAlert: () => {
    return swal({
      title: "Palette 2: Print cancelled",
      text: `Palette 2 print successfully cancelled. Please make sure you have pressed "Finished" on Palette 2's screen before starting a new print.`,
      type: "info"
    });
  },
  palette2NotConnectedAlert: () => {
    return swal({
      title: "Palette 2 not connected",
      text: "You have selected an .mcf file. Please enable the connection to Palette 2 before printing.",
      type: "info"
    });
  },
  noSerialPortsAlert: () => {
    return swal({
      title: "No serial ports detected",
      text: `Please make sure all cables are inserted properly into your Hub.`,
      type: "error"
    });
  },
  errorAlert: errorNumber => {
    return swal({
      title: `Error ${errorNumber} detected`,
      text: `An error occurred on Palette 2. Your print has been paused. Would you like to send a crash report to Mosaic for investigation?`,
      confirmButtonText: "Yes",
      showCancelButton: true,
      cancelButtonText: "No",
      reverseButtons: true,
      type: "error"
    });
  },
  errorTextAlert: () => {
    return swal({
      title: "Please provide additional details (OPTIONAL)",
      text:
        "(E.g: what part of the print you were at, what is displayed on your Palette 2 screen, is this the first time this has occurred, etc)",
      customClass: "error-container",
      input: "textarea",
      inputClass: "error-textarea",
      width: "40rem",
      confirmButtonText: "Send"
    });
  },
  displayHeartbeatAlert: () => {
    return swal({
      title: "No response from Palette 2",
      text: `Please make sure Palette 2 is turned on and try reconnecting to it in the Palette 2 tab before starting another print.`,
      type: "error"
    });
  },
  readyToStartAlert: (displayAlertsSetting, autoStartAfterLoadSetting) => {
    const titleLabel = "Filament in place and ready to go";
    const confirmLabel = autoStartAfterLoadSetting ? "Okay" : "Start Print";
    const bodyLabel = autoStartAfterLoadSetting
      ? "Your print should be starting automatically."
      : `Please press "Start Print" below or directly on your Palette 2 screen to begin your print.`;
    return swal({
      title: titleLabel,
      type: "info",
      html: `
      <div>${bodyLabel}</div>
      <ul class="swal2-p2-settings">
        <li class="swal2-p2-setting">
          <input type="checkbox" id="swal2-p2-checkbox1" ${displayAlertsSetting ? null : 'checked'}>
          <label for="swal2-p2-checkbox1">
            Don't show me these setup alerts anymore
          </label>
        </li>
        <li class="swal2-p2-setting">
          <input type="checkbox" id="swal2-p2-checkbox2" ${autoStartAfterLoadSetting ? 'checked' : null}>
          <label for="swal2-p2-checkbox2">
            Start future prints automatically after loading sequence
          </label>
        </li>
      </ul>`,
      confirmButtonText: confirmLabel,
      preConfirm: () => {
        // return text label when user clicks on confirmButton
        // "Okay" = close modal and do nothing, "Start Print" = actually start print
        return confirmLabel;
      },
    });
  },
  autoLoadFailAlert: () => {
    return swal({
      title: "Smart Load did not complete properly",
      text: `Filament stopped moving. Please make sure the filament is properly placed in the extruder and then continue extruding, either with "Smart Load" again or with manual controls. If a splice is occurring, please wait for it to finish before trying again.`,
      type: "info"
    });
  },
  P2SerialConnectionErrorAlert: () => {
    return swal({
      title: "Palette 2 connection error detected",
      text: `The connection between CANVAS Hub and Palette 2 has stopped. Please make sure Palette 2 is turned on and its cable is properly inserted into the Hub before connecting again.`,
      type: "error"
    });
  },
  python3CompatibilityAlert: (pluginsToUpdate) => {
    let pluginsToUpdateText = "";
    pluginsToUpdate.forEach(plugin => {
      pluginsToUpdateText += `<li style="margin-bottom: 5px">${plugin.name}</li>`;
    });
    return swal({
      title: "Python 3 Compatibility",
      html: `We detected that you are currently using other Mosaic helpers plugins that must be updated to be compatible with future versions of OctoPrint.
       Please update the following plugins to their latest version:
       <br>
       <br>
       <ul>${pluginsToUpdateText}</ul>
       <br>
       Please refer to this <a target="_blank" href="http://mm3d.co/python3-update">article</a> for more information.`,
      type: "info",
      confirmButtonText: "Update Now"
    });
  },
};
