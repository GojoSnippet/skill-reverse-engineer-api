#!/usr/bin/env python3
# run-in-page (contract 1) — execute a captured in-page fetch INSIDE the agent's already-authenticated
# browser tab over CDP, with a body-derived read/write gate, a success predicate, and binary-to-file
# output. This is a generic runtime primitive resolved BY NAME on PATH (never a path into a skill).
#
# A generated workflow step calls it like:
#   run-in-page --contract 1 [--allow-mutation] --match next.waveapps.com \
#     --out /agent/user-data/outputs/invoice.pdf \
#     --vars-json '{"invoice_id":"123","business_id":"abc"}' \
#     --js '(async () => { ... {{invoice_id}} ... return { ok, status, contentType, download:{url} }; })()'
#
# The JS must return a small JSON-serializable object:
#   { ok: <strong predicate: status + content-type + a positive shape signal>, status, contentType, ...,
#     download?: { url } ,           # helper fetches this URL and writes bytes to --out (e.g. pre-signed S3)
#     dataBase64?: "<small inline>" }# OR small inline bytes the helper decodes to --out
# {{var}} placeholders are replaced with the JSON-encoded value from --vars-json (do NOT add your own quotes).
#
# Exit codes (the step branches: 0 => done, anything else => UI fallback):
#   0 success | 1 ran but ok=false / bad output | 2 JS threw / tab not found
#   3 REFUSED: write fetch without --allow-mutation | 4 contract mismatch | 5 usage error
#
# Prereq: a CDP-enabled Chromium on a loopback debug port + `pip install websocket-client`.

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.request

CONTRACT_VERSION = 1

# Exit codes
OK, FAIL, THREW, REFUSED_WRITE, BAD_CONTRACT, USAGE = 0, 1, 2, 3, 4, 5


# ---- pure logic (unit-tested without a browser) ----------------------------

