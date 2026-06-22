#!/usr/bin/env python3
# analyze.py — run the vendored engine's ANALYSIS stages only (load -> filter -> normalize -> infer)
# and surface candidate endpoints for the agent to turn into an in-page fetch step.
#
# The engine's `emit` stage is PURE RENDERING (openapi/client/report/html). We never run it, so none
# of those files are generated. All the analysis we need (request/response pairing, parameter
# identification, schema inference, secret redaction) is done by load..infer and lands in
# `endpoints.with-schemas.jsonl`.
#
# Usage:
#   python analyze.py --run .o11y/<run> [--match <url-substr>] [--top N] [--no-engine]
#
# Reads:  <run>/api-spec/intermediate/endpoints.with-schemas.jsonl   (engine infer output)
#         <run>/api-spec/samples/<method>__<hash>.json               (redacted concrete example)
# Output: compact JSON of candidate endpoints -> stdout (the agent picks the one matching the
#         demonstrated action and writes the in-page fetch from it).

import argparse
import json
import os
import subprocess
import sys

ENGINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_engine", "discover.mjs")
ANALYSIS_STAGES = ["load", "filter", "normalize", "infer"]  # deliberately NOT "emit"

# Headers the browser sets automatically on an in-page fetch (credentials: 'include'); the agent
# should NOT hand-set these. What's left in customHeaders is app-specific and likely required
# (CSRF tokens, x-requested-with, etc.).
AUTO_HEADERS = {
    "host", "connection", "content-length", "origin", "referer", "cookie",
    "user-agent", "accept", "accept-encoding", "accept-language",
    "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform",
    "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site",
    "pragma", "cache-control", "dnt", "te",
    # Auth headers are surfaced via observedAuthHeaders (cookie=auto, bearer=re-source live),
    # not as copyable customHeaders — their captured values are redacted and unusable.
    "authorization", "x-api-key",
}


def run_engine(run: str) -> None:
    if not os.path.exists(ENGINE):
        sys.exit(f"engine not found at {ENGINE}")
    for stage in ANALYSIS_STAGES:
        proc = subprocess.run(
            ["node", ENGINE, "--run", run, "--stage", stage],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            sys.exit(f"engine stage '{stage}' failed:\n{proc.stderr or proc.stdout}")


def load_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    rows: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def sample_for(run: str, method: str, path_hash: str) -> dict | None:
    path = os.path.join(run, "api-spec", "samples", f"{method.lower()}__{path_hash}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def custom_headers(sample: dict | None) -> dict[str, str]:
    if not sample:
        return {}
    headers = (sample.get("request") or {}).get("headers") or {}
    return {k: v for k, v in headers.items() if k.lower() not in AUTO_HEADERS}


def compact(obj: object, limit: int = 4000) -> object:
    """Return the example as-is when small; otherwise a truncated-but-useful view so a giant response can't
    bloat the output. Either way the agent sees the success field WITHOUT re-opening the raw capture."""
    if obj is None:
        return None
    s = json.dumps(obj)
    if len(s) <= limit:
        return obj
    return {"__truncated__": True, "preview": s[:limit] + " …",
            "topLevelKeys": sorted(obj.keys()) if isinstance(obj, dict) else None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--match", default=None, help="only endpoints whose url contains this substring")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--no-engine", action="store_true", help="skip running the engine (analysis already done)")
    args = ap.parse_args()

    if not args.no_engine:
        run_engine(args.run)

    eps = load_jsonl(os.path.join(args.run, "api-spec", "intermediate", "endpoints.with-schemas.jsonl"))
    if not eps:
        sys.exit("no endpoints analyzed; did the capture record any traffic?")

    candidates: list[dict] = []
    for ep in eps:
        url = (ep.get("origin") or "") + (ep.get("path") or "")
        if args.match and args.match not in url:
            continue
        sample = sample_for(args.run, ep.get("method", "GET"), ep.get("pathHash", ""))
        resp_example = ep.get("responseExample")
        candidates.append({
            "method": ep.get("method"),
            "url": url,
            # GraphQL / multiplexed endpoints carry these so the agent can dispatch the operation:
            "operationName": ep.get("operationName"),
            "parentPath": ep.get("parentPath"),
            "discriminatorField": ep.get("discriminatorField"),
            "pathParams": ep.get("pathParams") or [],
            "queryParams": ep.get("queryParams") or [],
            "requestContentType": ep.get("requestContentType"),
            # Auth headers OBSERVED in the trace. Cookies ride the in-page fetch automatically;
            # a Bearer/Authorization or token header must be re-sourced from the page (see SKILL.md).
            "observedAuthHeaders": ep.get("observedAuthHeaders") or [],
            # App-specific non-auto headers the fetch likely needs (CSRF, x-requested-with, ...).
            "customHeaders": custom_headers(sample),
            "requestExample": ep.get("requestExample"),  # redacted body template
            # FULL redacted response (nested) so the predicate's success field (e.g. data.x.pdfUrl) is
            # visible WITHOUT re-opening the raw capture. The engine already inferred this; we used to drop
            # it to top-level keys — which is exactly what forced the manual python-digging.
            "responseExample": compact(resp_example),
            "responseContentTypes": ep.get("responseContentTypes"),  # json vs binary -> predicate + dataBase64/url choice
            "responseBodyKnown": ep.get("responseBodyKnown"),         # false -> body not captured -> can't derive a predicate -> keep UI
            "sampleCount": ep.get("sampleCount"),
            "statusCodes": ep.get("statusCodes") or [],
        })

    # Rank by sample count as a hint only — the agent picks the endpoint matching the action it
    # just demonstrated (use --match to narrow by URL).
    candidates.sort(key=lambda c: (c.get("sampleCount") or 0), reverse=True)

    print(json.dumps({
        "run": args.run,
        "candidate_count": len(candidates),
        "candidates": candidates[: args.top],
    }, indent=2))


if __name__ == "__main__":
    main()
