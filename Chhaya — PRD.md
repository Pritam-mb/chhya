# Chhaya — PRD

Oct 8, 2026 · @KAI

## Overview

Chhaya is a Kolkata map that moves shadows with the sun and routes people through shade instead of the shortest path. The name is Bengali and Hindi for "shade".

A user types or says "Walk dadu to the clinic around noon, he can't take much sun." An open model turns that into routing parameters. The route glows green where shaded and red where exposed, and a sun-minutes counter compares it with the shortest path. Then they close the app and walk, so the screen is the shortest part of the experience.

This is our entry to the Hacktoberfest Open-Source AI Challenge, Week 1, theme Touch Grass.

## Challenge constraints

Seven rules shape the product, and two matter most: writing quality is weighted highest, and the open AI must be what makes it work.

| Rule | What it means for us |
| --- | --- |
| Deadline Oct 11, 2026, 11:59 PM PDT | Oct 12 around 12:30 PM IST; confirm on the official rules page |
| New project only | Repo started and finished inside the window; commits after the deadline are noted in the README |
| Open AI at the core | An open-weight model, open-source agent framework or local inference does the work |
| Judging | Writing quality (most weight), relevance to theme, creativity, technical execution, partner tech (optional) |
| Theme: Touch Grass | The screen is the shortest part; people end up outside |
| Team | Up to four people, one post, teammates' DEV handles in the body; DEV does not split prizes |
| Demo | A deployed link or a video |

