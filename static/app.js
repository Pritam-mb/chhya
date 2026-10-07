// ===================================================================
// Chhaya (ছায়া) — Map & Agent Client Application
// ===================================================================

const KOLKATA_CENTER = [88.3530, 22.5510]; // Park Street & Camac Street, Kolkata
let map = null;
let currentRouteData = null;
let isPlaying = false;
let playInterval = null;
let currentBriefingText = "";

// Initialize Application
document.addEventListener("DOMContentLoaded", async () => {
  initMap();
  setupSlider();
  setupForm();
  setupChips();
  setupVoice();
  loadBestWindowWidget();
  
  // Trigger initial demo scenario at 3 PM
  setTimeout(() => {
    loadRoute("Walk dadu to the clinic around 3 pm, he can't take much sun.", "15:00");
  }, 1200);
});

// 1. Map Initialization
function initMap() {
  map = new maplibreGl.Map({
    container: "map",
    style: {
      version: 8,
      sources: {
        "carto-dark": {
          type: "raster",
          tiles: [
            "https://a.basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}@2x.png",
            "https://b.basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}@2x.png"
          ],
          tileSize: 256,
          attribution: "&copy; OpenStreetMap contributors &copy; CARTO"
        }
      },
      layers: [
        {
          id: "carto-dark-layer",
          type: "raster",
          source: "carto-dark",
          minzoom: 0,
          maxzoom: 20
        }
      ]
    },
    center: KOLKATA_CENTER,
    zoom: 16.2,
    pitch: 42,
    bearing: -15,
    antialias: true
  });

  map.addControl(new maplibreGl.NavigationControl(), "top-left");

  map.on("load", () => {
    addBuildingsLayer();
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

    // 3D Extruded Buildings
    map.addLayer({
      id: "buildings-3d",
      type: "fill-extrusion",
      source: "buildings-data",
      paint: {
        "fill-extrusion-color": [
          "case",
          ["boolean", ["feature-state", "hover"], false],
          "#38bdf8",
          "#1e293b"
        ],
        "fill-extrusion-height": ["get", "height"],
        "fill-extrusion-base": 0,
        "fill-extrusion-opacity": 0.88
      }
    });

    // Building Roof Borders
    map.addLayer({
      id: "buildings-outline",
      type: "line",
      source: "buildings-data",
      paint: {
        "line-color": "rgba(255, 255, 255, 0.15)",
        "line-width": 1
      }
    });
  } catch (e) {
    console.warn("Could not load local buildings layer:", e);
  }
}

// 3. Add Dynamic Building Shadows Layer
function addShadowsLayer() {
  map.addSource("shadows-data", {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] }
  });

  map.addLayer(
    {
      id: "building-shadows",
      type: "fill",
      source: "shadows-data",
      paint: {
        "fill-color": "#060913",
        "fill-opacity": 0.68
      }
    },
    "buildings-3d" // Render under 3D buildings
  );

  map.addLayer(
    {
      id: "building-shadows-blur",
      type: "line",
      source: "shadows-data",
      paint: {
        "line-color": "#060913",
        "line-width": 2,
        "line-opacity": 0.4
      }
    },
    "buildings-3d"
  );
}

// 4. Add Dual Route Layers
function addRouteLayers() {
  // Shortest path baseline (purple dashed)
  map.addSource("shortest-route-data", {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] }
  });

  map.addLayer({
    id: "shortest-route-line",
    type: "line",
    source: "shortest-route-data",
    paint: {
      "line-color": "#8b5cf6",
      "line-width": 4,
      "line-dasharray": [2, 2],
      "line-opacity": 0.75
    }
  });

  // Shade Route (split into shaded vs exposed segments)
  map.addSource("shade-route-data", {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] }
  });

  // Glowing casing for shaded route
  map.addLayer({
    id: "shade-route-casing",
    type: "line",
    source: "shade-route-data",
    paint: {
      "line-color": [
        "case",
        ["get", "is_shaded"],
        "rgba(16, 185, 129, 0.4)",
        "rgba(239, 68, 68, 0.4)"
      ],
      "line-width": 10,
      "line-blur": 3
    }
  });

  // Core route line
  map.addLayer({
    id: "shade-route-core",
    type: "line",
    source: "shade-route-data",
    paint: {
      "line-color": [
        "case",
        ["get", "is_shaded"],
        "#10b981", // Green where shaded
        "#ef4444"  // Red where exposed
      ],
      "line-width": 5,
      "line-cap": "round",
      "line-join": "round"
    }
  });
}

