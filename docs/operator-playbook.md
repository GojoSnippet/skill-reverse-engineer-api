# Operator playbook — turn a client's UI step into an API-backed step

**Who this is for:** whoever onboards clients and runs this task day to day.
**What it does:** you demonstrate one UI step **once**; teaching mode captures the real API behind it and
rewrites that step to call the API directly — falling back to the UI automatically if the API ever fails.
A later run does the step via API: faster, cheaper, no clicking.

**The whole job is 5 steps:** make sure the UI step exists → teach it → review the diff → commit → reuse test.

---

## 0. Is this step worth API-ifying? (10-second filter)
- ✅ **Yes:** the step does **one clear data action** backed by the app's own API — a download/export, a
  fetch/read, or a render/generate. **Reads** and **consequence-free writes** (e.g. "generate a PDF") are ideal.
- ❌ **No — leave it as UI:** destructive/irreversible writes (send, pay, delete) with no safe way to test;
  pages behind CAPTCHA / anti-bot / signed requests; steps that are mostly human judgement.
  (Teaching mode will *also* refuse these and keep the UI — but don't waste a session starting.)

## 1. Prereqs
- Dev stack up: `make run` (gives you the SPA on `:5173` and the event API on `:8004`).
- On the test Agent you can mount two skills:
  - **`reverse-engineer-api`** (read-only) — the teaching helper.
  - the **client skill repo** (editable) — the workflow you're API-ifying.
- The step you'll teach **already exists as a UI step file** in the client repo (mission style). If you're
  starting a brand-new workflow, write the UI step first from [`templates/step.md`](templates/step.md).
  **Teaching mode API-ifies an existing UI step — it does not invent the workflow.**

## 2. Teach it (one session)
1. Mount `reverse-engineer-api` (ro) + the client repo (editable). **Fresh session.**
2. **Warm up** — log into the app first, using the login prompt in
   [`templates/teach-prompt.md`](templates/teach-prompt.md). *(Why: the API needs a live logged-in session,
   and it keeps the capture clean.)*
3. **Teach** — paste the teach prompt from the same template, filling in `<skill>`, `<step>`, the prep, and
   the **one action** to capture.
4. Let it run. It ends with a `TAUGHT` report: **`api-added`** or **`kept-ui`** (both are valid — see §6).

## 3. Review the diff (1 minute)
`git -C <client-repo> diff` and confirm:
- exactly **one** step file changed;
- a `## API attempt` block was inserted **above** the original instructions (now `## UI instructions`);
- the `## UI instructions` are **byte-identical** to the old steps — your proven path is untouched;
- the header says `validated: yes (<evidence>)`.

If anything else changed, or the UI was reworded → stop and re-teach. (The tooling prevents this, so it
shouldn't happen — but always glance.)

## 4. Commit
Commit the one changed file.
**Do it on a branch first:** use a **slash-free** branch name like `api-<step>` (e.g. `api-download-summary`).
⚠️ **Not** `feat/...` — a `/` in the branch name breaks the skill mount (see §7). Test reuse on the branch,
then merge to `main`.

## 5. Reuse test (prove the payoff)
1. **Fresh session**, the client repo mounted on your **branch** (read-only is fine — not teaching now).
2. **Warm up** — log into the app.
3. Give the **plain task** — the normal request, *no mention of API* (e.g. "download invoice 12345").
4. It should run the API and report `method: api` — **no UI clicking**.

**Verify from the events:**
```bash
curl "http://localhost:8004/events?agent_id=<session-id>&order=asc&size=1000"
```
- **Win:** a `run-in-page` result `{"ok": true, ...}` and `method: api`, with **no `computer` tool calls** in the step.
- **Kept-UI:** `method: ui` — read §6 before deciding it's a problem.

## 6. Expectations (read this — manage your own)
- **`api-added`** → success. The step now runs via API, with the UI as automatic fallback.
- **`kept-ui`** → **NOT a failure.** Some steps genuinely can't be replayed (the app's auth isn't
  reproducible, or it's signed/anti-bot). The taught report tells you *why*. The step keeps working via the
  UI exactly as before — **you've lost nothing**, you just didn't gain the speedup for that one step.
- **Teaching takes a few minutes; reuse is seconds.** The teach is a one-time cost per step.
- It edits **only the one step file** and never touches the UI text — by design.

## 7. Troubleshooting (the real gotchas we hit)
| Symptom | Cause / fix |
|---|---|
| Session **errors immediately**; logs show `resolve_skill_mounts` failing | Branch name has a `/`. Use a **slash-free** branch (`api-download`, not `feat/api-download`). |
| **Reuse runs the UI**, not the API | You mounted the wrong branch (the one without `## API attempt`), or didn't log in first. Open the step in the Skills panel — it must show `## API attempt` at the top. |
| Event query returns **422 / empty** | `size` must be **≤ 1000**. |
| Teach feels **slow** | Normal — capture + analyze + validate. Only worry if it's >15 min with no `TAUGHT` report; then stop and retry. |

## Worked examples (both proven end-to-end)
- **Wave** — `download-invoice`: a GraphQL mutation authed by the `waveapps` cookie used as a bearer →
  PDF. Taught + reused via API in **22 s**.
- **Metaview** (`clicks-ai/alphaskill`, `open_and_download_summary`): a 2-call chain
  `BootstrapSynthesis → ExportAiNotesMutation` → base64 PDF. Taught + reused via API in **~37 s**.
