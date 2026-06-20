#!/usr/bin/env python3
# Unit tests for run_in_page pure logic + the non-browser gate paths. Runs with plain `python` (no
# pytest needed) or under pytest. The CDP/browser path itself is covered by the integration-test gate.
import io
import json
import sys
from contextlib import redirect_stdout

import run_in_page as r

UNUSED_PORT = 59999  # nothing listens here -> browser attempts fail fast with connection refused


def _run(argv: list[str]) -> int:
    with redirect_stdout(io.StringIO()):
        return r.main(argv)


# ---- substitute_vars ----
def test_substitute_replaces_and_json_encodes():
    out = r.substitute_vars('const id = {{invoice_id}}; const n = {{count}};', {"invoice_id": "a/b", "count": 3})
    assert out == 'const id = "a/b"; const n = 3;', out

def test_substitute_missing_var_raises():
    try:
        r.substitute_vars('x = {{missing}}', {})
    except ValueError as e:
        assert "missing" in str(e)
    else:
        raise AssertionError("expected ValueError for missing var")


# ---- classify ----
def test_classify_graphql_mutation_is_write():
    assert r.classify('fetch(u,{method:"POST",body:JSON.stringify({query:"mutation Gen($i:X){ gen(input:$i){ ok } }"})})') == "write"

def test_classify_graphql_query_is_read():
    assert r.classify('fetch(u,{method:"POST",body:JSON.stringify({query:"query Me{ me{ id } }"})})') == "read"

def test_classify_get_is_read():
    assert r.classify('fetch(u,{method:"GET",credentials:"include"})') == "read"

def test_classify_delete_is_write():
    assert r.classify('fetch(u,{method:"DELETE"})') == "write"

def test_classify_plain_post_is_unknown():
    assert r.classify('fetch(u,{method:"POST",body:"name=x"})') == "unknown"

def test_classify_persisted_query_is_unknown():
    assert r.classify('fetch(u,{method:"POST",body:JSON.stringify({extensions:{persistedQuery:{sha256Hash:"abc"}}})})') == "unknown"

def test_classify_no_method_is_read():
    assert r.classify('fetch(u,{credentials:"include"})') == "read"


# ---- evaluate_outcome ----
def test_outcome_ok_no_out():
    code, rep = r.evaluate_outcome({"ok": True, "status": 200}, None, True)
    assert code == r.OK and rep["ok"] is True

def test_outcome_ok_false():
    code, _ = r.evaluate_outcome({"ok": False}, None, True)
    assert code == r.FAIL

def test_outcome_out_missing_fails_even_if_ok():
    code, rep = r.evaluate_outcome({"ok": True}, "/agent/user-data/outputs/x.pdf", False)
    assert code == r.FAIL and "missing or empty" in rep["reason"]

def test_outcome_non_dict_result_fails():
    code, _ = r.evaluate_outcome("not-a-dict", None, True)
    assert code == r.FAIL


# ---- main() gate paths (no browser) ----
def test_main_contract_mismatch():
    assert _run(["--contract", "999", "--js", "x"]) == r.BAD_CONTRACT

def test_main_write_without_allow_mutation_refused():
    js = 'fetch(u,{method:"POST",body:JSON.stringify({query:"mutation M{ m{ ok } }"})})'
    assert _run(["--contract", "1", "--port", str(UNUSED_PORT), "--js", js]) == r.REFUSED_WRITE

def test_main_unknown_without_allow_mutation_refused():
    js = 'fetch(u,{method:"POST",body:"raw"})'
    assert _run(["--contract", "1", "--port", str(UNUSED_PORT), "--js", js]) == r.REFUSED_WRITE

def test_main_read_passes_gate_then_tries_browser():
    # a READ should get PAST the gate and fail at the (absent) browser -> THREW, proving the gate let it through
    js = 'fetch(u,{method:"GET"})'
    assert _run(["--contract", "1", "--port", str(UNUSED_PORT), "--js", js]) == r.THREW

def test_main_write_with_allow_mutation_passes_gate():
    js = 'fetch(u,{method:"POST",body:JSON.stringify({query:"mutation M{ m{ ok } }"})})'
    assert _run(["--contract", "1", "--allow-mutation", "--port", str(UNUSED_PORT), "--js", js]) == r.THREW

def test_main_missing_js_is_usage():
    assert _run(["--contract", "1", "--js", "   "]) == r.USAGE

def test_main_missing_var_is_usage():
    assert _run(["--contract", "1", "--port", str(UNUSED_PORT), "--js", "x={{nope}}", "--vars-json", "{}"]) == r.USAGE


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
    print(f"\n{'ALL PASS' if not failed else f'{failed} FAILED'} ({len(tests)} tests)")
    sys.exit(1 if failed else 0)