// 5. Update Building Shadows from API
async function updateShadowsForTime(timeStr) {
  try {
    const res = await fetch(`/shadows?time=${encodeURIComponent(timeStr)}`);
    const geojson = await res.json();
    
    if (map.getSource("shadows-data")) {
      map.getSource("shadows-data").setData(geojson);
    }

    // Update solar badge
    const props = geojson.properties || {};
    const elev = props.solar_elevation ?? 30.2;
    const factor = props.shadow_factor ?? 1.72;
    const badge = document.getElementById("solar-badge");
    badge.textContent = `Solar: ${elev}° (${factor}x shadow)`;

    // Check High Noon honesty alert
    const noonAlert = document.getElementById("noon-alert");
    if (elev > 55.0) {
      noonAlert.classList.remove("hidden");
    } else {
      noonAlert.classList.add("hidden");
    }
  } catch (err) {
    console.error("Failed to update shadows:", err);
  }
}

// 6. Daylight Slider Setup
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

    // If active route, re-route with new time
    if (currentRouteData) {
      recomputeActiveRoute(timeStr);
    }
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
    }, 1200);
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

  document.getElementById("noon-alert-close").addEventListener("click", () => {
    document.getElementById("noon-alert").classList.add("hidden");
  });
}

// 7. Form Submission & Agent Call
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

  document.getElementById("hud-close").addEventListener("click", () => {
    document.getElementById("route-hud").classList.add("hidden");
  });
}

// 8. Preset Chips
function setupChips() {
  const chips = document.querySelectorAll(".chip");
  chips.forEach((c) => {
    c.addEventListener("click", () => {
      chips.forEach((x) => x.classList.remove("chip-active"));
      c.classList.add("chip-active");
      const prompt = c.getAttribute("data-prompt");
      document.getElementById("prompt-input").value = prompt;
      loadRoute(prompt);
    });
  });
}

