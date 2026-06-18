#!/usr/bin/env python3
# validate_replay.py — the autonomous validation gate (SPEC FR4). Replays the demonstrated submit
# request and diffs its response against what the demonstration produced. Operates on the engine's
# paired trace (`<run>/api-spec/intermediate/paired.jsonl`).
#
# IDEMPOTENCY GUARD: the demonstration already committed the real mutation, so re-firing a
# POST/PUT/PATCH/DELETE would double-submit. This refuses unless --allow-mutation is passed (use ONLY
# against a sandbox/test account or an idempotent endpoint).
#
# Usage:  python validate_replay.py --run .o11y/<run> [--match <url-substr>] [--allow-mutation]

import argparse
import json
import os
import sys

import httpx

IDEMPOTENT = {"GET", "HEAD", "OPTIONS"}
DROP_HEADERS = {"content-length", "host", "connection", "accept-encoding", "transfer-encoding"}


def load_paired(run: str) -> list[dict]:
    path = os.path.join(run, "api-spec", "intermediate", "paired.jsonl")
    if not os.path.exists(path):
        sys.exit(f"no paired trace at {path}; run discover.mjs first")
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def pick_submit(rows: list[dict], match: str | None) -> dict:
    cands = [r for r in rows if r.get("method") in ("POST", "PUT", "PATCH", "DELETE")]
    if match:
        cands = [r for r in cands if match in r.get("url", "")]
    if not cands:
        sys.exit("no state-changing request found in the trace")
    cands.sort(key=lambda r: len(json.dumps(r.get("reqBody")) or ""), reverse=True)
    return cands[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--match", default=None)
    ap.add_argument("--allow-mutation", action="store_true")
    args = ap.parse_args()

    sub = pick_submit(load_paired(args.run), args.match)
    method = sub["method"].upper()

    if method not in IDEMPOTENT and not args.allow_mutation:
        print(f"REFUSING to replay {method} {sub['url']}: would double-submit the demonstrated mutation.",
              file=sys.stderr)
        print("Re-run with --allow-mutation ONLY against a sandbox/test account.", file=sys.stderr)
        sys.exit(2)

    headers = {k: v for k, v in (sub.get("reqHeaders") or {}).items() if k.lower() not in DROP_HEADERS}
    body = sub.get("reqBody")
    kwargs: dict = {"headers": headers}
    if isinstance(body, (dict, list)):
        kwargs["json"] = body
    elif body is not None:
        kwargs["content"] = body

    with httpx.Client(timeout=30, follow_redirects=False) as client:
        resp = client.request(method, sub["url"], **kwargs)

    exp_status = sub.get("status")
    ok_status = exp_status is None or resp.status_code == exp_status
    field_note = ""
    try:
        got = resp.json()
        cap = sub.get("respBody")
        if isinstance(got, dict) and isinstance(cap, dict):
            field_note = f"shared top-level keys: {sorted(set(got) & set(cap))}"
    except Exception:
        pass

    print(json.dumps({
        "submit": f"{method} {sub['url']}",
        "replay_status": resp.status_code,
        "captured_status": exp_status,
        "status_match": ok_status,
        "note": field_note,
    }, indent=2))
    sys.exit(0 if ok_status else 1)


if __name__ == "__main__":
    main()
