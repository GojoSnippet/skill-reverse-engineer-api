# Runbook — teach a UI step into an API-backed step, then reuse it

Teaching mode watches you do one UI step, captures the real API call, and — **if it can be faithfully
replayed** — writes an `## API attempt` into that step (the original UI is preserved verbatim as the
fallback). A later session runs the step via the API, no UI. If it can't be replayed, it keeps the UI and
says why. It edits **only the one target step file**.

---

## Phase 0 — Prereqs (once)
- Stack up: `make run` (SPA `:5173`, `event_read :8004`).
- The test Agent can mount **`reverse-engineer-api`** (read-only) + the **client skill repo** (editable).

## Phase 1 — Teach a step
1. **Mount** `reverse-engineer-api` (ro) + `<client-repo>` (editable). Start a **fresh session**.
2. **Warm up** — log into the app (so capture records only the action, and the API has a live session).
3. **Teach** (fill in `<skill>`, `<step>`, and any prep):
   ```
   Use the reverse-engineer-api skill in teaching mode to convert the <skill> "<step>" step into an
   API-backed step.
   - Target (editable): the <skill> skill, step "<step>".
   - Read reverse-engineer-api's SKILL.md and follow its Procedure exactly.
   - I'm already logged in. [PREP if needed: <reach the state where the action is possible>.]
     Capture ONLY the action: capture --start -> do the action ONCE -> capture --stop.
   - Do NOT git commit — I'll review the diff.
   ```
4. **What good looks like:** `probe_auth` runs (fast auth decision) → faithful replay → one validation run
   → `teach_insert` → the `git diff --name-only` check shows **only the one step file** → a `TAUGHT`
   report (`api-added` or `kept-ui`).

## Phase 2 — Review the diff
`git -C <client-repo> diff` and confirm:
- exactly **one** step file changed;
- `## API attempt` inserted **above** `## UI instructions`, which is **byte-identical** to the old steps;
- header says `validated: yes (<evidence>)`;
- the `## API attempt` command is a faithful transcription (real op/URL/headers), predicate uses real
  response fields, auth is re-sourced live (no committed token).

## Phase 3 — Commit (your call)
If the diff is good, commit it in the client repo (your name). That's what makes the API step permanent.

## Phase 4 — Reuse (prove the payoff)
1. **Fresh session**, the client repo mounted (now with the committed API step).
2. **Warm up** — log into the app.
3. **Plain task** (no teaching, no mention of API): the normal request, e.g. *"download invoice X"*.
4. It should run the **API** (`run-in-page`) and report `method: api` — **no UI clicking**.

## Reading any session's result
- `curl "http://localhost:8004/events?agent_id=<session-id>&order=asc&size=1000"`  *(size ≤ 1000)*
- **API win:** a `run-in-page` result `{"ok": true, ...}` + `method: api`, and **no `computer` calls**.
- **Kept-UI:** the report says `kept-ui` with the case + reason — a valid outcome (not every step replays).

---

## Current state
- **Wave** (`GojoSnippet/skill-test-workflows`, `download-invoice`): taught + **reuse proven** (22 s, API, no UI).
- **Metaview** (`clicks-ai/alphaskill`, `open_and_download_summary`): taught + validated live (45 KB PDF via a
  `BootstrapSynthesis → ExportAiNotesMutation` chain); diff ready for review/commit.
