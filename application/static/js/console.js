/* LocateTheShip console — Leaflet + JSON API client. No framework, no build step. */
"use strict";

/* ------------------------------- constants ------------------------------ */
const SOG_NA = 102.3;
const COG_NA = 360.0;
const HEADING_NA = 511;

const TILES = {
  dark: {
    url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
  },
  light: {
    url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
  },
};

/* --------------------------------- state -------------------------------- */
const state = {
  vessels: [],
  stats: null,
  sources: [],
  filters: { ship_names: "", mmsi: "", source: "", start: "", end: "" },
  search: "",
  sortBy: "latest",
  selected: null,          // mmsi
  paused: false,
  intervalSec: 30,
  fetchedAt: null,         // Date of last successful fetch
  warmingUp: false,
  hasFitted: false,
  refitNext: false,
};

let map, tileLayer, trackLayer, dotLayer, markerLayer;
let refreshTimer = null;
let ageTimer = null;
const markersByMmsi = new Map();

const $ = (id) => document.getElementById(id);

/* ------------------------------- formatting ----------------------------- */
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}
function fmtSog(sog) {
  return sog == null || sog >= SOG_NA ? "N/A" : sog.toFixed(1) + " kn";
}
function fmtCog(cog) {
  return cog == null || cog >= COG_NA ? "N/A" : cog.toFixed(1) + "°";
}
function fmtHeading(h) {
  return h == null || h === HEADING_NA ? "N/A" : h + "°";
}
function fmtAge(seconds) {
  if (seconds == null) return "—";
  if (seconds < 60) return seconds + "s ago";
  if (seconds < 3600) return Math.floor(seconds / 60) + "m ago";
  if (seconds < 86400) return Math.floor(seconds / 3600) + "h ago";
  return Math.floor(seconds / 86400) + "d ago";
}
function liveAge(vessel) {
  const drift = state.fetchedAt ? Math.floor((Date.now() - state.fetchedAt.getTime()) / 1000) : 0;
  return vessel.latest.age_seconds + drift;
}
function rotationFor(latest) {
  if (latest.heading != null && latest.heading >= 0 && latest.heading < HEADING_NA) return latest.heading;
  if (latest.cog != null && latest.cog >= 0 && latest.cog < COG_NA) return latest.cog;
  return 0;
}
function toLocalInput(date) {
  const p = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}T${p(date.getHours())}:${p(date.getMinutes())}`;
}

/* --------------------------------- status ------------------------------- */
function setStatus(stateName, text) {
  const pill = $("statusPill");
  pill.dataset.state = stateName;
  $("statusText").textContent = text;
}

let toastTimer = null;
function toast(message, kind) {
  const el = $("toast");
  el.textContent = message;
  el.className = "toast" + (kind === "info" ? " info" : "");
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 4000);
}

function showOverlay(title, text) {
  $("overlayTitle").textContent = title;
  $("overlayText").textContent = text;
  $("overlay").hidden = false;
}
function hideOverlay() {
  $("overlay").hidden = true;
}

/* ---------------------------------- URL --------------------------------- */
function filtersToQuery() {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(state.filters)) {
    if (value) qs.set(key, value);
  }
  return qs;
}
function syncUrl() {
  const qs = filtersToQuery().toString();
  history.replaceState(null, "", qs ? "?" + qs : location.pathname);
}
function loadFiltersFromUrl() {
  const qs = new URLSearchParams(location.search);
  for (const key of Object.keys(state.filters)) {
    state.filters[key] = qs.get(key) || "";
  }
}
function filtersActiveCount() {
  return Object.values(state.filters).filter(Boolean).length;
}

/* --------------------------------- fetch -------------------------------- */
let inFlight = null;

async function fetchData() {
  if (inFlight) inFlight.abort();
  const ctl = new AbortController();
  inFlight = ctl;
  try {
    const resp = await fetch("/api/vessels?" + filtersToQuery().toString(), { signal: ctl.signal });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const data = await resp.json();

    state.vessels = data.vessels;
    state.stats = data.stats;
    state.sources = data.sources;
    state.warmingUp = data.warming_up;
    state.fetchedAt = new Date();

    renderSources();
    renderKpis();
    renderMap();
    renderList();
    renderDetail();

    if (state.warmingUp) {
      setStatus("warming", "Warming up");
      showOverlay("Pipeline warming up", "Kafka, ksqlDB and the sink connector are still starting. Data usually appears within a minute or two.");
    } else if (!state.vessels.length) {
      setStatus(state.paused ? "paused" : "live", state.paused ? "Paused" : "Live");
      showOverlay("No vessels match", "No position reports for the current filters. Widen the time range or reset the filters.");
    } else {
      hideOverlay();
      setStatus(state.paused ? "paused" : "live", state.paused ? "Paused" : "Live");
      if (state.stats.truncated) toast("Result capped at newest " + state.stats.reports + " reports — narrow the time range", "info");
    }
  } catch (err) {
    if (err.name === "AbortError") return;
    setStatus("error", "Connection lost");
    toast("Failed to reach the server: " + err.message);
  } finally {
    if (inFlight === ctl) inFlight = null;
    scheduleNext();
  }
}

function scheduleNext() {
  clearTimeout(refreshTimer);
  if (state.paused || !state.intervalSec) return;
  refreshTimer = setTimeout(() => {
    if (document.hidden) { scheduleNext(); return; }
    fetchData();
  }, state.intervalSec * 1000);
}

/* ---------------------------------- map --------------------------------- */
function initMap() {
  map = L.map("map", { zoomControl: true, attributionControl: true, preferCanvas: true })
    .setView([1.25, 103.8], 9);
  applyTiles();
  trackLayer = L.layerGroup().addTo(map);
  dotLayer = L.layerGroup().addTo(map);
  markerLayer = L.layerGroup().addTo(map);
}

function applyTiles() {
  const theme = document.documentElement.dataset.theme === "light" ? "light" : "dark";
  if (tileLayer) map.removeLayer(tileLayer);
  tileLayer = L.tileLayer(TILES[theme].url, {
    attribution: TILES[theme].attribution,
    maxZoom: 19,
    subdomains: "abcd",
  }).addTo(map);
}

function shipIcon(vessel, selected) {
  const rot = rotationFor(vessel.latest);
  const size = selected ? 26 : 18;
  return L.divIcon({
    className: "ship-marker" + (selected ? " selected" : ""),
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html:
      `<div style="transform: rotate(${rot}deg); width:${size}px; height:${size}px;">` +
      `<svg viewBox="0 0 24 24" width="${size}" height="${size}">` +
      (selected ? `<circle cx="12" cy="12" r="11" fill="none" stroke="${vessel.color}" stroke-width="1.5" opacity="0.8"/>` : "") +
      `<path d="M12 2.5 L18 20 L12 16 L6 20 Z" fill="${vessel.color}" stroke="#0d0d0d" stroke-width="1.2" stroke-linejoin="round"/>` +
      `</svg></div>`,
  });
}

function renderMap() {
  trackLayer.clearLayers();
  dotLayer.clearLayers();
  markerLayer.clearLayers();
  markersByMmsi.clear();

  const bounds = [];
  for (const vessel of state.vessels) {
    const latlngs = vessel.track.map((p) => [p.lat, p.lon]);
    bounds.push(...latlngs);
    const selected = vessel.mmsi === state.selected;

    if (latlngs.length > 1) {
      trackLayer.addLayer(L.polyline(latlngs, {
        color: vessel.color,
        weight: selected ? 3 : 2,
        opacity: selected ? 0.95 : 0.65,
      }));
      for (const p of vessel.track.slice(0, -1)) {
        dotLayer.addLayer(
          L.circleMarker([p.lat, p.lon], {
            radius: 3, color: vessel.color, weight: 1, fillOpacity: 0.85, fillColor: vessel.color,
          }).bindTooltip(`${escapeHtml(vessel.name)} · ${p.time} · ${fmtSog(p.sog)}`)
        );
      }
    }

    const marker = L.marker([vessel.latest.lat, vessel.latest.lon], {
      icon: shipIcon(vessel, selected),
      zIndexOffset: selected ? 1000 : 0,
    })
      .bindTooltip(`<strong>${escapeHtml(vessel.name)}</strong> · ${fmtSog(vessel.latest.sog)} · ${fmtAge(liveAge(vessel))}`)
      .on("click", () => selectVessel(vessel.mmsi));
    markerLayer.addLayer(marker);
    markersByMmsi.set(vessel.mmsi, marker);
  }

  if (bounds.length && (!state.hasFitted || state.refitNext)) {
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 13 });
    state.hasFitted = true;
    state.refitNext = false;
  }
}

function fitAll() {
  const bounds = [];
  for (const vessel of state.vessels) for (const p of vessel.track) bounds.push([p.lat, p.lon]);
  if (bounds.length) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 13 });
}

/* ------------------------------ vessel list ----------------------------- */
function visibleVessels() {
  const q = state.search.trim().toLowerCase();
  let list = state.vessels;
  if (q) {
    list = list.filter((v) =>
      v.name.toLowerCase().includes(q) || String(v.mmsi).includes(q));
  }
  const sorters = {
    latest: (a, b) => a.latest.age_seconds - b.latest.age_seconds,
    name: (a, b) => a.name.localeCompare(b.name),
    speed: (a, b) => (b.latest.sog ?? -1) - (a.latest.sog ?? -1),
    reports: (a, b) => b.reports - a.reports,
  };
  return [...list].sort(sorters[state.sortBy] || sorters.latest);
}

function renderList() {
  const listEl = $("vesselList");
  const vessels = visibleVessels();
  $("listCount").textContent =
    vessels.length === state.vessels.length
      ? `${vessels.length} vessel${vessels.length === 1 ? "" : "s"}`
      : `${vessels.length} of ${state.vessels.length} vessels`;

  listEl.textContent = "";
  if (!vessels.length) {
    const empty = document.createElement("li");
    empty.className = "vessel-empty";
    empty.textContent = state.vessels.length ? "No vessels match this search." : "No vessels in the current view.";
    listEl.appendChild(empty);
    return;
  }

  const frag = document.createDocumentFragment();
  for (const vessel of vessels) {
    const li = document.createElement("li");
    li.className = "vessel-row" + (vessel.mmsi === state.selected ? " selected" : "");
    li.dataset.mmsi = vessel.mmsi;
    li.innerHTML =
      `<span class="vessel-swatch" style="background:${vessel.color}"></span>` +
      `<span class="vessel-main">` +
      `<span class="vessel-name"></span>` +
      `<span class="vessel-mmsi">${vessel.mmsi}</span>` +
      `</span>` +
      `<span class="vessel-side">` +
      `<div class="vessel-speed">${fmtSog(vessel.latest.sog)}</div>` +
      `<div class="vessel-age">${fmtAge(liveAge(vessel))}</div>` +
      `</span>`;
    li.querySelector(".vessel-name").textContent = vessel.name;
    li.addEventListener("click", () => selectVessel(vessel.mmsi, { fly: true }));
    frag.appendChild(li);
  }
  listEl.appendChild(frag);
}

/* ------------------------------ detail panel ---------------------------- */
function selectedVessel() {
  return state.vessels.find((v) => v.mmsi === state.selected) || null;
}

function selectVessel(mmsi, opts = {}) {
  state.selected = state.selected === mmsi && !opts.fly ? null : mmsi;
  renderMap();
  renderList();
  renderDetail();
  const vessel = selectedVessel();
  if (vessel && opts.fly) {
    map.flyTo([vessel.latest.lat, vessel.latest.lon], Math.max(map.getZoom(), 12), { duration: 0.6 });
  }
}

function clearSelection() {
  if (state.selected == null) return;
  state.selected = null;
  renderMap();
  renderList();
  renderDetail();
}

function renderDetail() {
  const vessel = selectedVessel();
  const panel = $("detail");
  if (!vessel) { panel.hidden = true; return; }
  const l = vessel.latest;
  $("dSwatch").style.background = vessel.color;
  $("dName").textContent = vessel.name;
  $("dMmsi").textContent = "MMSI " + vessel.mmsi;
  $("dPos").textContent = l.lat.toFixed(5) + ", " + l.lon.toFixed(5);
  $("dTime").textContent = l.time + " (" + fmtAge(liveAge(vessel)) + ")";
  $("dSog").textContent = fmtSog(l.sog);
  $("dCog").textContent = fmtCog(l.cog);
  $("dHeading").textContent = fmtHeading(l.heading);
  $("dNav").textContent = l.nav_text;
  $("dReports").textContent = vessel.reports;
  $("dFirst").textContent = vessel.first_seen;
  $("dSource").textContent = l.source || "unknown";
  panel.hidden = false;
}

/* --------------------------------- KPIs --------------------------------- */
function renderKpis() {
  $("kpiVessels").textContent = state.stats ? state.stats.vessels : "–";
  $("kpiReports").textContent = state.stats ? state.stats.reports : "–";
  const newest = state.vessels.reduce(
    (best, v) => (best == null || v.latest.age_seconds < best ? v.latest.age_seconds : best), null);
  $("kpiUpdated").textContent = newest == null ? "–" : fmtAge(newest);
  const badge = $("filtersBadge");
  const n = filtersActiveCount();
  badge.hidden = n === 0;
  badge.textContent = n;
}

function renderSources() {
  const select = $("fSource");
  const current = state.filters.source;
  select.textContent = "";
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "All sources";
  select.appendChild(all);
  for (const src of state.sources) {
    const opt = document.createElement("option");
    opt.value = src;
    opt.textContent = src;
    select.appendChild(opt);
  }
  select.value = current;
  if (select.value !== current) select.value = "";
}

/* -------------------------------- filters ------------------------------- */
function readFilterInputs() {
  state.filters.ship_names = $("fShipNames").value.trim();
  state.filters.mmsi = $("fMmsi").value.trim();
  state.filters.source = $("fSource").value;
  state.filters.start = $("fStart").value;
  state.filters.end = $("fEnd").value;
}

function writeFilterInputs() {
  $("fShipNames").value = state.filters.ship_names;
  $("fMmsi").value = state.filters.mmsi;
  $("fSource").value = state.filters.source;
  $("fStart").value = state.filters.start;
  $("fEnd").value = state.filters.end;
}

function applyFilters() {
  readFilterInputs();
  syncUrl();
  state.refitNext = true;
  setStatus("connecting", "Loading");
  fetchData();
}

function resetFilters() {
  for (const key of Object.keys(state.filters)) state.filters[key] = "";
  writeFilterInputs();
  document.querySelectorAll("#quickChips button").forEach((b) => b.classList.remove("active"));
  applyFilters();
}

function setQuickRange(minutes, button) {
  document.querySelectorAll("#quickChips button").forEach((b) => b.classList.remove("active"));
  if (button) button.classList.add("active");
  if (!minutes) {
    $("fStart").value = "";
    $("fEnd").value = "";
  } else {
    $("fStart").value = toLocalInput(new Date(Date.now() - minutes * 60000));
    $("fEnd").value = "";
  }
  applyFilters();
}

/* --------------------------------- theme -------------------------------- */
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("console-theme", theme);
  if (map) applyTiles();
}

/* ---------------------------------- init -------------------------------- */
function bindEvents() {
  $("applyBtn").addEventListener("click", applyFilters);
  $("resetBtn").addEventListener("click", resetFilters);
  document.querySelectorAll("#quickChips button").forEach((button) => {
    button.addEventListener("click", () => setQuickRange(Number(button.dataset.mins) || 0, button));
  });
  ["fShipNames", "fMmsi"].forEach((id) => {
    $(id).addEventListener("keydown", (e) => { if (e.key === "Enter") applyFilters(); });
  });

  $("search").addEventListener("input", (e) => { state.search = e.target.value; renderList(); });
  $("sortBy").addEventListener("change", (e) => { state.sortBy = e.target.value; renderList(); });

  $("refreshInterval").addEventListener("change", (e) => {
    state.intervalSec = Number(e.target.value);
    localStorage.setItem("console-interval", e.target.value);
    scheduleNext();
  });
  $("pauseBtn").addEventListener("click", () => {
    state.paused = !state.paused;
    $("pauseBtn").textContent = state.paused ? "Resume" : "Pause";
    setStatus(state.paused ? "paused" : "live", state.paused ? "Paused" : "Live");
    if (!state.paused) fetchData(); else clearTimeout(refreshTimer);
  });
  $("exportBtn").addEventListener("click", () => {
    window.location.href = "/api/export.csv?" + filtersToQuery().toString();
  });
  $("themeBtn").addEventListener("click", () => {
    applyTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light");
  });

  $("fitBtn").addEventListener("click", fitAll);
  $("detailClose").addEventListener("click", clearSelection);
  $("focusVessel").addEventListener("click", () => {
    const vessel = selectedVessel();
    if (vessel) map.flyTo([vessel.latest.lat, vessel.latest.lon], Math.max(map.getZoom(), 13), { duration: 0.6 });
  });
  $("copyCoords").addEventListener("click", async () => {
    const vessel = selectedVessel();
    if (!vessel) return;
    const text = vessel.latest.lat.toFixed(5) + ", " + vessel.latest.lon.toFixed(5);
    try {
      await navigator.clipboard.writeText(text);
      toast("Coordinates copied: " + text, "info");
    } catch {
      toast("Could not access the clipboard");
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement.tagName !== "INPUT") {
      e.preventDefault();
      $("search").focus();
    }
    if (e.key === "Escape") clearSelection();
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && !state.paused) fetchData();
  });
}

function init() {
  applyTheme(localStorage.getItem("console-theme") || "dark");
  const savedInterval = localStorage.getItem("console-interval");
  if (savedInterval != null) {
    state.intervalSec = Number(savedInterval);
    $("refreshInterval").value = savedInterval;
  }

  loadFiltersFromUrl();
  writeFilterInputs();
  if (filtersActiveCount()) $("filtersBox").open = true;

  initMap();
  bindEvents();
  showOverlay("Connecting…", "Fetching live vessel data.");
  fetchData();

  // keep relative ages ticking between fetches
  ageTimer = setInterval(() => {
    if (state.vessels.length) { renderList(); renderKpis(); if (state.selected != null) renderDetail(); }
  }, 10000);
}

init();
