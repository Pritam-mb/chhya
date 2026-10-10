// ===================================================================
// Chhaya (ছায়া) — Paper Map & Agent Client (visual pass, logic untouched)
// ===================================================================

const KOLKATA_CENTER = [88.3530, 22.5510]; // Park Street & Camac Street, Kolkata
let map = null;
let currentRouteData = null;
let currentTripData = null;
let currentTripCode = "parkst-club";
let currentMode = "club";
let isPlaying = false;
let playInterval = null;
let currentBriefingText = "";
let loadedPOIs = [];
let poiMarkers = [];
let restStopMarkers = [];
let cardMarkers = [];
let originMarker = null;
let destinationMarker = null;
let walkingDotMarker = null;
let walkingAnimationId = null;
let currentCheckinIndex = 1;
let landmarksVisible = true;
let streetCorrections = {};
let accuracyData = null;
let currentSegments = [];
// Which ticket the walker picked in Shade Studio: "shade" (guided, default)
// or "shortest" (direct baseline preview — guided stops still follow shade).
let activePathChoice = "shade";
// Hand-picked map points ("lat,lon" strings the router resolves), card place,
// GPS tracking, and trip chat polling state.
let pickedOrigin = null;
let pickedDest = null;
let cardPlace = null;
let cardPhotoData = null;
let gpsMarker = null;
let gpsWatchId = null;
let lastChatId = 0;
let chatTimer = null;
let currentActivePage = "feed";
let userGrassPoints = 40;
let userSimulatedCoords = [88.3526, 22.5532];
let simStepIndex = 0;
let userWalkerMarker = null;

// User Identity & Registration State
let userWalkerName = "Pritam";
let isUserRegistered = false;
let pendingEmbarkTripCode = null;
let isAutoWalking = false;
let autoWalkInterval = null;
let deviceGpsActive = false;
try {
  const saved = localStorage.getItem("chhaya_walker_name");
  if (saved) {
    userWalkerName = saved;
    isUserRegistered = true;
  }
} catch (_) {}

// Bengali/English UI toggle (locale file; dynamic route numbers stay as computed)
let currentLang = "en";
let LOCALES = {};
try { currentLang = localStorage.getItem("chhaya-lang") || "en"; } catch (_) {}

// Initialize Application
document.addEventListener("DOMContentLoaded", async () => {
  initMap();
  setupSlider();
  setupForm();
  setupChips();
  setupVoice();
  setupQuickSelectors();
  setupModeSwitcher();
  setupHudTabs();
  setupModals();
  setupWalkActions();
  setupShadeTaps();
  setupWalkerRegistration();
  setupFixedRoutesStudio();
  setupMultiPageNav();
  setupGroupDashboard();
  setupRealTimeLocationTracker();
  setupSimulatorControls();
  setupStoryCelebrationModal();
  setupFeedPage();
  setupPassportPage();
  setupTrailEnroll();
  setupMapPost();
  setupPathChoice();
  startGroupPolling();
  setupRadarActions();
  setupQrActions();
  loadBestWindowWidget();
  loadPOIs();
  checkUrlRouteOnLoad();
  loadLocale();

  // Trigger initial demo scenario after map renders
  setTimeout(() => {
    switchTripGroup(currentTripCode || "parkst-club");
  }, 800);
});

// 1. Map Initialization — paper-toned basemap (warm grey, sage water, no blue)
function initMap() {
  map = new maplibregl.Map({
    container: "map",
    style: {
      version: 8,
      sources: {
        "paper-base": {
          type: "raster",
          tiles: [
            "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
          ],
          tileSize: 256,
          attribution: "&copy; Esri &copy; OpenStreetMap contributors"
        },
        "paper-labels": {
          type: "raster",
          tiles: [
            "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
          ],
          tileSize: 256
        }
      },
      layers: [
        { id: "paper-wash", type: "background", paint: { "background-color": "#F4E9D4" } },
        { id: "paper-base-layer", type: "raster", source: "paper-base", minzoom: 0, maxzoom: 20, paint: { "raster-opacity": 0.92, "raster-hue-rotate": -12, "raster-saturation": 0.25 } },
        { id: "paper-labels-layer", type: "raster", source: "paper-labels", minzoom: 0, maxzoom: 20, paint: { "raster-opacity": 0.9 } }
      ]
    },
    center: KOLKATA_CENTER,
    zoom: 16.2,
    pitch: 42,
    bearing: -15,
    antialias: true
  });

  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-left");

  map.on("load", async () => {
    await addBuildingsLayer();
    addShadowsLayer();
    addRouteLayers();
    updateShadowsForTime("15:00");
    setupMapPick();
    setupLocate();
  });
}

// Tap the map to pick a point: start here, end here, or leave a card here.
// Picks outside the Park St pack snap to the nearest lane for routing;
// cards and chat work at the exact tapped spot, map-wide.
function setupMapPick() {
  if (!map || map.__pickWired) return;
  map.__pickWired = true;
  map.on("click", (e) => {
    if (e.originalEvent && e.originalEvent.target &&
        e.originalEvent.target.closest(".maplibregl-marker, .maplibregl-popup, .maplibregl-ctrl")) return;
    const lat = +e.lngLat.lat.toFixed(5), lon = +e.lngLat.lng.toFixed(5);
    const label = `${lat}, ${lon}`;
    // Feed the Live Trail → Post tab preview on every tap (during a journey).
    try { window.__setMappostPicked?.(lat, lon); } catch (_) {}
    const html = document.createElement("div");
    html.innerHTML = `
      <div class="popup-landmark-title">Pinned point</div>
      <div class="popup-landmark-addr">${label} · snaps to nearest lane for routing</div>
      <div class="popup-actions" style="flex-wrap:wrap;">
        <button class="btn-popup" data-act="orig">Start here</button>
        <button class="btn-popup" data-act="dest">End here</button>
        <button class="btn-popup" data-act="card">Leave card</button>
      </div>`;
    const popup = new maplibregl.Popup({ offset: 14, closeButton: true })
      .setLngLat(e.lngLat).setDOMContent(html).addTo(map);
    html.querySelectorAll("button").forEach(b => b.addEventListener("click", () => {
      const act = b.getAttribute("data-act");
      const ll = `${lat},${lon}`;
      if (act === "orig") { pickedOrigin = ll; startPickedRoute(); }
      if (act === "dest") { pickedDest = ll; startPickedRoute(); }
      if (act === "card") { openCardAt(lat, lon, label); }
      popup.remove();
    }));
  });
}

function startPickedRoute() {
  const oSel = document.getElementById("origin-select").value;
  const dSel = document.getElementById("destination-select").value;
  const orig = oSel || pickedOrigin, dest = dSel || pickedDest;
  if (orig && dest && orig !== dest) {
    loadDirectRoute(orig, dest, document.getElementById("time-display").textContent || "15:00");
  }
}

function openCardAt(lat, lon, label) {
  cardPlace = { lat, lon, label: label || `${lat}, ${lon}` };
  const lbl = document.getElementById("card-coords-label");
  if (lbl) lbl.textContent = cardPlace.label;
  const modal = document.getElementById("radar-modal");
  if (modal) {
    modal.classList.remove("hidden");
    document.getElementById("radar-tab-leave")?.click();
  }
}

// My-location dot + follow tracking (browser geolocation, opt-in per tap)
function setupLocate() {
  const btn = document.getElementById("locate-btn");
  if (!btn || !("geolocation" in navigator)) {
    if (btn) { btn.disabled = true; btn.title = "Geolocation not available"; }
    return;
  }
  btn.addEventListener("click", () => {
    if (gpsWatchId !== null) {
      navigator.geolocation.clearWatch(gpsWatchId);
      gpsWatchId = null;
      btn.classList.remove("active");
      btn.textContent = "◎ Locate";
      return;
    }
    btn.textContent = "◎ Locating…";
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        showGps(pos.coords);
        map.flyTo({ center: [pos.coords.longitude, pos.coords.latitude], zoom: 16.5 });
        gpsWatchId = navigator.geolocation.watchPosition(showGps, null,
          { enableHighAccuracy: true, maximumAge: 10000 });
        btn.classList.add("active");
        btn.textContent = "◉ Tracking (tap to stop)";
      },
      () => { btn.textContent = "◎ Locate"; },
      { enableHighAccuracy: true, timeout: 12000 }
    );
  });
}

function showGps(coords) {
  const ll = [coords.longitude, coords.latitude];
  if (!gpsMarker) {
    const el = document.createElement("div");
    el.className = "gps-dot";
    el.title = "You are here";
    gpsMarker = new maplibregl.Marker({ element: el }).setLngLat(ll).addTo(map);
  } else {
    gpsMarker.setLngLat(ll);
  }
  shareLiveSpot(coords.latitude, coords.longitude);
}

// Shares my spot with the group (only while GPS tracking is on = opt-in),
// throttled to one post per 15 s.
let lastSpotPost = 0;
async function shareLiveSpot(lat, lon) {
  const now = Date.now();
  if (now - lastSpotPost < 15000) return;
  lastSpotPost = now;
  const walker = ((document.getElementById("walker-name-input")?.value) || "Walker").trim();
  try {
    await fetch(`/api/trip/${currentTripCode}/position`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ walker, lat, lon }),
    });
  } catch (_) {}
}

// Group dashboard: live member spots on the map + grass-points table.
let memberMarkers = [];
let groupTimer = null;
function startGroupPolling() {
  if (!groupTimer) {
    groupTimer = setInterval(() => {
      const modal = document.getElementById("walk-modal");
      if (modal && !modal.classList.contains("hidden")) pollGroup(true);
    }, 10000);
  }
}

async function pollGroup(quiet) {
  const box = document.getElementById("group-members");
  const pts = document.getElementById("group-points");
  try {
    const [posRes, ptsRes] = await Promise.all([
      fetch(`/api/trip/${currentTripCode}/positions`),
      fetch(`/api/trip/${currentTripCode}/points`),
    ]);
    const members = (await posRes.json()).members || [];
    const board = (await ptsRes.json()).leaderboard || [];
    renderMemberMarkers(members);
    if (box) {
      box.innerHTML = members.length ? "" : `<p style="font-size:13px;">No live spots yet — members appear here when they tap ◎ Locate.</p>`;
      const checkins = await getCheckinWalkers();
      members.forEach(m => {
        const row = document.createElement("div");
        row.className = "member-row";
        const seen = m.stale ? "stale spot" : "live now";
        const atStop = checkins[m.walker] ? ` · at Stop ${checkins[m.walker]}` : "";
        row.innerHTML = `<strong>${m.walker}</strong><span style="font-family:var(--font-mono);font-size:11px;">${seen}${atStop}</span>`;
        box.appendChild(row);
      });
    }
    if (pts) {
      pts.innerHTML = board.length ? "" : `<p style="font-size:13px;">No points yet — tap a checkpoint or unlock a story.</p>`;
      board.forEach(b => {
        const row = document.createElement("div");
        row.className = "points-row";
        row.innerHTML = `<span>🌱 ${b.walker}</span><strong>${b.points} pts · ${b.events} acts</strong>`;
        pts.appendChild(row);
      });
    }
  } catch (_) {
    if (!quiet && box) box.innerHTML = `<p style="font-size:13px;">Dashboard offline.</p>`;
  }
}

let checkinCache = {};
async function getCheckinWalkers() {
  try {
    const res = await fetch(`/api/trip/${currentTripCode}`);
    const data = await res.json();
    const map = {};
    (data.checkins || []).forEach(c => { map[c.walker] = Math.max(map[c.walker] || 0, c.stop_index); });
    checkinCache = map;
    return map;
  } catch (_) { return checkinCache; }
}

function renderMemberMarkers(members) {
  memberMarkers.forEach(m => m.remove());
  memberMarkers = [];
  (members || []).forEach(m => {
    if (m.stale) return;
    const el = document.createElement("div");
    el.className = "member-pin";
    el.textContent = (m.walker || "?").trim().slice(0, 2).toUpperCase();
    el.title = m.walker;
    memberMarkers.push(new maplibregl.Marker({ element: el }).setLngLat([m.lon, m.lat]).addTo(map));
  });
}

// 2. Add Building Layer
async function addBuildingsLayer() {
  try {
    const resp = await fetch("/static/data/buildings.geojson");
    const data = await resp.json();
    
    map.addSource("buildings-data", {
      type: "geojson",
      data: data
    });

    // 3D Extruded Buildings — clay tones, warmed by real sun elevation
    map.addLayer({
      id: "buildings-3d",
      type: "fill-extrusion",
      source: "buildings-data",
      paint: {
        "fill-extrusion-color": [
          "case",
          ["boolean", ["feature-state", "hover"], false],
          "#D2410D",
          "#B8553A"
        ],
        "fill-extrusion-height": ["get", "height"],
        "fill-extrusion-base": 0,
        "fill-extrusion-opacity": 0.92
      }
    });

    // Building Roof Borders — ink rules, print feel
    map.addLayer({
      id: "buildings-outline",
      type: "line",
      source: "buildings-data",
      paint: {
        "line-color": "#2A1F17",
        "line-width": 1,
        "line-opacity": 0.55
      }
    });
  } catch (e) {
    console.warn("Could not load local buildings layer:", e);
  }
}

// 3. Add Dynamic Building Shadows Layer — ink-green hatch, no blur
function ensureHatchPattern() {
  if (map.hasImage("shade-hatch")) return;
  const c = document.createElement("canvas");
  c.width = 16; c.height = 16;
  const g = c.getContext("2d");
  g.clearRect(0, 0, 16, 16);
  g.strokeStyle = "#1F4D3A"; g.lineWidth = 2.4;
  g.beginPath(); g.moveTo(-4, 12); g.lineTo(12, -4); g.stroke();
  g.beginPath(); g.moveTo(4, 20); g.lineTo(20, 4); g.stroke();
  map.addImage("shade-hatch", { width: 16, height: 16, data: g.getImageData(0, 0, 16, 16).data }, { pixelRatio: 2 });
}
function addShadowsLayer() {
  ensureHatchPattern();
  map.addSource("shadows-data", {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] }
  });

  // flat ink-green wash under the hatch
  map.addLayer(
    {
      id: "building-shadows",
      type: "fill",
      source: "shadows-data",
      paint: { "fill-color": "#1F4D3A", "fill-opacity": 0.26 }
    },
    "buildings-3d" // Render under 3D buildings
  );
  // hatched pattern fill (semi-transparent, no blur)
  map.addLayer(
    {
      id: "building-shadows-hatch",
      type: "fill",
      source: "shadows-data",
      paint: { "fill-pattern": "shade-hatch", "fill-opacity": 0.55 }
    },
    "buildings-3d"
  );

  map.addLayer(
    {
      id: "building-shadows-edge",
      type: "line",
      source: "shadows-data",
      paint: {
        "line-color": "#1F4D3A",
        "line-width": 1.5,
        "line-opacity": 0.6
      }
    },
    "buildings-3d"
  );
}

// 4. Add Dual Route Layers — shade=solid green, sun=dashed vermilion (colour-blind safe)
function addRouteLayers() {
  // Shortest path baseline (ink dashed ticket line)
  map.addSource("shortest-route-data", {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] }
  });

  map.addLayer({
    id: "shortest-route-line",
    type: "line",
    source: "shortest-route-data",
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": "#2A1F17",
      "line-width": 3,
      "line-dasharray": [1.5, 2.5],
      "line-opacity": 0.75
    }
  });

  // Shade Route (split into shaded vs exposed segments)
  map.addSource("shade-route-data", {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] }
  });

  // Hard paper casing (no blur, no glow)
  map.addLayer({
    id: "shade-route-casing",
    type: "line",
    source: "shade-route-data",
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": "#FBF7EE",
      "line-width": 9,
      "line-opacity": 0.95
    }
  });

  // Shaded stretches — solid thick green
  map.addLayer({
    id: "shade-route-shade",
    type: "line",
    source: "shade-route-data",
    filter: ["==", ["get", "is_shaded"], true],
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": "#1F4D3A", "line-width": 6 }
  });

  // Exposed stretches — dashed vermilion/marigold (style encodes exposure too)
  map.addLayer({
    id: "shade-route-sun",
    type: "line",
    source: "shade-route-data",
    filter: ["==", ["get", "is_shaded"], false],
    layout: { "line-cap": "butt", "line-join": "round" },
    paint: {
      "line-color": "#C8321E",
      "line-width": 5,
      "line-dasharray": [2.2, 1.4]
    }
  });
}

// 5. Load POIs & Place Glass Markers on Map
async function loadPOIs() {
  try {
    const res = await fetch("/pois");
    const data = await res.json();
    loadedPOIs = data.pois || [];

    // Update legend badge
    const badge = document.getElementById("poi-count-badge");
    if (badge) badge.textContent = loadedPOIs.length;

    // Populate quick dropdowns
    const origSel = document.getElementById("origin-select");
    const destSel = document.getElementById("destination-select");
    const annOrigSel = document.getElementById("ann-origin-select");
    const annDestSel = document.getElementById("ann-dest-select");
    
    if (origSel && destSel) {
      origSel.innerHTML = '<option value="">Select origin...</option>';
      destSel.innerHTML = '<option value="">Select destination...</option>';

      loadedPOIs.forEach((p) => {
        const opt1 = document.createElement("option");
        opt1.value = p.id;
        opt1.textContent = p.name;
        origSel.appendChild(opt1);

        const opt2 = document.createElement("option");
        opt2.value = p.id;
        opt2.textContent = p.name;
        destSel.appendChild(opt2);
      });

      // Default values
      if (loadedPOIs.length >= 2) {
        origSel.value = loadedPOIs[3]?.id || loadedPOIs[0].id; // Flurys
        destSel.value = loadedPOIs[5]?.id || loadedPOIs[1].id; // Camac Square
      }
    }

    if (annOrigSel && annDestSel) {
      annOrigSel.innerHTML = '<option value="">Select origin...</option>';
      annDestSel.innerHTML = '<option value="">Select destination...</option>';

      loadedPOIs.forEach((p) => {
        const opt1 = document.createElement("option");
        opt1.value = p.id;
        opt1.textContent = p.name;
        annOrigSel.appendChild(opt1);

        const opt2 = document.createElement("option");
        opt2.value = p.id;
        opt2.textContent = p.name;
        annDestSel.appendChild(opt2);
      });

      if (loadedPOIs.length >= 2) {
        annOrigSel.value = loadedPOIs[0].id;
        annDestSel.value = loadedPOIs[loadedPOIs.length - 1].id;
      }
    }

    // Place POI markers on map
    renderPOIMarkers();

    // Setup toggle button in legend
    const toggleBtn = document.getElementById("toggle-landmarks-btn");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        landmarksVisible = !landmarksVisible;
        poiMarkers.forEach(m => {
          m.getElement().style.display = landmarksVisible ? "flex" : "none";
        });
        toggleBtn.style.opacity = landmarksVisible ? "1" : "0.5";
      });
    }
  } catch (err) {
    console.error("Failed to load POIs:", err);
  }
}

function getPOIEmoji(category) {
  switch (category) {
    case "clinic": return "🏥";
    case "landmark": return "☕";
    case "shop": return "📚";
    case "commercial": return "🏢";
    case "pharmacy": return "💊";
    case "home": return "🏠";
    default: return "📍";
  }
}

