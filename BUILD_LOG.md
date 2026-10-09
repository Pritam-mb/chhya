# Chhaya (ছায়া) — Build & Decision Log

**Project:** Chhaya — Kolkata Shade-Aware Navigation Map & Agent  
**Challenge:** Hacktoberfest Open-Source AI Challenge 2026 (Week 1: Touch Grass)  
**Session Started:** Oct 8, 2026  
**Log Maintained By:** Antigravity AI Pair Programmer & Teammate  

---

## 1. Project Initialization & Git Setup
- Initialized a brand new Git repository in `d:/chya` (strictly complying with the "New Project Only" constraint inside the challenge window).
- Initial commit `e427231` recorded inside the challenge window.
- Configured `.gitignore` for Python environments, Node modules, data caches, `.env` files, and build artifacts.
- Target Neighborhood selected: **Park Street & Camac Street, Kolkata** (dense colonial & modern urban fabric with tall buildings, narrow lanes like Middleton Row, and prominent medical centers like Belle Vue Clinic and Park Clinic).

---

## 2. Real GIS Data Extraction from OpenStreetMap
- **Script:** `scripts/fetch_osm.py` queried the OpenStreetMap Overpass API for bounding box `[22.5470, 88.3480, 22.5565, 88.3585]`.
- **Downloaded:** 5,455 raw OSM elements (`data/osm_raw.json`).
- **Processor:** `scripts/process_osm.py` converted raw OSM into:
  - `data/buildings.geojson`: **650 building footprints** with tagged heights/levels or default 16m (~4-5 storeys).
  - `data/streets.geojson`: Walkable street segments.
  - `data/street_graph.json`: **1,203 bidirectional street segments** across **1,108 intersection nodes**.
  - `data/pois.json`: Key Points of Interest:
    - *Dadu's Residence (Middleton Row)*
    - *Belle Vue Clinic (Dr. U. N. Brahmachari St)*
    - *Park Clinic (Gorky Terrace)*
    - *Flurys Tea Room (Park Street)*
    - *Oxford Bookstore (Park Street)*
    - *Camac Street Mall & Offices*
    - *Russell Street Market & Pharmacy*

---

## 3. Solar Geometry & UTM Metric Shadow Engine (`backend/geo_shadows.py`)
- **Metric Projection:** All geometry math is calculated in **UTM Zone 45N (EPSG:32645)**, converting to meters rather than raw latitude/longitude degrees to avoid distortion.
- **NOAA Solar Position Algorithm:** Computes exact solar elevation $\alpha$ and azimuth $\phi$ for Kolkata coordinates (22.5510° N, 88.3530° E, UTC+5:30).
- **Shadow Extrusion:**
  - Shadow length factor: $s_f = 1 / \tan(\alpha)$
  - Anti-solar vector: $\phi_{\text{shadow}} = (\phi + 180^\circ) \pmod{360^\circ}$
  - Roof vertex displacement in UTM meters: $dx = \sin(\phi_{\text{shadow}}) \cdot (h \cdot s_f)$, $dy = \cos(\phi_{\text{shadow}}) \cdot (h \cdot s_f)$
  - Extruded shadow polygon = convex hull of building base and roof offset.
  - Merged using Shapely `unary_union` and projected back to WGS84 GeoJSON.
- **Verification (`tests/test_shadows.py`):**
  - **09:00 IST:** Elevation 44.98°, Azimuth 124.21°, Shadow factor 1.001x
  - **12:00 IST (High Noon):** Elevation 60.53°, Azimuth 198.48°, Shadow factor **0.565x** (shadows barely reach the street!)
  - **15:00 IST (The Demo Hour):** Elevation 30.16°, Azimuth 248.66°, Shadow factor **1.721x** (~3x longer than noon, casting deep lane shade!)
  - **Execution speed:** 650 buildings processed in **0.100s**.

---

