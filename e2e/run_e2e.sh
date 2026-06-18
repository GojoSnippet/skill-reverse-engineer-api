#!/usr/bin/env bash
# End-to-end test of the reverse-engineer-api skill (C2 pipeline) against a safe fake API.
# Asserts SPEC acceptance criteria AC1–AC4. No cloud, no API key.
#
# Env overrides (defaults suit the real runtime; dev boxes pass their own):
#   CHROME=/path/to/chromium   PY=python3   NODE=node
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(git -C "$HERE" rev-parse --show-toplevel)"
SKILL="$ROOT"
CHROME="${CHROME:-chromium}"; PY="${PY:-python3}"; NODE="${NODE:-node}"
PORT=9222; HTTP_PORT=8771
WORK="$(mktemp -d)"; FAILS=0
pass(){ echo "  PASS  $1"; }
fail(){ echo "  FAIL  $1"; FAILS=$((FAILS+1)); }

cleanup(){ kill -9 "${HTTP:-0}" "${CH:-0}" 2>/dev/null; rm -rf "$WORK"; }
trap cleanup EXIT

"$PY" -m http.server "$HTTP_PORT" --bind 127.0.0.1 --directory "$HERE" >/dev/null 2>&1 & HTTP=$!

launch_capture(){  # <page> <run>
  "$CHROME" --headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage \
    --remote-debugging-port="$PORT" --remote-allow-origins='*' \
    --user-data-dir="$WORK/prof-$2" "http://127.0.0.1:$HTTP_PORT/$1" >/dev/null 2>&1 & CH=$!
  for _ in $(seq 1 20); do curl -s -o /dev/null "http://127.0.0.1:$PORT/json" && break || sleep 0.5; done
  "$PY" "$SKILL/scripts/capture_cdp.py" --port "$PORT" --seconds 10 --out "$WORK/$2"
  kill -9 "$CH" 2>/dev/null; CH=; sleep 1   # free port 9222 before the next launch
}

echo "== capture (replayable page) =="
launch_capture test_page.html run1
NET="$WORK/run1/cdp/network"
[ -s "$NET/requests.jsonl" ] && grep -q jsonplaceholder "$NET/requests.jsonl" && pass "AC1 requests.jsonl has the POST" || fail "AC1 requests.jsonl"
ls "$NET"/bodies/*/response.json >/dev/null 2>&1 && pass "AC1 response body captured" || fail "AC1 response body"

echo "== analyze (Browserbase engine) =="
"$NODE" "$SKILL/scripts/_engine/discover.mjs" --run "$WORK/run1" >/dev/null 2>&1
grep -q '/posts' "$WORK/run1/api-spec/openapi.yaml" && pass "AC2 openapi.yaml has the endpoint" || fail "AC2 endpoint in spec"
if grep -rq secret123 "$WORK/run1/api-spec/samples" 2>/dev/null; then fail "AC2 secret NOT redacted"; else pass "AC2 secret redacted in samples"; fi

echo "== decide + validate =="
"$PY" "$SKILL/scripts/detect_replayable.py" --run "$WORK/run1" >/dev/null; [ $? -eq 0 ] && pass "AC (replayable verdict)" || fail "replayable verdict"
"$PY" "$SKILL/scripts/validate_replay.py" --run "$WORK/run1" >/dev/null 2>&1; [ $? -eq 2 ] && pass "AC3 idempotency guard refuses POST" || fail "AC3 guard"
"$PY" "$SKILL/scripts/validate_replay.py" --run "$WORK/run1" --allow-mutation >/dev/null 2>&1; [ $? -eq 0 ] && pass "AC3 replay matches captured" || fail "AC3 replay match"

echo "== bail-to-GUI (signed page) =="
launch_capture test_page_signed.html run2
"$NODE" "$SKILL/scripts/_engine/discover.mjs" --run "$WORK/run2" >/dev/null 2>&1
"$PY" "$SKILL/scripts/detect_replayable.py" --run "$WORK/run2" >/dev/null; [ $? -eq 3 ] && pass "AC4 signed body -> bail to GUI" || fail "AC4 bail"

echo "== $([ $FAILS -eq 0 ] && echo ALL PASS || echo "$FAILS FAILED") =="
exit $FAILS