function renderPOIMarkers() {
  // Clear existing
  poiMarkers.forEach(m => m.remove());
  poiMarkers = [];

  loadedPOIs.forEach(poi => {
    const el = document.createElement("div");
    el.className = "poi-marker";
    el.innerHTML = getPOIEmoji(poi.category);
    el.title = poi.name;

    const popupHTML = `
      <div class="popup-content">
        <h4 class="popup-landmark-title">${poi.name}</h4>
        <p class="popup-landmark-addr">${poi.address || ""}</p>
        <div class="popup-actions">
          <button class="btn-popup set-origin-btn" data-id="${poi.id}" data-name="${poi.name}">Start Here</button>
          <button class="btn-popup set-dest-btn" data-id="${poi.id}" data-name="${poi.name}">End Here</button>
        </div>
      </div>
    `;

    const popup = new maplibregl.Popup({ offset: 18, closeButton: true })
      .setHTML(popupHTML);

    const marker = new maplibregl.Marker({ element: el, anchor: "bottom", offset: [0, -6] })
      .setLngLat([poi.lon, poi.lat])
      .setPopup(popup)
      .addTo(map);

    // Bind popup actions after popup opens (POI landmarks)
    marker.getPopup().on("open", () => {
      const popupEl = marker.getPopup().getElement();
      if (!popupEl) return;

      const origBtn = popupEl.querySelector(".set-origin-btn");
      const destBtn = popupEl.querySelector(".set-dest-btn");

      if (origBtn) {
        origBtn.onclick = () => {
          const sel = document.getElementById("origin-select");
          if (sel) sel.value = poi.id;
          marker.getPopup().remove();
          checkAndTriggerQuickRoute();
        };
      }
      if (destBtn) {
        destBtn.onclick = () => {
          const sel = document.getElementById("destination-select");
          if (sel) destSel = poi.id;
          const dSel = document.getElementById("destination-select");
          if (dSel) dSel.value = poi.id;
          marker.getPopup().remove();
          checkAndTriggerQuickRoute();
        };
      }
    });

    poiMarkers.push(marker);
  });
}

function checkAndTriggerQuickRoute() {
  const orig = document.getElementById("origin-select").value;
  const dest = document.getElementById("destination-select").value;
  if (orig && dest && orig !== dest) {
    const time = document.getElementById("time-display").textContent || "15:00";
    loadDirectRoute(orig, dest, time);
  }
}

// Setup Quick Dropdown Selector Buttons (falls back to hand-picked points)
function setupQuickSelectors() {
  const btn = document.getElementById("quick-route-btn");
  if (btn) {
    btn.addEventListener("click", () => {
      const orig = document.getElementById("origin-select").value || pickedOrigin;
      const dest = document.getElementById("destination-select").value || pickedDest;
      if (!orig || !dest) {
        alert("Pick an origin and destination: use the dropdowns or tap the map.");
        return;
      }
      if (orig === dest) {
        alert("Origin and Destination cannot be the same landmark.");
        return;
      }
      const time = document.getElementById("time-display").textContent || "15:00";
      loadDirectRoute(orig, dest, time);
    });
  }
}

// 6. Update Building Shadows from API
async function updateShadowsForTime(timeStr) {
  try {
    const res = await fetch(`/shadows?time=${encodeURIComponent(timeStr)}`);
    const geojson = await res.json();
    
    if (map && map.getSource("shadows-data")) {
      map.getSource("shadows-data").setData(geojson);
    }

    // Update solar badge
    const props = geojson.properties || {};
    const elev = props.solar_elevation ?? 30.2;
    const factor = props.shadow_factor ?? 1.72;
    const azim = props.solar_azimuth ?? 248.7;
    const badge = document.getElementById("solar-badge");
    if (badge) {
      badge.textContent = `Solar: ${elev}° (${factor}x shadow)`;
    }

    // Check High Noon honesty alert (> 55 degrees)
    const noonAlert = document.getElementById("noon-alert");
    if (noonAlert) {
      if (elev > 55.0) {
        noonAlert.classList.remove("hidden");
      } else {
        noonAlert.classList.add("hidden");
      }
    }
    try { updateSundial(timeStr); modulateBuildings(elev, azim); } catch (_) {}
  } catch (err) {
    console.error("Failed to update shadows:", err);
  }
}

// 7. Daylight Slider Setup
function setupSlider() {
  const slider = document.getElementById("time-slider");
  const timeDisplay = document.getElementById("time-display");
  const playBtn = document.getElementById("play-btn");

  function getStepTime(val) {
    const hr = Math.floor(val / 2);
    const mn = (val % 2 === 1) ? "30" : "00";
    return `${hr.toString().padStart(2, "0")}:${mn}`;
  }

  slider.addEventListener("input", (e) => {
    const timeStr = getStepTime(parseInt(e.target.value));
    timeDisplay.textContent = timeStr;
    updateShadowsForTime(timeStr);
    updateActiveTick(parseInt(e.target.value));

    // If active route, re-route with new time
    if (currentRouteData) {
      recomputeActiveRoute(timeStr);
    }
  });

  // Clickable tick buttons
  const tickBtns = document.querySelectorAll(".tick-btn");
  tickBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const step = parseInt(btn.getAttribute("data-step"));
      slider.value = step;
      const timeStr = getStepTime(step);
      timeDisplay.textContent = timeStr;
      updateShadowsForTime(timeStr);
      updateActiveTick(step);
      if (currentRouteData) {
        recomputeActiveRoute(timeStr);
      }
    });
  });

  // Play / Pause auto sweep
  playBtn.addEventListener("click", () => {
    if (isPlaying) {
      stopAutoSweep();
    } else {
      startAutoSweep();
    }
  });

  function startAutoSweep() {
    isPlaying = true;
    playBtn.innerHTML = `
      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
        <rect x="6" y="4" width="4" height="16"/>
        <rect x="14" y="4" width="4" height="16"/>
      </svg>
    `;
    playInterval = setInterval(() => {
      let cur = parseInt(slider.value);
      cur += 1;
      if (cur > 36) cur = 12; // loop 6 AM to 6 PM
      slider.value = cur;
      const t = getStepTime(cur);
      timeDisplay.textContent = t;
      updateShadowsForTime(t);
      updateActiveTick(cur);
      if (currentRouteData) {
        recomputeActiveRoute(t);
      }
    }, 1400);
  }

  function stopAutoSweep() {
    isPlaying = false;
    clearInterval(playInterval);
    playBtn.innerHTML = `
      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
        <polygon points="5 3 19 12 5 21 5 3"/>
      </svg>
    `;
  }

  const noonAlertClose = document.getElementById("noon-alert-close");
  if (noonAlertClose) {
    noonAlertClose.addEventListener("click", () => {
      document.getElementById("noon-alert").classList.add("hidden");
    });
  }
}

function updateActiveTick(step) {
  document.querySelectorAll(".tick-btn").forEach(btn => {
    const s = parseInt(btn.getAttribute("data-step"));
    if (s === step) {
      btn.classList.add("tick-active");
    } else {
      btn.classList.remove("tick-active");
    }
  });
}

// 8. Form Submission & Agent Call
function setupForm() {
  const form = document.getElementById("agent-form");
  const input = document.getElementById("prompt-input");

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const query = input.value.trim();
    if (query) {
      loadRoute(query);
    }
  });

  const hudClose = document.getElementById("hud-close");
  if (hudClose) {
    hudClose.addEventListener("click", () => {
      document.getElementById("route-hud").classList.add("hidden");
    });
  }
}

// 9. Preset Chips
function setupChips() {
  const chips = document.querySelectorAll(".chip");
  chips.forEach((c) => {
    c.addEventListener("click", () => {
      chips.forEach((x) => x.classList.remove("chip-active"));
      c.classList.add("chip-active");
      const prompt = c.getAttribute("data-prompt");
      const mode = c.getAttribute("data-mode") || currentMode;
      document.getElementById("prompt-input").value = prompt;
      setAppMode(mode);
      loadRoute(prompt, null, mode);
    });
  });
}

// 10. Load Route via Master Plan API & Agent
async function loadRoute(promptText, overrideTime = null, modeOverride = null) {
  const submitBtn = document.getElementById("submit-btn");
  submitBtn.disabled = true;
  submitBtn.innerHTML = `<span>Planning in Shade...</span>`;

  try {
    const targetMode = modeOverride || currentMode;

    // First attempt Master Plan API Engine (Section 4, P0-P2)
    const planRes = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: promptText,
        mode: targetMode,
        earliest_time: overrideTime
      })
    });

    if (planRes.ok) {
      const planData = await planRes.json();
      if (planData.route_data && planData.route_data.shade_route) {
        renderMasterPlan(planData);
        return;
      }
    }

    // Fallback to /agent/chat
    const payload = { message: promptText };
    if (overrideTime) payload.depart_time = overrideTime;

    const res = await fetch("/agent/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    
    if (data.route_data) {
      renderRouteResult(data.route_data, data.reply);
    } else {
      const msg = data.reply || data.error || "Could not find a route in the demo area.";
      showClarificationPrompt(msg);
    }
  } catch (err) {
    console.error("Routing error:", err);
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = `
      <span>Route in Shade</span>
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M5 12h14M12 5l7 7-7 7"/>
      </svg>
    `;
  }
}

// 11. Direct Route Call by Landmark IDs
async function loadDirectRoute(originId, destinationId, timeStr) {
  const submitBtn = document.getElementById("submit-btn");
  submitBtn.disabled = true;
  submitBtn.innerHTML = `<span>Routing...</span>`;

  try {
    const res = await fetch("/route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        origin: originId,
        destination: destinationId,
        depart_time: timeStr || "15:00",
        sun_tolerance: "low",
        speed_kmh: 3.0
      })
    });
    const data = await res.json();
    if (data.shade_route) {
      renderRouteResult(data, data.trade_off_sentence);
    } else {
      alert("Route calculation failed: " + (data.detail || "Unknown error"));
    }
  } catch (err) {
    console.error("Direct route error:", err);
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = `
      <span>Route in Shade</span>
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M5 12h14M12 5l7 7-7 7"/>
      </svg>
    `;
  }
}

function showClarificationPrompt(msg) {
  const hud = document.getElementById("route-hud");
  hud.classList.remove("hidden");
  document.getElementById("hud-title").textContent = "Location Clarification";
  document.getElementById("tradeoff-text").textContent = msg;
  document.getElementById("saved-sun-mins").textContent = "—";
  document.getElementById("savings-subtitle").textContent = "Please select known landmarks from the dropdowns above";
}

// 12. Render Route Result
function renderRouteResult(routeData, agentReply) {
  currentRouteData = routeData;

  // Sync dropdown selectors with resolved locations
  const origSel = document.getElementById("origin-select");
  const destSel = document.getElementById("destination-select");
  if (origSel && routeData.origin?.id) origSel.value = routeData.origin.id;
  if (destSel && routeData.destination?.id) destSel.value = routeData.destination.id;

  // Sync slider with route depart time
  const [hr, mn] = routeData.depart_time.split(":").map(Number);
  const stepVal = hr * 2 + (mn >= 30 ? 1 : 0);
  const slider = document.getElementById("time-slider");
  if (slider) {
    slider.value = stepVal;
    document.getElementById("time-display").textContent = routeData.depart_time;
    updateActiveTick(stepVal);
  }
  updateShadowsForTime(routeData.depart_time);

  // Render Shaded Route Segments
  const segments = routeData.shade_route.segments || [];
  const shadeFeatures = segments.map((s, idx) => ({
    type: "Feature",
    id: `seg_${idx}`,
    properties: {
      is_shaded: s.is_shaded,
      exposure: s.exposure,
      length_m: s.length_m,
      name: s.name
    },
    geometry: {
      type: "LineString",
      coordinates: s.coordinates
    }
  }));

  if (map.getSource("shade-route-data")) {
    map.getSource("shade-route-data").setData({
      type: "FeatureCollection",
      features: shadeFeatures
    });
  }

  // Render Shortest Path Baseline
  const shortestCoords = routeData.shortest_route.coordinates || [];
  if (map.getSource("shortest-route-data")) {
    map.getSource("shortest-route-data").setData({
      type: "FeatureCollection",
      features: shortestCoords.length
        ? [{
            type: "Feature",
            properties: {},
            geometry: { type: "LineString", coordinates: shortestCoords }
          }]
        : []
      });
  }

  // Render Start & Destination custom endpoint markers
  updateEndpointMarkers(routeData);

  // Fit camera bounds to route
  if (routeData.shade_route.coordinates && routeData.shade_route.coordinates.length > 0) {
    const coords = routeData.shade_route.coordinates;
    const bounds = coords.reduce(
      (b, c) => b.extend(c),
      new maplibregl.LngLatBounds(coords[0], coords[0])
    );
    map.fitBounds(bounds, { padding: { top: 120, bottom: 120, left: 60, right: 400 }, duration: 1000 });
  }

  // Update HUD Cards
  const hud = document.getElementById("route-hud");
  hud.classList.remove("hidden");

  document.getElementById("hud-title").textContent = 
    `${routeData.origin.name} → ${routeData.destination.name}`;

  const saved = routeData.comparison.sun_minutes_saved;
  document.getElementById("saved-sun-mins").textContent = 
    saved > 0 ? `+${saved.toFixed(1)}` : "0.0";

  if (saved > 0) {
    document.getElementById("savings-subtitle").textContent = 
      `Shields you from ${saved.toFixed(1)} minutes of direct Kolkata sun!`;
  } else {
    document.getElementById("savings-subtitle").textContent = 
      "Direct lane is already naturally shielded by street buildings.";
  }

  // Shade Route Stats
  const shadeSunEl = document.getElementById("shade-sun-mins");
  const shadeTotalEl = document.getElementById("shade-total-mins");
  const shadeDistEl = document.getElementById("shade-dist");
  const shadeBarEl = document.getElementById("shade-bar");
  const shadePctEl = document.getElementById("shade-pct");

  if (shadeSunEl) shadeSunEl.textContent = `${routeData.shade_route.sun_minutes} mins`;
  if (shadeTotalEl) shadeTotalEl.textContent = `${routeData.shade_route.duration_minutes}`;
  if (shadeDistEl) shadeDistEl.textContent = `${Math.round(routeData.shade_route.distance_meters)}m`;
  if (shadeBarEl) shadeBarEl.style.width = `${routeData.shade_route.shade_percentage}%`;
  if (shadePctEl) shadePctEl.textContent = `${routeData.shade_route.shade_percentage}% shaded lanes`;

  // Shortest Route Stats
  const shortSunEl = document.getElementById("shortest-sun-mins");
  const shortTotalEl = document.getElementById("shortest-total-mins");
  const shortDistEl = document.getElementById("shortest-dist");
  const shortBarEl = document.getElementById("shortest-bar");
  const shortPctEl = document.getElementById("shortest-pct");

  if (shortSunEl) shortSunEl.textContent = `${routeData.shortest_route.sun_minutes} mins`;
  if (shortTotalEl) shortTotalEl.textContent = `${routeData.shortest_route.duration_minutes}`;
  if (shortDistEl) shortDistEl.textContent = `${Math.round(routeData.shortest_route.distance_meters)}m`;
  if (shortBarEl) shortBarEl.style.width = `${routeData.shortest_route.shade_percentage}%`;
  if (shortPctEl) shortPctEl.textContent = `${routeData.shortest_route.shade_percentage}% shaded`;

  // Trade-off explanation
  const tradeEl = document.getElementById("tradeoff-text");
  if (tradeEl) tradeEl.textContent = routeData.trade_off_sentence;

  // Render Street Segments list in HUD
  currentSegments = segments;
  renderSegmentsList(segments);

  // Voice briefing script
  currentBriefingText = `Walking from ${routeData.origin.name} to ${routeData.destination.name} at ${routeData.depart_time}. ${routeData.trade_off_sentence}`;
  const scriptEl = document.getElementById("voice-script");
  if (scriptEl) scriptEl.textContent = `"${currentBriefingText}"`;

  // Signature: sun-budget gauge + stamp + self-drawing route (visual only)
  try {
    updateSunGauge(routeData.shade_route.sun_minutes, routeData.comparison);
    const stamp = document.getElementById("savings-stamp");
    if (stamp) { stamp.classList.remove("landed"); void stamp.offsetWidth; stamp.classList.add("landed"); }
    animateRouteDraw(shadeFeatures);
  } catch (_) {}
  // Live Trail chain-by-chain: same lanes appear in the dashboard Route tab
  // during AND after the journey (Shade Studio sub-view of Live Trail).
  try {
    const dirs = routeData.directions || routeData.shade_route?.directions || [];
    if (dirs && dirs.length) renderTrailDirectionsInDashboard(dirs);
  } catch (_) {}
  // New display = new choice. Default to the shaded ticket and refresh the
  // "Continue on this route" subtitle with the exact From → To @ time.
  activePathChoice = "shade";
  try { updateContinueCta(); } catch (_) {}
}

// 13. Update Origin and Destination Markers on Map
function updateEndpointMarkers(routeData) {
  if (originMarker) originMarker.remove();
  if (destinationMarker) destinationMarker.remove();

  if (routeData.origin && routeData.origin.lon && routeData.origin.lat) {
    const oEl = document.createElement("div");
    oEl.className = "endpoint-marker origin-marker";
    oEl.innerHTML = "🟢";
    oEl.title = `Start: ${routeData.origin.name}`;
    originMarker = new maplibregl.Marker({ element: oEl })
      .setLngLat([routeData.origin.lon, routeData.origin.lat])
      .addTo(map);
  }

  if (routeData.destination && routeData.destination.lon && routeData.destination.lat) {
    const dEl = document.createElement("div");
    dEl.className = "endpoint-marker destination-marker";
    dEl.innerHTML = "🏁";
    dEl.title = `End: ${routeData.destination.name}`;
    destinationMarker = new maplibregl.Marker({ element: dEl })
      .setLngLat([routeData.destination.lon, routeData.destination.lat])
      .addTo(map);
  }
}

// 14. Render Segments Breakdown in HUD
function renderSegmentsList(segments) {
  const container = document.getElementById("segments-list");
  const countBadge = document.getElementById("segment-count");
  if (!container) return;

  container.innerHTML = "";
  if (countBadge) countBadge.textContent = `${segments.length} lanes`;

  segments.forEach((s) => {
    const item = document.createElement("div");
    item.className = `segment-item ${s.is_shaded ? "is-shaded" : "is-exposed"}`;

    const streetName = s.name || "Connecting lane";
    const shadeLabel = s.is_shaded ? "🌿 Shaded" : "☀️ Sunlit";
    const pillClass = s.is_shaded ? "shaded" : "exposed";
    // Calibrated style: a learned per-label correction exists for this lane
    const corrStreet = (accuracyData?.streets || []).find(st => {
      const a = st.label.toLowerCase(), b = streetName.toLowerCase();
      return st.correction_ready && (a.includes(b) || b.includes(a));
    });
    const calibTag = corrStreet
      ? `<span class="calib-tag" title="Walkers report this lane ${corrStreet.correction > 0 ? "shadier" : "sunnier"} than buildings alone predict — ${corrStreet.taps} taps">✎ ${corrStreet.correction > 0 ? "+" : ""}${Math.round(corrStreet.correction * 100)}% · ${corrStreet.taps} taps</span>`
      : "";
    if (corrStreet) item.classList.add("is-calibrated");

    item.innerHTML = `
      <span class="segment-name" title="${streetName}">${streetName}${calibTag}</span>
      <div class="segment-meta">
        <span class="segment-len">${Math.round(s.length_m)}m</span>
        <span class="exposure-pill ${pillClass}">${shadeLabel}</span>
      </div>
    `;
    container.appendChild(item);
  });
}

// Shaded vs Direct ticket picker + "Continue on this route".
// Any change in the shaded area (time slider, From/To preview, map Start/End
// taps) re-renders currentRouteData; Continue carries EXACTLY that displayed
// route into a personal trip + Live Trail — never a stale fixed route.
function setupPathChoice() {
  const shadeBox = document.getElementById("shade-stat-box");
  const shortBox = document.getElementById("shortest-stat-box");
  if (shadeBox && !shadeBox.__wired) {
    shadeBox.__wired = true;
    shadeBox.title = "Walk the shaded path (guided)";
    shadeBox.addEventListener("click", () => {
      activePathChoice = "shade";
      updateContinueCta();
    });
  }
  if (shortBox && !shortBox.__wired) {
    shortBox.__wired = true;
    shortBox.title = "Preview the direct baseline";
    shortBox.addEventListener("click", () => {
      activePathChoice = "shortest";
      updateContinueCta();
    });
  }
}

