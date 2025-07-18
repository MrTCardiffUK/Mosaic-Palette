if (!document.getElementById("material-icons")) {
  let link = document.createElement("link");
  link.id = "material-icons";
  link.href = "https://fonts.googleapis.com/icon?family=Material+Icons";
  link.rel = "stylesheet";
  document.head.appendChild(link);
}

const Palette2UI = {
  /* LOADER */
  loadingOverlay: (condition, status) => {
    if (condition) {
      if (status === "connect") {
        message = `<h1 class="loading-overlay-message">Trying to connect to Palette 2...</h1>`;
      } else if (status === "disconnect") {
        message = `<h1 class="loading-overlay-message">Disconnecting Palette 2...</h1>`;
      } else if (status === "heartbeat") {
        message = `<h1 class="loading-overlay-message">Verifying Palette 2 connection before starting print...</h1>`;
      }
      $("body").append(`<div class="loading-overlay-container">
    <div class="loader"></div>
    ${message}
    </div>`);
    } else {
      $("body")
        .find(".loading-overlay-container")
        .remove();
    }
  },
  /* HIGHLIGHT TO HELP USER USE TEMP CONTROLS */
  temperatureHighlight: () => {
    $("body")
      .find(`#temperature-table .input-mini.input-nospin:first`)
      .addClass("highlight-glow")
      .on("focus", event => {
        $(event.target).removeClass("highlight-glow");
      });
  },
  /* HIGHLIGHT TO HELP USER USE EXTRUSION CONTROLS */
  extrusionHighlight: () => {
    $("body")
      .find("#control-jog-extrusion .input-mini.text-right")
      .addClass("highlight-glow")
      .on("focus", event => {
        $(event.target).removeClass("highlight-glow");
      });
    $("body")
      .find("#control-jog-extrusion > div :nth-child(3)")
      .addClass("highlight-glow-border")
      .on("focus", event => {
        $(event.target).removeClass("highlight-glow-border");
      });
  },
  /* CLOSE ALERT */
  closeAlert: () => {
    if (Swal.isVisible()) {
      Swal.close();
    }
  },
  /* Append Notification List to DOM */
  addNotificationList: () => {
    if ($("body").find(".side-notifications-list").length === 0) {
      $("body")
        .css("position", "relative")
        .append(`<ul class="side-notifications-list"></ul>`);
    }
  },
}