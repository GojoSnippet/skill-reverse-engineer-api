# reverse-engineer-api — Design (C2)

Implements [SPEC.md](./SPEC.md). **C2 = our thin CDP capture + Browserbase's `browser-to-api`
engine run locally.** Adds Node + a Chromium flag; everything else is skill content.

## Data flow
```
 demonstrate (browser, debug port)
        │  CDP: Network.requestWillBeSent / responseReceived / getResponseBody
        ▼
 capture_cdp.py  ──►  .o11y/<run>/cdp/network/
        │                 requests.jsonl   (raw requestWillBeSent events)
        │                 responses.jsonl  (raw responseReceived events)
        │                 bodies/<requestId>/{request,response}.json   ({id, body})
        ▼
 discover.mjs (Browserbase brain, Node, MIT)  ──►  .o11y/<run>/api-spec/
        │      load→filter→normalize→infer→emit        openapi.yaml / .json
        │      (noise filter, path-template, schema      client.mjs   (typed fetch client)
        │       inference, redaction, GraphQL split)     report.md / confidence.json / samples/
        ▼
 detect_replayable.py  ──►  replayable? else BAIL-TO-GUI (reason)
        ▼
 validate_replay.py    ──►  replay client + diff vs golden; idempotency-guarded; persist on pass
```

## The capture↔engine contract (verified against the engine's `load.mjs`)
The engine reads the **raw CDP events** — our capture writes each event verbatim, one per line:
- `requests.jsonl`: each line = a `Network.requestWillBeSent` message; engine reads
  `params.requestId`, `params.request.{method,url,headers,postData}`, `params.type`, `params.wallTime`.
- `responses.jsonl`: each line = a `Network.responseReceived` message; engine reads
  `params.requestId`, `params.response.{status,headers}`.
- `bodies/<requestId>/response.json` = `{"id":"<requestId>","body":"<text>"}` — response bodies
  (the CDP firehose doesn't embed them; we pull via `Network.getResponseBody`). `request.json` likewise
  for non-`postData` request bodies.
Join key throughout is `requestId`. **No translation layer** — we emit the events we already receive.

## Components
| File | Lang | Origin | Role |
|---|---|---|---|
| `scripts/capture_cdp.py` | Python | **ours** | CDP client → writes the `.o11y` trace layout |
| `scripts/discover.mjs` (+ filter/normalize/infer/emit/load + lib/*) | Node | **vendored Browserbase (MIT)** | traffic → OpenAPI + typed client + redaction + GraphQL |
| `scripts/detect_replayable.py` | Python | **ours** | bail-to-GUI classifier |
| `scripts/validate_replay.py` | Python | **ours** | replay-and-diff gate (idempotency guard) |
| `SKILL.md` | — | **ours** | method, triggers, when-to-bail |

## Infra changes (the only product code)
1. `infra/images/vnc-desktop-base/install/25-apt-node.sh` — install Node 18+, following the existing
   numbered install-script pattern (Dockerfile adds `RUN /opt/vnc-desktop-install/25-apt-node.sh`).
2. `infra/images/vnc-desktop-base/image/usr/local/bin/chromium` — append
   `--remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --remote-allow-origins=*`.

## Bail-to-GUI heuristics (`detect_replayable.py`)
Flag **non-replayable** when the captured submit request shows any of: a body field/header that looks
HMAC/signature/nonce (`*sig*`, `*signature*`, `*nonce*`, base64/hex blobs with high entropy), a
Turnstile/reCAPTCHA token, an anti-bot challenge response (403/429 + `cf-mitigated`/`akamai` headers),
or the workflow needed N coupled calls where a later call consumes a value minted by in-page JS (not
present in any earlier response). On any flag → recommend GUI fallback, with the specific reason.

## Test harness (`specs/reverse-engineer-api/e2e/`)
`run_e2e.sh` + `test_page.html` (POSTs to a safe fake API) launch a debug-port Chromium, run all four
scripts, and assert AC1–AC4. No cloud, no API key.