## 4. Shade-Aware Street Graph Routing Engine (`backend/routing.py`)
- **Cost Function:**
  $$c_e = \ell_e \,(1 + k\, s_e), \qquad s_e \in [0, 1]$$
  where $\ell_e$ is length in meters, $s_e$ is sunlit fraction of the street segment (0 = full shade, 1 = full sun), and $k$ is the sun aversion penalty ($k=4.5$ for low tolerance / dadu).
- **Sun-Minutes Counter:**
  $$\text{sun-minutes} = \sum_e \frac{\ell_e \, s_e}{v}$$
  with walking speed $v = 3.0\text{ km/h} \approx 50\text{ m/min}$.
- **Dual Path Dijkstra:** Simultaneously solves Shortest Path ($k=0$) and Shade-Aware Path ($k=4.5$).
- **One-Sentence Trade-Off:** Automatically synthesized explanation comparing distance difference, walking time, and sun-minutes saved.
- **Divergence Verification (`tests/find_differing_routes.py`):**
  - Found **12 distinct POI pairs** where the shade route takes an alternate path (e.g., detour through shaded Middleton Row / Little Russell St instead of broad exposed avenues), fulfilling acceptance requirement P0-2!

---

## 5. Agent Natural Language Parser (`backend/agent_parser.py`)
- **Supported Backends:**
  - **Groq API:** Llama-3.3-70b-versatile or Qwen-2.5-32b for near-instant open-weight inference.
  - **Local Ollama:** `http://localhost:11434` fallback.
  - **100% Offline Rule/Regex Engine:** High-precision deterministic parser that runs on the host machine without any internet connection (fulfills P0-4 requirement).
- **Multilingual normalization:** Romanized Bengali/Hindi is rewritten to English tokens before parsing (`bari/ghor/ghar`→home, `klinik`→clinic, `daktar`→doctor, `bazar`→market, `roddur/dhup/dhoop`→sun words, `tay/baje`→am/pm, `dhire/aaram`→slow, `jaldi`→fast), with `X theke Y` / `X se Y` route patterns and `dadu ke <place> niye chalo` destination patterns.
- **Benchmark Evaluation (`tests/parser_test_set.json`, `scripts/benchmark_parser.py`):**
  - Hand-written, code-mixed set of **30 requests** (10 English, 8 romanized Bengali, 6 romanized Hindi, 6 code-mixed).
  - **Offline deterministic parser: 30/30 (100%)** on origin, destination, depart-time and sun-tolerance; per-field scoring uses the real `RoutingEngine` resolver, so synonyms count as correct. Report: `results/parser_offline.json`.
  - **Groq open-weight parser: 20/30 (66.7%)** with `openai/gpt-oss-120b` (`results/parser_groq.json`). The LLM slips on romanized time words (`baje` → am/pm), `dupahar/bikel` mappings, and sun-tolerance cues that the deterministic rules encode exactly — an honest and mildly surprising result (the small rule parser beats the hosted LLM on this niche set). `llama-3.3-70b-versatile` was retired from Groq's catalog, so the code now auto-selects from `GROQ_MODEL` (default `openai/gpt-oss-120b`, then `qwen/qwen3.8-27b`, then `openai/gpt-oss-20b`).
  - **Anti-fake guard:** `score_parser(..., require_source_prefix="groq")` records the `parser_source` seen per request, so if every call silently fell back to offline the report is written with `status: model_unavailable` instead of claiming LLM accuracy.
  - **Caveat:** this set was written by us and the offline parser was iterated against it, so its 100% is a co-developed, not a held-out, number. It is published as-is for transparency. The Groq number is a genuine, untuned run.

---

## 6. Best-Window Forecaster: TabPFN + Climatology (`backend/best_window.py`)
> **Superseded in Workstream 4 (section 14).** The original version used `np.random` synthetic data and a hard-coded MAE. It is now trained on real Open-Meteo archive data with a computed, held-out MAE. The numbers below were placeholders and must not be quoted.
- Fulfills requirement F6 (committed TabPFN partner category, $200 prize).

