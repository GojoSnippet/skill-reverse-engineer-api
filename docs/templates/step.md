<!--
  Mission-style UI step template.
  Copy to <client-skill>/steps/<step>.md and fill in the <...> slots.
  This is the UI baseline; teaching mode later inserts an "## API attempt" ABOVE the instructions and
  preserves these instructions verbatim as "## UI instructions". So write the UI steps well — they stay
  as the permanent fallback.

  How to write good instructions:
  - ONE concrete action per numbered line (open / navigate / click X / type Y / wait for Z).
  - Make the LAST data action (download / read / generate) unambiguous — that's the one teaching mode
    turns into an API call.
  - Keep it deterministic: name exact buttons/links, say what "done" looks like.
  - Inline login creds are fine for a test account (rotate after). They live ONLY in this step file.
-->

### <Step title>

Mission: <one sentence — what this step accomplishes and the single output it produces>.

Inputs:
- <input_name>: <what it is and where it comes from, e.g. "the invoice id, from the URL .../invoices/<id>/view">.

Instructions:
1. Open Chrome.
2. Navigate to `<app url>`. If you are not already logged in, log in at `<login url>` with:
   - email: `<email>`
   - password: `<password>`
3. <concrete UI action>
4. <concrete UI action>
5. <the data action — download / read / generate — this is what gets API-ified>
6. <if it produced a file, save it to `/agent/user-data/outputs/`>

Return value:
- <field>: <what to return>, or `NAN` if it could not be completed.

Important:
- <safety: read-only? do not modify/delete? only return X, never Y>.
- If you cannot find the target or cannot log in, return `NAN` — do not guess.
