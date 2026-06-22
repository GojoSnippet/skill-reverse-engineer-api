---
name: reverse-engineer-api
description: >-
  Teaching-mode helper: convert one demonstrated UI workflow step into a faster API-backed version WHEN
  the request can be faithfully replayed. It captures the real request, decides if it's reproducible, and
  EITHER writes an `## API attempt` into the step (preserving the UI verbatim as the fallback) OR keeps
  the UI with a short written reason. Disciplined: edits only the one target step file. Trigger words:
  reverse engineer api, use the api, apify, make this cheaper, convert this step to api, skip the UI.
---

# Reverse-Engineer-API (teaching-mode helper)

A universal helper like `skill-creator`. In teaching mode it converts ONE step of a target workflow skill
into an API-backed step **when the captured request can be faithfully replayed**, and otherwise **keeps
the UI** and says why. Normal sessions never use this skill.

**The two rules that make this trustworthy:**
1. **Faithful replay, not guessing.** The API call is built by TRANSCRIBING the captured request (method,
   URL, headers, body); the success check comes from the captured RESPONSE. Never invent fields.
2. **Converge, don't grind.** Follow the decision tree with its fixed probe budget. Decide, write the
   outcome, stop. **No open-ended auth hunting** (the failure mode that wasted 6 minutes last time).

## Inputs (from the human)
- `TARGET_SKILL` — path to the editable skill, e.g. `/agent/skills/editable/<repo>/<skill>`.
- `STEP` — the step to convert; `steps/<STEP>.md` is its mission-style UI baseline.

## Prerequisites
`command -v run-in-page` and `curl -s http://127.0.0.1:9222/json/version` must both succeed.

## Procedure — do exactly this, in order

> **HARD RULES — this is the whole point (keeping the teach cheap).** This is a FIXED, short sequence.
> Each script's printed output is the **source of truth** — trust it and move on; never verify it by hand.
> Your entire analysis budget is about **1× capture · 1× analyze.py · 1× detect_replayable · 1× probe_auth ·
> 1× build the command · 1× validate**. If you are on a **3rd `run-in-page`**, writing **`python` to inspect
> the capture**, or **reading a script's source** — STOP: you are off-procedure and burning money.
>
> **NEVER:**
> - write `python`/`python3 -c` to open or inspect `.o11y/` capture files — `analyze.py`'s output is all you get and all you need.
> - run `run-in-page` more than **once to validate + at most one fix** on failure — then bail to UI.
> - read the source of `run-in-page` / `analyze.py` / `teach_insert.py` / etc. — everything is here and in `--help`.
> - re-run `analyze.py` or `probe_auth.py` to "double-check" — **one run each, trust it**.

### 1. Capture the demo (ONE action)
```bash
python scripts/capture_cdp.py --out .o11y/run --start    # begin capture (background)
#   … perform EXACTLY the one action (e.g. download the invoice) in the browser, ONCE …
python scripts/capture_cdp.py --out .o11y/run --stop     # end capture
```

### 2. Find the request
```bash
python scripts/analyze.py --run .o11y/run --match <url-substr-of-the-action>
```
Pick the ONE candidate matching the action **from `analyze.py`'s printed output** (by `--match` and
`operationName`). Note its `method`, `url`, `operationName`, `customHeaders`, `requestExample`,
`observedAuthHeaders`, and the **full `responseExample`** (the nested response — your success field is
already in there, e.g. `data.x.pdfUrl`). **Do NOT open the raw `.o11y/` files or write python to
inspect them — `analyze.py` already parsed everything.** If `--match` returns too many, narrow it; don't dig.

### 3. Bail check
```bash
python scripts/detect_replayable.py --run .o11y/run
```
Flags a signature / HMAC / nonce / CAPTCHA / anti-bot → **keep UI** (step 7, case 5).

### 4. Detect the auth case — DETERMINISTICALLY, do not hand-hunt cookies
Build the request JSON from the candidate and let `probe_auth.py` find the working auth in one bounded pass:
```bash
printf '%s' '{"method":"<METHOD>","url":"<URL>","headers":{<non-auth customHeaders + content-type>},"body":<request body as a JSON string, or null>}' > /tmp/req.json
python scripts/probe_auth.py --match <origin> --request /tmp/req.json --expect-status 200
```
It returns `{working, case, recipe}`:
- **case 1** — `credentials:"include"`, no auth header (cookie session).
- **case 2** — `recipe` names the readable cookie/localStorage value to send as `Bearer`.
- **case 3** (`working:false`) — no readable auth reproduced it → **keep UI** (step 7).

**This is the ONLY auth probing.** Do not grep cookies, read `__NEXT_DATA__`, or try fetches by hand.
(Case 4 — an official API + a configured token → prefer a `curl` step; case 5 — signed/anti-bot → UI. See `references/hard-cases.md`.)