---

## 7. Voice Briefing Integration (`backend/voice.py`)
- Fulfills requirement F7 (ElevenLabs partner category, $100 prize).
- Integrates ElevenLabs Text-to-Speech API (`eleven_monolingual_v1`, voice ID: Rachel).
- Includes automatic fallback to browser Web Speech Synthesis if `ELEVENLABS_API_KEY` is not set.

---

## 8. Complete FastAPI Application Server (`backend/main.py`)
- Endpoints implemented:
  - `GET /`: Serves rich MapLibre client application.
  - `GET /health`: Health status and coordinates.
  - `GET /pois`: Returns list of neighborhood landmarks and medical centers.
  - `GET /shadows?time=HH:MM`: Returns building shadow polygons for any 30-min daylight step.
  - `POST /route`: Solves dual routes and returns GeoJSON segments colored by exposure.
  - `GET /window?date=YYYY-MM-DD`: Returns TabPFN best-window forecast.
  - `POST /agent/chat`: Full natural language to route flow.
  - `POST /voice/briefing`: Generates spoken audio summary.
  - `GET /static/*`: Serves client JS, CSS, and GeoJSON datasets.

---

## 9. Interactive Map UI & Client Experience (`static/`)
- **Technology Choice:** Modern Vanilla ES6 modules + MapLibre GL 4.7.1 + Custom CSS Design Tokens (zero build step, instant startup, no Node dependencies required).
- **Files Created:**
  - `static/index.html`: UI structure with glassmorphism layout, 30-minute Daylight Timeline Slider, Prompt input with Kolkata presets, Right-side Route HUD, and Bottom-left TabPFN Weather Widget.
  - `static/style.css`: Visual design tokens with dark glassmorphic panels, Emerald Shade accents (`#10b981`), Amber Solar tags (`#f59e0b`), and exposure glowing effects.
  - `static/app.js`: Complete client logic binding MapLibre 3D building extrusions, real-time shadow updates on slider drag, auto-sweep daylight play/pause animation, route rendering (Green for shade, Red for exposure, dashed purple for shortest baseline), and speech synthesis.
  - **High-Noon Honesty Banner:** Automatically pops up at 12:00 PM alerting users that building shadows shrink to 0.56x height and barely reach street pavements.

---

## 10. Acceptance Checklist Status (against `Chhaya — MVP.md`)

| MVP Item | Requirement | Status | Verification Detail |
|---|---|---|---|
| **P0-1** | Shadow map for demo area | **DONE** | Slider updates shadow polygons in 30-min steps from 6 AM to 6 PM via NOAA solar math & UTM Zone 45N extrusion. |
| **P0-2** | Shade-aware route | **DONE** | 12 distinct POI pairs show route divergence with alternate shaded lane paths; segments colored green (shaded) and red (exposed). |
| **P0-3** | Sun-minutes counter | **DONE** | Displays exact sun-minutes for both Shade Route and Shortest Path ($\sum \frac{\ell_e s_e}{v}$), reproducible from same inputs. |
| **P0-4** | Request parsing by local open model | **DONE** | Hand-written code-mixed set of 30: offline deterministic parser 30/30 (100%, `results/parser_offline.json`); Groq open-weight `gpt-oss-120b` 20/30 (66.7%, `results/parser_groq.json`). Works 100% offline without internet. |
| **P0-5** | Agent end to end | **DONE** | Natural language request ("Walk dadu to the clinic around 3 pm, he can't take much sun.") directly maps to route with 1-sentence trade-off. |
| **P0-6** | Valid submission | **IN PROGRESS** | Fresh repo started Oct 8; README, build log, and test suites created. |
| **P1** | TabPFN Best Window Widget | **DONE** | TabPFN-2 trained on real Open-Meteo ERA5 archive (Oct 2006-2025); held-out Oct 2025 MAE **0.47 vs 1.77** climatology. Live Open-Meteo forecast at request time. See section 14. |
| **P1** | Voice briefing | **DONE** | ElevenLabs TTS endpoint with automatic browser speech synthesis fallback. |
| **P1** | Noon honesty note | **DONE** | UI and agent state when shade barely helps at solar noon (60° elevation). |