function updateContinueCta() {
  const shadeBox = document.getElementById("shade-stat-box");
  const shortBox = document.getElementById("shortest-stat-box");
  if (shadeBox) shadeBox.classList.toggle("active-path", activePathChoice === "shade");
  if (shortBox) shortBox.classList.toggle("active-path", activePathChoice === "shortest");
  const pickBadge = document.querySelector("#shade-stat-box .badge-mini");
  if (pickBadge) pickBadge.textContent = activePathChoice === "shade" ? "Picked ✓" : "Pick";
  const directBadge = document.querySelector("#shortest-stat-box .badge-mini");
  if (directBadge) directBadge.textContent = activePathChoice === "shortest" ? "Previewing" : "Direct";
  const sub = document.getElementById("studio-continue-sub");
  if (sub) {
    if (!currentRouteData) {
      sub.textContent = "Pick shaded or direct above, then continue — your Live Trail opens with these exact lanes.";
    } else {
      const o = currentRouteData.origin?.name || "Start";
      const d = currentRouteData.destination?.name || "Finish";
      const t = currentRouteData.depart_time || "";
      sub.textContent = activePathChoice === "shade"
        ? `Continues ${o} → ${d} @ ${t} on the shaded path — Live Trail opens with these exact lanes.`
        : `Direct ${o} → ${d} @ ${t} is a sun-exposed baseline preview — guided stops + lanes still follow the shaded path.`;
    }
  }
}

// Starts a personal journey on the CURRENTLY DISPLAYED route and opens it in
// Live Trail (chain-by-chain lanes, stories, chat, shade studio).
async function continueDisplayedRoute() {
  if (!currentRouteData) {
    promptRegistrationOrEmbark(currentTripCode || "parkst-club");
    return;
  }
  const btn = document.getElementById("btn-studio-start-hike");
  const oldLabel = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span>Starting your journey…</span>`;
  }
  try {
    const walker = (userWalkerName || document.getElementById("ann-walker-name")?.value || "Walker").trim() || "Walker";
    const planRes = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: currentMode || "family",
        origin: currentRouteData.origin?.name,
        destination: currentRouteData.destination?.name,
        earliest_time: currentRouteData.depart_time,
        latest_time: currentRouteData.depart_time,
        walkers: [{ name: walker, sun_sensitivity: "high", pace: "slow" }],
      })
    });
    if (!planRes.ok) {
      const err = await planRes.json().catch(() => ({}));
      throw new Error(err.detail || "Could not continue on this route.");
    }
    const plan = await planRes.json();
    const code = plan.trip_code;
    try {
      await fetch(`/api/trip/${code}/join`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ walker })
      });
    } catch (_) {}
    if (!isUserRegistered) {
      userWalkerName = walker;
      isUserRegistered = true;
      try { localStorage.setItem("chhaya_walker_name", walker); } catch (_) {}
      const nd = document.getElementById("nav-walker-name");
      if (nd) nd.textContent = walker;
    }
    const enrollInput = document.getElementById("trail-enroll-name");
    if (enrollInput) enrollInput.value = walker;
    await switchTripGroup(code);
    switchPage("active-hike");
  } catch (e) {
    alert(e.message || "Could not continue on this route.");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = oldLabel;
    }
  }
}

// Recompute active route when slider moves
async function recomputeActiveRoute(timeStr) {
  if (!currentRouteData) return;
  try {
    const res = await fetch("/route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        origin: currentRouteData.origin.name,
        destination: currentRouteData.destination.name,
        depart_time: timeStr,
        sun_tolerance: currentRouteData.sun_tolerance,
        speed_kmh: currentRouteData.speed_kmh
      })
    });
    const updated = await res.json();
    if (updated.shade_route) {
      renderRouteResult(updated, updated.trade_off_sentence);
    }
  } catch (e) {
    console.error("Failed to recompute route:", e);
  }
}

// 15. Voice Briefing (ElevenLabs & Web Speech fallback)
function setupVoice() {
  const voiceBtn = document.getElementById("voice-play-btn");
  const providerTag = document.getElementById("voice-provider-tag");
  const waveEl = document.getElementById("voice-wave");

  function setWavePlaying(playing) {
    if (waveEl) {
      if (playing) waveEl.classList.remove("hidden");
      else waveEl.classList.add("hidden");
    }
  }

  voiceBtn.addEventListener("click", async () => {
    if (!currentBriefingText) return;
    voiceBtn.disabled = true;
    voiceBtn.querySelector("span").textContent = "Synthesizing...";
    setWavePlaying(true);

    try {
      const res = await fetch("/voice/briefing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: currentBriefingText })
      });
      const data = await res.json();

      if (data.has_audio && data.audio_base64) {
        providerTag.textContent = "ElevenLabs Audio Active";
        const audio = new Audio("data:audio/mpeg;base64," + data.audio_base64);
        audio.onended = () => {
          setWavePlaying(false);
          voiceBtn.querySelector("span").textContent = "Replay Briefing";
        };
        audio.play();
      } else {
        // Fallback to Web Speech API
        providerTag.textContent = "Browser Speech Active";
        if ("speechSynthesis" in window) {
          window.speechSynthesis.cancel();
          const utterance = new SpeechSynthesisUtterance(currentBriefingText);
          utterance.rate = 0.95;
          utterance.onend = () => {
            setWavePlaying(false);
            voiceBtn.querySelector("span").textContent = "Replay Briefing";
          };
          utterance.onerror = () => setWavePlaying(false);
          window.speechSynthesis.speak(utterance);
        } else {
          setWavePlaying(false);
        }
      }
    } catch (e) {
      console.warn("Speech synthesis fallback:", e);
      if ("speechSynthesis" in window) {
        const utterance = new SpeechSynthesisUtterance(currentBriefingText);
        utterance.onend = () => setWavePlaying(false);
        window.speechSynthesis.speak(utterance);
      } else {
        setWavePlaying(false);
      }
    } finally {
      voiceBtn.disabled = false;
      voiceBtn.querySelector("span").textContent = "Replay Briefing";
    }
  });
}

// 16. Load Best Window Widget (TabPFN)
async function loadBestWindowWidget() {
  try {
    const res = await fetch("/window");
    const data = await res.json();

    const bestWinTimeEl = document.getElementById("best-window-time");
    const bestWinReasonEl = document.getElementById("best-window-reason");
    if (bestWinTimeEl) bestWinTimeEl.textContent = data.best_window;
    if (bestWinReasonEl) bestWinReasonEl.textContent = data.explanation;

    const metrics = data.model_metrics || {};
    const maeTag = document.getElementById("mae-tag");
    if (maeTag) {
      if (metrics.tabpfn_mae != null && metrics.baseline_mae != null) {
        maeTag.textContent = `MAE: ${metrics.tabpfn_mae} vs ${metrics.baseline_mae} Base`;
        maeTag.title = `${metrics.model || "TabPFN"} · held-out ${metrics.held_out || ""}`;
      } else {
        maeTag.textContent = "MAE: climatology fallback";
      }
    }

    const list = document.getElementById("window-list");
    if (!list) return;
    list.innerHTML = "";

    (data.windows || []).slice(0, 5).forEach((w) => {
      const item = document.createElement("div");
      item.className = "window-item" + (w.is_recommended ? " active" : "");
      item.innerHTML = `
        <span>${w.time_window} (${w.label})</span>
        <strong style="color: ${w.is_recommended ? '#1F4D3A' : '#C8321E'}">${w.discomfort_score}/100</strong>
      `;
      
      // Make window cards clickable! Clicking applies this time window to the slider and route!
      item.addEventListener("click", () => {
        applyWindowTime(w.time_window);
        document.querySelectorAll(".window-item").forEach(x => x.classList.remove("active"));
        item.classList.add("active");
      });

      list.appendChild(item);
    });

    // Also make the top recommendation card clickable
    const recBox = document.querySelector(".window-recommendation");
    if (recBox) {
      recBox.style.cursor = "pointer";
      recBox.title = "Click to apply this recommended walking window";
      recBox.addEventListener("click", () => {
        applyWindowTime(data.best_window);
      });
    }
  } catch (e) {
    console.error("Failed to load best window:", e);
  }
}

function applyWindowTime(windowStr) {
  // e.g. "14:30 - 16:30" -> set time to 15:00, "06:30 - 08:30" -> set time to 07:30
  if (!windowStr) return;
  const parts = windowStr.split("-");
  const startTime = parts[0].trim();
  const [hr, mn] = startTime.split(":").map(Number);
  
  // Pick mid-hour
  let targetHr = hr + 1;
  let targetTime = `${targetHr.toString().padStart(2, "0")}:00`;
  if (targetHr > 18) targetTime = "17:30";
  if (targetHr < 6) targetTime = "07:00";

  const slider = document.getElementById("time-slider");
  const timeDisplay = document.getElementById("time-display");
  if (slider && timeDisplay) {
    const stepVal = targetHr * 2;
    slider.value = stepVal;
    timeDisplay.textContent = targetTime;
    updateShadowsForTime(targetTime);
    updateActiveTick(stepVal);
    if (currentRouteData) {
      recomputeActiveRoute(targetTime);
    }
  }
}

// ===================================================================
// Master Plan Functions (P0, P1, P2)
// ===================================================================

function setAppMode(mode) {
  currentMode = mode;
  try { document.body.setAttribute("data-mode", mode); } catch (_) {}
  document.querySelectorAll(".mode-tab").forEach(tab => {
    if (tab.getAttribute("data-mode") === mode) tab.classList.add("active");
    else tab.classList.remove("active");
  });

  const modeLabel = document.getElementById("hud-mode-label");
  if (modeLabel) {
    if (mode === "family") modeLabel.textContent = lt("mode.familyPlan", "Family Walk Plan (Dadu)");
    else if (mode === "club") modeLabel.textContent = lt("mode.clubPlan", "Club Regroup Plan (Camac Loop)");
    else if (mode === "trail") modeLabel.textContent = lt("mode.trailPlan", "Trail Hike Plan (GPX Regroup)");
  }
}

function setupModeSwitcher() {
  document.querySelectorAll(".mode-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      const mode = tab.getAttribute("data-mode");
      setAppMode(mode);
      if (mode === "family") {
        document.getElementById("prompt-input").value = "Walk Dadu to the clinic around noon, he can't take much sun.";
        loadRoute("Walk Dadu to the clinic around noon, he can't take much sun.", null, "family");
      } else if (mode === "club") {
        document.getElementById("prompt-input").value = "Sunday 4pm, 6 of us, Dadu can't take much sun, Rina wants chai on the way.";
        loadRoute("Sunday 4pm, 6 of us, Dadu can't take much sun, Rina wants chai on the way.", null, "club");
      } else if (mode === "trail") {
        document.getElementById("prompt-input").value = "Hike Russell Street to Camac loop with regroup points.";
        loadRoute("Hike Russell Street to Camac loop with regroup points.", null, "trail");
      }
    });
  });
}

function setupHudTabs() {
  const tabs = document.querySelectorAll(".hud-tab-btn");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");

      const targetId = tab.getAttribute("data-target");
      document.querySelectorAll(".hud-tab-panel").forEach(panel => {
        if (panel.id === targetId) panel.classList.remove("hidden");
        else panel.classList.add("hidden");
      });
    });
  });
}

function setupModals() {
  // Walk Modal
  const openWalkBtn = document.getElementById("open-walk-btn");
  const walkModal = document.getElementById("walk-modal");
  const closeWalkBtn = document.getElementById("close-walk-modal");
  if (openWalkBtn && walkModal) {
    openWalkBtn.addEventListener("click", () => walkModal.classList.remove("hidden"));
  }
  if (closeWalkBtn && walkModal) {
    closeWalkBtn.addEventListener("click", () => walkModal.classList.add("hidden"));
  }

  // Radar Modal
  const openRadarBtn = document.getElementById("open-radar-btn");
  const radarModal = document.getElementById("radar-modal");
  const closeRadarBtn = document.getElementById("close-radar-modal");
  if (openRadarBtn && radarModal) {
    openRadarBtn.addEventListener("click", () => {
      radarModal.classList.remove("hidden");
      loadNearbyCards(KOLKATA_CENTER[1], KOLKATA_CENTER[0]);
    });
  }
  if (closeRadarBtn && radarModal) {
    closeRadarBtn.addEventListener("click", () => radarModal.classList.add("hidden"));
  }

  // Feed Modal
  const openFeedBtn = document.getElementById("open-feed-btn");
  const feedModal = document.getElementById("feed-modal");
  const closeFeedBtn = document.getElementById("close-feed-modal");
  if (openFeedBtn && feedModal) {
    openFeedBtn.addEventListener("click", () => {
      feedModal.classList.remove("hidden");
      loadFeed();
    });
  }
  if (closeFeedBtn && feedModal) {
    closeFeedBtn.addEventListener("click", () => feedModal.classList.add("hidden"));
  }

  // QR Modal
  const openQrBtn = document.getElementById("open-qr-btn");
  const openQrDirect = document.getElementById("open-trip-qr-direct");
  const qrModal = document.getElementById("qr-modal");
  const closeQrBtn = document.getElementById("close-qr-modal");
  function showQr() {
    if (qrModal) {
      qrModal.classList.remove("hidden");
      loadTripQr(currentTripCode);
    }
  }
  if (openQrBtn) openQrBtn.addEventListener("click", showQr);
  if (openQrDirect) openQrDirect.addEventListener("click", showQr);
  if (closeQrBtn && qrModal) {
    closeQrBtn.addEventListener("click", () => qrModal.classList.add("hidden"));
  }

  // Close modals on clicking background overlay
  document.querySelectorAll(".modal-overlay").forEach(overlay => {
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) overlay.classList.add("hidden");
    });
  });
}

function setupWalkActions() {
  // Walker / Watcher / Chat view switcher
  const views = [
    ["view-mode-walker", "view-content-walker"],
    ["view-mode-watcher", "view-content-watcher"],
    ["view-mode-chat", "view-content-chat"],
    ["view-mode-group", "view-content-group"],
  ];
  views.forEach(([btnId, panelId]) => {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    btn.addEventListener("click", () => {
      views.forEach(([b, p]) => {
        document.getElementById(b)?.classList.toggle("active", b === btnId);
        document.getElementById(p)?.classList.toggle("hidden", p !== panelId);
      });
      if (panelId === "view-content-watcher") refreshWatcherTimeline(currentTripCode);
      if (panelId === "view-content-chat") { lastChatId = 0; pollChat(); }
      if (panelId === "view-content-group") pollGroup();
    });
  });

  // Walker Tap: "I'm at Stop N"
  const tapCheckinBtn = document.getElementById("btn-tap-checkin");
  if (tapCheckinBtn) {
    tapCheckinBtn.addEventListener("click", async () => {
      const walkerName = (document.getElementById("walker-name-input")?.value || "Walker").trim();
      tapCheckinBtn.disabled = true;
      tapCheckinBtn.querySelector("span").textContent = `Logging Check-in ${currentCheckinIndex}...`;

      try {
        const res = await fetch(`/api/trip/${currentTripCode}/checkin`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ walker: walkerName, stop_index: currentCheckinIndex })
        });
        const data = await res.json();
        currentCheckinIndex++;
        tapCheckinBtn.querySelector("span").textContent = `📍 I'm at Stop ${currentCheckinIndex}`;

        // Update checkpoint display
        const nextStopName = document.getElementById("next-stop-name");
        if (nextStopName) nextStopName.textContent = `Stop ${currentCheckinIndex}: Verified Rest Point`;

        // If in club mode, re-check repair
        if (currentMode === "club") {
          loadStragglerRepair(currentTripCode);
        }
      } catch (e) {
        console.error("Check-in error:", e);
      } finally {
        tapCheckinBtn.disabled = false;
      }
    });
  }

  // Walker Tap: "We Reached Safely" (Family ping)
  const tapReachedBtn = document.getElementById("btn-tap-reached");
  if (tapReachedBtn) {
    tapReachedBtn.addEventListener("click", async () => {
      tapReachedBtn.disabled = true;
      tapReachedBtn.querySelector("span").textContent = "Sending Ping...";

      try {
        const walker = ((document.getElementById("walker-name-input")?.value) || "Walker").trim();
        const res = await fetch(`/api/trip/${currentTripCode}/reached?walker=${encodeURIComponent(walker)}`, { method: "POST" });
        const data = await res.json();
        const pts = data.grass_points?.points ? ` (+${data.grass_points.points} 🌱)` : "";
        tapReachedBtn.querySelector("span").textContent = `✅ Reached${pts} (Ping Sent!)`;
        tapReachedBtn.style.background = "#1F4D3A";

        // Update Watcher view
        const wIcon = document.getElementById("watcher-status-icon");
        const wTitle = document.getElementById("watcher-status-title");
        const wDesc = document.getElementById("watcher-status-desc");
        if (wIcon) wIcon.textContent = "🎉";
        if (wTitle) wTitle.textContent = lt("walk.reached", "Reached Safely!");
        if (wDesc) wDesc.textContent = `Family notified safely at ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}. Walk complete.`;
      } catch (e) {
        console.error("Reached error:", e);
      } finally {
        tapReachedBtn.disabled = false;
      }
    });
  }
}

async function refreshWatcherTimeline(tripCode) {
  const container = document.getElementById("watcher-timeline");
  if (!container) return;
  try {
    const res = await fetch(`/api/trip/${tripCode}`);
    const data = await res.json();
    const checkins = data.checkins || [];
    container.innerHTML = "";

    if (!checkins.length) {
      container.innerHTML = `<p style="font-size:11px; color:#6B5D4D;">No check-ins logged yet. Walkers departed.</p>`;
      return;
    }

    checkins.forEach(chk => {
      const item = document.createElement("div");
      item.style.cssText = "background:rgba(255,255,255,0.06); padding:6px 10px; border-radius:4px; font-size:11px; display:flex; justify-content:space-between;";
      item.innerHTML = `
        <span>📍 <strong>${chk.walker}</strong> at Stop ${chk.stop_index}</span>
        <span style="color:#1F4D3A;">${chk.time.split('T')[1]?.slice(0,5) || 'Just now'}</span>
      `;
      container.appendChild(item);
    });
  } catch (e) {
    console.error("Watcher refresh error:", e);
  }
}

function setupRadarActions() {
  const tabView = document.getElementById("radar-tab-view");
  const tabLeave = document.getElementById("radar-tab-leave");
  const panelView = document.getElementById("radar-panel-view");
  const panelLeave = document.getElementById("radar-panel-leave");

  if (tabView && tabLeave) {
    tabView.addEventListener("click", () => {
      tabView.classList.add("active");
      tabLeave.classList.remove("active");
      panelView.classList.remove("hidden");
      panelLeave.classList.add("hidden");
    });
    tabLeave.addEventListener("click", () => {
      tabLeave.classList.add("active");
      tabView.classList.remove("active");
      panelLeave.classList.remove("hidden");
      panelView.classList.add("hidden");
    });
  }

  // Submit Leave Card form (pins at the tapped point, or the map centre)
  const form = document.getElementById("leave-card-form");
  const photoInput = document.getElementById("card-photo-input");
  if (photoInput) {
    photoInput.addEventListener("change", () => {
      cardPhotoData = null;
      const prev = document.getElementById("card-photo-preview");
      if (prev) { prev.style.display = "none"; prev.src = ""; }
      const file = photoInput.files && photoInput.files[0];
      if (!file) return;
      const img = new Image();
      img.onload = () => {
        const scale = Math.min(1, 800 / Math.max(img.width, img.height));
        const cv = document.createElement("canvas");
        cv.width = Math.round(img.width * scale);
        cv.height = Math.round(img.height * scale);
        cv.getContext("2d").drawImage(img, 0, 0, cv.width, cv.height);
        cardPhotoData = cv.toDataURL("image/jpeg", 0.7);
        URL.revokeObjectURL(img.src);
        if (prev) { prev.src = cardPhotoData; prev.style.display = "block"; }
      };
      img.src = URL.createObjectURL(file);
    });
  }
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const type = document.getElementById("card-type-select").value;
      const text = document.getElementById("card-text-input").value.trim();
      if (!text) return;

      const postBtn = document.getElementById("btn-post-card");
      postBtn.disabled = true;
      postBtn.querySelector("span").textContent = "Moderating & Posting...";

      const at = cardPlace || { lat: KOLKATA_CENTER[1], lon: KOLKATA_CENTER[0] };
      try {
        const res = await fetch("/api/cards", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            trip_code: currentTripCode,
            type: type,
            text: text,
            lat: at.lat,
            lon: at.lon,
            visibility: "public",
            shade_at_creation: 0.82,
            photo: cardPhotoData,
          })
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          alert(err.detail || "Card was not pinned.");
          return;
        }
        const saved = await res.json();
        if (saved.moderation_status === "photo_too_large_dropped") {
          alert("Text pinned, but the photo was too large and was dropped.");
        }
        document.getElementById("card-text-input").value = "";
        if (photoInput) photoInput.value = "";
        cardPhotoData = null;
        const prev = document.getElementById("card-photo-preview");
        if (prev) { prev.style.display = "none"; prev.src = ""; }
        tabView.click();
        loadNearbyCards(at.lat, at.lon);
      } catch (err) {
        console.error("Post card error:", err);
      } finally {
        postBtn.disabled = false;
        postBtn.querySelector("span").textContent = "Pin Card to Location";
      }
    });
  }
}

