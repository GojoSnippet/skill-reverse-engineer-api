---
name: reverse-engineer-api
description: >-
  Reproduce a web-app workflow with direct HTTP API calls instead of clicking through the UI —
  especially long, multi-field form submissions — by discovering the app's underlying API from a
  demonstration. Use when the user asks to call a site's API directly, reverse engineer an API,
  speed up or cut the cost of a repetitive form submission, or "do this without the UI". Trigger
  words: reverse engineer api, call the api directly, skip the UI, automate this form, intercept
  requests, network tab.
---

# Reverse-Engineer-API

Turn a demonstrated UI workflow into a direct API call. The hard analysis (endpoints, schemas,
auth, GraphQL) is done by the bundled engine; you orchestrate and decide.

## When NOT to use this (bail to the GUI)
If the submit request carries a value only the live browser can produce — a JS/HMAC **signature**,
a per-request **nonce**, a **CAPTCHA/Turnstile** token — or the site throws an active **anti-bot**
challenge, do **not** force a direct call. `detect_replayable.py` flags these; on a bail verdict,
fall back to the normal screenshot+click GUI path. Better a correct GUI run than a script that 200s
in dev and 403s in prod.

## Prerequisite
Chromium must be running with `--remote-debugging-port=9222 --remote-allow-origins=*` (baked into
the base image). The agent operates its own already-authenticated browser.

## Method

1. **Demonstrate.** Perform the target workflow once in the browser while capturing traffic:
   ```bash
   python scripts/capture_cdp.py --port 9222 --seconds 90 --out .o11y/run1
   ```
   This writes the network trace under `.o11y/run1/cdp/network/`.

2. **Analyze.** Turn the trace into an API spec + a typed client (this also strips secrets and
   splits GraphQL operations automatically):
   ```bash
   node scripts/_engine/discover.mjs --run .o11y/run1
   ```
   Outputs land in `.o11y/run1/api-spec/`: `openapi.yaml`, `client.mjs`, `report.md`,
   `confidence.json`, `samples/`. Read `report.md` first.

3. **Decide replayable vs bail.**
   ```bash
   python scripts/detect_replayable.py --run .o11y/run1
   ```
   Exit 3 = bail to GUI (read `reasons`). Exit 0 = proceed.

4. **Validate (mandatory before trusting it).** Replay the submit and diff against the demonstrated
   result. The demonstration already mutated the target, so this **refuses** to re-fire a mutating
   request unless you point it at a sandbox/idempotent target:
   ```bash
   python scripts/validate_replay.py --run .o11y/run1            # idempotent/read probe
   python scripts/validate_replay.py --run .o11y/run1 --allow-mutation   # sandbox/test account only
   ```
   Only persist the client on a passing status/field match.

5. **Reuse.** Save the validated operation (from `client.mjs` / `openapi.yaml`) and call the API
   directly next time. Re-source auth (cookies/headers) from the **live session** each run — never
   hardcode tokens; they expire.

## Bundled scripts
- `scripts/capture_cdp.py` — CDP capture → the engine's `.o11y` trace layout (ours).
- `scripts/_engine/` — Browserbase `browser-to-api` engine (MIT, vendored, unmodified; see
  `scripts/_engine/LICENSE.txt`): trace → OpenAPI + typed client + redaction + GraphQL.
- `scripts/detect_replayable.py` — bail-to-GUI classifier (ours).
- `scripts/validate_replay.py` — replay-and-diff gate with idempotency guard (ours).

## References
- `references/hard-cases.md` — signed bodies, anti-bot, GraphQL, multi-call chains, and how to bail. *(TODO)*
