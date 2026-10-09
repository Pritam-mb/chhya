// ===================================================================
// Chhaya (ছায়া) — Paper Map & Agent Client (visual pass, logic untouched)
// ===================================================================

const KOLKATA_CENTER = [88.3530, 22.5510]; // Park Street & Camac Street, Kolkata
let map = null;
let currentRouteData = null;
let currentTripData = null;
let currentTripCode = "dadu-clinic";
let currentMode = "family";
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
  setupRadarActions();
  setupQrActions();
  loadBestWindowWidget();
  loadPOIs();
  checkUrlRouteOnLoad();

  // Trigger initial demo scenario after map renders
  setTimeout(() => {
    loadRoute("Walk Dadu to the clinic around noon, he can't take much sun.", null, "family");
  }, 1200);
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

// Setup Quick Dropdown Selector Buttons
function setupQuickSelectors() {
  const btn = document.getElementById("quick-route-btn");
  if (btn) {
    btn.addEventListener("click", () => {
      const orig = document.getElementById("origin-select").value;
      const dest = document.getElementById("destination-select").value;
      if (!orig || !dest) {
        alert("Please select both Origin and Destination landmarks.");
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
    if (mode === "family") modeLabel.textContent = "Family Walk Plan (Dadu)";
    else if (mode === "club") modeLabel.textContent = "Club Regroup Plan (Camac Loop)";
    else if (mode === "trail") modeLabel.textContent = "Trail Hike Plan (GPX Regroup)";
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
  // Walker vs Watcher view switcher
  const btnWalker = document.getElementById("view-mode-walker");
  const btnWatcher = document.getElementById("view-mode-watcher");
  const contentWalker = document.getElementById("view-content-walker");
  const contentWatcher = document.getElementById("view-content-watcher");

  if (btnWalker && btnWatcher) {
    btnWalker.addEventListener("click", () => {
      btnWalker.classList.add("active");
      btnWatcher.classList.remove("active");
      contentWalker.classList.remove("hidden");
      contentWatcher.classList.add("hidden");
    });
    btnWatcher.addEventListener("click", () => {
      btnWatcher.classList.add("active");
      btnWalker.classList.remove("active");
      contentWatcher.classList.remove("hidden");
      contentWatcher.classList.add("hidden");
      refreshWatcherTimeline(currentTripCode);
    });
  }

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
        const res = await fetch(`/api/trip/${currentTripCode}/reached`, { method: "POST" });
        const data = await res.json();
        tapReachedBtn.querySelector("span").textContent = "✅ Safely Reached (Ping Sent!)";
        tapReachedBtn.style.background = "#1F4D3A";

        // Update Watcher view
        const wIcon = document.getElementById("watcher-status-icon");
        const wTitle = document.getElementById("watcher-status-title");
        const wDesc = document.getElementById("watcher-status-desc");
        if (wIcon) wIcon.textContent = "🎉";
        if (wTitle) wTitle.textContent = "Reached Safely!";
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

  // Submit Leave Card form
  const form = document.getElementById("leave-card-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const type = document.getElementById("card-type-select").value;
      const text = document.getElementById("card-text-input").value.trim();
      if (!text) return;

      const postBtn = document.getElementById("btn-post-card");
      postBtn.disabled = true;
      postBtn.querySelector("span").textContent = "Moderating & Posting...";

      try {
        const res = await fetch("/api/cards", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            trip_code: currentTripCode,
            type: type,
            text: text,
            lat: KOLKATA_CENTER[1],
            lon: KOLKATA_CENTER[0],
            visibility: "public",
            shade_at_creation: 0.82
          })
        });
        const saved = await res.json();
        document.getElementById("card-text-input").value = "";
        tabView.click();
        loadNearbyCards(KOLKATA_CENTER[1], KOLKATA_CENTER[0]);
      } catch (err) {
        console.error("Post card error:", err);
      } finally {
        postBtn.disabled = false;
        postBtn.querySelector("span").textContent = "Pin Card to Location";
      }
    });
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
      const icon = c.type === "warning" ? "⚠️" : (c.type === "meetup" ? "☕" : "💡");
      item.innerHTML = `
        <div class="repair-card-header">
          <span>${icon} ${c.type.toUpperCase()}</span>
          <span style="color:#1F4D3A; font-size:10px;">${c.distance_m}m ${c.bearing}</span>
        </div>
        <div class="repair-card-desc">"${c.text}"</div>
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
    const icon = c.type === "warning" ? "⚠️" : (c.type === "meetup" ? "☕" : "💡");
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