---

## 11. Environment Variables & Keys Needed from User

To enable live cloud LLM reasoning and ElevenLabs voice audio, place these keys into a `.env` file in the project root (see `.env.example`):

1. **`GROQ_API_KEY`** *(Recommended for open-weight model)*
   - Used for Groq's open `llama-3.3-70b-versatile` / `qwen-2.5-32b` models.
   - *Note:* If omitted, the app automatically runs on the **100% offline deterministic parser** or local Ollama without errors.
2. **`ELEVENLABS_API_KEY`** *(Partner category)*
   - Used for high-fidelity ElevenLabs neural speech briefing.
   - *Note:* If omitted, the app automatically falls back to browser **Web Speech Synthesis API**.
3. **`ELEVENLABS_VOICE_ID`** *(Optional)*
   - Default: `21m00Tcm4TlvDq8ikWAM` (Rachel).
4. **`SENTRY_DSN`** *(Optional)*
   - For agent tracing.

---

## 12. How to Run Locally

Start the backend and UI with a single command:

```powershell
pip install -r requirements.txt
python backend/main.py
```

Open your browser at:
`http://localhost:8000`

---

## 13. Workstreams 1 & 2 Execution Log

**What changed & Decisions Made:**
- **OSM POIs (WS1)**: Instead of the 7 hardcoded POIs, I extracted real clinics, pharmacies, cafes, etc. from `osm_raw.json`. Dadu's residence remains an illustrative POI. 
- **Testing Scale Issue (WS2)**: When running `search_demo_trips.py` for all POI pairs, the script hung because `compute_edge_exposure` (Shapely intersection) takes ~1 second per call, and it was being called inside a loop over thousands of pairs.
- **Fix**: Implemented a caching mechanism (`_exposure_cache`) in `plan_route()` so that the exposure map for a given `dt_ist` is only computed once.
- **Topological Errors (WS2)**: Replaced the bare `except Exception:` in `compute_edge_exposure` with `shapely.errors.TopologicalError` to avoid suppressing unrelated bugs while catching valid geometric failures.
- **Tests (WS2)**: Upgraded all testing scripts to use `pytest` assertions. Discovered exactly 40 diverging shade routes at 3:00 PM, and selected the Belle Vue Clinic -> Oxford Bookstore route as the primary demo trip.
- **Cleanup**: Purged the unused scaffolding in `frontend/` to strictly favor the active `static/` directory. Added `requirements.txt` to streamline local setup.

---

## 14. Workstream 4 Execution Log — Real Weather + TabPFN (Open-Meteo)

**What changed & Decisions Made:**
- **Replaced synthetic data**: The old `backend/best_window.py` generated weather with `np.random` and hard-coded `mae_tabpfn = 1.18`. Both were fake. Deleted.
- **Real archive (`scripts/fetch_openmeteo.py`)**: Fetched **14,880 hourly rows** of real ERA5 reanalysis for Park Street, Kolkata (22.5510, 88.3530) covering every October from **2006 to 2025** from the Open-Meteo archive API. Saved to `data/openmeteo_kolkata_october.csv` (+ provenance in `data/openmeteo_source.json`). Committed so the repo runs from a fresh clone.
- **Honest target choice**: First fit used `heat_index` as the target, but heat index is an algebraic function of temperature and humidity, so TabPFN reproduced the formula (MAE 0.066 °C) — circular and not credible. Switched the target to Open-Meteo `apparent_temperature` (feels-like) and withheld wind speed, so the model genuinely infers a non-trivial quantity.
- **Held-out evaluation (`scripts/train_window_model.py`)**: Train = Oct 2006-2024, test = Oct 2025 (403 daylight rows). Baseline = hour-of-day climatology mean over the training years.
  - **TabPFN-2 MAE: 0.470 °C** vs **climatology MAE: 1.772 °C** → **73.5% error reduction** (`results/window_eval.json`).
