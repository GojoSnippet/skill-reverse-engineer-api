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
- Read reverse-engineer-api's SKILL.md and follow its Procedure exactly.
- I'm already logged in. [PREP if the action needs setup: <reach the state where the action is possible>.]
  Capture ONLY the action: capture --start -> do the action ONCE -> capture --stop.
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

**Teach** (API-ify just the download action of `open_and_download_summary`)
```
Use the reverse-engineer-api skill in teaching mode to convert the alphaskill-metaview
"open_and_download_summary" step's DOWNLOAD action into an API-backed call.
- Target (editable): the alphaskill-metaview skill, step "open_and_download_summary".
- Read reverse-engineer-api's SKILL.md and follow its Procedure exactly.
- PREP (outside capture): open the note "<title or https://my.metaview.app/notes/<id>>", select the
  Summary tab, apply the One Pager template, wait for "Saved".
- Then capture ONLY the download: capture --start -> click the download icon ONCE -> capture --stop.
- Do NOT git commit — I'll review the diff.
```

**Reuse**
```
Open and download the One Pager summary for the Metaview note <id> ("<title>"). Just download the summary.
```
