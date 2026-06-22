# Operator playbook — API-ify one UI step (non-CS tick-box)

**Who this is for:** whoever onboards clients and runs this task day to day.
**What it does:** you demonstrate one UI step **once**; teaching mode captures the real API behind it and
rewrites that step to call the API directly — falling back to the UI automatically if the API ever fails.
A later run does the step via API: faster, cheaper, no clicking.

You never judge a value yourself. **Each box is a command with a binary outcome, and the gates decide.**
Your only human inputs are the **clean ≥2-run capture** and the **frozen per-segment comparator**. A
`→ KEEP UI` exit is the system working, not a failure (see Expectations).

The full algorithm is in [`DESIGN.md`](DESIGN.md); the frozen wire formats are in
[`../CONTRACTS.md`](../CONTRACTS.md). This page is the operator surface only.

---

## 0. Is this step worth API-ifying? (10-second filter)
- **Yes:** the step has a clear data goal backed by the app's own API — a download/export, a fetch/read, or
  a render/generate — reachable as one call or a short self-contained chain (set up → act). Reads and
  consequence-free writes are ideal.
- **No — leave it as UI:** destructive/irreversible writes (send, pay, delete) with no safe way to test;
  pages behind CAPTCHA / anti-bot / signed requests; steps that are mostly human judgement. (The gates will
  *also* refuse these and keep the UI — this filter just saves you a session.)