function cardIcon(type) {
  switch (type) {
    case "warning": return "⚠️";
    case "meetup": return "☕";
    case "hike": return "🥾";
    case "story": return "📖";
    case "note": return "📝";
    default: return "💡";
  }
}

async function loadNearbyCards(lat, lon) {
  try {
    const res = await fetch(`/api/cards/near?lat=${lat}&lon=${lon}&radius=300`);
    const data = await res.json();
    const countBadge = document.getElementById("radar-card-count");
    if (countBadge) countBadge.textContent = data.radar_count || 0;

    const list = document.getElementById("radar-cards-list");
    if (!list) return;
    list.innerHTML = "";

    const allCards = data.radar_cards || [];
    if (!allCards.length) {
      list.innerHTML = `<p style="font-size:11px; color:#6B5D4D;">No cards left nearby yet. Be the first to leave a shade tip!</p>`;
      return;
    }

    allCards.forEach(c => {
      const item = document.createElement("div");
      item.className = "repair-card-item";
      const icon = cardIcon(c.type);
      const photoHtml = c.photo ? `<img class="card-photo-thumb" src="${c.photo}" alt="Card photo" loading="lazy" />` : (c.has_photo ? `<div style="font-size:11px;">📷 photo attached — get closer to view</div>` : "");
      const storyHtml = c.type === "story"
        ? `<div style="margin-top:6px;display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
             <span class="lock-tag">${c.locked ? `🔒 LOCKED · ${c.distance_m} m away` : "🔓 WITHIN REACH"}</span>
             <button class="btn-popup" style="padding:6px 10px;" onclick="unlockStory('${c.id}', this)">Unlock +25 🌱</button>
           </div>
           <div class="unlock-result" style="font-size:12px;margin-top:4px;"></div>`
        : "";
      item.innerHTML = `
        <div class="repair-card-header">
          <span>${icon} ${c.type.toUpperCase()}</span>
          <span style="color:#1F4D3A; font-size:10px;">${c.distance_m}m ${c.bearing}</span>
        </div>
        <div class="repair-card-desc">"${c.text}"</div>
        ${photoHtml}
        ${storyHtml}
        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px; font-size:10px; color:#6B5D4D;">
          <span>Shade: ${Math.round((c.shade_at_creation || 0.8) * 100)}%</span>
          <button class="btn-popup" style="padding:2px 6px; font-size:9.5px;" onclick="reportCard('${c.id}')">Report</button>
        </div>
      `;
      list.appendChild(item);
    });

    renderCardsOnMap(allCards);
  } catch (e) {
    console.error("Load nearby cards error:", e);
  }
}

async function reportCard(cardId) {
  try {
    await fetch(`/api/cards/${cardId}/report`, { method: "POST" });
    loadNearbyCards(KOLKATA_CENTER[1], KOLKATA_CENTER[0]);
  } catch (e) {
    console.error("Report card error:", e);
  }
}

// Unlocks a geo-locked story using the phone's GPS (no spoofing via map
// centre: the server checks the real distance).
async function unlockStory(cardId, btn) {
  const box = btn?.closest(".repair-card-item")?.querySelector(".unlock-result");
  const say = t => { if (box) box.textContent = t; };
  if (!("geolocation" in navigator)) { say("GPS unavailable on this device."); return; }
  const walker = ((document.getElementById("walker-name-input")?.value) || "Walker").trim();
  if (btn) btn.disabled = true;
  say("Reading GPS…");
  navigator.geolocation.getCurrentPosition(async (pos) => {
    try {
      const res = await fetch(`/api/cards/${cardId}/unlock`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ walker, trip_code: currentTripCode, lat: pos.coords.latitude, lon: pos.coords.longitude }),
      });
      const data = await res.json();
      if (!res.ok) { say(data.detail || "Unlock failed."); return; }
      if (!data.unlocked) { say(`🔒 ${data.distance_m} m away — need ${data.need_m} m. Walk closer.`); return; }
      say(data.already ? "Already in your journal — no repeat points." : `🔓 Unlocked! "${data.text}" (+${data.points} 🌱)`);
      if (data.photo) {
        const img = document.createElement("img");
        img.className = "card-photo-thumb"; img.src = data.photo; img.alt = "Story photo";
        box.appendChild(img);
      }
      pollGroup(true);
    } finally { if (btn) btn.disabled = false; }
  }, () => say("GPS fix failed — step into the open and retry."), { enableHighAccuracy: true, timeout: 12000 });
}

function setupQrActions() {
  const copyBtn = document.getElementById("copy-qr-link-btn");
  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      const url = window.location.origin + `/t/${currentTripCode}`;
      navigator.clipboard.writeText(url).then(() => {
        copyBtn.querySelector("span").textContent = "✓ Link Copied!";
        setTimeout(() => { copyBtn.querySelector("span").textContent = "📋 Copy Trip Link"; }, 2000);
      });
    });
  }

  const copyShareBtn = document.getElementById("copy-share-btn");
  if (copyShareBtn) {
    copyShareBtn.addEventListener("click", () => {
      const text = document.getElementById("share-plan-text")?.textContent || "";
      navigator.clipboard.writeText(text).then(() => {
        copyShareBtn.querySelector("span").textContent = "✓ Briefing Copied!";
        setTimeout(() => { copyShareBtn.querySelector("span").textContent = "📋 Copy Message"; }, 2000);
      });
    });
  }

  const copyRepairBtn = document.getElementById("copy-repair-btn");
  if (copyRepairBtn) {
    copyRepairBtn.addEventListener("click", () => {
      const text = document.getElementById("repair-copy-text")?.textContent || "";
      navigator.clipboard.writeText(text).then(() => {
        copyRepairBtn.textContent = "✓ Alert Copied!";
        setTimeout(() => { copyRepairBtn.textContent = "📋 Copy Group Alert"; }, 2000);
      });
    });
  }
}

async function loadTripQr(tripCode) {
  try {
    const res = await fetch(`/api/trip/${tripCode}/qr`);
    const data = await res.json();
    const img = document.getElementById("qr-image");
    const urlText = document.getElementById("qr-url-text");
    if (img) img.src = `data:image/png;base64,${data.qr_base64}`;
    if (urlText) urlText.textContent = `${window.location.origin}/t/${tripCode}`;
  } catch (e) {
    console.error("Load trip QR error:", e);
  }
}

function checkUrlRouteOnLoad() {
  const path = window.location.pathname;
  if (path.startsWith("/t/")) {
    const parts = path.split("/").filter(Boolean);
    const code = parts[1];
    const isWatch = parts[2] === "watch";
    if (code) {
      currentTripCode = code;
      const walkModal = document.getElementById("walk-modal");
      if (walkModal) walkModal.classList.remove("hidden");
      if (isWatch) {
        document.getElementById("view-mode-watcher")?.click();
      }
    }
  }
}

// -------------------------------------------------------------------
// Render Master Plan Engine Result
// -------------------------------------------------------------------
function renderMasterPlan(plan) {
  currentTripData = plan;
  currentTripCode = plan.trip_code;
  setAppMode(plan.mode);

  // 1. Render primary route & comparison
  renderRouteResult(plan.route_data, plan.share_message || plan.trade_off_sentence);

  // 2. Weather & Budget Banner
  const condText = document.getElementById("weather-condition-text");
  const budTag = document.getElementById("weather-budget-tag");
  const advText = document.getElementById("weather-advice-text");
  const wScaling = plan.weather_scaling || {};
  if (condText) {
    condText.textContent = `🌤️ Open-Meteo: ${wScaling.apparent_temperature || 32}°C · UV ${wScaling.uv_index || 4}`;
  }
  if (budTag) {
    budTag.textContent = `Budget: ${(plan.effective_budget_min || 4).toFixed(1)}m`;
  }
  if (advText) {
    advText.textContent = (wScaling.factor && wScaling.factor < 1.0)
      ? "Scaled budget for Kolkata afternoon heat/UV."
      : "Comfortable standard sun budget active.";
  }

  // 3. Render 10-Minute Best Start Sweep
  renderSweepChart(plan.sweep);

  // 4. Render Rest Stops on Map & HUD Panel
  renderRestStopsOnMap(plan.rest_stops);
  renderRestStopsList(plan.rest_stops);

  // 5. Render Shareable Message
  const shareText = document.getElementById("share-plan-text");
  const shareCode = document.getElementById("share-trip-code");
  if (shareText) shareText.textContent = plan.share_message;
  if (shareCode) shareCode.textContent = plan.trip_code;

  // 6. If Club Mode, load Straggler Repair options
  if (plan.mode === "club") {
    loadStragglerRepair(plan.trip_code);
  }

  // 7. Animate walking dot along shaded route
  if (plan.route_data?.shade_route?.coordinates) {
    startWalkingDotAnimation(plan.route_data.shade_route.coordinates);
  }

  // 8. Update Walk Modal data
  const tripBadge = document.getElementById("walk-modal-trip-code");
  if (tripBadge) tripBadge.textContent = `TRIP: ${plan.trip_code}`;
  currentCheckinIndex = 1;
  const tapBtn = document.getElementById("btn-tap-checkin");
  if (tapBtn) tapBtn.querySelector("span").textContent = "📍 I'm at Stop 1";
  const thanks = document.getElementById("tap-thanks");
  if (thanks) thanks.textContent = "";

  // 9. Refresh the field-check accuracy meter (counts + learned corrections)
  refreshAccuracyMeter();
}

function renderSweepChart(sweep) {
  const container = document.getElementById("sweep-bars-container");
  const badge = document.getElementById("sweep-best-badge");
  const warning = document.getElementById("sweep-budget-warning");
  if (!container || !sweep) return;

  container.innerHTML = "";
  if (badge) badge.textContent = `Best: ${sweep.best_time || '11:40'}`;

  if (sweep.no_comfortable_window) {
    if (warning) warning.classList.remove("hidden");
  } else {
    if (warning) warning.classList.add("hidden");
  }

  const results = sweep.sweep_results || [];
  if (!results.length) return;

  const maxSun = Math.max(...results.map(r => r.sun_minutes), 1.0);

  results.forEach(r => {
    const col = document.createElement("div");
    col.className = "sweep-bar-col" + (r.is_best ? " best" : "");
    col.title = `Start: ${r.start_time} | Sun: ${r.sun_minutes.toFixed(1)}m (Budget: ${sweep.effective_budget_min.toFixed(1)}m)`;

    const heightPct = Math.max(15, Math.round((r.sun_minutes / maxSun) * 100));
    col.innerHTML = `
      <div class="sweep-bar-fill" style="height: ${heightPct}%"></div>
      <span class="sweep-label">${r.start_time.split(':')[0]}:${r.start_time.split(':')[1]}</span>
    `;

    col.addEventListener("click", () => {
      updateShadowsForTime(r.start_time);
      const [h, m] = r.start_time.split(":").map(Number);
      const step = h * 2 + (m >= 30 ? 1 : 0);
      const slider = document.getElementById("time-slider");
      if (slider) {
        slider.value = step;
        document.getElementById("time-display").textContent = r.start_time;
        updateActiveTick(step);
      }
    });

    container.appendChild(col);
  });

  // Signature: hand-drawn exposure curve + LEAVE AT stamp (visual only)
  try { drawSweepCurve(results, sweep.best_time); } catch (_) {}
}

function renderRestStopsOnMap(stops) {
  restStopMarkers.forEach(m => m.remove());
  restStopMarkers = [];
  if (!stops || !stops.length) return;

  stops.forEach((s, idx) => {
    const el = document.createElement("div");
    el.className = "rest-stop-marker" + (s.approximate ? " approximate" : "");
    const icon = s.kind === "cafe" ? "☕" : (s.kind === "shelter" ? "⛱️" : "🪑");
    el.innerHTML = icon;

    const shadePct = Math.round((s.shade_at_arrival || 0.8) * 100);
    const popup = new maplibregl.Popup({ offset: 15 }).setHTML(`
      <div class="popup-landmark-title">Stop ${idx + 1}: ${s.name}</div>
      <div class="popup-landmark-addr">Type: ${s.kind.toUpperCase()} · ${Math.round(s.distance_m)}m</div>
      <div style="font-size:11px; color:#1F4D3A;">Arrival Shade: <strong>${shadePct}%</strong></div>
    `);

    const marker = new maplibregl.Marker({ element: el, anchor: "bottom", offset: [0, -6] })
      .setLngLat([s.lon, s.lat])
      .setPopup(popup)
      .addTo(map);
    restStopMarkers.push(marker);
  });
}

function renderRestStopsList(stops) {
  const list = document.getElementById("rest-stops-list");
  const badge = document.getElementById("stops-count-badge");
  if (badge) badge.textContent = stops ? stops.length : 0;
  if (!list) return;

  list.innerHTML = "";
  if (!stops || !stops.length) {
    list.innerHTML = `<p style="font-size:11px; color:#6B5D4D;">Direct route without intermediate pauses.</p>`;
    return;
  }

  stops.forEach((s, idx) => {
    const item = document.createElement("div");
    item.className = "repair-card-item ticket-card";
    const shadePct = Math.round((s.shade_at_arrival || 0.8) * 100);
    item.innerHTML = `
      <div class="repair-card-header">
        <span>Stop ${idx + 1}: ${s.name}</span>
        <span style="color:#1F4D3A;">${shadePct}% shade</span>
      </div>
      <div class="repair-card-desc">
        ${s.kind.toUpperCase()} · ${Math.round(s.distance_m)}m from start (~${Math.round(s.arrival_time_min)} min)
      </div>
    `;
    item.addEventListener("click", () => {
      map.flyTo({ center: [s.lon, s.lat], zoom: 17.5 });
    });
    list.appendChild(item);
  });
}

function renderCardsOnMap(cards) {
  cardMarkers.forEach(m => m.remove());
  cardMarkers = [];
  if (!cards || !cards.length) return;

  cards.forEach(c => {
    const el = document.createElement("div");
    el.className = "card-pin";
    const icon = cardIcon(c.type);
    el.innerHTML = icon;

    const popup = new maplibregl.Popup({ offset: 15 }).setHTML(`
      <div class="popup-landmark-title">${c.type.toUpperCase()} Card</div>
      <p style="font-size:11px; color:#2A1F17; margin:4px 0;">"${c.text}"</p>
      <div style="font-size:10px; color:#6B5D4D;">Shade at creation: ${Math.round((c.shade_at_creation || 0.8) * 100)}%</div>
      <button class="btn-popup" style="margin-top:6px; color:#C8321E;" onclick="reportCard('${c.id}')">🚩 Report</button>
    `);

    const marker = new maplibregl.Marker({ element: el, anchor: "bottom", offset: [0, -6] })
      .setLngLat([c.lon, c.lat])
      .setPopup(popup)
      .addTo(map);
    el.addEventListener("mouseenter", () => addInkRing([c.lon, c.lat]));
    el.addEventListener("click", () => addInkRing([c.lon, c.lat]));
    cardMarkers.push(marker);
  });
}

async function loadStragglerRepair(tripCode) {
  try {
    const res = await fetch(`/api/trip/${tripCode}/repair?elapsed_min=18.0`);
    const data = await res.json();

    const titleEl = document.getElementById("repair-status-title");
    const descEl = document.getElementById("repair-status-desc");
    const cardsList = document.getElementById("repair-cards-list");
    const copyTextEl = document.getElementById("repair-copy-text");

    if (data.has_straggler) {
      if (titleEl) titleEl.textContent = `Straggler Alert: ${data.primary_straggler.name} Behind`;
      if (descEl) descEl.textContent = `${data.primary_straggler.name} is ${data.primary_straggler.delay_min} min behind schedule. Top ranked repair tactics:`;
    } else {
      if (titleEl) titleEl.textContent = `All Walkers On Schedule`;
      if (descEl) descEl.textContent = `Group pace intact. Grace window: 3 min.`;
    }

    if (copyTextEl) copyTextEl.textContent = data.message || "Group moving together.";

    if (cardsList) {
      cardsList.innerHTML = "";
      (data.repair_options || []).forEach(opt => {
        const c = document.createElement("div");
        c.className = "repair-card-item";
        c.innerHTML = `
          <div class="repair-card-header">
            <span>${opt.type}: ${opt.title}</span>
            <span style="font-size:10px; color:#1F4D3A;">Score: ${opt.score.toFixed(2)}</span>
          </div>
          <div class="repair-card-desc">${opt.description}</div>
          <div class="repair-stats">
            <span>Wait: ${opt.group_wait_min}m</span>
            <span>Sun: ${opt.max_walker_sun_min}m</span>
            <span>Delay: ${opt.rejoin_delay_min}m</span>
          </div>
        `;
        cardsList.appendChild(c);
      });
    }

    // Also update walk-behind-banner in Walk modal
    const behindBanner = document.getElementById("walk-behind-banner");
    const behindText = document.getElementById("walk-behind-text");
    const repairShortcut = document.getElementById("walk-repair-shortcut");
    if (behindBanner && data.has_straggler) {
      behindBanner.classList.remove("hidden");
      if (behindText) behindText.textContent = `${data.primary_straggler.name} is ${data.primary_straggler.delay_min} min behind schedule.`;
      if (repairShortcut && data.repair_options && data.repair_options[0]) {
        repairShortcut.textContent = `Suggested (${data.repair_options[0].type}): ${data.repair_options[0].description}`;
      }
    }
  } catch (e) {
    console.error("Straggler repair fetch error:", e);
  }
}

function startWalkingDotAnimation(coordinates) {
  if (walkingAnimationId) cancelAnimationFrame(walkingAnimationId);
  if (walkingDotMarker) walkingDotMarker.remove();
  if (!coordinates || coordinates.length < 2) return;

  const dotEl = document.createElement("div");
  dotEl.className = "walking-dot";
  walkingDotMarker = new maplibregl.Marker({ element: dotEl })
    .setLngLat(coordinates[0])
    .addTo(map);

  let step = 0;
  const totalSteps = Math.max(120, coordinates.length * 35);
  function animate() {
    step = (step + 1) % totalSteps;
    const progress = step / totalSteps;
    const totalSegments = coordinates.length - 1;
    const currentSeg = Math.floor(progress * totalSegments);
    const fraction = (progress * totalSegments) - currentSeg;

    const p1 = coordinates[currentSeg];
    const p2 = coordinates[Math.min(currentSeg + 1, totalSegments)];
    if (p1 && p2) {
      const lng = p1[0] + (p2[0] - p1[0]) * fraction;
      const lat = p1[1] + (p2[1] - p1[1]) * fraction;
      walkingDotMarker.setLngLat([lng, lat]);
    }
    walkingAnimationId = requestAnimationFrame(animate);
  }
  animate();
}

