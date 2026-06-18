# reverse-engineer-api — Specification

## 1. Purpose
Let an agent learn a web app's underlying HTTP API from a demonstration and then reproduce a
workflow with **direct API calls** instead of GUI clicks — collapsing a long form's dozen+ expensive
GUI inferences into a single request. Biggest payoff: long, multi-field form submissions.

## 2. Scope
**In:** discover the request(s) behind a demonstrated workflow, generate a parameterized client,
validate it reproduces the outcome, save it as a reusable skill, and bail back to the GUI when the
workflow can't be reproduced via direct calls.
**Out (this version):** WebSocket/gRPC-web workflows; defeating active anti-bot/JS-signed requests
(these must be *detected* and routed back to the GUI, not solved); a UI for browsing discovered APIs.

## 3. Delivery model (C2)
Shipped as a **skill** (`SKILL.md` + bundled scripts run via the agent's `bash` tool) — **no `apps/`
code change**. Two infra changes only: **Node** in the runtime base image and a **Chromium
debug-port flag**. Capture is ours (thin Python CDP client); analysis/codegen is **Browserbase's
`browser-to-api` engine (MIT) run locally** (OpenAPI + typed client + secret-redaction + GraphQL).

## 4. Capability contract (phases)
| Phase | Input | Output |
|---|---|---|
| Capture | a debug-port Chromium + a demonstrated workflow | `.o11y/<run>/cdp/network/{requests,responses}.jsonl` + `bodies/<requestId>/` |
| Analyze | that trace | `<run>/api-spec/{openapi.yaml, client.mjs, report.md, confidence.json, samples/}` |
| Decide | the spec + traffic | replayable ✅ / **bail-to-GUI** ❌ (with reason) |
| Validate | the generated client | pass/fail vs the demonstrated outcome (idempotency-guarded) |
| Persist | a validated client | saved into the skill for reuse |

## 5. Functional requirements
- **FR1 Capture** — record every request/response (method, URL, headers, request body, response body,
  status) of the demonstrated workflow from the agent's own authenticated browser via CDP, writing the
  exact `.o11y` layout the analysis engine consumes. Filter obvious static/analytics noise.
- **FR2 Analyze** — run the local engine to emit an OpenAPI 3.1 spec + a typed client, with secrets
  redacted (`authorization`/`cookie`/tokens/JWTs/emails → `<redacted>`) and GraphQL/multiplexed
  endpoints decomposed.
- **FR3 Parameterize** — identify the submit operation and expose the form fields as inputs (constants
  vs inputs vs session-derived).
- **FR4 Validate (gate)** — replay the generated client once and diff its result against the
  demonstrated outcome; **refuse to re-fire a mutating request** unless pointed at a sandbox/idempotent
  target. Persist only on pass.
- **FR5 Bail-to-GUI** — detect non-replayable workflows (JS/WASM-signed or HMAC'd bodies, per-request
  server nonces, active anti-bot challenges, multi-call chains that don't reduce) and fall back to the
  existing GUI path, recording why.
- **FR6 Reuse** — a saved client re-sources auth from the live session each run (no hardcoded,
  stale credentials).

## 6. Non-functional requirements
- **NFR1** No MCP dependency (our runtime has none). Capture talks raw CDP.
- **NFR2** Runtime languages: Python 3.14 (present) for capture/validate; Node 18+ (added) for the engine.
- **NFR3** All scripts run via the agent's `bash` tool; no native product code path.
- **NFR4** Vendored third-party code (Browserbase engine) is MIT, attributed, unmodified, with provenance.
- **NFR5** Capture binds the debug port to loopback only.

## 7. Skill interface (how the agent uses it)
Triggered by the SKILL.md description (e.g. "reverse engineer api", "call the API directly",
"automate this form"). The agent runs, in order:
```
python scripts/capture_cdp.py --port 9222 --out .o11y/<run>      # FR1
node   scripts/discover.mjs   --run .o11y/<run>                  # FR2/FR3
python scripts/detect_replayable.py --run .o11y/<run>           # FR5 (gate)
python scripts/validate_replay.py --run .o11y/<run> [--allow-mutation]   # FR4
```

## 8. Acceptance criteria (testable)
- **AC1** Given a page that performs a JSON `POST`, `capture_cdp.py` produces `requests.jsonl`,
  `responses.jsonl`, and `bodies/<id>/response.json` containing that POST with its body.
- **AC2** `discover.mjs` on that capture emits `openapi.yaml` + `client.mjs` containing the POST
  endpoint, with any auth header redacted.
- **AC3** `validate_replay.py` replays against an idempotent/sandbox target and reports a status/field
  match; without `--allow-mutation` it **refuses** to replay a mutating method (exit 2).
- **AC4** `detect_replayable.py` flags a signed-body/anti-bot capture as **bail-to-GUI**.
- **AC5** No file under `apps/` changes; the only product changes are `install/25-apt-node.sh` and the
  chromium wrapper flag.

## 9. Verification
A self-contained E2E harness (`specs/reverse-engineer-api/e2e/`) launches a debug-port Chromium against
a local page that POSTs to a safe fake API, runs all four scripts, and asserts AC1–AC4. Runs in CI/dev
with Python + Node + a Chromium binary (no cloud, no API key).
