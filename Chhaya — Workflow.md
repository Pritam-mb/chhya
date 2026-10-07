# Chhaya — Workflow

Oct 8, 2026 · @KAI

## Timeline

Four build days each end in a gate, and the last day is for proof and writing, not leftover hours.

&#91;embedded content: timeline · 4 build days, 3 gates plus the submission gate\]

If a gate is missed, the MVP doc's cut rules say what to drop; the schedule does not stretch.

## Workstreams

Seven workstreams cover the build; owners are left open on purpose, so type a name in the Owner cell to claim one.

| Workstream | Scope | Output | Owner |
| --- | --- | --- | --- |
| Geo data and shadows | OSM footprints for the demo area, default heights, sun position, shadow polygons every 30 minutes | Shadow GeoJSON per time slot |  |
| Routing | Street graph, sunlit share per edge, cost function, shortest-path baseline | Route service |  |
| Map UI | MapLibre and deck.gl, time slider, green and red route, sun-minutes counter, corner widget | Web app |  |
| Agent | Local open model via Ollama, Mastra agent and tools, parsing test set | Request-to-route flow |  |
| Best window | Weather archive CSV, TabPFN, climatology baseline, error numbers | Window endpoint and widget |  |
| Voice and traces | ElevenLabs briefing, Sentry agent traces | Audio and trace screenshots |  |
| Proof and writing | Field test, README approximations, DEV post, demo video | Published post |  |

## Repo and git rules

Create one fresh repo today; the challenge rejects old projects and disqualifies undisclosed commits after the deadline.

- Start a new repo on Oct 8, with no code copied from earlier projects.
- One repo, short-lived branches per workstream, small commits.
- Credit any non-trivial open-source code or prior work in the README.
- If anything is committed after the deadline, note it in the README.
- Keep API keys in a git-ignored env file, never in the repo.
- README sections: what it is, how to run it, approximations and limits, credits, field-test results.
- Both teammates' DEV handles go in the post body; only one person publishes.

## Working with Antigravity

AI use is allowed by the rules, so both of you can build with Antigravity; the risk is code nobody understands, which costs you in the write-up and the demo.

- Give each agent session one workstream and the interface contract from this doc.
- Read and run every diff before keeping it. Geometry bugs are quiet: do shadow and distance math in a metric projection (UTM zone 45N), not in degrees.
- Keep a short decision log as you go: what failed, what you changed, and why. It is the raw material for the post.
- Agent sessions can be shown in the post, which the challenge calls optional but helpful. Check early whether Antigravity sessions can be exported or linked; if not, summarize the key prompts instead.
- Hand-write the parsing test set (20 to 30 requests) yourselves, since it measures the model rather than the tool that built the app.

## Interface contract

Three endpoints separate the geo engine from the agent and the map, so the work can run in parallel.

| Endpoint | Input | Output |
| --- | --- | --- |
| GET /shadows | time slot (30-minute step) | Shadow polygons as GeoJSON for that slot |
| POST /route | origin, destination, depart time, sun tolerance, walking speed | Route segments as GeoJSON with sunlit share per segment, sun-minutes for the shade route and for the shortest path |
| GET /window | date | Ranked 2-hour windows with predicted heat and the baseline's prediction |

The model's parsed request is a small JSON object, shown here as an example. Sun tolerance maps to the penalty k in the routing cost.

```json
{
  "origin": "home",
  "destination": "the clinic",
  "depart_time": "15:00",
  "sun_tolerance": "low",
  "speed_kmh": 3
}
```

Place names resolve against points of interest inside the demo area. An unknown place makes the agent ask rather than guess.

## Field test

The field test is the cheapest way to earn the challenge's "take it outside" bonus and to give the write-up real numbers. Run it on a sunny day.

1. Pick two routes in the demo area where the shade route differs from the shortest path.
2. At 3 pm, photograph about 20 spots along them and note each as lit or shaded. Repeat a few spots in the morning if time allows.
3. Compare each spot with the model's prediction for that time and count the matches.
4. Walk both routes and record how long each took and how it felt.
5. Put the photos, the match count and the failures in the post. Misses are useful: they show where default heights or missing trees broke the model.

## Writing plan

Writing quality carries the most weight, so draft the post while you build rather than after. Each section of the submission template has a job:

| Template section | What goes in it |
| --- | --- |
| What I Built | The problem in two sentences, who it is for, and how it gets people outside |
| Demo | The 3 pm video, plus a link if it is hosted |
| Code | The repo embed |
| How I Built It | Stack, shadow math, routing cost, agent tools, and the measured numbers |
| Why Does Open Innovation Matter? | Health and location privacy with a local model, no per-call cost, swapping and tuning models, and the closed ElevenLabs layer stated plainly |
| My Agent Session | Optional; include if sessions can be exported |
| Prize Categories | Only categories genuinely used: Mastra, TabPFN, ElevenLabs, plus any others that ship |

Lead with the field-test result. Say what is approximate before a reader finds out.

## Submission checklist

Publish by Sunday night IST; the deadline is Oct 11, 11:59 PM PDT, which is about 12:30 PM IST on Monday.

- [ ] Post is written in English; non-English posts are not prize-eligible.
- [ ] Post is built from the submission template, with the devchallenge and hf26challenge tags.
- [ ] One person publishes; the other's DEV handle is listed in the body.
- [ ] Repo is embedded, and the README notes any commits made after the deadline.
- [ ] Demo video is linked; a hosted link is added only if it exists.
- [ ] Prize Categories lists only technology actually used.
- [ ] Open-source code and prior work are credited.
- [ ] Approximations and limits are stated in both README and post.
- [ ] Deadline confirmed against the official rules page.