- **Live forecast at request time**: `/window` now fetches the real Open-Meteo *forecast* for the target date (falls back to the *archive*, then to the stored hourly climatology if offline). Predictions are cached per date; first call ~3 s on CPU, then instant.
- **TabPFN license verified**: v2 code + weights are the **Prior Labs License (Apache-2.0 + attribution)** and require the notice *"Built with PriorLabs-TabPFN"*. This is what we use (`ModelVersion.V2`). The newer v2.5/v2.6/v3 weights are non-commercial and are **not** used.
- **Tests (`tests/test_best_window.py`)**: 5 tests confirm the archive is present, the eval JSON is real and beats baseline, the metrics are not hard-coded, and the offline fallback ranks 5 windows correctly.

## 15. Workstream 5 Execution Log — AI Agent

**What changed & Decisions Made:**
- **Mastra agent (`agent/`)**: A real `@mastra/core` agent (`id: chhaya`) running the open-weight Groq model `openai/gpt-oss-120b` via `@ai-sdk/groq` (model selectable with `GROQ_MODEL`), with four function-calling tools — `plan_route`, `best_window`, `get_shadows`, `list_pois` — that call the FastAPI endpoints. Typechecks clean (`npm run typecheck`) and the tools were smoke-tested against a live server (`home -> Belle Vue Clinic` @ 15:00).
- **Python agent wrapper (`backend/agent.py`)**: The same tool set exposed in-process for the web app. Uses Groq tool-calling when `GROQ_API_KEY` is set; otherwise a **deterministic planner** so the app works out-of-the-box with no key (the offline claim applies to this path only). Each tool call is wrapped in retries and optional **Sentry** spans (`SENTRY_DSN`).
- **Unknown places ask, don't guess**: The deterministic planner checks `resolve_location` first and returns a clarification reply listing known places, satisfying the workflow contract.
- **Endpoints**: `/agent/chat` now runs the agent; new `/agent/tools` lists tool schemas. Existing response keys (`reply`, `parsed_parameters`, `route_data`) preserved for the UI.
- **Tests (`tests/test_agent.py`)**: 5 tests cover the tool registry, a deterministic shaded route, the clarification path, `/agent/tools`, and `/agent/chat`.
- **Cleanup**: Removed the leftover untracked `frontend/` scaffolding; the app keeps using `static/`.

## 16. Full Test Suite Status
`python -m pytest -q` → **17 passed** (shadows, routing, parser, endpoints, best-window, agent).

## 17. Workstream 7 Execution Log — UI Polish + Render Deploy