// -------------------------------------------------------------------
// Shade taps + accuracy meter (Section 3.6 / V10 — counts, never bare %)
// -------------------------------------------------------------------
function observationContext() {
  // The halt just checked into: check-in index is 1-based and already
  // incremented after a tap, so the reached stop is index - 1.
  const stops = (currentTripData && currentTripData.rest_stops) || [];
  const reached = stops[currentCheckinIndex - 2];
  if (reached) {
    return {
      label: reached.name || ("Stop " + (currentCheckinIndex - 1)),
      predicted_shade: reached.shade_at_arrival ?? 0.8,
      stop_index: currentCheckinIndex - 1,
    };
  }
  const pct = (currentRouteData?.shade_route?.shade_percentage ?? 50) / 100;
  return { label: "Stop " + Math.max(1, currentCheckinIndex - 1), predicted_shade: pct, stop_index: currentCheckinIndex - 1 };
}

function setupShadeTaps() {
  const btnShade = document.getElementById("btn-tap-shaded");
  const btnSun = document.getElementById("btn-tap-sunny");
  if (!btnShade || !btnSun) return;
  btnShade.addEventListener("click", () => sendObservation("shade", btnShade));
  btnSun.addEventListener("click", () => sendObservation("sun", btnSun));
}

async function sendObservation(observed, btn) {
  const thanks = document.getElementById("tap-thanks");
  const walker = (document.getElementById("walker-name-input")?.value || "Walker").trim();
  const ctx = observationContext();
  if (btn) { btn.disabled = true; }
  try {
    const res = await fetch(`/api/trip/${currentTripCode}/observation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        walker,
        label: ctx.label,
        observed,
        predicted_shade: ctx.predicted_shade,
        stop_index: ctx.stop_index,
      }),
    });
    if (res.ok) {
      const data = await res.json();
      if (thanks) thanks.textContent = data.matched
        ? `Noted — map said ${Math.round(ctx.predicted_shade * 100)}% shade, you saw shade. ✓`
        : `Noted — map said ${Math.round(ctx.predicted_shade * 100)}% shade, you saw ${observed}. The map learns.`;
      refreshAccuracyMeter();
    } else if (thanks) {
      thanks.textContent = "Tap not saved — check connection, it will keep on the next halt.";
    }
  } catch (e) {
    if (thanks) thanks.textContent = "Tap not saved — check connection, it will keep on the next halt.";
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function refreshAccuracyMeter() {
  const tally = document.getElementById("accuracy-tally");
  const streetsBox = document.getElementById("accuracy-streets");
  try {
    const res = await fetch("/api/accuracy");
    const data = await res.json();
    accuracyData = data;
    streetCorrections = data.corrections || {};
    if (tally) {
      tally.textContent = data.taps === 0
        ? "No taps yet — be the first to tap sun/shade on the walk."
        : `Predicted shade matched what walkers saw at ${data.matched} of ${data.taps} checkpoints.`;
    }
    if (streetsBox) {
      streetsBox.innerHTML = "";
      (data.streets || []).slice(0, 4).forEach(st => {
        const line = document.createElement("div");
        line.style.cssText = "font-family:var(--font-mono);font-size:11px;display:flex;justify-content:space-between;gap:8px;";
        const verdict = st.correction_ready
          ? `✎ ${st.correction > 0 ? "+" : ""}${Math.round(st.correction * 100)}% (${st.taps} taps)`
          : `${st.matched}/${st.taps} taps`;
        line.innerHTML = `<span>${st.label}</span><strong>${verdict}</strong>`;
        streetsBox.appendChild(line);
      });
    }
    // Re-mark lane list with any newly learned corrections
    if (currentSegments.length) renderSegmentsList(currentSegments);
  } catch (e) {
    if (tally) tally.textContent = "Accuracy meter offline — taps still save on the walk.";
  }
}

// -------------------------------------------------------------------
// Multi-Page Architecture, Individualized Groups & Side Dashboard
// -------------------------------------------------------------------

const banyanSvgDataUri = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 380' width='100%' height='100%'><rect width='600' height='380' fill='%23F4E9D4'/><rect x='20' y='20' width='560' height='340' fill='%23E8D6B5' stroke='%232A1F17' stroke-width='3'/><path d='M40 330 Q 300 310 560 330 L 560 360 L 40 360 Z' fill='%232A1F17'/><path d='M260 330 C 270 240, 230 180, 180 120 C 230 140, 280 200, 300 240 C 320 180, 380 140, 440 100 C 380 160, 330 220, 340 330 Z' fill='%232A1F17'/><ellipse cx='200' cy='90' rx='140' ry='65' fill='%231F4D3A'/><ellipse cx='320' cy='70' rx='160' ry='60' fill='%23173D2E'/><ellipse cx='430' cy='95' rx='130' ry='55' fill='%231F4D3A'/><ellipse cx='300' cy='110' rx='190' ry='70' fill='%235E8C6A' opacity='0.9'/><line x1='160' y1='120' x2='160' y2='330' stroke='%232A1F17' stroke-width='4'/><line x1='220' y1='140' x2='210' y2='330' stroke='%232A1F17' stroke-width='3.5'/><line x1='380' y1='130' x2='390' y2='330' stroke='%232A1F17' stroke-width='3.5'/><line x1='440' y1='110' x2='450' y2='330' stroke='%232A1F17' stroke-width='4'/><rect x='140' y='270' width='90' height='40' rx='4' fill='%23B8553A' stroke='%232A1F17' stroke-width='2.5'/><text x='185' y='295' font-family='serif' font-size='12' font-weight='bold' fill='%23FBF7EE' text-anchor='middle'>CHAI BENCH</text><circle cx='500' cy='65' r='28' fill='%23F2A900' opacity='0.4'/><text x='300' y='348' font-family='monospace' font-size='12' font-weight='bold' fill='%23FBF7EE' text-anchor='middle'>PARK ST · 110-YR BANYAN CANOPY · 92% SHADE</text></svg>";
const bakerySvgDataUri = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 380' width='100%' height='100%'><rect width='600' height='380' fill='%23F4E9D4'/><rect x='20' y='20' width='560' height='340' fill='%23E8D6B5' stroke='%232A1F17' stroke-width='3'/><rect x='60' y='60' width='480' height='260' fill='%23B8553A' stroke='%232A1F17' stroke-width='3'/><path d='M100 60 L180 180 L100 180 Z' fill='%232A1F17'/><rect x='160' y='120' width='280' height='160' rx='8' fill='%23FBF7EE' stroke='%232A1F17' stroke-width='3'/><text x='300' y='170' font-family='serif' font-size='20' font-weight='bold' fill='%23B8553A' text-anchor='middle'>BOW BARRACKS BAKERY</text><text x='300' y='210' font-family='serif' font-size='14' fill='%232A1F17' text-anchor='middle'>Fresh Coconut Patties &amp; Walnut Cake</text><circle cx='300' cy='250' r='18' fill='%23F2A900'/><text x='300' y='255' font-family='monospace' font-size='12' font-weight='bold' fill='%232A1F17' text-anchor='middle'>EST. 1942</text><text x='300' y='350' font-family='monospace' font-size='12' font-weight='bold' fill='%232A1F17' text-anchor='middle'>HERITAGE SHADED LANE · 88% SHADE</text></svg>";
const collegeSvgDataUri = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 380' width='100%' height='100%'><rect width='600' height='380' fill='%23F4E9D4'/><rect x='20' y='20' width='560' height='340' fill='%23E8D6B5' stroke='%232A1F17' stroke-width='3'/><rect x='50' y='60' width='500' height='260' fill='%231F4D3A' stroke='%232A1F17' stroke-width='3'/><text x='300' y='110' font-family='serif' font-size='22' font-weight='bold' fill='%23FBF7EE' text-anchor='middle'>COLLEGE STREET BOI PARA</text><text x='300' y='140' font-family='sans-serif' font-size='14' fill='%23F2A900' text-anchor='middle'>World Largest Second-Hand Book Market · Est. 1817</text><rect x='100' y='170' width='180' height='120' rx='6' fill='%23B8553A' stroke='%232A1F17' stroke-width='2'/><text x='190' y='210' font-family='serif' font-size='15' font-weight='bold' fill='%23FBF7EE' text-anchor='middle'>BOOK STALL #14</text><text x='190' y='240' font-family='sans-serif' font-size='12' fill='%23FBF7EE' text-anchor='middle'>Under Canvas Awning</text><rect x='320' y='170' width='180' height='120' rx='6' fill='%23FBF7EE' stroke='%232A1F17' stroke-width='2'/><text x='410' y='210' font-family='serif' font-size='15' font-weight='bold' fill='%232A1F17' text-anchor='middle'>COFFEE HOUSE</text><text x='410' y='240' font-family='monospace' font-size='12' fill='%23C8321E' text-anchor='middle'>Hot Infusion Coffee</text><text x='300' y='350' font-family='monospace' font-size='12' font-weight='bold' fill='%232A1F17' text-anchor='middle'>HERITAGE SHADED VERANDAH · 88% SHADE</text></svg>";

function getStoryCardPhoto(c) {
  if (c && c.photo) return c.photo;
  const t = (c && c.text) || "";
  if (t.includes("College") || t.includes("Book") || t.includes("Coffee")) return collegeSvgDataUri;
  if (t.includes("Bakery") || t.includes("Barracks") || t.includes("Patties")) return bakerySvgDataUri;
  return banyanSvgDataUri;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function setupWalkerRegistration() {
  const openBtn = document.getElementById("btn-open-register");
  const closeBtn = document.getElementById("close-register-modal");
  const modal = document.getElementById("register-walker-modal");
  const form = document.getElementById("form-register-walker");
  const nameInput = document.getElementById("input-reg-name");
  const nameDisplay = document.getElementById("nav-walker-name");

  if (nameDisplay) nameDisplay.textContent = userWalkerName;

  const showModal = () => {
    if (nameInput) nameInput.value = userWalkerName || "";
    if (modal) modal.classList.remove("hidden");
  };
  const hideModal = () => {
    if (modal) modal.classList.add("hidden");
  };

  if (openBtn) openBtn.addEventListener("click", showModal);
  if (closeBtn) closeBtn.addEventListener("click", hideModal);

  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const val = (nameInput?.value || "").trim();
      if (!val) return;
      const wasRegistered = isUserRegistered;
      userWalkerName = val;
      isUserRegistered = true;
      try {
        localStorage.setItem("chhaya_walker_name", userWalkerName);
      } catch (_) {}

      if (nameDisplay) nameDisplay.textContent = userWalkerName;
      const hostInput = document.getElementById("ann-walker-name");
      if (hostInput) hostInput.value = userWalkerName;

      if (!wasRegistered) {
        updateGrassPointsWallet(10, "registration");
        alert(`Welcome, ${userWalkerName}! Registered with +10 🌱 Grass Points.`);
      }

      hideModal();

      if (pendingEmbarkTripCode) {
        const code = pendingEmbarkTripCode;
        pendingEmbarkTripCode = null;
        switchTripGroup(code);
        switchPage("active-hike");
      }
    });
  }
}

function promptRegistrationOrEmbark(tripCode) {
  if (!isUserRegistered) {
    pendingEmbarkTripCode = tripCode;
    const modal = document.getElementById("register-walker-modal");
    if (modal) modal.classList.remove("hidden");
  } else {
    switchTripGroup(tripCode);
    switchPage("active-hike");
  }
}

function setupFixedRoutesStudio() {
  document.querySelectorAll(".fixed-route-pill").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".fixed-route-pill").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const code = btn.getAttribute("data-route-id");
      const mode = btn.getAttribute("data-mode") || "club";
      setAppMode(mode);
      switchTripGroup(code);
    });
  });
}

function setupRealTimeLocationTracker() {
  const toggleGpsBtn = document.getElementById("btn-toggle-device-gps");
  const toggleAutoBtn = document.getElementById("btn-toggle-auto-walk");
  const closePosLockBtn = document.getElementById("btn-close-pos-lock");
  const closePosLockX = document.getElementById("close-position-locked-modal");
  const posLockModal = document.getElementById("position-locked-modal");

  const hidePosLock = () => { if (posLockModal) posLockModal.classList.add("hidden"); };
  if (closePosLockBtn) closePosLockBtn.addEventListener("click", hidePosLock);
  if (closePosLockX) closePosLockX.addEventListener("click", hidePosLock);

  if (toggleGpsBtn) {
    toggleGpsBtn.addEventListener("click", () => {
      if (deviceGpsActive) {
        stopDeviceGps();
      } else {
        startDeviceGps();
      }
    });
  }

  if (toggleAutoBtn) {
    toggleAutoBtn.addEventListener("click", () => {
      toggleAutoWalk();
    });
  }

  // Attempt real device GPS on load if available
  if (navigator.geolocation) {
    startDeviceGps(true);
  }
}

function startDeviceGps(silent = false) {
  if (!navigator.geolocation) {
    if (!silent) alert("Geolocation is not supported by your browser.");
    return;
  }
  deviceGpsActive = true;
  const toggleBtn = document.getElementById("btn-toggle-device-gps");
  if (toggleBtn) toggleBtn.innerHTML = `<span>🛰️ GPS Active</span>`;

  if (gpsWatchId) navigator.geolocation.clearWatch(gpsWatchId);
  gpsWatchId = navigator.geolocation.watchPosition(
    (pos) => {
      const lat = pos.coords.latitude;
      const lon = pos.coords.longitude;
      const acc = Math.round(pos.coords.accuracy || 6);

      // Check if location is in Kolkata bounds
      if (lat >= 22.45 && lat <= 22.65 && lon >= 88.25 && lon <= 88.45) {
        userSimulatedCoords = [lon, lat];
        updateLocationHUD(lat, lon, acc, "🛰️ Device GPS");
        handleRealTimePositionUpdate(lat, lon);
      } else {
        // Outside Kolkata bounds: note to user and keep trail coords
        updateLocationHUD(userSimulatedCoords[1], userSimulatedCoords[0], acc, "🚶 Trail Sim");
        if (!silent) {
          console.log(`Device GPS (${lat.toFixed(4)}, ${lon.toFixed(4)}) is outside Kolkata. Using trail simulator.`);
        }
      }
    },
    (err) => {
      deviceGpsActive = false;
      if (toggleBtn) toggleBtn.innerHTML = `<span>🛰️ Use Device GPS</span>`;
      updateLocationHUD(userSimulatedCoords[1], userSimulatedCoords[0], 10, "🚶 Trail Sim");
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 3000 }
  );
}

function stopDeviceGps() {
  if (gpsWatchId) {
    navigator.geolocation.clearWatch(gpsWatchId);
    gpsWatchId = null;
  }
  deviceGpsActive = false;
  const toggleBtn = document.getElementById("btn-toggle-device-gps");
  if (toggleBtn) toggleBtn.innerHTML = `<span>🛰️ Use Device GPS</span>`;
  updateLocationHUD(userSimulatedCoords[1], userSimulatedCoords[0], 5, "🚶 Trail Sim");
}

function toggleAutoWalk() {
  const toggleBtn = document.getElementById("btn-toggle-auto-walk");
  const label = document.getElementById("label-auto-walk");
  if (isAutoWalking) {
    clearInterval(autoWalkInterval);
    autoWalkInterval = null;
    isAutoWalking = false;
    if (toggleBtn) toggleBtn.classList.remove("active-auto-walk");
    if (label) label.textContent = "▶ Auto-Walk";
  } else {
    isAutoWalking = true;
    if (toggleBtn) toggleBtn.classList.add("active-auto-walk");
    if (label) label.textContent = "⏸️ Stop Auto-Walk";
    stepSimulatorForward();
    autoWalkInterval = setInterval(() => {
      stepSimulatorForward();
    }, 2200);
  }
}

function updateLocationHUD(lat, lon, accuracy, modeName) {
  const coordsEl = document.getElementById("hud-live-coords");
  if (coordsEl) coordsEl.textContent = `${lat.toFixed(4)}° N, ${lon.toFixed(4)}° E`;
  const accEl = document.getElementById("hud-loc-accuracy");
  if (accEl) accEl.textContent = `±${accuracy || 6}m`;
  const modeEl = document.getElementById("hud-loc-mode");
  if (modeEl) modeEl.textContent = modeName || "🚶 Trail Sim";
}

function handleRealTimePositionUpdate(lat, lon) {
  if (userWalkerMarker) {
    userWalkerMarker.setLngLat([lon, lat]);
  } else if (map) {
    const el = document.createElement("div");
    el.className = "walker-live-marker";
    el.innerHTML = `
      <div style="background:var(--shade);color:#fff;border:2px solid var(--ink);border-radius:50%;width:26px;height:26px;display:flex;align-items:center;justify-content:center;font-size:13px;box-shadow:2px 2px 0 var(--ink);">
        🚶
      </div>
    `;
    userWalkerMarker = new maplibregl.Marker({ element: el }).setLngLat([lon, lat]).addTo(map);
  }

  // Post position to backend
  fetch(`/api/trip/${currentTripCode}/position`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      walker_name: userWalkerName || "Pritam",
      lat: lat,
      lon: lon,
      distance_along_route_m: simStepIndex * 50
    })
  }).catch(() => {});

  // Check nearby story unlocks & update proximity
  checkNearbyStoryUnlocks(lat, lon);
}

function showPositionLockedAlert(story, distMeters, userCoords) {
  const modal = document.getElementById("position-locked-modal");
  if (!modal) return;
  const desc = document.getElementById("pos-lock-desc");
  const userCoordsEl = document.getElementById("pos-lock-user-coords");
  const cardCoordsEl = document.getElementById("pos-lock-card-coords");
  const distEl = document.getElementById("pos-lock-dist-text");

  if (desc) {
    desc.textContent = `You must physically reach within 50 meters of "${story.text.split(':')[0] || 'this spot'}" along the trail to unlock its photo and story postcard!`;
  }
  if (userCoordsEl) userCoordsEl.textContent = `${userCoords[1].toFixed(4)}° N, ${userCoords[0].toFixed(4)}° E`;
  if (cardCoordsEl) cardCoordsEl.textContent = `${story.lat.toFixed(4)}° N, ${story.lon.toFixed(4)}° E`;
  if (distEl) distEl.textContent = `${Math.round(distMeters)} meters away`;

  modal.classList.remove("hidden");
}

function setupMultiPageNav() {
  document.querySelectorAll(".nav-page-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      const page = tab.getAttribute("data-page");
      if (page) switchPage(page);
    });
  });

  const startHikeBtn = document.getElementById("btn-studio-start-hike");
  if (startHikeBtn && !startHikeBtn.__wiredContinue) {
    startHikeBtn.__wiredContinue = true;
    startHikeBtn.addEventListener("click", () => {
      continueDisplayedRoute();
    });
  }

  // Handle URL hash changes
  window.addEventListener("hashchange", () => {
    const hash = (window.location.hash || "").replace("#", "");
    if (["studio", "active-hike", "feed", "passport"].includes(hash)) {
      switchPage(hash, false);
    }
  });

  // Check initial hash
  const initialHash = (window.location.hash || "").replace("#", "");
  if (["studio", "active-hike", "feed", "passport"].includes(initialHash)) {
    switchPage(initialHash, false);
  } else {
    // Default to feed so user chooses their agenda and route first!
    switchPage("feed", false);
  }
}

function switchPage(pageId, updateHash = true) {
  currentActivePage = pageId;
  if (updateHash) {
    try { window.location.hash = pageId; } catch (_) {}
  }

  // Update nav tabs
  document.querySelectorAll(".nav-page-tab").forEach(tab => {
    if (tab.getAttribute("data-page") === pageId) tab.classList.add("active");
    else tab.classList.remove("active");
  });

  // Update page containers
  document.querySelectorAll(".page-view").forEach(pv => {
    pv.classList.remove("active");
  });
  const activeView = document.getElementById(`page-${pageId}`);
  if (activeView) activeView.classList.add("active");

  // Resize map
  if (map) {
    setTimeout(() => { map.resize(); }, 100);
  }

  // Page-specific initializers
  if (pageId === "active-hike") {
    switchTripGroup(currentTripCode || "parkst-club");
    loadTrailStoriesRadar();
  } else if (pageId === "feed") {
    loadCommunityFeed();
  } else if (pageId === "passport") {
    loadPassportJournal();
  }
}

function setupGroupDashboard() {
  const select = document.getElementById("group-hike-select");
  if (select) {
    select.addEventListener("change", () => {
      switchTripGroup(select.value);
    });
  }

  // Sub-tab switching in side dashboard
  document.querySelectorAll(".sub-tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".sub-tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".dashboard-panel").forEach(p => p.classList.add("hidden"));
      btn.classList.add("active");
      const targetId = btn.getAttribute("data-tab");
      const panel = document.getElementById(targetId);
      if (panel) panel.classList.remove("hidden");
    });
  });

  setupTrailChat();
}

async function switchTripGroup(tripCode) {
  currentTripCode = tripCode || "parkst-club";
  lastChatId = 0;

  const select = document.getElementById("group-hike-select");
  if (select && select.value !== currentTripCode) select.value = currentTripCode;

  const pill = document.getElementById("active-group-pill");
  if (pill) {
    const text = (select ? select.options[select.selectedIndex]?.text : null) || currentTripCode || "Trail";
    pill.textContent = text.slice(0, 18);
  }

  const chatTitle = document.getElementById("chat-group-title");
  if (chatTitle) {
    const titleMap = {
      "parkst-club": "Park Street Club Chat",
      "dadu-clinic": "Dadu Clinic Chat",
      "heritage-food-trail": "Bow Barracks Trail Chat",
      "sarobar-trek": "Sarobar Lake Trek Chat",
      "college-street": "College Street Chat",
    };
    chatTitle.textContent = titleMap[tripCode] || `${tripCode} Chat`;
  }

  // Fetch trip details to load route onto map
  try {
    const res = await fetch(`/api/trip/${currentTripCode}`);
    if (res.ok) {
      const data = await res.json();
      currentTripData = data;
      if (data.plan) {
        currentRouteData = data.plan;
        renderRouteOnMap(data.plan);
        renderRestStopsOnMap(data.plan.stops || []);
        renderTrailStopsInDashboard(data.plan.stops || []);
        updateDashboardRouteSummary(data.plan);
        const dirs = data.plan.route_data?.directions || data.plan.route_data?.shade_route?.directions || [];
        renderTrailDirectionsInDashboard(dirs);
        const summary = document.getElementById("group-live-summary");
        if (summary) {
          const wLen = (data.plan.walkers || []).length || 5;
          summary.textContent = `${wLen} Walkers · ${Math.round(data.plan.shade_percentage || 74)}% Shade`;
        }
      }
    }
  } catch (_) {}

  pollTrailChat();
  pollLiveGroupRadar();
  loadTrailStoriesRadar();
  loadStragglerRepair(currentTripCode);
  try { loadMappostPins(); } catch (_) {}
  // Fallback: if the trip plan has no precomputed chain, derive it from the
  // live route result so Live Trail ALWAYS shows chain-by-chain lanes.
  try {
    const dirs = currentRouteData?.directions || currentRouteData?.shade_route?.directions || [];
    if (dirs && dirs.length) renderTrailDirectionsInDashboard(dirs);
  } catch (_) {}
}

function renderRouteOnMap(plan) {
  if (!plan) return;
  const rd = plan.route_data;
  if (rd && rd.shade_route) {
    renderRouteResult(rd, rd.trade_off_sentence || plan.share_message);
    return;
  }
  // If not embedded, fetch route directly from /route
  const orig = plan.origin?.name || plan.origin?.id || "poi_flurys";
  const dest = plan.destination?.name || plan.destination?.id || "poi_camac_square";
  const time = plan.depart_time || "15:00";
  loadDirectRoute(orig, dest, time);
}

function updateDashboardRouteSummary(plan) {
  if (!plan) return;
  const titleEl = document.getElementById("summary-route-title");
  const shadeEl = document.getElementById("summary-shade-badge");
  const endpointsEl = document.getElementById("summary-route-endpoints");
  const distEl = document.getElementById("summary-dist-val");
  const sunEl = document.getElementById("summary-sun-val");
  const durEl = document.getElementById("summary-duration-val");
  const uvEl = document.getElementById("summary-uv-val");

  if (titleEl) titleEl.textContent = plan.title || "Shaded Trail Route";
  const shadePct = plan.shade_percentage ?? plan.route_data?.shade_route?.shade_percentage ?? 74;
  if (shadeEl) shadeEl.textContent = `${Math.round(shadePct)}% Shade`;

  const fromName = plan.origin?.name || "Start";
  const toName = plan.destination?.name || "Finish";
  if (endpointsEl) endpointsEl.textContent = `${fromName} → ${toName}`;

  const distM = plan.distance_meters ?? plan.route_data?.shade_route?.distance_meters ?? 1200;
  if (distEl) distEl.textContent = distM >= 1000 ? `${(distM / 1000).toFixed(1)} km` : `${Math.round(distM)}m`;
  const sunM = plan.sun_minutes ?? plan.route_data?.shade_route?.sun_minutes ?? 3.5;
  if (sunEl) sunEl.textContent = `${sunM} mins`;
  const durM = plan.duration_minutes ?? plan.route_data?.shade_route?.duration_minutes ?? 18;
  if (durEl) durEl.textContent = `${Math.round(durM)} mins`;
  if (uvEl) uvEl.textContent = "UV 4.2 · Mild";
}

function renderTrailDirectionsInDashboard(directions) {
  const container = document.getElementById("trail-directions-list");
  if (!container) return;
  if (!directions || !directions.length) {
    container.innerHTML = `<p style="font-size:12px;color:var(--muted);text-align:center;padding:16px;">Directions loading for this trail…</p>`;
    return;
  }

  container.innerHTML = "";
  directions.forEach((d, idx) => {
    const card = document.createElement("div");
    card.className = "direction-step-card" + (idx === 0 ? " active-step" : "");
    const icon = d.type === "start" ? "🟢" : (d.type === "finish" ? "🏁" : (d.is_shaded ? "🌳" : "☀️"));
    const shadeTag = d.is_shaded
      ? `<span class="step-shade-tag">✓ ${d.shade_pct}% Shade</span>`
      : `<span class="step-sun-tag">☀️ ${100 - d.shade_pct}% Exposed</span>`;
    const distText = d.distance_m > 0 ? `<span>${Math.round(d.distance_m)}m</span>` : "";

    card.innerHTML = `
      <div class="step-num-icon">${d.step || (idx + 1)}</div>
      <div class="step-content">
        <div class="step-instruction"><strong>${icon}</strong> ${escapeHtml(d.instruction)}</div>
        <div class="step-meta-row">
          ${distText}
          ${shadeTag}
        </div>
      </div>
    `;
    container.appendChild(card);
  });
}

function setupTrailChat() {
  const form = document.getElementById("trail-chat-input-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const input = document.getElementById("trail-chat-text");
      const text = (input.value || "").trim();
      if (!text) return;
      const walker = (document.getElementById("ann-walker-name")?.value || "Walker").trim();
      input.value = "";
      try {
        await fetch(`/api/trip/${currentTripCode}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ walker, text })
        });
        pollTrailChat();
        if (text.toLowerCase().includes("rest")) {
          showRestingStatus("Rina", true);
        }
      } catch (_) {}
    });
  }

  // Quick Action Chips
  document.querySelectorAll(".quick-chip-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const msg = btn.getAttribute("data-msg");
      if (!msg) return;
      const walker = (document.getElementById("ann-walker-name")?.value || "Rina").trim();
      try {
        await fetch(`/api/trip/${currentTripCode}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ walker, text: msg })
        });
        pollTrailChat();
        if (msg.includes("taking a rest")) {
          showRestingStatus(walker, true);
        }
      } catch (_) {}
    });
  });

  // Polling chat every 4s
  if (!chatTimer) {
    chatTimer = setInterval(() => {
      if (currentActivePage === "active-hike") {
        pollTrailChat(true);
      }
    }, 4000);
  }
}

async function pollTrailChat(quiet) {
  const stream = document.getElementById("trail-chat-stream");
  if (!stream) return;
  try {
    const res = await fetch(`/api/trip/${currentTripCode}/chat?since_id=${lastChatId}`);
    const data = await res.json();
    const msgs = data.messages || [];
    if (!msgs.length) {
      if (lastChatId === 0 && !quiet) {
        stream.innerHTML = `<p style="font-size:12px;color:var(--muted);text-align:center;padding:12px;">No messages yet in this group.</p>`;
      }
      return;
    }
    if (lastChatId === 0) stream.innerHTML = "";
    const me = (document.getElementById("ann-walker-name")?.value || "Walker").trim().toLowerCase();
    msgs.forEach(m => {
      lastChatId = Math.max(lastChatId, m.id);
      const isMine = (!m.is_system && me && m.walker.toLowerCase() === me);
      const row = document.createElement("div");
      row.className = "chat-msg-row " + (m.is_system ? "system" : (isMine ? "mine" : "others"));
      const when = (m.timestamp || "").slice(11, 16);
      if (m.is_system) {
        row.innerHTML = `<span>◉ ${escapeHtml(m.walker)} ${escapeHtml(m.text)} <small>${when}</small></span>`;
      } else {
        const sender = isMine ? "You" : m.walker;
        row.innerHTML = `
          <span class="chat-sender-label">${escapeHtml(sender)}</span>
          <div class="chat-bubble ${isMine ? 'mine' : 'others'}">
            ${escapeHtml(m.text)}
          </div>
          <span class="chat-time-stamp">${when}</span>
        `;
      }
      stream.appendChild(row);
    });
    const countBadge = document.getElementById("chat-badge-count");
    if (countBadge) countBadge.textContent = String(msgs.length);
    stream.scrollTop = stream.scrollHeight;
  } catch (_) {}
}

function showRestingStatus(walkerName, isResting) {
  const banner = document.getElementById("straggler-alert-banner");
  if (banner) {
    banner.style.display = isResting ? "block" : "none";
  }
  const msg = document.getElementById("straggler-banner-message");
  if (msg) {
    msg.innerHTML = `<strong>${escapeHtml(walkerName)}</strong> is taking a rest at Russell Chai Stall bench (85% shade). Will continue shortly.`;
  }
}

async function pollLiveGroupRadar() {
  const radarList = document.getElementById("live-walkers-radar-list");
  if (!radarList) return;

  try {
    const [posRes, ptsRes] = await Promise.all([
      fetch(`/api/trip/${currentTripCode}/positions`),
      fetch(`/api/trip/${currentTripCode}/points`),
    ]);
    const members = (await posRes.json()).members || [];
    const ptsData = await ptsRes.json();
    renderMemberMarkers(members);

    // Default rich roster for current group if positions are sparse
    let walkersList = [];
    if (currentTripData?.plan?.walkers) {
      walkersList = currentTripData.plan.walkers;
    } else {
      walkersList = [
        { name: "Aarav (Lead)", role: "lead", pace: "4.2 km/h", progress: 80 },
        { name: "Rina", role: "straggler", pace: "3.0 km/h", progress: 45, resting: true },
        { name: "Kabir", role: "hiker", pace: "4.8 km/h", progress: 75 },
        { name: "Ananya", role: "hiker", pace: "4.2 km/h", progress: 74 },
        { name: "Dev", role: "hiker", pace: "4.2 km/h", progress: 74 },
        { name: "You (Walker)", role: "you", pace: "4.0 km/h", progress: 70 },
      ];
    }

    radarList.innerHTML = "";
    walkersList.forEach(w => {
      const isLead = (w.name.includes("Lead") || w.role === "lead");
      const isStraggler = (w.name.includes("Rina") || w.resting);
      const isYou = (w.name.includes("You") || w.role === "you");
      const initials = w.name.slice(0, 2).toUpperCase();

      const item = document.createElement("div");
      item.className = "walker-radar-item" + (isStraggler ? " straggler-item" : "");

      const avatarClass = isLead ? "lead" : (isStraggler ? "straggler" : "");
      const roleText = isLead ? "LEAD" : (isStraggler ? "RESTING" : (isYou ? "YOU" : "IN PACK"));
      const progressVal = w.progress || (isLead ? 80 : (isStraggler ? 45 : 74));
      const fillClass = isStraggler ? "lagging" : "";
      const statusText = isStraggler
        ? "⏸️ Resting at Chai Bench (+5.5 min)"
        : (isLead ? "Passing Stop 2 · High pace" : "Steady with pack · 74% shade");

      item.innerHTML = `
        <div class="walker-avatar ${avatarClass}">${initials}</div>
        <div class="walker-info-col">
          <div class="walker-name-row">
            <span class="walker-name-text">${escapeHtml(w.name)}</span>
            <span class="walker-role-pill">${roleText}</span>
          </div>
          <div class="walker-progress-bar">
            <div class="walker-progress-fill ${fillClass}" style="width: ${progressVal}%;"></div>
          </div>
          <div class="walker-meta-row">
            <span>${statusText}</span>
            <span>${w.pace_kmh ? w.pace_kmh + ' km/h' : (w.pace || '4.2 km/h')}</span>
          </div>
        </div>
      `;
      radarList.appendChild(item);
    });

    const meta = document.getElementById("walker-count-meta");
    if (meta) meta.textContent = `${walkersList.length} Walkers`;
  } catch (_) {}
}

async function loadTrailStoriesRadar() {
  const container = document.getElementById("trail-stories-radar-list");
  if (!container) return;

  const at = userSimulatedCoords || [KOLKATA_CENTER[0], KOLKATA_CENTER[1]];
  try {
    const res = await fetch(`/api/cards/near?lat=${at[1]}&lon=${at[0]}&radius=400&trip_code=${currentTripCode}`);
    const data = await res.json();
    const cards = (data.radar_cards || []).filter(c => c.type === "story");

    const badge = document.getElementById("drops-badge-count");
    if (badge) badge.textContent = String(cards.length || 2);

    if (!cards.length) {
      container.innerHTML = `
        <div class="story-radar-card">
          <strong style="font-size:13px;">110-Year-Old Heritage Banyan Canopy</strong>
          <p style="font-size:12.5px;color:var(--muted);">Continuous canopy shade and clay chai pots. Pin your own discovery using the button above.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = "";
    cards.forEach(c => {
      const card = document.createElement("div");
      card.className = "story-radar-card" + (!c.locked ? " unlocked-card" : "");
      const isLocked = Boolean(c.locked);
      const lockLabel = isLocked ? `🔒 LOCKED · ${c.distance_m || 45}m away` : "🔓 UNLOCKED · IN JOURNAL";
      const photoSrc = getStoryCardPhoto(c);

      card.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span class="badge-mini" style="background:${isLocked ? 'var(--sun)' : 'var(--shade)'};color:${isLocked ? 'var(--ink)' : '#FFF'};">
            ${lockLabel}
          </span>
          <span style="font-family:var(--font-mono);font-size:11px;">+25 🌱</span>
        </div>
        <strong style="font-size:13.5px;margin-top:2px;">${escapeHtml(c.text.split(":")[0])}</strong>
        <p style="font-size:12.5px;color:var(--muted);">${escapeHtml(c.text)}</p>
        ${!isLocked ? `<img class="story-radar-thumb" src="${photoSrc}" alt="Story preview" />` : ''}
        <button class="btn btn-glass-sm" style="margin-top:4px;width:100%;justify-content:center;" data-unlock-card="${c.id}">
          <span>${isLocked ? `🔒 Locked (${c.distance_m || 45}m) · Reach Spot` : 'View Full Story Postcard'}</span>
        </button>
      `;
      container.appendChild(card);
    });

    const nearestLocked = cards.find(c => c.locked);
    const nextStoryDistEl = document.getElementById("hud-dist-next-story");
    if (nextStoryDistEl) {
      nextStoryDistEl.textContent = nearestLocked ? `${Math.round(nearestLocked.distance_m || 45)}m away` : "Unlocked";
    }

    container.querySelectorAll("[data-unlock-card]").forEach(btn => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-unlock-card");
        const found = cards.find(c => c.id === id);
        if (!found) return;

        const at = userSimulatedCoords || [KOLKATA_CENTER[0], KOLKATA_CENTER[1]];
        const dist = haversineDistanceMeters(at[1], at[0], found.lat, found.lon);

        if (dist <= 50 || !found.locked) {
          triggerStoryCelebration(found, 25);
          updateGrassPointsWallet(25, "story");
          found.locked = false;
          loadTrailStoriesRadar();
        } else {
          showPositionLockedAlert(found, dist, at);
        }
      });
    });
  } catch (_) {}
}

function renderTrailStopsInDashboard(stops) {
  const container = document.getElementById("trail-stops-radar-list");
  if (!container) return;
  if (!stops || !stops.length) {
    container.innerHTML = `<p style="font-size:12px;color:var(--muted);">No stops registered on this route.</p>`;
    return;
  }
  container.innerHTML = "";
  stops.forEach((s, idx) => {
    const item = document.createElement("div");
    item.className = "ticket-card";
    item.style.cursor = "pointer";
    const shadePct = Math.round((s.shade_at_arrival || 0.8) * 100);
    item.innerHTML = `
      <div style="display:flex;justify-content:space-between;font-weight:700;font-size:13px;">
        <span>Stop ${idx + 1}: ${escapeHtml(s.name)}</span>
        <span style="color:var(--shade);">${shadePct}% shade</span>
      </div>
      <div style="font-size:11.5px;color:var(--muted);margin-top:2px;">
        ${escapeHtml(s.description || s.kind.toUpperCase())} · ETA ${s.arrival_time || Math.round(s.cumulative_walk_min) + 'm'}
      </div>
    `;
    item.addEventListener("click", () => {
      if (map) map.flyTo({ center: [s.lon, s.lat], zoom: 17.5 });
    });
    container.appendChild(item);
  });
}

function setupSimulatorControls() {
  const btnStep = document.getElementById("btn-advance-simulator");
  if (btnStep) {
    btnStep.addEventListener("click", () => stepSimulatorForward());
  }

  const btnCheckin = document.getElementById("btn-checkin-checkpoint");
  if (btnCheckin) {
    btnCheckin.addEventListener("click", async () => {
      const walker = (document.getElementById("ann-walker-name")?.value || "Walker").trim();
      try {
        const res = await fetch(`/api/trip/${currentTripCode}/checkin`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ walker, stop_index: 1 })
        });
        if (res.ok) {
          updateGrassPointsWallet(10, "checkin");
          alert("Checked into Stop 1 (+10 🌱 Grass Points)!");
          pollTrailChat();
        }
      } catch (_) {}
    });
  }

  const btnReached = document.getElementById("btn-reached-finish");
  if (btnReached) {
    btnReached.addEventListener("click", async () => {
      const walker = (document.getElementById("ann-walker-name")?.value || "Walker").trim();
      try {
        const res = await fetch(`/api/trip/${currentTripCode}/reached?walker=${encodeURIComponent(walker)}`, {
          method: "POST"
        });
        if (res.ok) {
          updateGrassPointsWallet(50, "reached");
          alert("We Reached Safely! (+50 🌱 Grass Points Awarded) Walk completed!");
          pollTrailChat();
        }
      } catch (_) {}
    });
  }
}

function stepSimulatorForward() {
  const coords = currentRouteData?.geometry?.coordinates ||
                 currentRouteData?.shaded_route?.geometry?.coordinates ||
                 [[88.3526, 22.5532], [88.3522, 22.5523], [88.3518, 22.5518], [88.3527, 22.5505], [88.3538, 22.5492]];

  simStepIndex = (simStepIndex + 1) % coords.length;
  const target = coords[simStepIndex];
  userSimulatedCoords = target;

  // Move marker on map
  if (!userWalkerMarker && map) {
    const el = document.createElement("div");
    el.className = "member-pin";
    el.style.background = "var(--sindoor)";
    el.textContent = "ME";
    userWalkerMarker = new maplibregl.Marker({ element: el })
      .setLngLat(target)
      .addTo(map);
  } else if (userWalkerMarker) {
    userWalkerMarker.setLngLat(target);
  }

  if (map) map.easeTo({ center: target, zoom: 17 });

  // Post updated spot
  const walker = (document.getElementById("ann-walker-name")?.value || "Walker").trim();
  fetch(`/api/trip/${currentTripCode}/position`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ walker, lat: target[1], lon: target[0] })
  });

  // Check proximity to stories (unlocks automatically if near!)
  checkNearbyStoryUnlocks(target[1], target[0]);

  // Check proximity to stops
  const stops = currentTripData?.plan?.stops || [];
  stops.forEach((s, idx) => {
    const d = haversineDistanceMeters(target[1], target[0], s.lat, s.lon);
    if (d <= 50) {
      fetch(`/api/trip/${currentTripCode}/checkin`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ walker, stop_index: idx + 1 })
      });
    }
  });

  // Re-poll dashboard
  pollLiveGroupRadar();
}

function haversineDistanceMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon/2) * Math.sin(dLon/2);
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

async function checkNearbyStoryUnlocks(lat, lon) {
  try {
    const res = await fetch(`/api/cards/near?lat=${lat}&lon=${lon}&radius=350&trip_code=${currentTripCode}`);
    const data = await res.json();
    const stories = (data.radar_cards || []).filter(c => c.type === "story");
    stories.forEach(async (st) => {
      if (st.distance_m <= 65) {
        const walker = (document.getElementById("ann-walker-name")?.value || "Walker").trim();
        const unRes = await fetch(`/api/cards/${st.id}/unlock`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ walker, trip_code: currentTripCode, lat, lon })
        });
        const unData = await unRes.json();
        if (unData.unlocked && !unData.already) {
          triggerStoryCelebration(st, unData.points || 25);
          updateGrassPointsWallet(unData.points || 25, "story");
          loadTrailStoriesRadar();
        }
      }
    });
  } catch (_) {}
}

function triggerStoryCelebration(story, points = 25) {
  const modal = document.getElementById("story-unlock-modal");
  if (!modal) return;
  const title = document.getElementById("story-unlock-modal-title");
  const img = document.getElementById("story-unlock-image");
  const p = document.getElementById("story-unlock-paragraph");
  const shade = document.getElementById("story-unlock-shade");
  const dist = document.getElementById("story-unlock-dist");

  if (title) title.textContent = story.text.split(":")[0] || "110-Year-Old Heritage Banyan Canopy";
  if (img) {
    img.src = story.photo || (story.text.includes("Banyan") ? banyanSvgDataUri : bakerySvgDataUri);
    img.style.display = "block";
  }
  if (p) p.textContent = story.text;
  if (shade) shade.textContent = `${Math.round((story.shade_at_creation || 0.88) * 100)}%`;
  if (dist) dist.textContent = "At checkpoint (<60m)";

  modal.classList.remove("hidden");
}

function setupStoryCelebrationModal() {
  const closeBtn = document.getElementById("close-story-unlock-modal");
  const collectBtn = document.getElementById("btn-collect-story-points");
  const modal = document.getElementById("story-unlock-modal");

  const close = () => { if (modal) modal.classList.add("hidden"); };
  if (closeBtn) closeBtn.addEventListener("click", close);
  if (collectBtn) {
    collectBtn.addEventListener("click", () => {
      close();
      loadPassportJournal();
    });
  }

  setupStoryPinning();
}

function setupStoryPinning() {
  const openBtn = document.getElementById("btn-open-drop-modal");
  const closeBtn = document.getElementById("close-drop-story-modal");
  const modal = document.getElementById("drop-story-modal");
  const form = document.getElementById("drop-story-form");
  const fileInput = document.getElementById("drop-story-file");
  const prev = document.getElementById("drop-story-photo-preview");

  if (openBtn) openBtn.addEventListener("click", () => { if (modal) modal.classList.remove("hidden"); });
  if (closeBtn) closeBtn.addEventListener("click", () => { if (modal) modal.classList.add("hidden"); });

  let pinnedPhotoData = null;
  if (fileInput) {
    fileInput.addEventListener("change", () => {
      const file = fileInput.files && fileInput.files[0];
      if (!file) return;
      const r = new FileReader();
      r.onload = (e) => {
        pinnedPhotoData = e.target.result;
        if (prev) { prev.src = pinnedPhotoData; prev.style.display = "block"; }
      };
      r.readAsDataURL(file);
    });
  }

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const text = (document.getElementById("drop-story-text")?.value || "").trim();
      if (!text) return;
      const at = userSimulatedCoords || [KOLKATA_CENTER[0], KOLKATA_CENTER[1]];
      try {
        await fetch("/api/cards", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            trip_code: currentTripCode,
            type: "story",
            text: text,
            lat: at[1],
            lon: at[0],
            visibility: "public",
            shade_at_creation: 0.88,
            photo: pinnedPhotoData || banyanSvgDataUri
          })
        });
        updateGrassPointsWallet(25, "pinned-story");
        alert("Story successfully pinned to trail! (+25 🌱 Grass Points)");
        if (modal) modal.classList.add("hidden");
        loadTrailStoriesRadar();
      } catch (_) {}
    });
  }
}

function updateGrassPointsWallet(ptsToAdd, reason) {
  userGrassPoints += ptsToAdd;
  const navPts = document.getElementById("nav-wallet-pts");
  if (navPts) navPts.textContent = `${userGrassPoints} 🌱`;
  const passPts = document.getElementById("passport-total-points");
  if (passPts) passPts.textContent = String(userGrassPoints);

  let tier = "Seedling";
  let fillPct = 25;
  if (userGrassPoints >= 150) { tier = "Chhaya Master"; fillPct = 100; }
  else if (userGrassPoints >= 80) { tier = "Canopy Ranger"; fillPct = 75; }
  else if (userGrassPoints >= 40) { tier = "Trail Scout"; fillPct = 50; }

  const tierPill = document.getElementById("passport-tier-pill");
  if (tierPill) tierPill.textContent = tier;
  const fill = document.getElementById("tier-bar-fill");
  if (fill) fill.style.width = `${fillPct}%`;
}

// -------------------------------------------------------------------
// Page 3: Community Hike Feed
// -------------------------------------------------------------------
function setupFeedPage() {
  const toggleBtn = document.getElementById("btn-toggle-announce-form");
  const announceCard = document.getElementById("announce-hike-card");
  if (toggleBtn && announceCard) {
    toggleBtn.addEventListener("click", () => {
      announceCard.classList.toggle("hidden");
    });
  }

  const form = document.getElementById("announce-hike-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const title = (document.getElementById("ann-title-input")?.value || "").trim();
      const origin = document.getElementById("ann-origin-select")?.value;
      const dest = document.getElementById("ann-dest-select")?.value;
      const category = document.getElementById("ann-category-select")?.value;
      const packageType = document.getElementById("ann-package-select")?.value;
      const departTime = document.getElementById("ann-depart-time")?.value || "15:30";
      const walker = (document.getElementById("ann-walker-name")?.value || "Walker").trim();

      if (!title || !origin || !dest) return;
      const btn = document.getElementById("btn-submit-announce");
      if (btn) btn.disabled = true;

      try {
        const res = await fetch("/api/feed/create", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title,
            origin,
            destination: dest,
            walker,
            category,
            package: packageType,
            depart_time: departTime
          })
        });
        if (res.ok) {
          const data = await res.json();
          updateGrassPointsWallet(5, "host");
          alert(`Hike "${title}" initiated! Group chat room and shade route are finalized. (+5 🌱 Grass Points)`);
          if (announceCard) announceCard.classList.add("hidden");
          const code = data.trip_code || "parkst-club";
          switchTripGroup(code);
          switchPage("active-hike");
        } else {
          const err = await res.json().catch(() => ({}));
          alert(err.detail || "Could not announce hike.");
        }
      } finally {
        if (btn) btn.disabled = false;
      }
    });
  }

  setupDaduPersonalAgenda();

  // Filter chips in Feed
  document.querySelectorAll("[data-filter-agenda]").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-filter-agenda]").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const ag = btn.getAttribute("data-filter-agenda");
      const daduCard = document.getElementById("dadu-agenda-card");
      if (daduCard) {
        if (ag === "help" || ag === "all") daduCard.style.display = "block";
        else daduCard.style.display = "none";
      }
      applyFeedFilters();
    });
  });
  document.querySelectorAll("[data-filter-dist]").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-filter-dist]").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      applyFeedFilters();
    });
  });
  document.querySelectorAll("[data-filter-pkg]").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-filter-pkg]").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      applyFeedFilters();
    });
  });
}

function setupDaduPersonalAgenda() {
  const origSel = document.getElementById("dadu-origin-select");
  const destSel = document.getElementById("dadu-dest-select");
  const modeSel = document.getElementById("dadu-mode-select");
  const embarkBtn = document.getElementById("btn-embark-dadu-custom");
  const timeBtns = document.querySelectorAll(".dadu-time-btn");

  let selectedTime = "08:30";

  // Fill From/To with the full POI list so ANY personal journey is possible.
  // Dadu's home->clinic stays the default, but it is just one preset.
  function populateJourneySelects() {
    if (!loadedPOIs || !loadedPOIs.length) return;
    const keepOrig = origSel?.value || "poi_dadu_home";
    const keepDest = destSel?.value || "poi_clinic_bellevue";
    if (origSel) {
      origSel.innerHTML = "";
      loadedPOIs.forEach((p) => {
        const o = document.createElement("option");
        o.value = p.id;
        o.textContent = p.name;
        origSel.appendChild(o);
      });
      if ([...origSel.options].some(o => o.value === keepOrig)) origSel.value = keepOrig;
    }
    if (destSel) {
      destSel.innerHTML = "";
      loadedPOIs.forEach((p) => {
        const o = document.createElement("option");
        o.value = p.id;
        o.textContent = p.name;
        destSel.appendChild(o);
      });
      if ([...destSel.options].some(o => o.value === keepDest)) destSel.value = keepDest;
    }
  }
  // POIs load async — retry until available, then refresh preview once.
  let popTries = 0;
  const popTimer = setInterval(() => {
    popTries += 1;
    if (loadedPOIs && loadedPOIs.length) {
      populateJourneySelects();
      clearInterval(popTimer);
      updateDaduRoutePreview();
    } else if (popTries > 40) {
      clearInterval(popTimer);
    }
  }, 500);

  async function updateDaduRoutePreview() {
    const orig = origSel?.value || "poi_dadu_home";
    const dest = destSel?.value || "poi_clinic_bellevue";
    const origName = origSel?.options[origSel.selectedIndex]?.text || "Start";
    const destName = destSel?.options[destSel.selectedIndex]?.text || "Finish";

    const titleEl = document.getElementById("dadu-preview-title");
    if (titleEl) titleEl.textContent = `${origName.split('(')[0].trim()} → ${destName.split('(')[0].trim()}`;

    try {
      const res = await fetch("/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin: orig,
          destination: dest,
          depart_time: selectedTime,
          sun_tolerance: "low",
          speed_kmh: 3.0
        })
      });
      if (res.ok) {
        const data = await res.json();
        const shadeBadge = document.getElementById("dadu-preview-shade-badge");
        const tradeoffP = document.getElementById("dadu-preview-tradeoff");
        const distEl = document.getElementById("dadu-preview-dist");
        const sunEl = document.getElementById("dadu-preview-sun");

        if (shadeBadge) shadeBadge.textContent = `${Math.round(data.shade_route.shade_percentage)}% Shade`;
        if (tradeoffP) tradeoffP.textContent = data.trade_off_sentence || `At ${selectedTime}, this lane gives ${data.shade_route.shade_percentage}% continuous shade.`;
        if (distEl) distEl.textContent = `${Math.round(data.shade_route.distance_meters)}m`;
        if (sunEl) sunEl.textContent = `${data.shade_route.sun_minutes} mins`;

        // Render immediately on map so the route line + Shade Studio lane list are visible
        renderRouteResult(data, data.trade_off_sentence);
      }
    } catch (_) {}
  }

  if (origSel) origSel.addEventListener("change", updateDaduRoutePreview);
  if (destSel) destSel.addEventListener("change", updateDaduRoutePreview);

  timeBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      timeBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      selectedTime = btn.getAttribute("data-time") || "08:30";
      updateDaduRoutePreview();
    });
  });

  if (embarkBtn && !embarkBtn.__wiredPersonal) {
    embarkBtn.__wiredPersonal = true;
    embarkBtn.addEventListener("click", async () => {
      const orig = origSel?.value || "poi_dadu_home";
      const dest = destSel?.value || "poi_clinic_bellevue";
      if (orig === dest) {
        alert("From and To cannot be the same place.");
        return;
      }
      const mode = modeSel?.value || currentMode || "family";
      const walker = (userWalkerName || document.getElementById("ann-walker-name")?.value || "Walker").trim() || "Walker";
      embarkBtn.disabled = true;
      const oldLabel = embarkBtn.innerHTML;
      embarkBtn.innerHTML = `<span>Starting your journey…</span>`;
      try {
        // Build a REAL personal trip (Groq-assisted when key is set, deterministic otherwise),
        // fixed to the exact From → To + time the user picked.
        const planRes = await fetch("/api/plan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mode,
            origin: orig,
            destination: dest,
            earliest_time: selectedTime,
            latest_time: selectedTime,
            walkers: [{ name: walker, sun_sensitivity: "high", pace: "slow" }],
          })
        });
        if (!planRes.ok) {
          const err = await planRes.json().catch(() => ({}));
          throw new Error(err.detail || "Could not start journey.");
        }
        const plan = await planRes.json();
        const code = plan.trip_code;
        // Enroll me by name so Live Trail shows my spot, stories, chat + shade lanes.
        try {
          await fetch(`/api/trip/${code}/join`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ walker })
          });
        } catch (_) {}
        if (!isUserRegistered) {
          userWalkerName = walker;
          isUserRegistered = true;
          try { localStorage.setItem("chhaya_walker_name", walker); } catch (_) {}
          const nd = document.getElementById("nav-walker-name");
          if (nd) nd.textContent = walker;
        }
        const enrollInput = document.getElementById("trail-enroll-name");
        if (enrollInput) enrollInput.value = walker;
        await switchTripGroup(code);
        switchPage("active-hike");
      } catch (e) {
        alert(e.message || "Could not start journey.");
      } finally {
        embarkBtn.disabled = false;
        embarkBtn.innerHTML = oldLabel;
      }
    });
  }
}

// Enroll-by-name on the Live Trail dashboard: type a name → join trip →
// predefined chain-by-chain path + stories + chat + shade lanes appear.
function setupTrailEnroll() {
  const btn = document.getElementById("btn-trail-enroll");
  const input = document.getElementById("trail-enroll-name");
  if (!btn || btn.__wired) return;
  btn.__wired = true;
  if (input && userWalkerName && !input.value) input.value = userWalkerName;
  const doEnroll = async () => {
    const walker = ((input?.value || "").trim() || userWalkerName || document.getElementById("ann-walker-name")?.value || "Walker").trim();
    if (!walker) {
      alert("Type your name to enroll.");
      return;
    }
    btn.disabled = true;
    try {
      const res = await fetch(`/api/trip/${currentTripCode}/join`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ walker })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Could not enroll.");
      }
      const data = await res.json();
      userWalkerName = walker;
      isUserRegistered = true;
      try { localStorage.setItem("chhaya_walker_name", walker); } catch (_) {}
      const nd = document.getElementById("nav-walker-name");
      if (nd) nd.textContent = walker;
      const hostInput = document.getElementById("ann-walker-name");
      if (hostInput) hostInput.value = walker;
      try { updateGrassPointsWallet(data.points || 5, "trail-enroll"); } catch (_) {}
      // Refresh the Uber-style dashboard: radar, chain-by-chain route, stories, chat.
      await switchTripGroup(currentTripCode);
      document.querySelector('[data-tab="tab-directions"]')?.click();
      setTimeout(() => document.querySelector('[data-tab="tab-radar"]')?.click(), 1800);
    } catch (e) {
      alert(e.message || "Could not enroll.");
    } finally {
      btn.disabled = false;
    }
  };
  btn.addEventListener("click", doEnroll);
  input?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      doEnroll();
    }
  });
}

// Post-to-map during a journey: tap map (or Post tab) → pin title/desc/type →
// saved as a card, rendered on the map + listed beautifully under the form.
let mappostPicked = null;
function setupMapPost() {
  const form = document.getElementById("mappost-form");
  const preview = document.getElementById("mappost-coords-preview");
  const list = document.getElementById("mappost-pins-list");
  const setPicked = (lat, lon) => {
    mappostPicked = { lat, lon };
    if (preview) preview.textContent = `${lat.toFixed(5)}° N, ${lon.toFixed(5)}° E · ready to pin`;
  };
  // Expose for the global map-click handler.
  window.__setMappostPicked = setPicked;
  if (form && !form.__wired) {
    form.__wired = true;
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!mappostPicked) {
        alert("Tap anywhere on the map first — then write what you found.");
        document.querySelector('[data-tab="tab-mappost"]')?.click();
        return;
      }
      const title = document.getElementById("mappost-title")?.value.trim() || "Trail note";
      const desc = document.getElementById("mappost-desc")?.value.trim() || title;
      const typeSel = document.getElementById("mappost-type")?.value || "observation";
      const cardType = typeSel === "shade" ? "tip" : (typeSel === "warning" ? "warning" : (typeSel === "story" ? "story" : "note"));
      const btn = document.getElementById("btn-submit-mappost");
      if (btn) btn.disabled = true;
      try {
        const res = await fetch("/api/cards", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            trip_code: currentTripCode,
            type: cardType,
            text: `${title}: ${desc}`.slice(0, 280),
            lat: mappostPicked.lat,
            lon: mappostPicked.lon,
            visibility: "public",
          })
        });
        if (!res.ok) throw new Error("Could not pin to map.");
        const card = await res.json();
        renderMappostPin(card);
        renderMappostMarker(card);
        form.reset();
        mappostPicked = null;
        if (preview) preview.textContent = "No location picked yet";
      } catch (err) {
        alert(err.message || "Could not pin to map.");
      } finally {
        if (btn) btn.disabled = false;
      }
    });
  }
  loadMappostPins();
}

function renderMappostPin(card) {
  const list = document.getElementById("mappost-pins-list");
  if (!list || !card) return;
  const empty = list.querySelector("p");
  if (empty) empty.remove();
  const row = document.createElement("div");
  row.style.cssText = "background:var(--paper);border:1.5px solid var(--ink);border-radius:6px;padding:8px 10px;font-size:12.5px;";
  row.innerHTML = `<strong>${escapeHtml((card.text || "Trail note").split(":")[0])}</strong><br><span style="color:var(--muted);">${escapeHtml(card.text || "")}</span><br><span style="font-family:var(--font-mono);font-size:10.5px;color:var(--shade);">${card.type || "note"} · ${(card.lat || 0).toFixed(4)}, ${(card.lon || 0).toFixed(4)}</span>`;
  list.prepend(row);
}

function renderMappostMarker(card) {
  try {
    if (!map || card.lat == null || card.lon == null) return;
    const el = document.createElement("div");
    el.className = "poi-marker";
    el.textContent = card.type === "warning" ? "⚠️" : (card.type === "story" ? "📸" : "📍");
    el.title = card.text || "Trail pin";
    cardMarkers.push(new maplibregl.Marker({ element: el }).setLngLat([card.lon, card.lat]).addTo(map));
  } catch (_) {}
}

async function loadMappostPins() {
  const list = document.getElementById("mappost-pins-list");
  try {
    const res = await fetch(`/api/cards/near?lat=${KOLKATA_CENTER[1]}&lon=${KOLKATA_CENTER[0]}&trip_code=${encodeURIComponent(currentTripCode)}&radius=2000`);
    if (!res.ok) return;
    const data = await res.json();
    const cards = data.cards || data.near || data.results || [...(data.immediate_cards || []), ...(data.radar_cards || [])];
    if (list) list.innerHTML = cards.length ? "" : `<p style="font-size:12px;color:var(--muted);">No pins yet — tap the map, describe the shade / food / warning, hit Pin.</p>`;
    cards.slice(0, 20).forEach(c => { renderMappostPin(c); renderMappostMarker(c); });
  } catch (_) {
    if (list && !list.children.length) list.innerHTML = `<p style="font-size:12px;color:var(--muted);">No pins yet — tap the map, describe the shade / food / warning, hit Pin.</p>`;
  }
}

function applyFeedFilters() {
  const activeAgenda = document.querySelector("[data-filter-agenda].active")?.getAttribute("data-filter-agenda") || "all";
  const activeDist = document.querySelector("[data-filter-dist].active")?.getAttribute("data-filter-dist") || "all";
  const activePkg = document.querySelector("[data-filter-pkg].active")?.getAttribute("data-filter-pkg") || "all";

  document.querySelectorAll(".feed-hike-card").forEach(card => {
    const ag = card.getAttribute("data-agenda") || "hike";
    const d = card.getAttribute("data-dist");
    const p = card.getAttribute("data-pkg");
    const matchAgenda = (activeAgenda === "all" || ag === activeAgenda);
    const matchDist = (activeDist === "all" || d === activeDist);
    const matchPkg = (activePkg === "all" || p === activePkg);
    if (matchAgenda && matchDist && matchPkg) card.style.display = "flex";
    else card.style.display = "none";
  });
}

async function loadCommunityFeed() {
  const grid = document.getElementById("community-feed-grid");
  if (!grid) return;
  grid.innerHTML = `<p style="font-size:13px;padding:20px;text-align:center;">Loading community hike feed…</p>`;

  try {
    const res = await fetch("/api/feed");
    const data = await res.json();
    const trips = data.trips || [];

    const countPill = document.getElementById("nav-feed-count");
    if (countPill) countPill.textContent = `${trips.length}`;

    if (!trips.length) {
      grid.innerHTML = `<p style="font-size:13px;padding:20px;">No hikes announced yet. Announce yours above!</p>`;
      return;
    }

    grid.innerHTML = "";
    trips.forEach(t => {
      const card = document.createElement("div");
      card.className = "feed-hike-card";
      const ag = t.agenda || (t.mode === "family" ? "help" : (t.mode === "trail" ? "self" : "hike"));
      card.setAttribute("data-agenda", ag);
      card.setAttribute("data-dist", t.distance_m < 1500 ? "short" : (t.distance_m < 4000 ? "medium" : "long"));
      card.setAttribute("data-pkg", (t.package || "").includes("food") ? "food" : "water");

      const walkersList = (t.walkers || []).slice(0, 4).join(", ") || "Active pack";
      const pkgBadge = (t.package || "").includes("food") ? "☕ Complete Food Package" : "💧 Carry Water";
      const catBadge = t.category || (t.distance_m < 1500 ? "Short stroll" : "Medium trek");
      const agendaBadge = ag === "hike" ? "🥾 Group Hike" : (ag === "help" ? "👵 Help Companion" : "🚶 Self Travel");
      const agendaClass = ag === "hike" ? "agenda-badge-hike" : (ag === "help" ? "agenda-badge-help" : "agenda-badge-self");

      card.innerHTML = `
        <div class="feed-hike-header">
          <div>
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">
              <span class="agenda-pill-badge ${agendaClass}">${agendaBadge}</span>
              <span class="badge-mini">${catBadge}</span>
            </div>
            <h4 class="feed-hike-title">${escapeHtml(t.title || "Kolkata Shaded Hike")}</h4>
            <div class="feed-route-summary">${escapeHtml(t.from || "Start")} → ${escapeHtml(t.to || "Finish")}</div>
          </div>
          <span class="badge badge-accent">${t.shade_percentage ?? 75}% Shade</span>
        </div>
        <div class="feed-tags-row">
          <span class="badge-mini">${Math.round(t.distance_m)}m</span>
          <span class="badge-mini" style="background:var(--sun);">${pkgBadge}</span>
          <span class="badge-mini">${t.sun_minutes ?? 3.5} sun-min</span>
        </div>
        <div class="feed-walkers-row" style="margin-top:6px;">
          <span>🚶 Pack: <strong>${escapeHtml(walkersList)}</strong></span>
        </div>
        <div class="feed-action-dual" style="display:flex;gap:6px;margin-top:8px;">
          <button class="btn btn-primary" style="flex:1.2;justify-content:center;padding:8px 10px;" data-embark-feed="${t.trip_code}">
            <span>🥾 Embark on Trail</span>
          </button>
          <button class="btn btn-glass-sm" style="flex:1;justify-content:center;padding:8px 10px;" data-preview-feed="${t.trip_code}">
            <span>🗺️ View Route</span>
          </button>
          <button class="btn btn-glass-sm" style="flex:1;justify-content:center;padding:8px 10px;" data-join-feed="${t.trip_code}">
            <span>🌱 Join (+5)</span>
          </button>
        </div>
      `;
      grid.appendChild(card);
    });

    // Wire buttons
    grid.querySelectorAll("[data-embark-feed]").forEach(b => {
      b.addEventListener("click", () => {
        const code = b.getAttribute("data-embark-feed");
        promptRegistrationOrEmbark(code);
      });
    });
    grid.querySelectorAll("[data-preview-feed]").forEach(b => {
      b.addEventListener("click", () => {
        const code = b.getAttribute("data-preview-feed");
        switchTripGroup(code);
        switchPage("active-hike");
      });
    });
    grid.querySelectorAll("[data-join-feed]").forEach(b => {
      b.addEventListener("click", () => joinFeedGroup(b.getAttribute("data-join-feed"), b));
    });
  } catch (_) {
    grid.innerHTML = `<p style="font-size:13px;padding:20px;">Feed offline.</p>`;
  }
}

async function joinFeedGroup(code, btn) {
  const walker = ((document.getElementById("trail-enroll-name")?.value || "").trim() || userWalkerName || (document.getElementById("ann-walker-name")?.value || "Walker").trim()) || prompt("Your name?");
  if (!walker) return;
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(`/api/trip/${code}/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ walker })
    });
    if (res.ok) {
      const data = await res.json();
      updateGrassPointsWallet(data.points || 5, "join");
      userWalkerName = walker;
      isUserRegistered = true;
      try { localStorage.setItem("chhaya_walker_name", walker); } catch (_) {}
      const nd = document.getElementById("nav-walker-name");
      if (nd) nd.textContent = walker;
      const enrollInput = document.getElementById("trail-enroll-name");
      if (enrollInput) enrollInput.value = walker;
      alert(`Joined ${code}! (+${data.points || 5} 🌱 Grass Points). Opening Live Trail Dashboard...`);
      await switchTripGroup(code);
      switchPage("active-hike");
    } else {
      const err = await res.json().catch(() => ({}));
      alert(err.detail || "Could not join.");
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

// -------------------------------------------------------------------
// Page 4: Grass Points & Outdoor Passport
// -------------------------------------------------------------------
function setupPassportPage() {
  loadPassportJournal();
}

async function loadPassportJournal() {
  const gallery = document.getElementById("unlocked-stories-gallery");
  const board = document.getElementById("passport-leaderboard-list");
  const walker = (document.getElementById("ann-walker-name")?.value || "Walker").trim();

  try {
    const [storyRes, boardRes] = await Promise.all([
      fetch(`/api/stories/unlocked?walker=${encodeURIComponent(walker)}`),
      fetch("/api/leaderboard?limit=8"),
    ]);
    const stories = (await storyRes.json()).stories || [];
    const leaders = (await boardRes.json()).leaderboard || [];

    const badge = document.getElementById("unlocked-count-badge");
    if (badge) badge.textContent = `${stories.length} Unlocked`;

    if (gallery) {
      if (!stories.length) {
        gallery.innerHTML = `
          <div class="gallery-story-card" style="padding:16px;text-align:center;grid-column:1/-1;">
            <p style="font-size:13px;color:var(--muted);">No stories unlocked yet. Step forward along the trail in Live Trail &amp; Dashboard to unlock geo-tagged discoveries!</p>
          </div>
        `;
      } else {
        gallery.innerHTML = "";
        stories.forEach(st => {
          const card = document.createElement("div");
          card.className = "gallery-story-card";
          const photoSrc = st.photo || (st.text.includes("Banyan") ? banyanSvgDataUri : bakerySvgDataUri);
          card.innerHTML = `
            <img class="gallery-photo" src="${photoSrc}" alt="Discovery photo" />
            <div class="gallery-body">
              <strong style="font-size:14px;">${escapeHtml(st.text.split(":")[0])}</strong>
              <p class="gallery-text">${escapeHtml(st.text)}</p>
              <div style="display:flex;justify-content:space-between;font-family:var(--font-mono);font-size:11px;color:var(--muted);margin-top:4px;">
                <span>🌿 ${Math.round((st.shade_at_creation || 0.88)*100)}% Shade</span>
                <span>${(st.unlocked_at || "").slice(0, 10)}</span>
              </div>
            </div>
          `;
          gallery.appendChild(card);
        });
      }
    }

    if (board) {
      board.innerHTML = "";
      leaders.forEach((l, idx) => {
        const row = document.createElement("div");
        row.style.cssText = "display:flex;justify-content:space-between;padding:8px;border-bottom:1px solid var(--paper-deep);font-size:13.5px;";
        const medal = idx === 0 ? "🥇" : (idx === 1 ? "🥈" : (idx === 2 ? "🥉" : `#${idx+1}`));
        row.innerHTML = `
          <div><strong>${medal} ${escapeHtml(l.walker)}</strong></div>
          <div style="font-family:var(--font-mono);font-weight:700;color:var(--shade);">${l.points} 🌱 <small style="color:var(--muted);">(${l.events} events)</small></div>
        `;
        board.appendChild(row);
      });
    }
  } catch (_) {}
}


// -------------------------------------------------------------------
// Bengali/English toggle (static/locale.json; computed numbers untouched)
// -------------------------------------------------------------------
function t(key) {
  if (LOCALES[currentLang] && LOCALES[currentLang][key] != null) return LOCALES[currentLang][key];
  if (LOCALES.en && LOCALES.en[key] != null) return LOCALES.en[key];
  return key;
}

// Localized text with a hard English fallback (used before locale loads)
function lt(key, fallback) {
  const v = t(key);
  return v === key ? fallback : v;
}

async function loadLocale() {
  try {
    const res = await fetch("/static/locale.json");
    LOCALES = await res.json();
  } catch (_) { LOCALES = {}; }
  wireLangToggle();
  applyLocale(currentLang === "bn" ? "bn" : "en");
}

function wireLangToggle() {
  const btn = document.getElementById("lang-toggle");
  if (!btn || btn.__wired) return;
  btn.__wired = true;
  btn.addEventListener("click", () => applyLocale(currentLang === "bn" ? "en" : "bn"));
}

function applyLocale(lang) {
  currentLang = lang === "bn" ? "bn" : "en";
  try { localStorage.setItem("chhaya-lang", currentLang); } catch (_) {}
  document.documentElement.lang = currentLang;
  document.querySelectorAll("[data-i18n]").forEach(el => { el.innerHTML = t(el.getAttribute("data-i18n")); });
  document.querySelectorAll("[data-i18n-ph]").forEach(el => { el.setAttribute("placeholder", t(el.getAttribute("data-i18n-ph"))); });
  const toggle = document.getElementById("lang-toggle");
  if (toggle) toggle.title = t("lang.toggleTitle");
  // dynamic mode label follows the toggle
  setAppMode(currentMode);
}

// -------------------------------------------------------------------
// Paper-pass signature helpers (visual only — no data/API/route changes)
// -------------------------------------------------------------------
const REDUCED_MOTION = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function updateSundial(timeStr) {
  const svg = document.getElementById("gnomon-shadow");
  if (!svg || !timeStr) return;
  const parts = String(timeStr).split(":");
  const h = parseFloat(parts[0]) + (parseFloat(parts[1] || 0) / 60);
  const t = Math.min(18, Math.max(6, h));
  const ang = ((t - 12) / 6) * 62; // -62deg at 6AM .. +62deg at 6PM
  const rad = (ang * Math.PI) / 180;
  const len = 40;
  const x2 = 60 + Math.sin(rad) * len;
  const y2 = 60 - Math.cos(rad) * len;
  svg.setAttribute("x2", x2.toFixed(1));
  svg.setAttribute("y2", y2.toFixed(1));
  const ticks = document.getElementById("sundial-ticks");
  if (ticks && !ticks.children.length) {
    for (let hh = 6; hh <= 18; hh += 1) {
      const a = (((hh - 12) / 6) * 62 * Math.PI) / 180;
      const x1 = 60 + Math.sin(a) * 44, y1 = 60 - Math.cos(a) * 44;
      const x2t = 60 + Math.sin(a) * 50, y2t = 60 - Math.cos(a) * 50;
      const ln = document.createElementNS("http://www.w3.org/2000/svg", "line");
      ln.setAttribute("x1", x1); ln.setAttribute("y1", y1);
      ln.setAttribute("x2", x2t); ln.setAttribute("y2", y2t);
      ticks.appendChild(ln);
    }
  }
}

function modulateBuildings(elev, azim) {
  // Warm clay light shift with real sun elevation (visual only)
  if (!map || !map.getLayer("buildings-3d")) return;
  try {
    const lift = Math.min(1, Math.max(0, (elev || 30) / 60));
    const col = lift > 0.75 ? "#D2410D" : (lift > 0.4 ? "#B8553A" : "#8F4A34");
    map.setPaintProperty("buildings-3d", "fill-extrusion-color",
      ["case", ["boolean", ["feature-state", "hover"], false], "#D2410D", col]);
  } catch (_) {}
}

function updateSunGauge(sunMinutes, comparison) {
  const fill = document.getElementById("gauge-fill");
  const needle = document.getElementById("gauge-needle");
  const label = document.getElementById("gauge-label");
  const ticks = document.getElementById("gauge-ticks");
  if (ticks && !ticks.children.length) {
    for (let i = 0; i <= 8; i++) {
      const a = (Math.PI * i) / 8;
      const x1 = 100 - Math.cos(a) * 72, y1 = 100 - Math.sin(a) * 72;
      const x2 = 100 - Math.cos(a) * 80, y2 = 100 - Math.sin(a) * 80;
      const ln = document.createElementNS("http://www.w3.org/2000/svg", "line");
      ln.setAttribute("x1", x1); ln.setAttribute("y1", y1);
      ln.setAttribute("x2", x2); ln.setAttribute("y2", y2);
      ticks.appendChild(ln);
    }
  }
  const budget = 4.0;
  const frac = Math.min(1, (sunMinutes || 0) / budget);
  const ARC = 271;
  if (fill) {
    fill.style.strokeDasharray = String(ARC);
    fill.style.strokeDashoffset = String(ARC * (1 - frac));
    fill.setAttribute("stroke", frac < 0.5 ? "#1F4D3A" : (frac < 0.8 ? "#F2A900" : "#C8321E"));
  }
  if (needle) {
    const a = Math.PI * (1 - frac);
    needle.setAttribute("x2", (100 - Math.cos(a) * 62).toFixed(1));
    needle.setAttribute("y2", (100 - Math.sin(a) * 62).toFixed(1));
  }
  if (label) label.textContent = `${(sunMinutes || 0).toFixed(1)} / ${budget.toFixed(1)} sun-min`;
}

function drawSweepCurve(results, bestTime) {
  const svg = document.getElementById("sweep-curve-svg");
  if (!svg || !results || !results.length) return;
  const W = 320, H = 90, PAD = 8;
  const maxSun = Math.max(...results.map(r => r.sun_minutes), 1.0);
  const minSun = Math.min(...results.map(r => r.sun_minutes), 0);
  const X = i => PAD + (i / Math.max(1, results.length - 1)) * (W - PAD * 2);
  const Y = v => H - PAD - ((v - minSun) / Math.max(0.001, maxSun - minSun)) * (H - PAD * 2 - 14);
  let d = "";
  results.forEach((r, i) => { d += (i === 0 ? "M" : "L") + X(i).toFixed(1) + " " + (Y(r.sun_minutes) + ((i % 2) ? 1.2 : -1.2)).toFixed(1) + " "; });
  const best = results.find(r => r.is_best) || results.reduce((a, b) => (a.sun_minutes <= b.sun_minutes ? a : b));
  const bi = results.indexOf(best);
  svg.innerHTML =
    `<path d="${d}" fill="none" stroke="#2A1F17" stroke-width="2.5" stroke-linejoin="round"/>` +
    `<circle cx="${X(bi)}" cy="${Y(best.sun_minutes)}" r="5" fill="#C8321E" stroke="#2A1F17" stroke-width="2"/>` +
    `<text x="${Math.min(W - 118, X(bi) + 9)}" y="${Math.max(14, Y(best.sun_minutes) - 8)}" font-family="IBM Plex Mono,monospace" font-size="10" font-weight="700" fill="#C8321E" transform="rotate(-3 ${X(bi)} ${Y(best.sun_minutes)})">LEAVE AT ${best.start_time}</text>`;
}

// Route draws itself on load (progressive reveal, transform-free, skips on reduced motion)
let routeDrawRaf = null;
function animateRouteDraw(shadeFeatures) {
  if (!map || !map.getSource("shade-route-data") || !shadeFeatures || !shadeFeatures.length) return;
  try {
    if (REDUCED_MOTION) {
      map.getSource("shade-route-data").setData({ type: "FeatureCollection", features: shadeFeatures });
      return;
    }
    if (routeDrawRaf) cancelAnimationFrame(routeDrawRaf);
    const t0 = performance.now(), DUR = 900;
    function frame(t) {
      const p = Math.min(1, (t - t0) / DUR);
      const n = Math.max(1, Math.floor(shadeFeatures.length * p));
      map.getSource("shade-route-data").setData({ type: "FeatureCollection", features: shadeFeatures.slice(0, n) });
      if (p < 1) routeDrawRaf = requestAnimationFrame(frame);
      else map.getSource("shade-route-data").setData({ type: "FeatureCollection", features: shadeFeatures });
    }
    routeDrawRaf = requestAnimationFrame(frame);
  } catch (_) {
    try { map.getSource("shade-route-data").setData({ type: "FeatureCollection", features: shadeFeatures }); } catch (_) {}
  }
}

// Ink-ring proximity pulse near cards (expanding outlines, no blur/glow)
function addInkRing(lngLat) {
  try {
    const rings = document.querySelectorAll(".ink-ring");
    rings.forEach(r => r.remove());
    const pt = map.project(lngLat);
    const host = map.getCanvasContainer();
    const el = document.createElement("div");
    el.className = "ink-ring";
    el.style.left = (pt.x - 10) + "px";
    el.style.top = (pt.y - 10) + "px";
    host.appendChild(el);
    setTimeout(() => el.remove(), 3400);
  } catch (_) {}
}

// Warm-paper theme toggle (light/dark both warm, never blue-black)
function initPaperTheme() {
  const btn = document.getElementById("theme-toggle");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const html = document.documentElement;
    html.setAttribute("data-theme", html.getAttribute("data-theme") === "dark" ? "light" : "dark");
  });
}
document.addEventListener("DOMContentLoaded", () => {
  initPaperTheme();
  updateSundial((document.getElementById("time-display") || {}).textContent || "15:00");
  try { updateSunGauge(0, null); } catch (_) {}
  try { refreshAccuracyMeter(); } catch (_) {}
});

