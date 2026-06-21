#!/usr/bin/env python3
# capture_cdp.py — record the demonstrated action's HTTP traffic from the agent's own Chrome over the
# DevTools Protocol, into the `.o11y/<run>/cdp/network/` layout the engine (scripts/_engine/discover.mjs)
# consumes. No proxy, no MITM: it attaches to the live, already-authenticated tab via the debug port.
#
# CLEAN ONE-SHOT (preferred — record EXACTLY one action, no timing window to fumble):
#   python capture_cdp.py --out .o11y/run --start   # detaches a recorder, returns immediately
#   …perform the ONE action in the browser, once…
#   python capture_cdp.py --out .o11y/run --stop    # signals the recorder to flush + exit, prints count
# Blocking window (fallback): python capture_cdp.py --out .o11y/run --seconds 90
#
# Prereqs: Chromium launched with --remote-debugging-port=9222 --remote-allow-origins=*; websocket-client.

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

from websocket import WebSocketTimeoutException, create_connection

_STOP = False


def _on_term(_signum, _frame) -> None:
    global _STOP
    _STOP = True


def pick_page_target(port: int) -> dict:
    data = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5))
    pages = [t for t in data if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    if not pages:
        sys.exit("no page target with a debugger URL; is a tab open?")
    pages.sort(key=lambda t: t.get("url", "").startswith("http"), reverse=True)
    return pages[0]


class Conn:
    def __init__(self, ws_url: str) -> None:
        self.ws = create_connection(ws_url, max_size=None)
        self.ws.settimeout(1.0)
        self._id = 0

    def send(self, method: str, params: dict | None = None) -> int:
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params or {}}))
        return self._id

    def recv(self) -> dict | None:
        try:
            return json.loads(self.ws.recv())
        except WebSocketTimeoutException:
            return None


def capture(port: int, out: str, max_seconds: int) -> int:
    """Record until SIGTERM (one-shot --stop) or max_seconds elapses, then write the engine layout."""
    net_dir = os.path.join(out, "cdp", "network")
    os.makedirs(net_dir, exist_ok=True)
    target = pick_page_target(port)
    print(f"attached to: {target.get('url', '?')}", file=sys.stderr)
    c = Conn(target["webSocketDebuggerUrl"])
    c.send("Network.enable", {"maxResourceBufferSize": 100 << 20, "maxTotalBufferSize": 200 << 20})

    req_events: dict[str, dict] = {}
    resp_events: dict[str, dict] = {}
    resp_bodies: dict[str, str] = {}
    want_post: dict[int, str] = {}
    want_body: dict[int, str] = {}

    def on_reply(msg: dict) -> None:
        res = msg.get("result", {})
        if msg["id"] in want_post:
            rid = want_post.pop(msg["id"])
            ev = req_events.get(rid)
            if ev and res.get("postData") is not None:
                ev["params"]["request"]["postData"] = res["postData"]
        elif msg["id"] in want_body:
            rid = want_body.pop(msg["id"])
            if not res.get("base64Encoded") and res.get("body") is not None:
                resp_bodies[rid] = res["body"]

    deadline = time.time() + max_seconds
    while not _STOP and time.time() < deadline:
        msg = c.recv()
        if msg is None:
            continue
        if "method" in msg:
            m, p = msg["method"], msg.get("params", {})
            if m == "Network.requestWillBeSent":
                rid = p.get("requestId")
                req_events[rid] = msg
                r = p.get("request", {})
                if r.get("hasPostData") and not r.get("postData"):
                    want_post[c.send("Network.getRequestPostData", {"requestId": rid})] = rid
            elif m == "Network.responseReceived":
                resp_events[p.get("requestId")] = msg
            elif m == "Network.loadingFinished":
                rid = p.get("requestId")
                if rid in req_events:
                    want_body[c.send("Network.getResponseBody", {"requestId": rid})] = rid
        elif "id" in msg:
            on_reply(msg)

    drain = time.time() + 4
    while time.time() < drain and (want_post or want_body):
        msg = c.recv()
        if msg and "id" in msg:
            on_reply(msg)

    bodies_dir = os.path.join(net_dir, "bodies")
    with open(os.path.join(net_dir, "requests.jsonl"), "w") as f:
        for ev in req_events.values():
            f.write(json.dumps(ev) + "\n")
            rid = ev["params"]["requestId"]
            post = ev["params"].get("request", {}).get("postData")
            if post is not None:
                d = os.path.join(bodies_dir, rid)
                os.makedirs(d, exist_ok=True)
                json.dump({"id": rid, "body": post}, open(os.path.join(d, "request.json"), "w"))
    with open(os.path.join(net_dir, "responses.jsonl"), "w") as f:
        for ev in resp_events.values():
            f.write(json.dumps(ev) + "\n")
    for rid, body in resp_bodies.items():
        d = os.path.join(bodies_dir, rid)
        os.makedirs(d, exist_ok=True)
        json.dump({"id": rid, "body": body}, open(os.path.join(d, "response.json"), "w"))

    print(f"wrote {len(req_events)} requests, {len(resp_events)} responses to {net_dir}", file=sys.stderr)
    return len(req_events)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--out", required=True, help="run dir; trace under <out>/cdp/network/")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--start", action="store_true", help="detach a recorder and return immediately")
    g.add_argument("--stop", action="store_true", help="signal the recorder to flush + exit")
    g.add_argument("--seconds", type=int, help="blocking window mode (no detach)")
    g.add_argument("--_capture", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--max-seconds", type=int, default=300, help="safety cap for --start mode")
    args = ap.parse_args()

    pidfile = os.path.join(args.out, "cdp", "capture.pid")

    if args._capture:
        signal.signal(signal.SIGTERM, _on_term)
        signal.signal(signal.SIGINT, _on_term)
        capture(args.port, args.out, args.max_seconds)
        return

    if args.seconds:
        capture(args.port, args.out, args.seconds)
        return

    if args.start:
        os.makedirs(os.path.dirname(pidfile), exist_ok=True)
        log = open(os.path.join(args.out, "cdp", "capture.log"), "w")
        p = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--_capture",
             "--port", str(args.port), "--out", args.out, "--max-seconds", str(args.max_seconds)],
            start_new_session=True, stdout=log, stderr=log,
        )
        with open(pidfile, "w") as f:
            f.write(str(p.pid))
        time.sleep(1.5)  # let it attach + Network.enable before the action
        print(f"capture started (pid {p.pid}) — perform the ONE action now, then run --stop")
        return

    # --stop
    if not os.path.exists(pidfile):
        sys.exit("no capture.pid — was --start run for this --out?")
    pid = int(open(pidfile).read().strip())
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    for _ in range(40):  # wait up to ~10s for it to flush + exit
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.25)
    os.remove(pidfile)
    reqs = os.path.join(args.out, "cdp", "network", "requests.jsonl")
    n = sum(1 for _ in open(reqs)) if os.path.exists(reqs) else 0
    print(f"capture stopped — {n} requests recorded -> {os.path.dirname(reqs)}")


if __name__ == "__main__":
    main()
