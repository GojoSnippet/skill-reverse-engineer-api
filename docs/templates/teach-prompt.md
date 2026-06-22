# Teaching prompts — copy, fill the `<slots>`, paste into a session

Three prompts, used in order. Warm-up + Teach go in the **teaching** session; Reuse goes in a **separate,
later** session to prove it works.

---

## 1. Warm-up (always first — log into the app)
```
Log in to <app>. Go to <login url> and log in with <how: the creds below / "Continue with Microsoft" / ...>:
username <username>, password <password>.
Confirm you reach <the landing page>, then stop.
```

## 2. Teach
```
Use the reverse-engineer-api skill in teaching mode to convert the <skill> "<step>" step into an
API-backed step.
- Target (editable): the <skill> skill, step "<step>".
- Read reverse-engineer-api's SKILL.md and follow its Procedure exactly, including its HARD RULES.
- I'm already logged in.
- CAPTURE THE WHOLE ACTION FROM A CLEAN STATE. Start from <a clean instance: e.g. a note with NO template
  applied yet>. Do NOT do any setup before capture --start — if the UI does it (open, apply a template, wait
  for "Saved", download), it must all be inside the capture. capture --start -> do the entire action once ->
  capture --stop. Keep the UI's downloaded file as the golden.
- Then PROVE IT: rebuild the whole thing as one self-contained API chain and run the equivalence gate on a
  DIFFERENT, fresh instance (one you did NOT set up). Only write the API step if its output matches the UI's
  output (verify_equivalence = MATCH). If it doesn't match, keep the UI and tell me why.
- Do NOT git commit — I'll review the diff.
```

## 3. Reuse (a separate, later session — the proof)
A plain, normal request — **no mention of API or teaching**:
```
<the normal task>, e.g. "Download invoice 12345 and save the PDF to /agent/user-data/outputs/."
```

---

## Filled example — Metaview (`clicks-ai/alphaskill`)

**Warm-up**
```
Log in to Metaview. Go to https://my.metaview.app and log in with "Continue with Microsoft":
username clicks.agent@alphaskill.com, password <from the step file>.
Confirm you reach the conversations list, then stop.
```

**Teach** (API-ify `open_and_download_summary` — the WHOLE thing: apply One Pager + download)
```
Use the reverse-engineer-api skill in teaching mode to convert the alphaskill-metaview
"open_and_download_summary" step into an API-backed step.
- Target (editable): the alphaskill-metaview skill, step "open_and_download_summary".
- Read reverse-engineer-api's SKILL.md and follow its Procedure exactly.
- CAPTURE THE WHOLE ACTION FROM A CLEAN NOTE. Pick a note that does NOT have the One Pager applied yet. Do
  nothing before capture --start. Then: capture --start -> open the note, select Summary, Use template ->
  One Pager, wait for "Saved", click download -> capture --stop. The apply-template step MUST be inside the
  capture (last time it was done in prep and the API skipped it — that is the bug we are fixing). Keep the
  downloaded PDF as the golden.
- PROVE IT: run the equivalence gate on a DIFFERENT note that has no One Pager applied — the API chain must
  apply the template itself and produce a PDF that matches that note's UI download (verify_equivalence =
  MATCH). If it doesn't match, keep the UI and tell me why.
- Do NOT git commit — I'll review the diff.
```

**Reuse**
```
Open and download the One Pager summary for the Metaview note <id> ("<title>"). Just download the summary.
```
