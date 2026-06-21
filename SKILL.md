---
name: reverse-engineer-api
description: >-
  Teaching-mode helper: convert one existing UI workflow step into a faster API-backed version. It
  writes the result INLINE into the target step's file (§1 a single run-in-page call, §2 the original
  UI as fallback) plus a scrubbed capture.json sidecar — one fixed, reviewable, lintable pattern. Use
  when a human in teaching mode asks to make a step use the API instead of clicking, reverse engineer
  the API behind a step, "apify" a step, or make a workflow cheaper/faster. Trigger words: reverse
  engineer api, use the api, apify, make this cheaper, convert this step to api, skip the UI.
---

# Reverse-Engineer-API (teaching-mode helper)

A **universal helper**, like `skill-creator`. In **teaching mode** it converts one step of a *target
workflow skill* into an API-backed step, written **inline** into that step's file. Normal sessions just
run the step; they never use this skill and never edit skills.

- **Teacher/tool:** this skill. **Student/output:** the target workflow skill (e.g. `wave/`).
- The committed call runs as an **in-page `fetch()`** via the on-PATH `run-in-page` helper. The step
  **tries the API (§1) and falls back to the UI (§2)** in one file. There is **no `-api.md` sibling**.

## Inputs (from the human's instruction)
- `TARGET_SKILL` — path to the **editable** workflow skill, e.g. `/agent/skills/editable/<repo>/wave`.
- `STEP` — the step to convert; its current UI prose is `steps/<STEP>.md`.

## When NOT to do it — keep the UI step
- `detect_replayable.py` flags a **signature/HMAC/nonce**, **CAPTCHA/Turnstile**, or active **anti-bot**
  → keep the UI step (a correct UI run beats a script that 200s in dev and 403s in prod).
- **Policy:** a **WRITE** (mutation / POST-PUT-PATCH-DELETE) with **no consequence-free way to validate**
  stays **UI-only** — do not API-ify it. Reads, and writes you can safely re-run (e.g. a render), are eligible.

## Safety (always)
- **Never `git commit`/`git push` yourself.** You write files into the editable target skill; the
  **human reviews the diff and commits**. Outside teaching mode, never modify skills.
- **No secrets/identity in the committed artifact.** `run-in-page` re-sources auth live each run; the
  `capture.json` records only a *recipe* string, never a token/cookie/account-id. `lint_skill.py` enforces this.
- On the live site: no delete, no modify, no data leak.

## Prerequisite — `run-in-page` on PATH + a CDP-enabled Chromium
`run-in-page`, `websocket-client`, and a Chromium with a loopback CDP debug port are baked into the
runtime. Confirm: `command -v run-in-page` and `curl -s http://127.0.0.1:9222/json/version`.

## Method — produce the pattern

1. **Demonstrate + action-bounded capture.** Start capture, perform **exactly the one** action, stop —
   don't leave a wide time window of unrelated traffic.
   ```bash
   python scripts/capture_cdp.py --port 9222 --out .o11y/run1   # one action, then stop
   ```
2. **Analyze.** `python scripts/analyze.py --run .o11y/run1 [--match <url-substr>]` → pick the candidate
   matching the action (note `method`, `url`/origin, params, `requestExample`, `customHeaders`, `observedAuthHeaders`).
3. **Classify + bail check.** `python scripts/detect_replayable.py --run .o11y/run1` → signed/anti-bot
   ⇒ bail. Note **read vs write** (GraphQL `mutation` / REST verb). A WRITE with no safe validation target ⇒ **UI-only, stop**.
4. **Author the inline step + sidecar** (the fixed pattern):
   - `steps/<STEP>.ui.md` — the current UI prose, kept as the **immutable baseline** (if not present).
   - `steps/<STEP>.md` — `<!-- @generated … class: READ|WRITE (from the classifier, never a blind label) … auth: <rung> … -->`,
     a one-line what/default/fallback, then **`## 1. API attempt`** (build `--vars-json` from `<inputs>`;
     **one** `run-in-page --contract 1 [--allow-mutation for writes] --match <origin> --out <path>
     --vars-json '…' --js '<in-page fetch with {{vars}} returning {ok,…,download?:{url}}>'`; **branch on
     the exit code only**), then **`## 2. UI fallback`** = `steps/<STEP>.ui.md` **verbatim**.
   - **Auth ladder:** default `credentials:"include"` with **no** auth header; add a **live-re-sourced**
     token only if it 401/403s; record the rung in `capture.json.auth` (recipe only, never a value).
   - **Strong success predicate** in the returned `ok` (not bare 2xx): **expected status + content-type +
     a positive shape signal** from the demo response; `run-in-page` also checks the `--out` file is non-empty/typed.
   - **Chains:** inline a **self-contained** chain (every later value produced in the trace), including a
     **bounded poll-with-timeout**, into the one JS; **bail to UI** if it needs an uncaptured value, unbounded polling, or cross-step state.
   - `steps/<STEP>.capture.json` (`schema: reverse-engineer-api/capture@1`) — provenance + `class` +
     `approved_by` + `validated` + `success_predicate` + auth recipe + normalized `template`. **Scrubbed.**
   - Add the new `required_step_inputs` to the target `SKILL.md` (the vars + `allow_mutation` for writes).
5. **Validate by running it once.** Run the §1 `run-in-page` (reads freely; an eligible write once against
   a safe target). **Re-run with a different input** to prove the template generalizes. Set `validated` honestly
   (or `NOT VALIDATED — <why>` if no safe target).
6. **Lint.** `python scripts/lint_skill.py "$TARGET_SKILL"` → must be **CLEAN**.
7. **Stop — hand to the human.** Report the diff; the human reviews and commits.

See `references/hard-cases.md` for the worked Wave example and the full read/write, auth, and chain rules.

## Bundled scripts
- `scripts/capture_cdp.py` — CDP capture of the demonstrated action (teaching-time).
- `scripts/_engine/` — Browserbase `browser-to-api` engine (MIT, vendored, **unmodified**; analysis stages only, never `emit`).
- `scripts/analyze.py` — surface candidate endpoints (teaching-time).
- `scripts/detect_replayable.py` — signed/anti-bot bail + read/write note (teaching-time).
- `scripts/run_in_page.py` — source for **`run-in-page`**, the generic on-PATH runtime helper (body-derived
  read/write gate, success-predicate→exit, correct-tab, binary-to-file). The runtime installs it on PATH.
- `scripts/lint_skill.py` — the CI gate that enforces this pattern in every client repo.

## References
- `references/hard-cases.md` — signed bodies, anti-bot, GraphQL, chains, auth ladder, and when to bail.
