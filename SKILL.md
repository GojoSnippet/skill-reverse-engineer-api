---
name: reverse-engineer-api
description: >-
  Teaching-mode helper: convert one existing UI workflow step into a faster API-backed version. It edits
  the target step's single file IN PLACE — adding an `## API` section (one run-in-page call) above the
  original steps kept as `## UI`, ending with a `## Report` block. One file per step, no sidecars. Use
  when a human in teaching mode asks to make a step use the API instead of clicking, reverse engineer the
  API behind a step, "apify" a step, or make a workflow cheaper/faster. Trigger words: reverse engineer
  api, use the api, apify, make this cheaper, convert this step to api, skip the UI.
---

# Reverse-Engineer-API (teaching-mode helper)

A **universal helper**, like `skill-creator`. In **teaching mode** it converts one step of a *target
workflow skill* into an API-backed step. Normal sessions just run the step; they never use this skill and
never edit skills.

- **Teacher/tool:** this skill. **Student/output:** the target workflow skill (e.g. `wave/`).
- **One file per step.** You do not create `.ui.md` or `.capture.json` sidecars. You edit the one
  `steps/<STEP>.md` in place: a one-line provenance header → `## API` (a single on-PATH `run-in-page`
  call) → `## UI` (the original prose, unchanged) → `## Report`. The step tries the API and falls back to
  the UI on any failure. There is **no `-api.md` sibling** and **nothing to route**.

## Inputs (from the human's instruction)
- `TARGET_SKILL` — path to the **editable** workflow skill, e.g. `/agent/skills/editable/<repo>/wave`.
- `STEP` — the step to convert; its current UI prose is `steps/<STEP>.md`.

## When NOT to do it — keep the UI step
- `detect_replayable.py` flags a **signature/HMAC/nonce**, **CAPTCHA/Turnstile**, or active **anti-bot**
  → keep the UI step (a correct UI run beats a script that 200s in dev and 403s in prod).
- **Policy:** a **WRITE** (mutation / POST-PUT-PATCH-DELETE) with **no consequence-free way to validate**
  stays **UI-only** — do not API-ify it. Reads, and writes you can safely re-run (e.g. a PDF render), are eligible.

## Safety (always)
- **Never `git commit`/`git push` yourself.** You edit the file in the editable target skill; the
  **human reviews the diff and commits**. Outside teaching mode, never modify skills.
- **No secrets/identity in the file.** `run-in-page` re-sources auth live each run (default
  `credentials:"include"`, no header); never write a token/cookie/account-id. `lint_skill.py` enforces this.
- On the live site: no delete, no modify, no data leak.

## Prerequisite — `run-in-page` on PATH + a CDP-enabled Chromium
`run-in-page`, `websocket-client`, and a Chromium with a loopback CDP debug port are baked into the
runtime. Confirm: `command -v run-in-page` and `curl -s http://127.0.0.1:9222/json/version`.

## Method

1. **Read the current step.** `steps/<STEP>.md` is the UI baseline in mission style (Mission / Inputs /
   Instructions / Return value / Important). Its **Instructions** block is the proven UI path — it becomes
   the `## UI instructions` fallback **verbatim**. Don't rewrite or lose it.
2. **Demonstrate + action-bounded capture.** Start capture, perform **exactly the one** action, stop:
   ```bash
   python scripts/capture_cdp.py --port 9222 --out .o11y/run1   # one action, then stop
   ```
3. **Analyze.** `python scripts/analyze.py --run .o11y/run1 [--match <url-substr>]` → pick the candidate
   matching the action (note `method`, `url`/origin, params, `requestExample`, auth headers).
4. **Classify + bail check.** `python scripts/detect_replayable.py --run .o11y/run1` → signed/anti-bot ⇒
   keep UI. Note **read vs write** (GraphQL `mutation` / REST verb). A WRITE with no safe validation ⇒ **UI-only, stop.**
