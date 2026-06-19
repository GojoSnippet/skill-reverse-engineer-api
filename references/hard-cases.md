# Hard cases — when to bail to the UI (and the few you can handle)

The default is **API with UI fallback**. When in doubt, keep the UI step. A correct UI run beats an
API step that 200s in dev and 403s in prod. `detect_replayable.py` flags most of these automatically.

## Bail — keep the UI step

- **Signed / HMAC bodies.** A field whose value is a signature/hash computed by in-page JS (e.g.
  `x-sig`, `signature`, `_hmac`, `checksum`). You can't recompute it; the server rejects a stale one.
- **Per-request nonces.** A single-use token the server expects to differ each call. Replaying the
  captured one fails.
- **CAPTCHA / Turnstile / reCAPTCHA tokens.** Only the live page can mint these.
- **Active anti-bot challenges.** A `403`/`429` with Cloudflare/DataDome/Akamai/PerimeterX markers in
  the captured responses. (In-page fetch is same-origin and *usually* avoids passive anti-bot, but an
  active challenge in the trace means stop.)
- **Non-idempotent calls without a safe target.** `POST`/`PUT`/`PATCH`/`DELETE` that mutate. Do not
  auto-run them to "validate" — you'd double-submit. Convert these only with an explicit sandbox/test
  account, and only after the read-only steps are proven.

## Handle — these are fine with care

- **Cookie/session auth (the common case).** In-page `fetch(..., { credentials: "include" })` sends
  cookies automatically. Nothing to do.
- **CSRF tokens / custom required headers.** `analyze.py` surfaces these as `customHeaders` (anything
  not browser-auto). Include them in the fetch. With an in-page fetch the token is valid because it's
  the same session.
- **Bearer / `Authorization` / token headers.** These are **NOT** sent automatically by `fetch` — the
  app's JS normally adds them from storage. Read the token live from the page and add the header, e.g.
  `headers: { Authorization: "Bearer " + localStorage.getItem("token") }`. Never hardcode it.
  (`observedAuthHeaders` tells you when one was used.)
- **GraphQL / multiplexed endpoints.** `analyze.py` reports `operationName`, `parentPath`, and
  `discriminatorField`. Build the fetch to POST that one operation to `parentPath` (for persisted
  queries, include the `sha256Hash` from the captured request). Parameterize the `variables`.

## Tricky — usually bail for v1

- **Multi-call chains.** When the target call needs a value produced by an earlier call (a token,
  a cursor, an id) that the UI obtained in a prior step. Capturing one call isn't enough; you'd have
  to replay the chain. Bail to the UI unless the dependency is trivial and stable.
- **Parameters that change *structure*, not just value.** If different runs send a differently-shaped
  body (not just different field values), the template won't generalize. Keep the UI step.
- **Auth that expires mid-session or rotates on 401.** Re-source live each run; if it still 401s,
  fall back to the UI.