### 5. Build the faithful replay (cases 1 & 2) → write the `run-in-page` COMMAND (the invocation only, no prose) to `/tmp/command.sh`
Transcribe the candidate — do not hand-write:
- one `run-in-page --contract 1 [--allow-mutation for a write] --match <origin> --out <path>
  --vars-json '<inputs JSON>' --js '<fetch>'`
- the `<fetch>` copies the candidate's `method`, `url`, `requestContentType`, **every `customHeaders` key**,
  and the `requestExample` body — **parameterise only the step's inputs** as `{{var}}`. For case 2, set
  the auth header from the readable token (e.g. a cookie value); **never a literal token**.
- the returned `ok` predicate is derived from the candidate's **`responseExample`** — require the **real success fields the
  captured response has** (e.g. `pdfUrl`) plus status. **Do not invent fields** (the `didSucceed` mistake).
- **Binary output** — `run-in-page` writes `--out` from one of two fields you return; you do NOT need to
  read its source to learn this:
  - the response gives a **download URL** (e.g. pre-signed S3) → return `download: { url: "<that url>" }` and the helper fetches it.
  - the response gives the **bytes inline as base64** (e.g. an export mutation) → return `dataBase64: "<the base64 string>"` and the helper decodes it.
  Everything you need is in this file and `run-in-page --help`; **do not read `run-in-page`'s source.**
- **Chains** (one call's output feeds the next — e.g. a `BootstrapSynthesis` id → an `Export` mutation):
  both requests are already candidates in `analyze.py`'s output. Assemble **both** calls inside the single
  `--js`, in order, in **one** build — do NOT iterate `run-in-page` to "discover" the chain.

### 6. Validate — run it once (one fix max)
`probe_auth.py` already found the auth, so run the `run-in-page` command **once**:
- **exit 0 + a correct, typed `--out` file** → `validated: yes (ran live, <evidence>)`. Go to step 7.
- **non-zero** → make **exactly ONE** fix from the error message (an obvious wrong field name / missing
  header / wrong predicate) and re-run **once**. Still failing → **keep UI (case 3). STOP.**
- **Never** enter a tune-and-retry loop or hand-probe — that loop is the expensive mistake we are killing.

### 7. Write the outcome — mechanically, never by hand-editing the file
- **API-able (case 1/2 validated):**
  ```bash
  python scripts/teach_insert.py --step "$TARGET_SKILL/steps/<STEP>.md" \
    --header "reverse-engineer-api · taught <date> · class READ|WRITE · approved: <human> (<why-safe>) · validated: <state>" \
    --command /tmp/command.sh
  ```
  (This edits ONLY the step file. It wraps your command in the fixed **run-this-first / branch-on-exit**
  instruction, inserts it as `## API attempt` above the originals, and preserves them verbatim as
  `## UI instructions`. Do not edit the file by hand — that churns the UI and drops the run instruction.)
- **Keep UI (case 3/5):** do NOT touch the step file; write the structured reason in the report.

### 8. Verify discipline + report
```bash
git -C "$TARGET_SKILL" diff --name-only
```
MUST be **only** `steps/<STEP>.md` (or empty, if kept-UI). Anything else → `git -C "$TARGET_SKILL" checkout -- <that-file>`.
Then emit:
```
━━━━ TAUGHT ━━━━
STEP:      <skill>/<STEP>
RESULT:    api-added (case 1|2)   |   kept-ui (case 3|5)
VALIDATED: yes (<evidence>)       |   n/a
WHY (kept-ui only):
  case:    <3 cross-origin bearer | 5 signed/anti-bot>
  tried:   <one line — what was attempted>
  blocked: <one line — why it can't be replayed in-page>
FILES:     steps/<STEP>.md   (only)
```
Stop — the human reviews the one-file diff and commits. **Never `git commit`/`push` yourself.**

## Safety
- Edit only the target step file (the `git diff --name-only` check enforces it).
- No secrets in the artifact: `run-in-page` re-sources auth live; never write a token/cookie/account-id.
  (Login email/password may stay inline in the UI block, as in the Alphaskill steps.)
- On the live site: no delete/modify/leak beyond the demonstrated read or consequence-free write.

## Bundled scripts
- `capture_cdp.py` — clean one-shot capture (start → one action → stop).
- `analyze.py` (+ `_engine/`, Browserbase MIT, analysis-only) — surface the candidate request.
- `detect_replayable.py` — signed/anti-bot bail check.
- `probe_auth.py` — deterministic bounded auth search (cases 1/2/3) — replaces manual cookie hunting.
- `run_in_page.py` — `run-in-page`, the on-PATH in-page caller (cases 1 & 2).
- `teach_insert.py` — the mechanical single-file surgical insert (the write path).
- `lint_skill.py` — OPTIONAL CI consistency check; NOT part of this procedure.

## References
- `references/hard-cases.md` — the 5-case table, the auth ladder, chains, and when to bail.