**What changed & Decisions Made:**
- **Honesty fix in the UI**: The best-window card hard-coded `MAE: 1.18 vs 1.94 Base` from the deleted synthetic version. It is now populated live from the `/window` response (`model_metrics.tabpfn_mae` / `baseline_mae`, id `mae-tag`), so the widget shows the real **0.47 vs 1.77 °C** and falls back to a neutral "climatology fallback" label if metrics are missing. The solar badge was already dynamic.
- **`.env` actually loads**: `README` told users to `cp .env.example .env`, but nothing read it. Added `python-dotenv`, loaded at the top of `backend/main.py`; added the dependency to `requirements.txt`. `.env` was already git-ignored.
- **Configurable server**: `python backend/main.py` now honours `HOST` / `PORT` / `RELOAD` env vars instead of hard-coded `0.0.0.0:8000` with reload.
- **Render Blueprint (`render.yaml`)**: One free Python web service running `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`, health check `/health`, `PYTHON_VERSION=3.11.9`, and `sync: false` secret prompts for `GROQ_API_KEY` / `ELEVENLABS_API_KEY` / `SENTRY_DSN`. Optional keys — with none set the app uses the offline deterministic parser and browser speech. No DB/cron needed.
- **`frontend/`** was already removed (WS5); the app keeps serving `static/` only.
- **Smoke test** (`fastapi.testclient`, local): `/health` 200, `/` 200 (HTML), `/static/style.css` 200, `/agent/chat` 200 (parsed home→clinic @15:00, low), `/window` 200 → best window `06:30 - 08:30`, live `Open-Meteo forecast`, MAE `0.4699 vs 1.772`.
- **Sentry tracing wired end-to-end**: `init_sentry()` (`backend/agent.py:41`) now installs the `StarletteIntegration` + `FastApiIntegration` so every HTTP route and uncaught error is captured, not just agent tool calls; it is initialised at startup in `backend/main.py`. Env: `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE` (all in `.env`, git-ignored). `tests/conftest.py` blanks `SENTRY_DSN` so the suite never ships telemetry. Verified live: `/agent/chat` returns `"tracing": "sentry"` with a `plan_route` span.
- **Remaining manual step**: click "New > Blueprint" in Render with this repo to mint the live URL, then paste it into the README badge line.

## 18. Paper UI Restyle — "Hot Kolkata Afternoon, Printed on Paper" (`static/`)

**What changed & Decisions Made:**
- Visual pass only: no data, API, shadow, or routing logic touched. All 123 existing element IDs preserved so every `getElementById` binding keeps working.
- **Tokens (`static/tokens.css`, new):** single source of truth — `--paper #F4E9D4`, `--paper-deep #E8D6B5`, `--kash #FBF7EE`, `--ink #2A1F17`, `--shade #1F4D3A`, `--sun #F2A900`, `--sun-hot #D2410D`, `--clay #B8553A`, `--sindoor #C8321E`, `--water #9DAE9A`; warm dark theme (`--paper #1E1A15`, `--ink #F1E6D0`, never blue-black). Depth from `4px 4px 0` hard offset shadows + borders only.
- **Banned and removed:** violet/purple/indigo/blue/cyan glows, glassmorphism (`backdrop-filter` gone), blurred box-shadows, gradient meshes, Inter/Roboto (now Fraunces display / Instrument Sans body / IBM Plex Mono numerals / Hind Siliguri Bengali, Google Fonts with system fallback stacks).
- **Map (`static/app.js`, visual sections only):** paper-toned basemap (Esri light-grey raster + paper wash, no blue water), clay extrusions modulated by live solar elevation, shadows as ink-green wash + canvas hatch `fill-pattern` (no blur), routes as paper casing + solid green shade layer + dashed vermilion sun layer (colour-blind safe: style encodes exposure too), ink dashed baseline, self-drawing route reveal, paper-tag pins with ink-ring proximity pulses.
- **Signature elements:** SVG sundial with rotating gnomon shadow, sun-budget gauge (marigold→vermilion), hand-drawn start-time curve with "LEAVE AT" stamp, stop passport tickets, repair tickets, SVG-turbulence grain overlay, tram/banyan empty illustrations.
- **Verification:** `node --check` clean; codebase grep for banned hexes/glow/blur clean; `pytest` 26 passed.

## 19. Landmark Marker Fix (`static/app.js`, `static/style.css`)

- **What broke:** paper-tag POI markers rendered as oversized boxes scattered across the map. Cause: markers were center-anchored while the CSS drew a tail below the box, so each tag sat on top of its coordinate with the tail pointing at nothing; variable-width boxes + hover-shift + tilt made it worse.
- **Fix:** uniform 30px tags (32px rest/card pins), `anchor: "bottom", offset: [0, -6]` on POI/rest/card markers so tail tips land on the true coordinate; removed hover translate and card tilt. Endpoint circles and walking dot stay center-anchored (correct for dots).

