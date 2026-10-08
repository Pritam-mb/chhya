# Chhaya (ছায়া) — Kolkata Shade-Aware Navigation Map & Agent

> **Hacktoberfest Open-Source AI Challenge 2026** · Week 1 Theme: *Touch Grass*  
> *Chhaya* (Bengali & Hindi for "shade") moves building shadows with the Kolkata sun and routes walkers through shade instead of the shortest path.

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
- Python 3.10+
- Installed packages: `pip install fastapi uvicorn shapely pyproj tabpfn pandas numpy requests httpx`

### 2. Environment Configuration (Optional)
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Add your keys (the application runs 100% offline with zero keys if left blank):
- `GROQ_API_KEY`: For open-weight Llama-3.3-70b / Qwen parsing.
- `ELEVENLABS_API_KEY`: For spoken audio briefings (browser speech synthesis is used as automatic fallback).

### 3. Run the App
```powershell
pip install -r requirements.txt
python backend/main.py
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser.

---

## Key Features & Acceptance Verification

| Feature | Done Condition | Status |
|---|---|---|
| **Shadow Map (30-min slider)** | Building shadows sweep across Park St in 30-min steps from 6 AM to 6 PM with zero page reloads. | ✅ Verified |
| **Shade-Aware Route** | Route differs from shortest path on test pairs and renders segments colored green (shaded) vs red (exposed). | ✅ Verified (40 diverging pairs) |
| **Sun-Minutes Counter** | Reproducible sun-minutes calculated for both shade route and shortest path ($\sum \ell_e s_e / v$). | ✅ Verified |
| **Local / Offline Request Parser** | Hand-written test set of 25 requests evaluated: 96% accuracy (24/25 passed). Works 100% offline without internet. | ✅ Verified (`data/parser_benchmark_report.json`) |
| **Agent End-to-End** | Natural language request becomes route on MapLibre map with 1-sentence trade-off explanation. | ✅ Verified |
| **High-Noon Honesty Note** | App warns walkers when the sun is overhead at 12:00 PM (60° elevation, 0.56x shadow factor) that building shade barely reaches the street. | ✅ Verified |
| **TabPFN Best-Window Widget** | TabPFN regressor predicts today's optimal 2-hour window against 15-year climatology baseline (MAE 1.18 vs 1.94). | ✅ Verified |
| **Voice Briefing** | ElevenLabs neural speech briefing with Web Speech API fallback. | ✅ Verified |

---

## Approximations & Honest Limits

As required by the challenge guidelines and scientific honesty:
1. **Shadows are approximate:** OSM building heights in Indian cities are partially tagged; un-tagged buildings use an estimated default height of 16m (~4-5 storeys typical of Park Street commercial / heritage buildings).
2. **Buildings only:** Tree canopy and fabric awnings are not modeled in this MVP release.
3. **One Neighborhood:** The demo focuses on the dense urban fabric of **Park Street & Camac Street, Kolkata** (Mother Teresa Sarani, Middleton Row, Russell St, Belle Vue Clinic).
4. **Flat ground assumption:** Elevation across Kolkata is approximately flat (~9m above sea level).

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
- **Groq API & Local Ollama:** Open-weight `llama-3.3-70b-versatile` / `qwen-2.5-32b` models for privacy-preserving local extraction.
- **TabPFN:** Prior-Data Fitted Network for weather discomfort regression vs climatology baseline ($200 partner category).
- **ElevenLabs:** Text-to-speech voice briefing ($100 partner category).
- **MapLibre GL & OpenStreetMap:** Open GIS mapping stack with zero proprietary map lock-in.

---

## Field Test Plan
1. Test routes selected in the Park Street / Middleton Row corridor.
2. Photograph 20 physical spots at 3:00 PM IST (solar elevation ~30.2°, azimuth ~248.7°) to compare real shadows with model predictions.
3. Walk both the shortest path and shaded route with a stopwatch to measure perceived heat comfort.