5. **Edit `steps/<STEP>.md` in place** to the single-file pattern:
   The edit is a **surgical insert, not a rewrite.** Keep **Mission** and **Inputs** at the top and
   **Return value** / **Important** at the bottom exactly as they were. Only:
   - **Add a header comment (one line) at the very top:** `<!-- reverse-engineer-api · taught <date> ·
     class READ|WRITE · approved: <human> (<why-safe, writes only>) · validated: <state> · regenerate -->`
   - **Insert `## API attempt` ABOVE the original instructions:** (a) build `--vars-json` from the Inputs;
     (b) **one** `run-in-page --contract 1 [--allow-mutation for writes] --match <origin> --out <path>
     --vars-json '…' --js '<in-page fetch with {{vars}} returning {ok,…,download?:{url}}>'`; (c) **branch on
     the exit code only** — `0` ⇒ set Return value `method: api` + the path and stop; any other ⇒ do the UI
     instructions below, and tell the model **not** to investigate / read cookies / grep.
   - **Rename the original `Instructions:` heading to `## UI instructions`** — the numbered steps stay
     **byte-for-byte** (the proven fallback). Don't touch them.
   - **Add `method: "api" | "ui"`** to the **Return value** block so each run states which path ran.
   - **Auth ladder:** default `credentials:"include"` with **no** auth header; only climb to a
     live-re-sourced token if it 401/403s; never store a value. If auth needs an httpOnly token JS can't
     read and the cookie alone 401s ⇒ keep UI.
   - **Strong success predicate** in `ok` (not bare 2xx): **status + a positive shape signal appropriate
     to the response** — a content-type/magic-byte check for file responses, or an op-success field like
     `didSucceed` for GraphQL (it returns 200 even on errors); `run-in-page` also verifies `--out` is a
     non-empty, type-correct file (it rejects an HTML error page).
   - **Chains:** inline a **self-contained** chain (incl. a bounded poll) into the one JS; **bail to UI**
     if it needs an uncaptured value, unbounded polling, or cross-step state.
   - Add any new `required_step_inputs` (the vars + `allow_mutation` for writes) to the target `SKILL.md`.
6. **Validate by running it once** against a warm (logged-in) browser. Reads run freely; an eligible
   write runs once against a safe target. Set `validated` in the header honestly
   (`yes (ran live, <evidence>)` or `no — <why>`).
7. **Lint.** `python scripts/lint_skill.py "$TARGET_SKILL"` → must be **CLEAN**.
8. **Stop — hand to the human.** Emit the structured teaching report and let the human review + commit:
   ```
   ━━━━ TAUGHT ━━━━
   STEP:      <skill>/<STEP>
   RESULT:    api-added   (or: kept-ui — <reason>)
   CLASS:     read | write
   VALIDATED: yes (<evidence>)  | no (<why>)
   FILE:      steps/<STEP>.md   (one file; original steps preserved as ## UI)
   ```

See `references/hard-cases.md` for the worked Wave example and the full read/write, auth, and chain rules.

## Bundled scripts
- `scripts/capture_cdp.py` — CDP capture of the demonstrated action (teaching-time).
- `scripts/_engine/` — Browserbase `browser-to-api` engine (MIT, vendored, **unmodified**; analysis only, never `emit`).
- `scripts/analyze.py` — surface candidate endpoints (teaching-time).
- `scripts/detect_replayable.py` — signed/anti-bot bail + read/write note (teaching-time).
- `scripts/run_in_page.py` — source for **`run-in-page`**, the generic on-PATH runtime helper (body-derived
  read/write gate, success-predicate→exit, correct-tab, **waits for the browser/tab**, binary-to-file).
- `scripts/lint_skill.py` — the CI gate that enforces this single-file pattern in every client repo.

## References
- `references/hard-cases.md` — signed bodies, anti-bot, GraphQL, chains, auth ladder, and when to bail.
