#!/usr/bin/env python3
# Tests for teach_insert.transform — the mechanical surgical insert. Runs with plain `python`.
import sys

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

def test_api_section_present_with_body():
    out = t.transform(UI_ONLY, HEADER, API)
    assert "## API attempt\n\nrun-in-page --contract 1" in out

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
