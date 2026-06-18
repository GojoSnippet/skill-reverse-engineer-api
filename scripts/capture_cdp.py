#!/usr/bin/env python3
# capture_cdp.py — record the demonstrated workflow's HTTP traffic from the agent's own Chrome
# over the DevTools Protocol, into the `.o11y/<run>/cdp/network/` layout the analysis engine
# (scripts/_engine/discover.mjs) consumes. No proxy, no MITM, no cloud: it attaches to the live,
# already-authenticated tab via the debug port.
#
# Prereqs:  Chromium launched with --remote-debugging-port=9222 --remote-allow-origins=*
#           pip install websocket-client
# Usage:    python capture_cdp.py --port 9222 --seconds 90 --out .o11y/<run>
#
# Output (exact contract read by _engine/load.mjs):
#   <out>/cdp/network/requests.jsonl    one raw Network.requestWillBeSent message per line
#   <out>/cdp/network/responses.jsonl   one raw Network.responseReceived  message per line
#   <out>/cdp/network/bodies/<requestId>/response.json  {"id": "<requestId>", "body": "<text>"}
#   <out>/cdp/network/bodies/<requestId>/request.json   {"id": "<requestId>", "body": "<text>"}

import argparse
import json
import os
import sys
import time
import urllib.request

from websocket import WebSocketTimeoutException, create_connection


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--seconds", type=int, default=90)
    ap.add_argument("--out", required=True, help="run dir; trace written under <out>/cdp/network/")
    args = ap.parse_args()

    net_dir = os.path.join(args.out, "cdp", "network")
    os.makedirs(net_dir, exist_ok=True)

    target = pick_page_target(args.port)
    print(f"attached to: {target.get('url', '?')}", file=sys.stderr)
    c = Conn(target["webSocketDebuggerUrl"])
    c.send("Network.enable", {"maxResourceBufferSize": 100 << 20, "maxTotalBufferSize": 200 << 20})

    # Buffer by requestId so we can augment request events with their postData (fetched
    # asynchronously) and keep the terminal event per id before writing the engine's layout.
    req_events: dict[str, dict] = {}   # requestId -> raw Network.requestWillBeSent message
    resp_events: dict[str, dict] = {}  # requestId -> raw Network.responseReceived message
    resp_bodies: dict[str, str] = {}   # requestId -> response body text
    want_post: dict[int, str] = {}     # cmd id -> requestId (getRequestPostData)
    want_body: dict[int, str] = {}     # cmd id -> requestId (getResponseBody)

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

    deadline = time.time() + args.seconds
    print(f"capturing for {args.seconds}s — perform the workflow now…", file=sys.stderr)
    while time.time() < deadline:
        msg = c.recv()
        if msg is None:
            continue
        if "method" in msg:
            m, p = msg["method"], msg.get("params", {})
            if m == "Network.requestWillBeSent":
                rid = p.get("requestId")
                req_events[rid] = msg  # keep terminal event per id (redirects collapse to final)
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

    # drain late command replies
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

    print(
        f"wrote {len(req_events)} requests, {len(resp_events)} responses, "
        f"{len(resp_bodies)} response bodies -> {net_dir}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