## 20. Full-Spec Audit (Oct 9)

Audited the repo against the Section 1–15 specification. **Done:** P0 plan (parser, plan builder, weather budget, rest stops, sweep, share, no-window, noon note), P1 together (trips, check-ins, ping, watcher, repair + tests), P2 cards (CRUD, near/radar, report, QR, expiry, moderation), config, Render, Sentry, voice + fallback, 26 tests, paper UI (V6, V9, V12 partial). **Not done:** §1.1 de-hardcoding (fixed center/timezone/16m fallback, no area packs/settings/locale), §3.6+V10 observations, V7 printable ticket, P0.6 SerpApi, GPX/turnaround, Bengali toggle, V2/V3/V1/V4/V5/V8/V11, CREDITS + visible data credits, field test + post. Chose accuracy system first (original contribution the post needs numbers from).

## 21. Shade Observations & Calibration — §3.6 + V10

**What changed & Decisions Made:**
- **Backend:** `POST /api/trip/{code}/observation` (walker, label, shade/sun, predicted, stop; server stamps solar elevation/azimuth + time; 404 on unknown trip) and `GET /api/accuracy` (tally + per-label table + corrections) in `backend/main.py`. `observations` table + label index in `backend/db.py:init_db`. Config: `OBS_MATCH_TOLERANCE 0.25`, `OBS_MIN_TAPS_FOR_CORRECTION 5`, `OBS_MAX_CORRECTION 0.40`. Correction = mean(observed − predicted), learned only after 5 taps, clamped to ±0.40, never shown without its count.
- **Frontend:** walk modal gained "At this halt — sun or shade?" tap buttons auto-filled with the just-reached halt's label + predicted shade; HUD overview gained a field-check meter ("matched X of Y checkpoints" + top streets with counts); lanes with a learned correction render in calibrated ticket style (dashed ink outline + ✎ ±% · N taps tag).
- **Failure logged honestly:** an empty edit to `api_trip_repair` accidentally merged its `def` line with the docstring → `IndentationError` on import; caught by `python -c "import backend.main"`, fixed, import clean.
- **Verification:** manual API check (6 taps → 4 matched, correction −0.153 as hand-computed); test taps deleted from `data/chhaya.db` (0 rows remain). `tests/test_observations.py` (4 tests: tolerance, gating, clamp, endpoint 404/shape, hermetic tmp DB). Full suite: **30 passed**.

## 22. Pick-from-Map, Live GPS, Trip Chat, Cards-Anywhere + Photos

**What changed & Decisions Made:**
- **No zone rebuild (honest call):** the routing/shadow pack is one prebuilt bbox (`scripts/fetch_osm.py` BBOX, 650 buildings / 1,108 nodes). Extending it means an Overpass refetch + reprocess + re-verification of every tuned number, too risky mid-sprint. Instead: `resolve_location` already accepts `"lat,lon"`, so hand-picked points route today by snapping to the nearest lane (verified 200 with `Coordinates (22.5510, 88.3530)` origin). The pick popup says "snaps to nearest lane" so users are not misled. Cards, chat and GPS work at exact coordinates map-wide.
- **Tap-to-pick (`static/app.js:setupMapPick`):** map click (markers/popups/controls ignored) opens a paper popup — Start here / End here / Leave card here. Picks feed `loadDirectRoute` as `lat,lon`, alone or mixed with dropdown POIs.
- **GPS (`setupLocate`, `◎ Locate` button):** one-shot fix + `watchPosition` follow toggle with a green my-location dot; second tap stops tracking. Opt-in per tap, nothing in the background.
- **Trip chat:** `trip_messages` table + `POST/GET /api/trip/{code}/chat` (`since_id` polling, PII-stripped via card rules, 280 chars, empty → 400, unknown trip → 404). Every check-in posts a system message ("Dadu reached Stop 2"). Walk modal gained a third Chat view with live count badge and 5 s polling while open. Side-effect fix found while wiring: the old Watcher toggle added `hidden` right after removing it, so the watcher view could never show — replaced with a generic 3-view switcher.
- **Cards anywhere + motives + photos:** leave-card form pins at the tapped point (label shows where) with new motives `hike` and `story` (unknown types → 422, allowed list in config). Optional photo input downscaled client-side (800px JPEG) and capped server-side at 350 KB (`photo_too_large_dropped`, text still pins). `photo` column migrated via `ALTER TABLE`; near-responses carry full bytes for immediate cards, flag-only for radar.
- **Failure logged honestly:** my new `ChatRequest` model shadowed the agent-chat one → `/agent/chat` 422 in 2 existing tests. Renamed to `TripChatRequest`, suite green again.
- **Verification:** `tests/test_trip_chat.py` (3 tests: chat + system message + polling, PII/400/404, motives + photo round-trip + oversize drop). Full suite: **33 passed**. `node --check` clean.

