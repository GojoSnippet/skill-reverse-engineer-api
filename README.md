# reverse-engineer-api (Agent Skill)

A **universal, teaching-mode helper skill** (a sibling of `skill-creator`). In teaching mode it converts
one step of a *target* workflow skill into an **API-backed version** that runs as an **in-page `fetch()`**
in the agent's already-authenticated browser, and writes it **into the target skill** (default to API,
fall back to UI). It never stores any customer's API itself.

- `SKILL.md` — the teaching-mode method the agent follows.
- `scripts/capture_cdp.py` — CDP capture of the demonstrated step's traffic (ours).
- `scripts/_engine/` — Browserbase `browser-to-api` engine, **MIT**, vendored **unmodified**
  (see `scripts/_engine/LICENSE.txt`). We run only its analysis stages (`load..infer`), **never `emit`**,
  so no openapi/client/report/html files are generated.
- `scripts/analyze.py` — runs the engine analysis and surfaces candidate endpoints (ours).
- `scripts/detect_replayable.py` — bail-to-UI classifier: signed/nonce/anti-bot/non-idempotent (ours).
- `scripts/replay_in_page.py` — runs an in-page `fetch()` over CDP and returns the result (ours); both
  the teaching-time validator and the runtime executor for the committed step.
- `references/hard-cases.md` — when to bail to the UI.
- `e2e/run_e2e.sh` — offline smoke test of the pipeline.

The learned call goes into the **target** workflow skill, e.g. `metaview/steps/<step>-api.md`, sibling to
the UI step. Normal sessions run it by default and fall back to the UI on failure; they do **not** modify
skills (only teaching mode commits, human-reviewed).

Requires the runtime to have **Node** (teaching-time analysis only) and **Chromium with a CDP debug port**
(for capture and for the in-page fetch). The committed step needs neither Node nor httpx at run time.
