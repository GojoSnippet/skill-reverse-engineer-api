---
name: reverse-engineer-api
description: >-
  Teaching-mode helper: convert one demonstrated UI workflow step into a faster API-backed version ONLY
  when the API output is PROVEN to equal the UI's output. It captures the whole action, rebuilds it as one
  self-contained API chain, and proves equivalence on a fresh instance — then EITHER writes an `## API
  attempt` into the step (UI preserved verbatim as fallback) OR keeps the UI with a short written reason.
  Disciplined: edits only the one target step file. Trigger words: reverse engineer api, use the api, apify,
  make this cheaper, convert this step to api, skip the UI.
---

# Reverse-Engineer-API (teaching-mode helper)

A universal helper like `skill-creator`. In teaching mode it converts ONE step of a target workflow skill
into an API-backed step **only when the API reproduces the UI's result exactly**, and otherwise **keeps the
UI** and says why. Normal sessions never use this skill.

**The three rules that make this trustworthy:**
1. **Faithful replay, not guessing.** Build the call by TRANSCRIBING the captured requests (method, URL,
   headers, body); derive the success check from the captured RESPONSE. Never invent fields.
2. **Whole chain, not a fragment.** A UI step is usually a *chain* of calls — set up state, then act (e.g.
   *apply a template* → *export it*). Capture the ENTIRE action from a clean start and API-back a **complete,
   self-contained sub-goal**. **NEVER split a chain at a data-dependency** — never let the API depend on
   state a human or the UI set up out of band. That is the bug that ships a step that works once and silently
   exports junk on the next instance.
3. **Prove equivalence, don't assume.** "A file was produced" is NOT success. The API's output must EQUAL the
   UI's output, on an instance you did **not** set up by hand, before it ships. Otherwise keep UI.

## Inputs (from the human)
- `TARGET_SKILL` — path to the editable skill, e.g. `/agent/skills/editable/<repo>/<skill>`.
- `STEP` — the step to convert; `steps/<STEP>.md` is its mission-style UI baseline.

## Prerequisites
`command -v run-in-page` and `curl -s http://127.0.0.1:9222/json/version` must both succeed. The equivalence
gate (step 6) compares PDFs by text — `pdftotext` (poppler) or `pypdf` makes it automatic; without either it
falls back to a human eyeball.

## Procedure — do exactly this, in order

> **HARD RULES.** The forbidden thing is *hand-grinding and guessing* — NOT validating. Keep these:
> - never write `python`/`python3 -c` to open or inspect `.o11y/` capture files — `analyze.py`'s output is all you need.
> - never read the source of `run-in-page` / `analyze.py` / `teach_insert.py` — everything is here and in `--help`.
> - never enter a tune-and-retry loop on `run-in-page`, and never hand-hunt cookies — `probe_auth.py` owns auth.
>
> What is **NOT optional and IS where the time goes:** capturing the **whole** action (step 1) and the
> **equivalence gate** (step 6). The teach may take longer for the gate — that is the price of a reliable
> output, and it is the point. Budget: 1× whole-capture · 1× analyze · 1× detect · 1× probe_auth · 1× build
> the chain · 1× equivalence gate.

### 1. Capture the WHOLE action via the UI — from a CLEAN state — and keep the golden
- Start from a **clean** instance: logged in, but the action **not pre-done** (e.g. the template NOT yet
  applied, the note NOT yet set up). **Do not carve any state-changing part into "prep outside the capture."
  If the UI does it, capture it.**
- ```bash
  python scripts/capture_cdp.py --out .o11y/run --start    # begin capture (background)
  #   … perform the ENTIRE action through the UI, start to finish, ONCE …
  python scripts/capture_cdp.py --out .o11y/run --stop      # end capture
  ```
- Keep the UI's output as the **golden** (ground truth for step 6): `cp <downloaded file> /tmp/golden.<ext>`.

### 2. Identify the FULL chain (every call, in order)
```bash
python scripts/analyze.py --run .o11y/run --match <url-substr-of-the-action>
```
List **every** request the action fired, in order: the **setup** mutation(s), any **status/poll** reads, and
the **final** action. Most steps are a chain, not one call. If the UI "waits for Saved/Ready", there is a
status the chain must **poll**. The full `responseExample` is in the output (your predicate fields are
there) — **do not** open the raw `.o11y/` files or write python to inspect them.

### 3. Bail check
```bash
python scripts/detect_replayable.py --run .o11y/run
```
Flags a signature / HMAC / nonce / CAPTCHA / anti-bot → **keep UI** (step 8, case 5).

### 4. Detect the auth case — DETERMINISTICALLY
For the request(s) in the chain, let `probe_auth.py` find the working auth in one bounded pass:
```bash
printf '%s' '{"method":"<METHOD>","url":"<URL>","headers":{<non-auth customHeaders + content-type>},"body":<body as a JSON string, or null>}' > /tmp/req.json
python scripts/probe_auth.py --match <origin> --request /tmp/req.json --expect-status 200
```
- **case 1** — `credentials:"include"`, no auth header (cookie session).
- **case 2** — `recipe` names the readable cookie/localStorage value to send as `Bearer`.
- **case 3** (`working:false`) — no readable auth reproduced it → **keep UI** (step 8).

