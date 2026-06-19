---
name: reverse-engineer-api
description: >-
  Teaching-mode helper: convert one existing UI workflow step into a faster API-backed version that
  runs as an in-page fetch in the already-authenticated browser, then write it INTO the target
  workflow skill (default to API, fall back to UI). Use this when a human in teaching mode asks to
  make a step use the API instead of clicking, reverse engineer the API behind a step, "apify" a
  step, or make a workflow cheaper/faster. Trigger words: reverse engineer api, use the api, apify,
  make this cheaper, convert this step to api, skip the UI for this step.
---

# Reverse-Engineer-API (teaching-mode helper)

This is a **universal helper skill**, like `skill-creator`. It does **not** hold any customer's API.
It teaches you, **in teaching mode**, how to take one step of a *target workflow skill* and produce an
**API-backed version of that step** — committed into the **target** skill, never into this one.

- **Teacher / tool:** this skill.
- **Student / output:** the target workflow skill (e.g. `metaview/`), where the learned call lives.

The committed call runs as an **in-page `fetch()`** inside the agent's authenticated browser: cookies
ride the live session automatically, it's same-origin (anti-bot won't block it), and there's no Node
or extra runtime needed. The target step then **defaults to the API and falls back to the UI**.

## Inputs (from the human's instruction)
- `TARGET_SKILL` — path to the workflow skill to improve, e.g. `/agent/skills/editable/metaview`.
- `STEP` — the step to convert, e.g. `open-and-download-summary` (its UI version is `steps/<STEP>.md`).

## When NOT to do this — bail and keep the UI step
Run `detect_replayable.py` (below). Bail (leave the UI step as-is) if the request carries a value only
the live page JS can mint — a **signature/HMAC**, a per-request **nonce**, a **CAPTCHA/Turnstile**
token — or the site shows an active **anti-bot** challenge, or the call is **non-idempotent** and you
have no safe/sandbox target. See `references/hard-cases.md`. Better a correct UI run than an API step
that 200s in dev and 403s in prod.

## Safety (always)
- **Start with read-only / idempotent steps** (downloads, lists, gets). Do not auto-run mutations.
- **Never `git commit`/`git push` yourself.** You write files into the target skill's working tree;
  the **human reviews the diff and commits** (teaching mode). Outside teaching mode, never modify skills.
- On the live site: **no delete, no modify, no data leakage.** Re-source auth from the live session;
  never hardcode tokens.

## Prerequisite — Chromium with the CDP port
```bash
curl -s http://127.0.0.1:9222/json/version >/dev/null 2>&1 \
  || (DISPLAY=:1 /usr/local/bin/chromium >/tmp/chromium.log 2>&1 &) && sleep 2
```

## Method

1. **Demonstrate + capture.** With the human, perform the target step once in the UI while recording:
   ```bash
   python scripts/capture_cdp.py --port 9222 --seconds 90 --out .o11y/run1
   ```

2. **Analyze (engine brain, no noise files).** Runs the vendored engine's analysis stages only
   (`load→filter→normalize→infer`, never `emit`) and prints candidate endpoints:
   ```bash
   python scripts/analyze.py --run .o11y/run1            # add --match <url-substr> to narrow
   ```
   Pick the candidate matching the action you just demonstrated. Note its `method`, `url`,
   `pathParams`/`queryParams` (the per-run parameters), `requestExample` (body template),
   `customHeaders` (app-specific headers the fetch needs, e.g. CSRF), and `observedAuthHeaders`.

3. **Decide replayable vs bail.**
   ```bash
   python scripts/detect_replayable.py --run .o11y/run1   # exit 3 = BAIL TO UI (read "reasons")
   ```

4. **Write the in-page fetch and validate it once.** Author the `fetch()` for the chosen endpoint as
   an async IIFE that returns a small result, parameterizing the per-run inputs. Auth notes:
   - **Cookies are automatic** with `credentials: "include"` — do nothing.
   - **Bearer/`Authorization` or token headers are NOT automatic** — read them live from the page,
     e.g. `localStorage.getItem('token')`, and add the header. (`observedAuthHeaders` tells you if one
     was used.)
   - **Add only `customHeaders`** from step 2 (CSRF, `x-requested-with`, content-type). The browser
     sets origin/referer/sec-*/cookie itself.

   Validate by running it once in the live browser (read-only = safe), then diff against the UI result:
   ```bash
   python scripts/replay_in_page.py --port 9222 --js-file /tmp/try.js
   ```
   Re-run with a **different parameter value** to confirm the template generalizes. Only proceed on a
   2xx + a result that matches the demonstrated outcome.

5. **Write the API step into the TARGET skill.** Create `"$TARGET_SKILL"/steps/<STEP>-api.md` (see
   the template below). Then edit `"$TARGET_SKILL"/SKILL.md` so the step **defaults to the API version
   and falls back to the UI**: e.g. *"For `<STEP>`: run `steps/<STEP>-api.md`; if it errors / returns
   4xx / auth fails, run `steps/<STEP>.md` (UI)."*

6. **Stop — hand to the human.** Report what changed and let the human review the diff and commit. Do
   not commit or push.

## The `<STEP>-api.md` step you write (template)
````markdown
# <STEP> — API version (default; falls back to steps/<STEP>.md on failure)

Run this in-page fetch in the authenticated browser. Cookies ride the session; this is read-only.

Parameters: <list the per-run inputs, e.g. {meetingId}>

```bash
cat > /tmp/<STEP>.js <<'JS'
(async () => {
  const r = await fetch("https://HOST/api/...{meetingId}...", {
    method: "GET",
    credentials: "include",
    headers: { /* only app-specific headers, e.g. "x-csrf-token": "..." */ },
  });
  const body = await r.text();
  return { status: r.status, ok: r.ok, len: body.length, body: body.slice(0, 4000) };
})()
JS
python <reverse-engineer-api>/scripts/replay_in_page.py --port 9222 --js-file /tmp/<STEP>.js
```

If the fetch errors, returns a non-2xx status, or the result looks wrong: **fall back to the UI step**
`steps/<STEP>.md`.
````

## Bundled scripts
- `scripts/capture_cdp.py` — record the demonstrated step's traffic via CDP (ours).
- `scripts/_engine/` — Browserbase `browser-to-api` engine (MIT, vendored, **unmodified**). We run only
  its analysis stages; never `emit`.
- `scripts/analyze.py` — run the engine's `load..infer` and surface candidate endpoints (ours).
- `scripts/detect_replayable.py` — bail-to-UI classifier (ours).
- `scripts/replay_in_page.py` — run an in-page `fetch()` over CDP and return the result (ours); both the
  teaching-time validator and the runtime executor for the committed step.

## References
- `references/hard-cases.md` — signed bodies, anti-bot, GraphQL operations, multi-call chains,
  bearer tokens, and exactly when to bail to the UI.
