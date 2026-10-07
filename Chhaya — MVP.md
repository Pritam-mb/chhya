# Chhaya — MVP

Oct 8, 2026 · @KAI

## MVP and demo scenario

The MVP is one neighborhood with a working shadow slider, one shade-aware route with a sun-minutes counter, and a natural-language request parsed by a local open model. Everything else is optional and cut first.

The demo runs at 3 pm, not noon, because shadows are about three times longer then and the shade effect is visible:

1. Open the map on the demo neighborhood at 9 am, then drag the slider to 3 pm and watch the lane shadows lengthen.
2. Type "Walk dadu to the clinic around 3 pm, he can't take much sun."
3. The agent parses the request and calls the routing tool.
4. The route glows green where shaded and red where exposed, and the counter shows sun-minutes against the shortest path.
5. The agent explains the trade-off in one sentence, for example how much longer the route is and how many sun-minutes it saves.
6. If P1 is done: the corner widget shows the best window and the voice briefing plays.
7. Cut to a field-test photo showing the real shadow matches the model.

## P0 must-haves

Six items must work for the submission to be worth entering; each has a concrete done condition.

| ID | Must work | Done when |
| --- | --- | --- |
| P0-1 | Shadow map for the demo area | Dragging the slider updates shadow polygons in 30-minute steps through daylight, no reload |
| P0-2 | Shade-aware route | The route differs from the shortest path on at least three test pairs and is colored by exposure |
| P0-3 | Sun-minutes counter | Shade route and shortest path each show sun-minutes, reproducible from the same inputs |
| P0-4 | Request parsing by a local open model | A hand-written test set returns structured parameters; failures are counted and reported |
| P0-5 | Agent end to end | A typed request becomes a route on the map through a Mastra agent calling the routing tool |
| P0-6 | Valid submission | Fresh repo, README with approximations, DEV post from the template, demo video |

## P1 and P2

P1 items add partner categories and polish; start them only when every P0 item works.

P1:

- Best-window widget: TabPFN trained on historical weather CSV, with MAE against a climatology baseline.
- Voice briefing through ElevenLabs.
- Noon honesty note: the app says when shade barely helps at the chosen hour.
- Sentry traces of agent runs, if Mastra tracing is easy.
- Deployment on Render, only if it takes little time; a video demo is accepted.

P2 (stretch, only if time is left):

- Fine-tune a small model with Tinker on code-mixed Bengali, Hindi and English requests, and measure it against the base model.
- Tree shade layer.
- A second neighborhood.

## Out of scope

None of these are in the MVP, and the post does not claim them.

- Whole-city coverage; one small neighborhood only.
- Navigation features: turn-by-turn, live traffic, user accounts.
- A native mobile app.
- Accurate per-building heights; defaults are used and labeled approximate.
- Tree and canopy shade.
- Daily scheduled briefings (Temporal) and PostGIS hosting (Tiger Data); both were parked because they do not fit their categories.

## Acceptance checks

The MVP is done when every box below is ticked.

- [ ] Repo is new, and its first commit falls inside the challenge window.
- [ ] The slider updates shadows through all daylight steps for the demo area.
- [ ] A shade route and the shortest path both render, with sun-minutes for each.
- [ ] The request parser works on the model host without internet.
- [ ] README states that shadows are approximate, heights are defaults, and trees are not modeled.
- [ ] Field test done: about 20 photographed spots compared with the model, plus two walked routes.
- [ ] Demo video recorded on the 3 pm scenario.
- [ ] DEV post uses every template section and lists teammates' DEV handles.

## Cut rules

When behind schedule, drop things in this order and never touch the protected list.

1. Tinker fine-tuning and Bengali or Hindi input (P2).
2. Render deployment; the video demo replaces it.
3. Sentry traces.
4. ElevenLabs voice briefing.
5. TabPFN corner widget, as the last P1 item to go.

Protected, never cut: the shadow slider, the shade route, the sun-minutes counter, the request parser, the field test and the write-up.

Checkpoint: if P0-1 to P0-3 are not done by Friday night, drop every P1 item except the best window and tell the other person immediately.