## 23. Hike Loop — Live Dashboard, Grass Points, Locked Stories, Feed

**What changed & Decisions Made:**
- **Backend (`backend/db.py`, `backend/main.py`, `backend/config.py`):** `walker_positions` upsert + `GET /api/trip/{code}/positions` (stale flag after 120 s); `grass_ledger` with config points (join 5, check-in 10, story unlock 25, completion 50) + per-trip and global leaderboards; `story_unlocks` with `POST /api/cards/{id}/unlock` (60 m radius enforced, teaser text while locked, full story + photo only on unlock, no repeat points); feed via `trips.is_public/title` migration + `POST publish`, `GET /api/feed` (distance category: Short stroll / Medium march / Long haul; food package from café stops), `POST join` (appends to plan walkers via targeted UPDATE so `reached` state survives, +5 pts, system chat message). Check-ins award +10; `/reached?walker=` awards +50 with a system message. Story cards serve teaser + `locked:true` beyond 60 m; photos stay immediate-only.
- **Frontend:** 4th Group view (live member rows with stale/at-stop state + grass-points table + initial-dot member pins on the map); GPS tracking now shares the spot (throttled 15 s, opt-in only); `🌱 Feed` modal (announce + join flow that drops you into the Walk modal); story lock/unlock UI using real phone GPS (server re-checks distance, no map-centre spoofing).
- **Verification:** `tests/test_hike_loop.py` (4 tests: positions + stale, points flow, lock/unlock/no-double, feed/join/category; caught 2 test-side bugs — far point outside radar, walkers-are-dicts — fixed in the test). Migration proven against the real `data/chhaya.db` (new tables/columns present, zero test rows). Full suite: **37 passed**. `node --check` clean.

## 24. Bengali/English Toggle — V12

**What changed & Decisions Made:**
- **Real locale file, not hardcoded strings:** `static/locale.json` with 103 en + 103 bn keys (parity enforced by test). Bengali in Hind Siliguri (already loaded); `<html lang>` flips `en`/`bn`; choice persists in `localStorage`.
- **Wiring:** 92 `data-i18n` / `data-i18n-ph` tags across `index.html` (header, search, HUD tabs, stats, walk/watcher/chat/group, radar, card form, feed, QR, legend, slider); `বাং/EN` toggle badge in the header (44px tap target, paper style). `app.js` loader with English fallback per key plus `lt(key, fallback)` for labels set before the locale arrives (mode plan names, reached title).
- **Honest limits:** computed content stays as computed — route/place names, trade-off sentences, weather lines, and per-stop check-in button labels remain English (backend messages are a separate locale job). The earlier `UnicodeDecodeError` scare was only the Windows console codec; the file is clean UTF-8.
- **Verification:** `tests/test_i18n.py` (parity, no empties, every HTML key exists, JS wiring present). Full suite: **40 passed**. `node --check` clean.
