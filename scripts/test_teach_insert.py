#!/usr/bin/env python3
# Tests for teach_insert — the mechanical surgical insert + the verify-receipt gate. Runs with plain `python`.
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout

import teach_insert as t

UI_ONLY = """### Download invoice

Mission: open the given Wave invoice and download it as a PDF to /agent/user-data/outputs/.

Inputs:
- invoice_id: the Wave invoice id.
- business_id: the Wave business id.

Instructions:
1. Open Chrome.
2. Navigate to the invoice and click Export as PDF.
3. Save it to /agent/user-data/outputs/invoice.pdf.

Return value:
- note_file_path: the path, or NAN.

Important:
- Read-only: do not modify anything.
"""

# the exact original instruction block — must survive byte-for-byte under ## UI instructions
UI_STEPS = """1. Open Chrome.
2. Navigate to the invoice and click Export as PDF.
3. Save it to /agent/user-data/outputs/invoice.pdf."""

HEADER = "reverse-engineer-api · taught 2026-06-21 · class WRITE · approved: x · validated: no"
API = "run-in-page --contract 1 --allow-mutation --match next.waveapps.com --out /x --js '...'"


def test_header_on_top():
    out = t.transform(UI_ONLY, HEADER, API)
    assert out.startswith("<!-- reverse-engineer-api · taught 2026-06-21"), out[:60]

def test_api_section_has_command_and_run_branch():
    out = t.transform(UI_ONLY, HEADER, API)
    assert "```bash\nrun-in-page --contract 1" in out  # command in a runnable shell fence
    assert "Do this first" in out and "method: api` and STOP" in out  # the run+branch instruction

def test_ui_steps_preserved_byte_for_byte():
    out = t.transform(UI_ONLY, HEADER, API)
    assert "## UI instructions\n" + UI_STEPS in out, "UI steps were altered, not preserved verbatim"

def test_method_added_to_return_value():
    out = t.transform(UI_ONLY, HEADER, API)
    assert 'Return value:\n- method: "api" or "ui".\n- note_file_path: the path, or NAN.' in out

def test_mission_and_important_untouched():
    out = t.transform(UI_ONLY, HEADER, API)
    assert "Mission: open the given Wave invoice and download it as a PDF" in out
    assert "Important:\n- Read-only: do not modify anything." in out

def test_idempotent_refuses_already_taught():
    out = t.transform(UI_ONLY, HEADER, API)
    try:
        t.transform(out, HEADER, API)
    except ValueError as e:
        assert "already" in str(e)
    else:
        raise AssertionError("expected refusal on an already-taught step")

def test_rejects_non_mission_step():
    for bad in ("no instructions here\n\nReturn value:\n- x", "Instructions:\n1. x\n"):
        try:
            t.transform(bad, HEADER, API)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected rejection for: {bad!r}")


# ---- the verify-receipt gate (check_receipt) ----
# A receipt that PROVES the API equals the UI on a held-out instance (api_instance != golden_instance).
GOOD_RECEIPT = {
    "schema": "verify_receipt/v1",
    "segment_id": "s0",
    "verdict": "MATCH",
    "api_instance": "run-in-page replay on held-out instance",
    "golden_instance": "UI export on a different held-out instance",
}


def _receipt(**over: object) -> dict[str, object]:
    return {**GOOD_RECEIPT, **over}


def test_gate_accepts_valid_receipt():
    t.check_receipt(_receipt())  # held-out, MATCH -> no raise


def test_gate_rejects_mismatch_verdict():
    try:
        t.check_receipt(_receipt(verdict="MISMATCH"))
    except t.GateError as e:
        assert "MISMATCH" in str(e)
    else:
        raise AssertionError("expected GateError on a MISMATCH verdict")


def test_gate_rejects_inconclusive_verdict():
    try:
        t.check_receipt(_receipt(verdict="INCONCLUSIVE"))
    except t.GateError:
        pass
    else:
        raise AssertionError("expected GateError on a non-MATCH verdict")


def test_gate_rejects_same_instance():
    same = "the very instance we built the chain on"
    try:
        t.check_receipt(_receipt(api_instance=same, golden_instance=same))
    except t.GateError as e:
        assert "api_instance" in str(e)
    else:
        raise AssertionError("expected GateError when api_instance == golden_instance")


def test_gate_rejects_missing_instances():
    try:
        t.check_receipt({"verdict": "MATCH"})
    except t.GateError:
        pass
    else:
        raise AssertionError("expected GateError when held-out instances are absent")


def test_gate_rejects_non_object_receipt():
    try:
        t.check_receipt(["not", "an", "object"])
    except t.GateError:
        pass
    else:
        raise AssertionError("expected GateError for a non-object receipt")


# ---- main() wiring: the gate decides whether the file is written ----
def _run_main(step_md: str, receipt: object | None, command: str = API) -> tuple[int, str]:
    d = tempfile.mkdtemp()
    step_path = os.path.join(d, "STEP.md")
    cmd_path = os.path.join(d, "command.sh")
    with open(step_path, "w") as f:
        f.write(step_md)
    with open(cmd_path, "w") as f:
        f.write(command)
    argv = ["--step", step_path, "--header", HEADER, "--command", cmd_path]
    if receipt is not None:
        verify_path = os.path.join(d, "verify_receipt.json")
        with open(verify_path, "w") as f:
            json.dump(receipt, f)
        argv += ["--verify", verify_path]
    err = io.StringIO()
    with redirect_stdout(io.StringIO()), redirect_stderr(err):
        code = t.main(argv)
    with open(step_path) as f:
        written = f.read()
    return code, written


def test_main_writes_on_proven_receipt():
    code, written = _run_main(UI_ONLY, GOOD_RECEIPT)
    assert code == 0, code
    assert "## API attempt" in written  # the file WAS edited
    assert "## UI instructions\n" + UI_STEPS in written  # UI still verbatim


def test_main_refuses_and_leaves_file_untouched_on_mismatch():
    code, written = _run_main(UI_ONLY, _receipt(verdict="MISMATCH"))
    assert code != 0, "a MISMATCH receipt must NOT teach an API step"
    assert written == UI_ONLY, "the step file must be left byte-for-byte unchanged on refusal"


def test_main_refuses_on_same_instance():
    same = "build-instance-only"
    code, written = _run_main(UI_ONLY, _receipt(api_instance=same, golden_instance=same))
    assert code != 0, "a same-instance proof must NOT teach an API step"
    assert written == UI_ONLY


def test_main_refuses_on_missing_receipt_file():
    # --verify is required and must exist; a missing path is a clean refusal, not a crash.
    d = tempfile.mkdtemp()
    step_path = os.path.join(d, "STEP.md")
    with open(step_path, "w") as f:
        f.write(UI_ONLY)
    err = io.StringIO()
    with redirect_stdout(io.StringIO()), redirect_stderr(err):
        code = t.main(["--step", step_path, "--header", HEADER, "--verify", os.path.join(d, "nope.json"), "--command", "/dev/null"])
    assert code != 0
    with open(step_path) as f:
        assert f.read() == UI_ONLY


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
    print(f"\n{'ALL PASS' if not failed else f'{failed} FAILED'} ({len(tests)} tests)")
    sys.exit(1 if failed else 0)