// 9. Load Route via Agent
async function loadRoute(promptText, overrideTime = null) {
  const submitBtn = document.getElementById("submit-btn");
  submitBtn.disabled = true;
  submitBtn.innerHTML = `<span>Routing...</span>`;

  try {
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
      alert("Route error: " + (data.error || data.reply));
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

// 10. Render Route Result
function renderRouteResult(routeData, agentReply) {
  currentRouteData = routeData;

  // Sync slider with route depart time
  const [hr, mn] = routeData.depart_time.split(":").map(Number);
  const stepVal = hr * 2 + (mn >= 30 ? 1 : 0);
  const slider = document.getElementById("time-slider");
  if (slider) {
    slider.value = stepVal;
    document.getElementById("time-display").textContent = routeData.depart_time;
  }
  updateShadowsForTime(routeData.depart_time);

  // Render Shaded Route Segments (FeatureCollection of lines with is_shaded properties)
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
      type: "Feature",
      geometry: {
        type: "LineString",
        coordinates: shortestCoords
      }
    });
  }

  // Fit camera bounds to route
  if (routeData.shade_route.coordinates && routeData.shade_route.coordinates.length > 0) {
    const coords = routeData.shade_route.coordinates;
    const bounds = coords.reduce(
      (b, c) => b.extend(c),
      new maplibreGl.LngLatBounds(coords[0], coords[0])
    );
    map.fitBounds(bounds, { padding: { top: 100, bottom: 120, left: 60, right: 380 }, duration: 1000 });
  }

  // Update HUD Cards
  const hud = document.getElementById("route-hud");
  hud.classList.remove("hidden");

  document.getElementById("hud-title").textContent = 
    `${routeData.origin.name} → ${routeData.destination.name}`;

  const saved = routeData.comparison.sun_minutes_saved;
  document.getElementById("saved-sun-mins").textContent = 
    saved > 0 ? `+${saved.toFixed(1)}` : "0.0";

  // Shade Route Stats
  document.getElementById("shade-sun-mins").textContent = `${routeData.shade_route.sun_minutes} mins`;
  document.getElementById("shade-total-mins").textContent = `${routeData.shade_route.duration_minutes} mins`;
  document.getElementById("shade-dist").textContent = `${routeData.shade_route.distance_meters}m`;
  document.getElementById("shade-bar").style.width = `${routeData.shade_route.shade_percentage}%`;
  document.getElementById("shade-pct").textContent = `${routeData.shade_route.shade_percentage}% shaded lanes`;

  // Shortest Route Stats
  document.getElementById("shortest-sun-mins").textContent = `${routeData.shortest_route.sun_minutes} mins`;
  document.getElementById("shortest-total-mins").textContent = `${routeData.shortest_route.duration_minutes} mins`;
  document.getElementById("shortest-dist").textContent = `${routeData.shortest_route.distance_meters}m`;
  document.getElementById("shortest-bar").style.width = `${routeData.shortest_route.shade_percentage}%`;
  document.getElementById("shortest-pct").textContent = `${routeData.shortest_route.shade_percentage}% shaded`;

  // Trade-off explanation
  document.getElementById("tradeoff-text").textContent = routeData.trade_off_sentence;

  // Voice briefing script
  currentBriefingText = `Walking from ${routeData.origin.name} to ${routeData.destination.name} at ${routeData.depart_time}. ${routeData.trade_off_sentence}`;
  document.getElementById("voice-script").textContent = `"${currentBriefingText}"`;
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

// 11. Voice Briefing (ElevenLabs & Web Speech fallback)
function setupVoice() {
  const voiceBtn = document.getElementById("voice-play-btn");
  const providerTag = document.getElementById("voice-provider-tag");

  voiceBtn.addEventListener("click", async () => {
    if (!currentBriefingText) return;
    voiceBtn.disabled = true;
    voiceBtn.querySelector("span").textContent = "Synthesizing...";

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
        audio.play();
      } else {
        // Fallback to Web Speech API
        providerTag.textContent = "Browser Speech Active";
        if ("speechSynthesis" in window) {
          const utterance = new SpeechSynthesisUtterance(currentBriefingText);
          utterance.rate = 0.95;
          window.speechSynthesis.speak(utterance);
        }
      }
    } catch (e) {
      console.warn("Speech synthesis fallback:", e);
      if ("speechSynthesis" in window) {
        const utterance = new SpeechSynthesisUtterance(currentBriefingText);
        window.speechSynthesis.speak(utterance);
      }
    } finally {
      voiceBtn.disabled = false;
      voiceBtn.querySelector("span").textContent = "Replay Briefing";
    }
  });
}

// 12. Load Best Window Widget (TabPFN)
async function loadBestWindowWidget() {
  try {
    const res = await fetch("/window");
    const data = await res.json();

    document.getElementById("best-window-time").textContent = data.best_window;
    document.getElementById("best-window-reason").textContent = data.explanation;

    const list = document.getElementById("window-list");
    list.innerHTML = "";

    (data.windows || []).slice(0, 4).forEach((w) => {
      const item = document.createElement("div");
      item.className = "window-item" + (w.is_recommended ? " active" : "");
      item.innerHTML = `
        <span>${w.time_window} (${w.label})</span>
        <strong style="color: ${w.is_recommended ? '#34d399' : '#f87171'}">${w.discomfort_score}/100</strong>
      `;
      list.appendChild(item);
    });
  } catch (e) {
    console.error("Failed to load best window:", e);
  }
}
