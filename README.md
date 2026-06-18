# reverse-engineer-api (Agent Skill)

Discover a web app's underlying HTTP API from a demonstration and replay a workflow via
direct API calls instead of GUI clicks. Cloned by agents into `/agent/skills/reverse-engineer-api`.

- `SKILL.md` — the method the agent follows.
- `scripts/capture_cdp.py` — CDP capture → `.o11y` trace (ours).
- `scripts/_engine/` — Browserbase `browser-to-api` engine, **MIT**, vendored unmodified
  (see `scripts/_engine/LICENSE.txt`): trace → OpenAPI + typed client + redaction + GraphQL.
- `scripts/detect_replayable.py` — bail-to-GUI classifier (ours).
- `scripts/validate_replay.py` — replay-and-diff gate with idempotency guard (ours).

Requires the runtime to have Node 18+ and Chromium launched with a CDP debug port.