Source: [challenge page](https://dev.to/challenges/hacktoberfest-week1-2026-10-05).

## Problem and users

In Kolkata's heat, two walks of the same length can feel completely different depending on shade, and map apps only optimize for distance.

Who it is for: elderly people and the family who plan their walks, school kids, street vendors, delivery riders and runners. The job: choose when and where to walk so as to take the least sun.

Shade value depends on the hour. In early October the sun in Kolkata is roughly 60 degrees high at noon and roughly 30 degrees at 3 pm (approximate). Shadow length is building height divided by tan(elevation), so about 0.55 times the height at noon and about 1.7 times at 3 pm. Building shade barely reaches the street at noon and matters most around 8 to 10 am and 2 to 5 pm. Chhaya should say so: at noon, the honest advice may be to leave at a different time.

## Goals and non-goals

The goal is one convincing neighborhood, not a whole city.

Goals:

- A time slider that visibly sweeps building shadows across one demo neighborhood.
- Shade-aware routes that beat the shortest path on sun-minutes, with the number shown.
- A natural-language request handled by an open model running locally.
- A best-window prediction with numbers against a baseline.
- A write-up that states its approximations honestly and includes a real outdoor field test.

Non-goals:

- Whole-city coverage.
- Tree and canopy shade (a stretch goal, not a promise).
- Turn-by-turn navigation, live traffic or user accounts.
- A native mobile app.
- Accurate per-building heights.

## Functional requirements

Five requirements are P0 and form the demo; the rest are P1 or P2 and are cut first.

| ID | Requirement | Priority |
| --- | --- | --- |
| F1 | Shadow map: a time slider in 30-minute steps moves building shadows across the demo area | P0 |
| F2 | Shade routing: a route between two points that minimizes sun exposure, drawn green where shaded and red where exposed | P0 |
| F3 | Sun-minutes: the shade route's sun-minutes shown next to the shortest path's | P0 |
| F4 | Natural-language request: an open model turns text into origin, destination, time, sun tolerance and walking speed | P0 |
| F5 | Agent: a Mastra agent calls the routing tools and explains the trade-off in one sentence | P0 |
| F6 | Best window: TabPFN predicts the best 2-hour window today, shown as a small corner widget, with numbers against a baseline | P1 |
| F7 | Voice briefing: a spoken summary such as "leave at 11:40, take the lane behind the market" | P1 |
| F8 | Noon honesty: the app says when shade barely helps at the chosen hour | P1 |
| F9 | Bengali, Hindi and English requests, optionally with a fine-tuned small model | P2 |
| F10 | Tree shade layer | P2 |

## Open-source AI stack and why open matters

The shadow engine is geometry, not AI; the open model is the interface and the explainer, and the write-up should say so plainly.

Stack:

- Model: Qwen3 or Llama, run locally through Ollama.
- Agent framework: Mastra, with tools for routing, shade checks and best window.
- Tabular model: TabPFN for the best-window forecast. Verify its license is open-weight before we claim it as open.
- Geo: OpenStreetMap footprints, suncalc or pvlib for sun position, shapely for shadows, osmnx or Valhalla for the graph, MapLibre GL and deck.gl for the map.

Why open innovation matters here:

- Privacy: "walk dadu to the clinic" reveals health context and home and clinic locations. A local model keeps that off a server we do not control.
- Cost: a tool people use for two minutes a day should not carry per-call fees.
- Control: we can swap models, change agent behavior, and fine-tune on code-mixed Bengali, Hindi and English requests (stretch).
- Honest limit: ElevenLabs is a closed API. It is an optional voice layer, and the app works without it.

## Partner categories

We commit to three partner categories and park two from the original list because they do not genuinely fit. Judges check for real use, and the partner score is optional.

| Category | Prize | How we would use it | Status |
| --- | --- | --- | --- |
| Mastra | $100 | Agent that parses the request and calls the routing tools | Committed |
| TabPFN | $200 | Best-window forecast from historical weather CSV, with numbers against a baseline | Committed; verify license |
| ElevenLabs | $100 | Spoken briefing | Committed; cheap to add |
| Render | $200 | Host the app | Optional; a video demo is accepted |
| Sentry Agent Tracing | $100 | Traces of the agent's tool calls | Optional if Mastra tracing is easy |
| Tinker | $200 | Fine-tune a small model on code-mixed requests and show the gain over the base model | Stretch |
| Backboard | $100 | Hosted open-weight models as a fallback if the local model is unreachable | Fallback only |
| Tiger Data | $100 | Category is pgvector, hybrid search or Tiger MCP; PostGIS does not match | Parked |
| Temporal | $100 | Category is durable agents; a daily cron job is not that | Parked |

Free credits for Tinker, Render, Backboard and ElevenLabs can be claimed at hacktoberfest.com/my/promos.

## Architecture and data

The agent layer picks the tools, while the map reads shadow layers straight from the geo engine.

&#91;embedded content: architecture · 4 components, 1 interface\]

The browser sends requests to the agent and reads shadow layers directly; the agent calls the geo engine, the TabPFN window model and ElevenLabs as tools.

A building's shadow is its footprint swept along a vector pointing away from the sun, then unioned with every other shadow. The vector's length is the building height divided by the tangent of the sun's elevation. Do this in a metric projection (UTM zone 45N, EPSG:32645 covers Kolkata), not in raw latitude and longitude.

```latex
d = \frac{h}{\tan(\text{elevation})}
```

Routing runs on the street graph. Pure length times exposure would make fully shaded edges free and invite absurd detours, so each edge costs its length plus a penalty for its sunlit share, where k comes from the user's sun tolerance:

```latex
c_e = \ell_e \,(1 + k\, s_e), \qquad s_e \in [0, 1]
```

Sun-minutes for a route sum the sunlit length of each edge divided by walking speed v:

```latex
\text{sun-minutes} = \sum_e \frac{\ell_e \, s_e}{v}
```

Data sources: OpenStreetMap building footprints with a default height where none is tagged, sun position from suncalc or pvlib, and a free historical weather archive for TabPFN (to be chosen). The interface between the services is in the Workflow doc.

## Success metrics and honest limits

We measure five things and report whatever the numbers turn out to be, including weak ones. A write-up that states its limits scores better than one that hides them.

| Metric | How measured |
| --- | --- |
| Sun-minutes saved against the shortest path | Median over a set of test routes in the demo area |
| Shadow accuracy | Share of photographed spots (about 20) where lit or shaded matches the model |
| Best-window error | TabPFN mean absolute error against a climatology baseline on held-out days |
| Request parsing | Share of hand-written test requests parsed into valid, correct parameters |
| Route latency | Seconds per request on the demo machine |

Limits we state in the post and README:

- Shadows are approximate: OSM heights in Indian cities are patchy, so many buildings get a default height.
- Buildings only; no tree shade in the MVP.
- One neighborhood, not the whole city.
- TabPFN may beat the baseline only slightly, and we say so if it does.

## Risks and open questions

The biggest risk is scope: four days is short for seven original sponsor integrations, so the MVP doc fixes what gets cut first.

| Risk | Mitigation |
| --- | --- |
| Scope too big for the time left | P0 list in the MVP doc; cut order decided in advance |
| Missing OSM building heights | Default height, labeled approximate; choose an area with good footprints |
| Local model not reachable during a live demo | Record the demo video; Backboard as a fallback host |
| Weak demo hour | Demo at 3 pm, not noon, where shadows are short |
| TabPFN not clearly open, or barely beats baseline | Check license first; report numbers honestly or drop the category |
| Tree-dominated area breaks the buildings-only model | Pick dense built-up lanes, not a park |

Open questions:

- [ ] Which neighborhood is the demo area? Dense built-up lanes where buildings dominate, such as around College Street or Park Street, rather than Rabindra Sarobar.
- [ ] Which free historical weather archive feeds TabPFN?
- [ ] Which model size runs well on the machine that hosts Ollama?
- [ ] Is TabPFN's license open-weight? Verify before the post claims it.
- [ ] Who publishes the DEV post? One person per team.
