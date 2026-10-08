# Chhaya — Plan (Oct 8 → Oct 12 12:30 IST)

Deadline: Oct 11 2026 11:59 PM PDT. Judging: writing quality (most), theme fit, creativity, technical execution, partner tech.
Rule for everything below: **a number may appear in the README/post only if a script in this repo produced it and its output is committed under `results/`.**

## Current state (verified Oct 8)
- Shadow engine (NOAA sun + UTM 45N extrusion) and routing (cost `l(1+k·s)`, sun-minutes) work.
- Sampling 332 random node pairs (500–1200 m): at 15:00 the shade route saves >0.5 sun-min on 189; median 1.05; best 10.7 min for +153 m. The 7 hand-placed POIs are the problem, not the engine.
- 625/650 buildings use the 16 m default height. POIs are hand-placed (the "dadu home" is illustrative).
- NOT real yet: TabPFN (not installed; fallback multiplies baseline MAE by 0.61; weather data is `np.random`), the "Mastra agent" (does not exist), Sentry, Ollama path, field test, demo video. Parser benchmark is regex-only, self-written.
- Docs (README, BUILD_LOG) claim things the code does not do. Fix them to match reality.

## End product
A deployed web app, "Chhaya", for one Kolkata neighbourhood:
1. Slider sweeps building shadows 6 AM–6 PM.
2. Ask in English/Bengali/Hindi ("dadu ke clinic nie jao 3tay, roddur shojjo hobe na") → agent parses → route drawn green/red with sun-minutes vs shortest path + one-sentence trade-off + honest noon note.
3. Best-window widget from TabPFN trained on real historical weather, with MAE vs climatology baseline.
4. Daily briefing workflow (durable, retrying) that picks the best window and speaks it.
5. Agent traces visible in Sentry.
6. A DEV post led by the field-test result (≈20 photographed spots + 2 walked routes), with approximations stated up front.

## Target tracks (niche first)
TabPFN, Temporal, Sentry, Tinker, Entire (if sessions can be shared). Also used, not relied on: Mastra, Groq (open-weight models), Render, ElevenLabs. Gemma only if we actually run Gemma and benchmark it. List only what is genuinely shipped.

Open-AI honesty: the open model is hosted (Groq) unless local Ollama proves workable. Do not claim "runs offline" or "data never leaves your machine" for the model path; the offline claim applies only to the deterministic fallback parser, and the post must say so. Both laptops are modest, so nothing in the plan may depend on heavy local inference.

## Workstreams and owners
Person A = weaker laptop (cloud/browser/writing work). Person B = stronger laptop (local compute).

| # | Workstream | Owner | Output |
|---|---|---|---|
| 1 | Real POIs from OSM + demo-trip search (all node pairs), save to `results/` | A | demo trip chosen, `results/route_search_*.json` |
| 2 | Code fixes: date handling, bare excepts, node lookup speed, `requirements.txt`, asserting tests, README fixes | A | clean repo that runs from a fresh clone |
| 3 | Parser: Groq open-weight model (primary) + offline regex fallback; hand-written test set incl. Bengali/Hindi; benchmark each parser separately. Local Ollama is an optional extra: B tries one tiny model (≤3B) and keeps it only if it is fast and accurate enough; otherwise dropped, and no "runs locally" claim is made | A writes test set, B tries Ollama | `results/parser_*.json` |
| 4 | TabPFN on real archive data (Open-Meteo), held-out eval vs climatology; check weights license | B | `results/window_*.json`, honest MAE |
| 5 | Agent: Mastra tools over the FastAPI endpoints + Temporal workflow + Sentry tracing | B | working agent, trace screenshots |
| 6 | Tinker fine-tune on code-mixed requests, eval vs base model on A's hand-written set | A (cloud, no GPU needed) | `results/tinker_*.json` |
| 7 | UI polish (keep `static/`; remove or document `frontend/`), Render deploy | A | live link |
| 8 | Field test (both, outdoors ~3 PM), demo video, DEV post | both; A drafts post | photos, match rate, video, post |

Do before anything else (A): claim credits at hacktoberfest.com/my/promos (Tinker, Render, ElevenLabs).

## Working agreement
- One branch per workstream, small commits, merge after reading and running the diff.
- Log failures and decisions in `BUILD_LOG.md` as they happen (what broke, what changed, why).
- Hand-write the parser test set and field-test notes; do not generate them.
- Commits after the deadline must be noted in the README.
- Credit all non-trivial open-source code.

## Schedule
- Oct 8–9: 1, 2, 3 (A); 4, 5 skeleton (B). Claim credits.
- Oct 9–10: 5, 6, 7. Field test around 3 PM on a sunny day.
- Oct 10–11: results into README; post drafted; video recorded.
- Oct 11 (IST evening) → Oct 12 morning: publish. One person publishes; list the other's DEV handle in the post.

## Cut order if behind
Tinker → Sentry → Entire → Temporal → ElevenLabs. Never cut: shadow slider, shade route + sun-minutes, parser, TabPFN with honest numbers, field test, write-up.
