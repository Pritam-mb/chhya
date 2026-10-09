# Chhaya (ছায়া) — Kolkata Shade-Aware Navigation Map & Agent

> **Hacktoberfest Open-Source AI Challenge 2026** · Week 1 Theme: *Touch Grass*  
> *Chhaya* (Bengali & Hindi for "shade") moves building shadows with the Kolkata sun and routes walkers through shade instead of the shortest path.

**Live demo:** _coming online via Render — see [Deploy](#4-deploy-render) below._

---

## What It Is

In Kolkata's intense heat, two walks of the exact same length feel completely different depending on shade. Mainstream map applications optimize purely for distance or vehicle speed.

Chhaya takes a plain-language request like:
> *"Walk dadu to the clinic around 3 pm, he can't take much sun."*

An open model parses the walking constraints (origin, destination, depart time, sun aversion $k$, walking speed $v$). The routing engine models the sun's exact astronomical position, projects building shadows across the neighborhood in a metric projection (UTM Zone 45N), and discovers shaded side-lane routes (like Middleton Row and Little Russell Street) that minimize direct sun exposure.

The route glows **green where shaded** and **red where exposed**, accompanied by an exact **sun-minutes counter** against the shortest baseline and a one-sentence trade-off explanation.

---

## Quick Start

### 1. Prerequisites
- Python 3.11+
- Install dependencies: `pip install -r requirements.txt`

### 2. Environment Configuration (Optional)
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
The file is loaded automatically at startup (`python-dotenv`). Add your keys — the application runs 100% offline with zero keys if left blank:
- `GROQ_API_KEY`: For open-weight Llama-3.3-70b / Qwen parsing.
- `ELEVENLABS_API_KEY`: For spoken audio briefings (browser speech synthesis is used as automatic fallback).

### 3. Run the App
```powershell
python backend/main.py
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser. Set `PORT`/`HOST` to override the defaults.

### 4. Deploy (Render)
A [Render Blueprint](https://render.com/docs/blueprint-spec) is committed as `render.yaml`:
```bash
# push the repo, then in Render: New > Blueprint > pick this repo
```
It provisions one free Python web service that runs
`uvicorn backend.main:app --host 0.0.0.0 --port $PORT` and health-checks `/health`.
`GROQ_API_KEY` / `ELEVENLABS_API_KEY` / `SENTRY_DSN` are prompted in the dashboard
(`sync: false`) and are optional — with no keys the app uses the fully offline
deterministic parser and browser speech fallback. No database or cron is required.

---

## Key Features & Acceptance Verification

| Feature | Done Condition | Status |
|---|---|---|
| **Shadow Map (30-min slider)** | Building shadows sweep across Park St in 30-min steps from 6 AM to 6 PM with zero page reloads. | ✅ Verified |
| **Shade-Aware Route** | Route differs from shortest path on test pairs and renders segments colored green (shaded) vs red (exposed). | ✅ Verified (40 diverging pairs) |
| **Sun-Minutes Counter** | Reproducible sun-minutes calculated for both shade route and shortest path ($\sum \ell_e s_e / v$). | ✅ Verified |
| **Request Parser (offline + Groq)** | Hand-written code-mixed test set of 30 requests. Offline deterministic parser: **100% (30/30)**; Groq `openai/gpt-oss-120b`: **66.7% (20/30)**. The niche romanized Bengali/Hindi set is where the rule parser beats the LLM. Works 100% offline without internet. | ✅ Verified (`results/parser_offline.json`, `results/parser_groq.json`) |
| **Agent End-to-End** | Natural language request becomes route on MapLibre map with 1-sentence trade-off explanation. | ✅ Verified |
| **High-Noon Honesty Note** | App warns walkers when the sun is overhead at 12:00 PM (60° elevation, 0.56x shadow factor) that building shade barely reaches the street. | ✅ Verified |
| **TabPFN Best-Window Widget** | TabPFN-2 regressor predicts the best 2-hour window from the live Open-Meteo forecast; held-out (Oct 2025) MAE **0.47 °C vs 1.77 °C** for a 20-year hourly climatology baseline. | ✅ Verified (`results/window_eval.json`) |
| **AI Agent (Mastra + offline)** | Mastra agent (open-weight Groq `openai/gpt-oss-120b` tool-calling) calls the routing/shadow/window tools; a deterministic offline planner keeps the app working with no key. | ✅ Verified (`agent/`) |
| **Voice Briefing** | ElevenLabs neural speech briefing with Web Speech API fallback. | ✅ Verified |

---

## Approximations & Honest Limits

As required by the challenge guidelines and scientific honesty:
1. **Shadows are approximate:** OSM building heights in Indian cities are partially tagged; un-tagged buildings use an estimated default height of 16m (~4-5 storeys typical of Park Street commercial / heritage buildings).
2. **Buildings only:** Tree canopy and fabric awnings are not modeled in this MVP release.
3. **One Neighborhood:** The demo focuses on the dense urban fabric of **Park Street & Camac Street, Kolkata** (Mother Teresa Sarani, Middleton Row, Russell St, Belle Vue Clinic).
4. **Flat ground assumption:** Elevation across Kolkata is approximately flat (~9m above sea level).
5. **Best-window target:** The TabPFN model predicts Open-Meteo *apparent temperature* (feels-like) from the day's forecast weather (temperature, humidity, radiation, cloud; wind withheld). The baseline is an hour-of-day climatology from 2006-2025. The reported 0.47 °C MAE is a nowcast number using the same-day forecast as a feature, not a claim of day-ahead forecasting skill.
6. **Agent model path:** The Mastra/Groq agent is a hosted open-weight model and needs `GROQ_API_KEY`; the offline claim applies only to the deterministic fallback planner, which is what the web app uses with no key.

---

## Mathematical Foundations

### 1. Solar Elevation & Metric Shadow Extrusion
In UTM Zone 45N (EPSG:32645):
$$d = \frac{h}{\tan(\text{elevation})}$$
$$\Delta x = \sin(\phi_{\text{shadow}}) \cdot d, \quad \Delta y = \cos(\phi_{\text{shadow}}) \cdot d$$

### 2. Street Exposure & Routing Cost
Edge cost:
$$c_e = \ell_e \,(1 + k\, s_e), \qquad s_e \in [0, 1]$$
where $\ell_e$ is edge length, $s_e$ is sunlit share (0 = full shade, 1 = full sun), and $k$ is sun aversion penalty ($k=4.5$ for low tolerance / dadu).

### 3. Sun-Minutes Counter
$$\text{sun-minutes} = \sum_e \frac{\ell_e \, s_e}{v}$$
with walking speed $v = 3.0\text{ km/h} = 50\text{ m/min}$.

---

## Open-Source AI Stack & Partner Categories
- **Mastra (`agent/`):** Open-source agent framework. `chhayaAgent` runs the open-weight Groq model `openai/gpt-oss-120b` (via `@ai-sdk/groq`; override with `GROQ_MODEL`) with function-calling tools `plan_route`, `best_window`, `get_shadows`, `list_pois` that call the FastAPI endpoints. Run with `cd agent && npm install && GROQ_API_KEY=... npm run dev`.
- **Groq API & Local Ollama:** Open-weight `gpt-oss-120b` / `qwen3.8-27b` models (Groq) for request parsing and agent reasoning; local Ollama (`qwen2.5:7b`) is an optional fallback. Note: `llama-3.3-70b-versatile` was retired from Groq's catalog, so the code auto-selects from the current open-weight models.
- **TabPFN:** Regressor for the best-window forecast vs a 20-year climatology baseline (MAE **0.47 vs 1.77 °C**). Uses the **TabPFN-2 weights** under the [Prior Labs License](https://github.com/PriorLabs/TabPFN/blob/main/LICENSE) (Apache-2.0 with attribution) — *Built with PriorLabs-TabPFN*.
- **Open-Meteo:** Real ERA5 reanalysis archive (Oct 2006-2025) for training plus the live forecast API at request time.
- **ElevenLabs:** Text-to-speech voice briefing ($100 partner category).
- **MapLibre GL & OpenStreetMap:** Open GIS mapping stack with zero proprietary map lock-in.

### Running the Mastra agent
The Python app is fully self-contained and falls back to a deterministic planner with no key. To run the Mastra agent instead:
```bash
python backend/main.py            # terminal 1: API on :8000
cd agent && npm install
GROQ_API_KEY=... npm run dev "Walk dadu to the clinic around 3 pm, he can't take much sun"
```

---

## Field Test Plan
1. Test routes selected in the Park Street / Middleton Row corridor.
2. Photograph 20 physical spots at 3:00 PM IST (solar elevation ~30.2°, azimuth ~248.7°) to compare real shadows with model predictions.
3. Walk both the shortest path and shaded route with a stopwatch to measure perceived heat comfort.
