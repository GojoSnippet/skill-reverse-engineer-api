# reverse-engineer-api (Agent Skill)

A **universal, teaching-mode helper** (a sibling of `skill-creator`). In teaching mode it converts one
step of a *target* workflow skill into an API-backed step by editing that step's **single file** in place
— a one-line provenance header → `## API` (a single `run-in-page` call) → `## UI` (the original UI,
unchanged) → `## Report`. One file per step, no sidecars: one fixed, reviewable, lintable pattern, the
same for every client. It never stores any customer's API itself.

## What's in here
- `SKILL.md` — the teaching-mode method the agent follows to produce the pattern.
- `scripts/capture_cdp.py` — CDP capture of the demonstrated action (teaching-time).
- `scripts/_engine/` — Browserbase `browser-to-api` engine, **MIT**, vendored **unmodified**; analysis
  stages only (`load..infer`), **never `emit`** — no openapi/client/report/html files.
- `scripts/analyze.py` — surfaces candidate endpoints (teaching-time).
- `scripts/detect_replayable.py` — signed/nonce/CAPTCHA/anti-bot bail-to-UI classifier (teaching-time).
- `scripts/run_in_page.py` — source for **`run-in-page`** (contract 1), the generic **on-PATH** runtime
  helper: body-derived read/write gate (refuses a write without `--allow-mutation`), success-predicate →
  exit code, correct-tab targeting, binary-to-file. The runtime installs it on PATH; steps call it **by name**.
- `scripts/lint_skill.py` — the **CI gate** that enforces the pattern in every client skill repo.
- `references/hard-cases.md` — read/write, auth ladder, chains, and when to bail.
- `e2e/run_e2e.sh` — offline-ish smoke test of the pipeline.

## The output (in the target skill, never here)
```
<client>/steps/
  <step>.md   # ONE file: provenance header → ## API (run-in-page) → ## UI (fallback) → ## Report
```
Provenance (class, approver, validated) is the one-line header comment; the original UI lives in `## UI`.
No `.ui.md` / `.capture.json` sidecars. Normal sessions just run `<step>.md` (API, fall back to UI) and
**never modify skills**; only teaching mode commits, human-reviewed.

## Runtime requirements
- **Teaching-time:** Node (engine analysis), a CDP-enabled Chromium, `websocket-client`.
- **Run-time:** `run-in-page` on PATH + a CDP-enabled Chromium. No Node, no `httpx`.
