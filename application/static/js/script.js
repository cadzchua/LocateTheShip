function getField(id) {
  return document.getElementById(id);
}

function saveFormData() {
  var formData = {
    shipName: getField("shipName").value,
    mmsi: getField("mmsi").value,
    source: getField("source") ? getField("source").value : "",
    datetime1: getField("datetime1").value,
    datetime2: getField("datetime2").value,
  };
  localStorage.setItem("formData", JSON.stringify(formData));
}

function clearFormData() {
  localStorage.removeItem("formData");
  window.location.href = "/map";
}

function hasActiveFilter() {
  return (
    getField("shipName").value ||
    getField("mmsi").value ||
    (getField("source") && getField("source").value) ||
    getField("datetime1").value ||
    getField("datetime2").value
  );
}

function toggleForm() {
  var form = document.querySelector(".filter-form");
  var formContainer = document.querySelector(".filter-forms");
  var button = document.getElementById("myButton2");

  form.classList.toggle("minimized");
  formContainer.classList.toggle("expanded");

  if (form.classList.contains("minimized")) {
    button.textContent = "+";
    formContainer.style.backgroundColor = "#ffffff67";
  } else {
    button.textContent = "-";
    formContainer.style.backgroundColor = "#ffffff";
  }
}

function toLocalDatetimeValue(date) {
  function pad(n) {
    return String(n).padStart(2, "0");
  }
  return (
    date.getFullYear() +
    "-" +
    pad(date.getMonth() + 1) +
    "-" +
    pad(date.getDate()) +
    "T" +
    pad(date.getHours()) +
    ":" +
    pad(date.getMinutes())
  );
}

function setQuickRange(minutes) {
  if (minutes === null) {
    getField("datetime1").value = "";
    getField("datetime2").value = "";
  } else {
    var now = new Date();
    var start = new Date(now.getTime() - minutes * 60 * 1000);
    getField("datetime1").value = toLocalDatetimeValue(start);
    getField("datetime2").value = "";
  }
  saveFormData();
  document.getElementById("filterForm").submit();
}

var autoRefreshTimer = null;

function refreshNow() {
  if (localStorage.getItem("autoRefresh") !== "true") {
    return;
  }
  if (hasActiveFilter()) {
    saveFormData();
    document.getElementById("filterForm").submit();
  } else {
    window.location.href = "/map";
  }
}

function scheduleAutoRefresh() {
  var enabled = localStorage.getItem("autoRefresh") === "true";
  var interval = parseInt(localStorage.getItem("refreshInterval") || "30", 10);
  getField("autoRefresh").checked = enabled;
  getField("refreshInterval").value = String(interval);
  if (autoRefreshTimer !== null) {
    clearTimeout(autoRefreshTimer);
    autoRefreshTimer = null;
  }
  if (enabled) {
    autoRefreshTimer = setTimeout(refreshNow, interval * 1000);
  }
}

window.onload = function () {
  var savedFormData = localStorage.getItem("formData");
  if (savedFormData) {
    var formData = JSON.parse(savedFormData);
    getField("shipName").value = formData.shipName || "";
    getField("mmsi").value = formData.mmsi || "";
    if (getField("source")) {
      getField("source").value = formData.source || "";
    }
    getField("datetime1").value = formData.datetime1 || "";
    getField("datetime2").value = formData.datetime2 || "";
  }

  getField("autoRefresh").addEventListener("change", function () {
    localStorage.setItem("autoRefresh", this.checked ? "true" : "false");
    if (this.checked) {
      scheduleAutoRefresh();
    }
  });
  getField("refreshInterval").addEventListener("change", function () {
    localStorage.setItem("refreshInterval", this.value);
  });

  scheduleAutoRefresh();
};

document.getElementById("myButton").addEventListener("click", function () {
  window.location.href = "/";
});
