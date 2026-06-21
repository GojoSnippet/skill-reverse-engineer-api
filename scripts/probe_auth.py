#!/usr/bin/env python3
# probe_auth.py — deterministically find which auth makes a captured request authenticate, in ONE bounded
# in-page pass. This replaces the agent's manual auth hunting (try credentials:include, then grep cookies
# / localStorage, then try each as a Bearer) that was the ~4-minute convergence killer.
#
# Usage:  probe_auth.py --match <origin-substr> --request /tmp/req.json [--expect-status 200]
#   req.json = {"method":"POST","url":"https://...","headers":{...non-auth...},"body":"...or null"}
#
# Output (stdout JSON):  {"working": true, "case": 1|2, "recipe": "<how auth was supplied>", ...}
#                  or    {"working": false, "case": 3, "recipe": "...keep UI", ...}
#
# Cases: 1 = cookie session (credentials:include, no header) · 2 = a readable cookie/localStorage value
# sent as Bearer · 3 = no readable auth reproduced it -> keep the UI step.
#
# SAFETY: it re-fires the request once per auth candidate (<=6). Failed-auth attempts are rejected by the
# server BEFORE the operation runs (no side effect); only the working auth executes it, once. Use only on
# a read or a human-approved consequence-free write — the same gate run-in-page enforces.

import argparse
import json
import re
import sys

from run_in_page import evaluate_in_page, pick_target

PROBE_JS = r"""(async () => {
  const req = __REQ__;
  const expect = __EXPECT__;
  const authFail = /unauthenticat|authentication expired|not authenticat|unauthorized|invalid.{0,8}token|forbidden/i;
  const isAuth = /auth|token|session|sid|jwt|bearer|csrf|identity|__APP__/i;
  const cands = [{recipe: "credentials:include (case 1, cookie session)", c: 1, v: null}];
  document.cookie.split(";").forEach(s => {
    const i = s.indexOf("="); if (i < 0) return;
    const name = s.slice(0, i).trim(), val = s.slice(i + 1).trim();
    if (val && isAuth.test(name)) cands.push({recipe: "Bearer = readable cookie '" + name + "' (case 2)", c: 2, v: val});
  });
  try { for (const k of Object.keys(localStorage)) { if (isAuth.test(k)) { const v = localStorage.getItem(k); if (v && v.length < 4096) cands.push({recipe: "Bearer = readable localStorage['" + k + "'] (case 2)", c: 2, v: v}); } } } catch (e) {}
  const tried = [];
  for (const cand of cands.slice(0, 6)) {
    const headers = Object.assign({}, req.headers || {});
    if (cand.v) headers["authorization"] = "Bearer " + cand.v;
    try {
      const r = await fetch(req.url, {method: req.method || "GET", credentials: "include", headers, body: req.body || undefined});
      const text = await r.text();
      tried.push({recipe: cand.recipe, status: r.status});
      if (r.status === expect && !authFail.test(text)) {
        return {working: true, case: cand.c, recipe: cand.recipe, status: r.status, tried};
      }
    } catch (e) { tried.push({recipe: cand.recipe, error: String(e)}); }
  }
  return {working: false, case: 3, recipe: "no readable auth reproduced the request -> keep UI", tried};
})()"""


def build_js(req: dict, expect_status: int, match: str) -> str:
    app = re.sub(r"[^A-Za-z0-9]", "", (match.split(".")[0] if "." in match else match)) or "x"
    return (PROBE_JS
            .replace("__REQ__", json.dumps(req))
            .replace("__EXPECT__", str(int(expect_status)))
            .replace("__APP__", app))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="probe_auth")
    ap.add_argument("--match", required=True, help="substring of the target tab's URL")
    ap.add_argument("--request", required=True, help="json file: {method,url,headers,body}")
    ap.add_argument("--expect-status", type=int, default=200)
    ap.add_argument("--port", type=int, default=9222)
    args = ap.parse_args(argv)

    req = json.load(open(args.request))
    js = build_js(req, args.expect_status, args.match)
    try:
        target = pick_target(args.port, args.match)
        raw = evaluate_in_page(target["webSocketDebuggerUrl"], js, 30)
    except (LookupError, TimeoutError, OSError) as exc:
        print(json.dumps({"working": False, "case": 3, "reason": str(exc)}))
        return 2
    if raw.get("exceptionDetails"):
        print(json.dumps({"working": False, "case": 3, "reason": "probe threw in-page"}))
        return 2
    print(json.dumps(raw.get("result", {}).get("value", {}), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
