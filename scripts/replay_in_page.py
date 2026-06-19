#!/usr/bin/env python3
# replay_in_page.py — run a JS snippet (an in-page `fetch()`) INSIDE the agent's already-authenticated
# browser tab over CDP, and return its result.
#
# Why in-page: the request goes out from the live session — cookies attach automatically, it's the
# same origin/TLS fingerprint as the browser (so anti-bot won't block it), and there's no Node/httpx
# at run time. This is both the teaching-time validator AND the runtime executor for a committed
# `<step>-api.md` step.
#
# SAFETY: this evaluates whatever JS you pass. Only run read-only fetches that detect_replayable.py
# has cleared. The caller (skill) is responsible for not firing mutations here.
#
# Prereq:  Chromium running with --remote-debugging-port=9222 ; pip install websocket-client
# Usage:
#   python replay_in_page.py --port 9222 --js-file step.js
#   echo '<js expr>' | python replay_in_page.py --port 9222
#
# The JS must evaluate to a JSON-serializable value. Use an async IIFE that returns a small object,
# e.g.:
#   (async () => {
#     const r = await fetch("https://host/api/thing", { credentials: "include" });
#     const t = await r.text();
#     return { status: r.status, ok: r.ok, len: t.length, body: t.slice(0, 2000) };
#   })()
#
# Exit: 0 on success, 1 if the JS threw or the returned `.status` is non-2xx.

import argparse
import json
import sys
import urllib.request

from websocket import WebSocketTimeoutException, create_connection


def pick_page_target(port: int) -> dict:
    data = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5))
    pages = [t for t in data if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    if not pages:
        sys.exit("no page target with a debugger URL; is a tab open?")
    pages.sort(key=lambda t: t.get("url", "").startswith("http"), reverse=True)
    return pages[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--js-file", default=None, help="file with the JS expression; omit to read stdin")
    ap.add_argument("--timeout", type=int, default=30)
    args = ap.parse_args()

    js = open(args.js_file).read() if args.js_file else sys.stdin.read()
    if not js.strip():
        sys.exit("no JS provided (use --js-file or pipe it on stdin)")

    target = pick_page_target(args.port)
    print(f"running in: {target.get('url', '?')}", file=sys.stderr)
    ws = create_connection(target["webSocketDebuggerUrl"], max_size=None)
    ws.settimeout(args.timeout + 5)

    ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
    ws.send(json.dumps({"id": 2, "method": "Runtime.evaluate", "params": {
        "expression": js,
        "awaitPromise": True,
        "returnByValue": True,
        "timeout": args.timeout * 1000,
    }}))

    reply = None
    while reply is None:
        try:
            msg = json.loads(ws.recv())
        except WebSocketTimeoutException:
            sys.exit("timed out waiting for the evaluate result")
        if msg.get("id") == 2:  # ignore the Runtime.enable ack (id 1) and events (no id)
            reply = msg

    result = reply.get("result", {})
    if result.get("exceptionDetails"):
        exc = result["exceptionDetails"]
        detail = exc.get("exception", {}).get("description") or exc.get("text") or exc
        print(json.dumps({"error": detail}, indent=2))
        sys.exit(1)

    value = result.get("result", {}).get("value")
    print(json.dumps(value, indent=2, default=str))
    if isinstance(value, dict) and isinstance(value.get("status"), int) and not (200 <= value["status"] < 300):
        sys.exit(1)


if __name__ == "__main__":
    main()