def substitute_vars(js: str, vars_obj: dict) -> str:
    """Replace every ``{{key}}`` in ``js`` with the JSON-encoded value of ``vars_obj[key]``.

    JSON-encoding keeps substitution injection-safe (a string lands as ``"abc"``, a number as ``123``).
    Author the JS WITHOUT wrapping the placeholder in quotes: ``const id = {{invoice_id}};``.
    """
    placeholders = set(re.findall(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", js))
    missing = sorted(p for p in placeholders if p not in vars_obj)
    if missing:
        raise ValueError(f"--vars-json is missing values for: {', '.join(missing)}")
    out = js
    for key in placeholders:
        out = re.sub(r"\{\{\s*" + re.escape(key) + r"\s*\}\}", lambda _m, v=vars_obj[key]: json.dumps(v), out)
    return out


_METHOD_RE = re.compile(r"""method\s*:\s*['"]([A-Za-z]+)['"]""")
_GQL_MUTATION_RE = re.compile(r"\bmutation\b\s+[A-Za-z{]")  # `mutation Name(` / `mutation {`
_GQL_QUERY_RE = re.compile(r"\bquery\b\s+[A-Za-z{]")
_PERSISTED_RE = re.compile(r"persistedQuery|sha256Hash", re.I)


def classify(js: str) -> str:
    """Derive read|write|unknown from the fetch in ``js``. Fail SAFE: ambiguous => 'unknown' (treated
    as write by the gate). Never trust a caller-supplied label."""
    methods = {m.upper() for m in _METHOD_RE.findall(js)}
    if methods & {"DELETE", "PUT", "PATCH"}:
        return "write"
    if methods & {"GET", "HEAD"} and "POST" not in methods:
        return "read"
    if "POST" in methods or not methods:
        # POST (or method omitted, default GET but bodies suggest POST-for-graphql): inspect the body.
        if _GQL_MUTATION_RE.search(js):
            return "write"
        if _GQL_QUERY_RE.search(js) and not _GQL_MUTATION_RE.search(js):
            return "read"
        if _PERSISTED_RE.search(js):
            return "unknown"  # persisted query with no inline op text -> can't tell -> approval
        if "POST" in methods:
            return "unknown"  # a plain POST we can't classify -> require approval
        return "read"  # no method, no POST body markers -> a GET
    return "unknown"


def evaluate_outcome(result: object, out_path: str | None, out_exists_nonempty: bool) -> tuple[int, dict]:
    """Map the JS return value (+ whether --out got a non-empty file) to an exit code + a small report."""
    if not isinstance(result, dict):
        return FAIL, {"ok": False, "reason": "js did not return an object", "result": result}
    ok = result.get("ok") is True
    report = {k: v for k, v in result.items() if k not in ("dataBase64", "download")}
    report["ok"] = ok
    if out_path is not None and not out_exists_nonempty:
        return FAIL, {**report, "ok": False, "reason": "expected output file is missing or empty", "outPath": out_path}
    if out_path is not None:
        report["outPath"] = out_path
    return (OK if ok else FAIL), report


# ---- CDP + I/O (needs a real browser; covered by the integration-test gate) ----

def pick_target(port: int, match: str | None) -> dict:
    data = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5))
    pages = [t for t in data if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    if match:
        pages = [t for t in pages if match in (t.get("url") or "")]
        if not pages:
            raise LookupError(f"no open tab whose URL contains {match!r} — refusing to guess the wrong tab")
        if len(pages) > 1:
            raise LookupError(f"{len(pages)} tabs match {match!r} — ambiguous; narrow --match")
        return pages[0]
    http_pages = [t for t in pages if (t.get("url") or "").startswith("http")]
    if len(http_pages) == 1:
        return http_pages[0]
    raise LookupError("multiple/zero http tabs open — pass --match <url-substr> to target the right one")


def evaluate_in_page(ws_url: str, js: str, timeout: int) -> dict:
    from websocket import WebSocketTimeoutException, create_connection
    ws = create_connection(ws_url, max_size=None)
    ws.settimeout(timeout + 5)
    ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
    ws.send(json.dumps({"id": 2, "method": "Runtime.evaluate", "params": {
        "expression": js, "awaitPromise": True, "returnByValue": True, "timeout": timeout * 1000}}))
    while True:
        try:
            msg = json.loads(ws.recv())
        except WebSocketTimeoutException:
            raise TimeoutError("timed out waiting for the in-page evaluate result")
        if msg.get("id") == 2:
            return msg.get("result", {})


def write_out(result: dict, out_path: str, timeout: int) -> bool:
    """Write binary output to --out. Prefer a download URL the helper fetches (no base64 through CDP);
    fall back to small inline dataBase64. Returns True if a non-empty file was written."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    dl = result.get("download") if isinstance(result, dict) else None
    if isinstance(dl, dict) and dl.get("url"):
        with urllib.request.urlopen(dl["url"], timeout=timeout) as r:
            data = r.read()
        with open(out_path, "wb") as f:
            f.write(data)
    elif isinstance(result, dict) and result.get("dataBase64"):
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(result["dataBase64"]))
    else:
        return False
    return os.path.getsize(out_path) > 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="run-in-page", add_help=True)
    ap.add_argument("--contract", type=int, required=True)
    ap.add_argument("--js", default=None, help="JS expression; omit to read from stdin")
    ap.add_argument("--vars-json", default="{}")
    ap.add_argument("--allow-mutation", action="store_true")
    ap.add_argument("--match", default=None, help="substring of the target tab's URL (correct-tab targeting)")
    ap.add_argument("--out", default=None, help="write binary output here")
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--timeout", type=int, default=30)
    args = ap.parse_args(argv)

    if args.contract != CONTRACT_VERSION:
        print(json.dumps({"ok": False, "reason": f"contract mismatch: step wants {args.contract}, helper is {CONTRACT_VERSION}"}))
        return BAD_CONTRACT

    js_raw = args.js if args.js is not None else sys.stdin.read()
    if not js_raw.strip():
        print(json.dumps({"ok": False, "reason": "no JS (use --js or stdin)"}))
        return USAGE
    try:
        vars_obj = json.loads(args.vars_json)
        if not isinstance(vars_obj, dict):
            raise ValueError("--vars-json must be a JSON object")
        js = substitute_vars(js_raw, vars_obj)
    except ValueError as exc:
        print(json.dumps({"ok": False, "reason": str(exc)}))
        return USAGE

    cls = classify(js)
    if cls in ("write", "unknown") and not args.allow_mutation:
        print(json.dumps({"ok": False, "class": cls, "reason": "refusing a write/unclassified fetch without --allow-mutation"}))
        return REFUSED_WRITE

    try:
        target = pick_target(args.port, args.match)
        raw = evaluate_in_page(target["webSocketDebuggerUrl"], js, args.timeout)
    except (LookupError, TimeoutError, OSError) as exc:
        print(json.dumps({"ok": False, "reason": str(exc)}))
        return THREW

    if raw.get("exceptionDetails"):
        exc = raw["exceptionDetails"]
        detail = exc.get("exception", {}).get("description") or exc.get("text") or "js exception"
        print(json.dumps({"ok": False, "reason": detail}))
        return THREW

    result = raw.get("result", {}).get("value")
    out_ok = True
    if args.out is not None:
        try:
            out_ok = write_out(result if isinstance(result, dict) else {}, args.out, args.timeout)
        except OSError as exc:
            print(json.dumps({"ok": False, "reason": f"output write failed: {exc}"}))
            return FAIL

    code, report = evaluate_outcome(result, args.out, out_ok)
    report["class"] = cls
    print(json.dumps(report))
    return code


if __name__ == "__main__":
    sys.exit(main())