(Case 4 — official API + configured token → `curl`; case 5 — signed/anti-bot → UI. See `references/hard-cases.md`.)

### 5. Build the FULL self-contained chain → write the `run-in-page` COMMAND to `/tmp/command.sh`
- **One** `run-in-page --contract 1 [--allow-mutation] --match <origin> --out <path> --vars-json '<inputs JSON>' --js '<chain>'`.
- The `<chain>` runs the WHOLE thing in order: **setup mutation(s) → poll until ready → final action →
  return the artifact** (`download: { url }` for a download URL, or `dataBase64` for inline base64). Transcribe
  each call's method/url/headers/body from `analyze.py`; predicate from the captured responses.
- **Self-contained test (must pass before step 6):** given only the step's `{{inputs}}` and a CLEAN instance,
  does the chain produce the output by itself? If any value it needs only exists because a human set it up
  (an already-applied operation id, a pre-selected template) → the chain is INCOMPLETE; add the call that
  creates that state. **Never** parameterise on such a value.

### 6. THE EQUIVALENCE GATE — prove it on a FRESH instance (the whole point)
- Pick a **second, fresh instance** the chain was NOT built on (a different note/record). If none exists,
  reset the captured one to its clean state.
- Run the API chain on it → `/tmp/api_out.<ext>`.
- Produce the UI golden **on that same fresh instance** → `/tmp/golden_fresh.<ext>` (do the UI action once;
  reuse `/tmp/golden.<ext>` only if it is literally the same instance).
- ```bash
  python scripts/verify_equivalence.py --api /tmp/api_out.<ext> --golden /tmp/golden_fresh.<ext>
  ```
  - **exit 0 (MATCH)** → `validated: yes (equivalent to UI on a fresh instance)`. Go to step 7.
  - **exit 1 (MISMATCH)** → **KEEP UI.** The chain does not faithfully reproduce the UI (a missing setup call,
    the wrong endpoint, …). Go to step 8, kept-ui.
  - **exit 3 (INCONCLUSIVE)** → open both artifacts and confirm the same fields by eye; ship only if they
    match, else keep UI.
- **Non-negotiable: never write `validated: yes` without a MATCH on an instance you did not set up by hand.**

### 7. Write the outcome — mechanically, only on a MATCH
```bash
python scripts/teach_insert.py --step "$TARGET_SKILL/steps/<STEP>.md" \
  --header "reverse-engineer-api · taught <date> · class READ|WRITE · approved: <human> (<why-safe>) · validated: yes (equivalent to UI on fresh instance <id>)" \
  --command /tmp/command.sh
```
Edits ONLY the step file: wraps the command in the fixed **run-this-first / branch-on-exit** instruction,
inserts it as `## API attempt` above the originals, preserves them verbatim as `## UI instructions`. Do not
hand-edit. **Keep UI (case 3/5 or a MISMATCH):** do NOT touch the step file; write the reason in the report.

### 8. Verify discipline + report
```bash
git -C "$TARGET_SKILL" diff --name-only   # MUST be only steps/<STEP>.md (or empty if kept-UI)
```
Anything else → `git -C "$TARGET_SKILL" checkout -- <that-file>`. Then emit:
```
━━━━ TAUGHT ━━━━
STEP:       <skill>/<STEP>
RESULT:     api-added  |  kept-ui
EQUIVALENCE: MATCH on fresh instance <id> (<verify_equivalence verdict/overlap>)  |  n/a
VALIDATED:  yes (equivalent to UI on a fresh instance)  |  n/a
WHY (kept-ui only):
  reason:   <case 3 auth not reproducible | case 5 signed/anti-bot | MISMATCH: API output ≠ UI output>
  detail:   <one line — what was tried and what differed (e.g. api 45KB canary ≠ ui 107KB One Pager)>
FILES:      steps/<STEP>.md   (only)
```
Stop — the human reviews the one-file diff and commits.

## Safety
- Edit only the target step file (the `git diff --name-only` check enforces it).
- **Never split a chain at a data-dependency** — the API unit must be whole and self-contained (rule 2).
- No secrets in the artifact: `run-in-page` re-sources auth live; never write a token/cookie/account-id.
  (Login email/password may stay inline in the UI block, as in the Alphaskill steps.)
- On the live site: no delete/modify/leak beyond the demonstrated read or consequence-free write.

## Bundled scripts
- `capture_cdp.py` — clean capture (start → the whole action → stop).
- `analyze.py` (+ `_engine/`, Browserbase MIT, analysis-only) — surface the chain's candidate requests.
- `detect_replayable.py` — signed/anti-bot bail check.
- `probe_auth.py` — deterministic bounded auth search (cases 1/2/3).
- `run_in_page.py` — `run-in-page`, the on-PATH in-page caller (cases 1 & 2).
- `verify_equivalence.py` — **the gate**: API output vs UI golden, content-level. MATCH / MISMATCH / INCONCLUSIVE.
- `teach_insert.py` — the mechanical single-file surgical insert (the write path).
- `lint_skill.py` — OPTIONAL CI consistency check; NOT part of this procedure.

## References
- `references/hard-cases.md` — the 5-case table, the auth ladder, chains, and when to bail.