## 1. Prereqs
- Dev stack up (whatever your project's "run the full stack" target is) — the SPA and the event API.
- On the test Agent you mount two skills:
  - **`reverse-engineer-api`** (read-only) — the teaching helper.
  - the **client skill repo** (editable) — the workflow you're API-ifying.
- The step you'll teach **already exists as a UI step file** in the client repo (mission style). If you're
  starting a brand-new workflow, write the UI step first from [`templates/step.md`](templates/step.md).
  **Teaching mode API-ifies an existing UI step — it does not invent the workflow.**
- Log into the app first (warm session), using the warm-up prompt in
  [`templates/teach-prompt.md`](templates/teach-prompt.md). Then paste the teach prompt from the same file.

---

## The checklist (the whole job)

Run each box as a command and read its outcome. **The unit of API-ification is a SEGMENT** — a maximal
contiguous run of data-work actions, not the whole workflow and not a single action. A workflow yields
**0, 1, or many** segments; do boxes 1–8 per segment, then recombine once.

```
TEACH <skill>/<STEP>
[ ] 0 Partition     partition.py --step steps/<STEP>.md          → segments==0? KEEP UI, done.
[ ] 1 Capture WHOLE capture_cdp.py --start … do the ENTIRE segment, clean, ≥2 varied inputs … --stop
                    (writes the trace, the golden, and segment_inputs.json)
[ ] 2 Analyze       analyze.py --run .o11y/run --match <url-bit>
[ ] 3 Bail-scan     detect_replayable.py --run .o11y/run         → exit 3? KEEP UI (signed/anti-bot).
[ ] 4 Classify      classify_values.py --runs .o11y/run .o11y/run2 --plan plan.json
      (G1 + G2)      → unexplained==[] AND a poll/loop wherever the UI waited/paged? else fix capture or KEEP UI.
[ ] 4b Chain-check  check_chain.py --plan plan.json              → every value sourced + chain self-contained? else KEEP UI.
[ ] 5 Auth (G4)     probe_auth.py --request req.json             → working:false? KEEP UI.
[ ] 6 Build         author command.sh from plan.json (setup → POLL/REPEAT → act → return the artifact)
[ ] 7 PROVE (G3)    prove_runner.py --command command.sh --instances <fresh,isolated,boundary> --runs 2
      → MATCH on all (fresh, isolated, boundary, every-COMPUTED-perturbed)? else KEEP UI.
[ ] 8 Write         teach_insert.py --step steps/<STEP>.md --header "<provenance · validated:yes>" --command command.sh
      (only on a box-7 MATCH; KEEP UI ⇒ do NOT run this)
[ ] 9 Discipline    git diff --name-only → MUST be only steps/<STEP>.md (else git checkout it)
RESULT: api-added (all PASS) | kept-ui (any BAIL/FAIL) — both correct.
```

If the workflow has more than one segment, run boxes 1–8 for each, then:

```
[ ] R Recombine     recombine.py → ordered regions, typed handoffs validated, run-scope threaded.
```

**Rules of the checklist (these bind you, not the prose):**
- **Tick a box only after pasting that command's output.** No ticking from memory or expectation.
- **You may not run box 8 (`teach_insert.py`) until every gate has passed** — box 3 not exit 3, box 4
  `unexplained==[]`, box 5 not `working:false`, box 7 MATCH on all instances. The write is mechanical; the
  gates are what earn it.
- **Capture the WHOLE segment from a clean state, with ≥2 varied inputs** (box 1). Nothing set up before
  `capture --start`; if the UI does it (open, apply a template, wait for "Saved", download), all of it is
  inside the capture. The ≥2 varied inputs are what let box 4 separate constants from inputs from
  client-computed values.

---

## The gates (what each box is really checking)

Each gate is `input → {PASS | FAIL→keep-UI | BAIL→keep-UI}`. No operator prose overrides a gate.

| Gate | Box | Mechanical check | KEEP-UI when |
|---|---|---|---|
| **G1 self-contained** | 4, 4b | every request value is sourced (constant / input / derived / produced / client-computed); nothing unexplained; nothing contested | a value can't be sourced after a bounded code read (BAIL-2), or the golden appears in no response (BAIL-1) |
| **G2 no-fixed-wait** | 4 | every place the UI waited has a POLL; every continuation (cursor/`has_more`) has a REPEAT; **zero** fixed sleeps | readiness is push-only — no repeatable read reflects it (BAIL-3) |
| **G4 auth-reproducible** | 5 | the credential re-sources in a fresh context (cookie session / readable-token-as-bearer / signature-recipe / refresh-mint) and a guarded call isn't 401/403 | the credential is device/origin-bound or unreadable (BAIL-4) |
| **G3 proven** | 7 | the API output **content-equals** the UI golden under the **frozen** comparator, on **mutually-isolated, boundary-spanning** held-out instances — forcing pagination (if any loop) and perturbing every client-computed value | any instance/run diverges (BAIL-5), or a coverage obligation is unmet |

G3 is the backstop. It rejects the same-instance false-pass, the unsampled-band, the truncated-pagination,
and the masked-the-answer bugs — and the cautionary tale below.

---

## Review the diff (1 minute)

`git -C <client-repo> diff` and confirm:
- exactly **one** step file changed;
- an `## API attempt` block was inserted **above** the original instructions (now `## UI instructions`);
- the `## UI instructions` are **byte-identical** to the old steps — your proven path is untouched;
- the header says `validated: yes (equivalent to UI on a held-out instance …)` and the report has an
  **`EQUIVALENCE: MATCH`** line — *not* just "a file was produced."

If anything else changed, or the UI was reworded → stop and re-teach. (The tooling prevents this, so it
shouldn't happen — but always glance.)

## Commit
Commit the one changed file. **Do it on a branch first:** use a **slash-free** branch name like
`api-<step>` (e.g. `api-download-summary`). A `/` in the branch name breaks the skill mount (see
Troubleshooting). Test reuse on the branch, then merge to `main`.

## Reuse test (prove the payoff)
1. **Fresh session**, the client repo mounted on your **branch** (read-only is fine — not teaching now).
2. Warm up — log into the app.
3. Give the **plain task** — the normal request, *no mention of API* (e.g. "download invoice 12345").
   Prefer a **fresh entity** you didn't teach on, so you're testing generalization.
4. It should run the API and report `method: api` — no UI clicking.
5. **Open the produced file and check its contents** — not just that a file appeared. (A file existing is
   not proof; the gates are — but spot-check anyway.)

**Verify from the events** (`order=asc`, `size ≤ 1000`):
- **Win:** a `run-in-page` result `{"ok": true, ...}` and `method: api`, with **no `computer` tool calls** in the step.
- **Kept-UI:** `method: ui` — read Expectations before deciding it's a problem.

---

## Expectations (read this — manage your own)
- **`api-added`** → success. The step now runs via API, with the UI as automatic fallback.
- **`kept-ui`** → **NOT a failure, and a frequent, expected outcome.** Some steps genuinely can't be
  replayed (auth isn't reproducible, it's signed/anti-bot, the golden is client-rendered, or **the API
  output didn't content-equal the UI's** — a gate caught a chain that doesn't faithfully reproduce the UI).
  The report tells you *which gate* and *why*. The step keeps working via the UI exactly as before — **you've
  lost nothing**, you just didn't gain the speedup. A plan may be all-UI, all-API, or mixed.
- **`validated: yes` means "proven content-equal to the UI on held-out instances," not "a file exists."**
  That stronger bar is the point — it's what stops a fast-but-wrong step from shipping.
- **Teaching takes a few minutes; reuse is seconds.** The teach is a one-time cost per segment.
- It edits **only the one step file** and never touches the UI text — by design.

## The cautionary tale (the one bug this whole playbook exists to prevent)
> An early teach (a real one, on a template-then-download workflow) captured only the **download** and
> skipped the **setup mutation** that ran in "prep" *outside* the capture. The API "succeeded" — it produced
> a small PDF — but it was the **wrong artifact**: the real output was several times larger / multi-page.
> Nobody opened the file, so a transport-only "it worked" hid it.
>
> Two failures, two gates. The dropped setup mutation is a missing call in the segment → it surfaces as an
> unsourced value at **box 4 (G1)**. The "a file exists" rubber-stamp is what **box 7 (G3)** replaces with
> content-equality on a held-out instance. Capture the **whole** segment (box 1), and **prove the output
> equals the UI's** (box 7), and this bug cannot ship.

## Troubleshooting (the real gotchas)
| Symptom | Cause / fix |
|---|---|
| Session **errors immediately**; logs show skill-mount resolution failing | Branch name has a `/`. Use a **slash-free** branch (`api-download`, not `feat/api-download`). |
| **Reuse runs the UI**, not the API | You mounted the wrong branch (the one without `## API attempt`), or didn't log in first. Open the step in the Skills panel — it must show `## API attempt` at the top. |
| Event query returns **422 / empty** | `size` must be **≤ 1000**. |
| Teach feels **slow** | Expected — the whole-capture (box 1) and the proof (box 7) are where the time goes, by design. A few minutes to teach buys seconds per reuse. Only worry if there's no `TAUGHT` report after a long while with no progress. |

## Worked examples (labeled — illustrative only, never assumed by the tooling)
- **e.g. Wave — `download-invoice`:** a GraphQL mutation authed by a cookie value reused as a bearer → a
  pre-signed S3 PDF. A single self-contained call; taught + reused via API in seconds.
- **e.g. Metaview — `open_and_download_summary`:** the apply-template-then-download workflow that is the
  subject of the cautionary tale above.
