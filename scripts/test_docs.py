#!/usr/bin/env python3
# Tests the docs component's load-bearing invariants. Plain `python3`, no pytest, no browser, no other
# in-flight module. Reads the doc fixtures from the repo and asserts the contract this rebuild froze:
# the operator checklist boxes, the gate table, the single-home cautionary tale, the fixed step.md bug,
# the README script list, and the internal label on test-plan.md.
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAYBOOK = (ROOT / "docs" / "operator-playbook.md").read_text(encoding="utf-8")
TEACH = (ROOT / "docs" / "templates" / "teach-prompt.md").read_text(encoding="utf-8")
STEP = (ROOT / "docs" / "templates" / "step.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
TEST_PLAN = (ROOT / "docs" / "test-plan.md").read_text(encoding="utf-8")


# ---- operator-playbook: the tick-box checklist (DESIGN §7) ----
def test_playbook_has_every_checklist_box():
    # box label -> the command that box runs (both must be present, in the checklist)
    boxes = {
        "0 Partition": "partition.py",
        "1 Capture WHOLE": "capture_cdp.py",
        "2 Analyze": "analyze.py",
        "3 Bail-scan": "detect_replayable.py",
        "4 Classify": "classify_values.py",
        "5 Auth": "probe_auth.py",
        "7 PROVE": "prove_runner.py",
        "8 Write": "teach_insert.py",
        "9 Discipline": "git diff --name-only",
    }
    for label, cmd in boxes.items():
        assert label in PLAYBOOK, f"checklist box {label!r} missing"
        assert cmd in PLAYBOOK, f"command {cmd!r} for box {label!r} missing"

def test_playbook_segment_is_the_unit():
    # the documented root-cause discipline: not the whole workflow, not a single action
    assert "unit of API-ification is a SEGMENT" in PLAYBOOK
    assert "0, 1, or many" in PLAYBOOK  # a workflow yields 0/1/many segments

def test_playbook_both_outcomes_are_correct():
    assert "api-added" in PLAYBOOK and "kept-ui" in PLAYBOOK
    assert "both correct" in PLAYBOOK  # the RESULT line
    assert "NOT a failure" in PLAYBOOK  # kept-ui framed as success

def test_playbook_documents_the_four_gates():
    for gate in ("G1", "G2", "G3", "G4"):
        assert gate in PLAYBOOK, f"gate {gate} not documented"
    # each gate must name its keep-UI exit
    for bail in ("BAIL-1", "BAIL-2", "BAIL-3", "BAIL-4", "BAIL-5"):
        assert bail in PLAYBOOK, f"{bail} not documented"

def test_playbook_gate_precedes_write():
    # the operator may not run teach_insert (box 8) until the gates pass
    assert "may not run box 8" in PLAYBOOK or "may not run teach_insert" in PLAYBOOK.lower() \
        or "until every gate has passed" in PLAYBOOK

def test_playbook_demands_clean_whole_capture_with_varied_inputs():
    assert "WHOLE segment from a clean state" in PLAYBOOK
    assert "2 varied inputs" in PLAYBOOK  # ">=2 varied inputs"

def test_playbook_tick_only_after_pasting_output():
    assert "only after pasting that command" in PLAYBOOK


# ---- the cautionary tale lives in EXACTLY ONE place ----
def test_cautionary_tale_single_home():
    # the narrative ("the one bug this whole playbook exists to prevent") appears once, in the playbook
    assert PLAYBOOK.count("## The cautionary tale") == 1
    # the other docs reference that home, they do not re-tell it
    assert "cautionary tale in docs/operator-playbook.md" in STEP
    assert "cautionary tale in docs/operator-playbook.md" in TEACH
    # the tale stays generic — no app/protocol/artifact baked into the narrative body
    tale = PLAYBOOK.split("## The cautionary tale", 1)[1].split("##", 1)[0]
    for banned in ("One Pager", "Metaview", "Wave", "GraphQL"):
        assert banned not in tale, f"cautionary tale leaked {banned!r} — keep it generic"


# ---- step.md: the FIXED bug ----
def test_step_template_does_not_say_only_last_action():
    # the old, wrong framing: "the LAST data action ... that's the one teaching mode turns into an API call"
    assert "that's the one teaching mode\n    turns into an API call" not in STEP
    assert "this is what gets API-ified" not in STEP

def test_step_template_says_whole_segment_including_setup():
    assert "WHOLE data segment, including any SETUP" in STEP
    assert "captures the ENTIRE\n    chain" in STEP


# ---- teach-prompt: short, generic, gate-disciplined ----
def test_teach_prompt_is_generic():
    # app/protocol names only inside the clearly-labeled example block, never in the reusable prompt
    head = TEACH.split("## Filled example", 1)[0]
    for banned in ("Metaview", "Wave", "GraphQL", "One Pager"):
        assert banned not in head, f"reusable teach prompt leaked {banned!r}"

def test_teach_prompt_carries_the_disciplines():
    assert "WHOLE SEGMENT FROM A CLEAN STATE" in TEACH
    assert "varied inputs" in TEACH
    assert "NOT run teach_insert" in TEACH and "until every gate" in TEACH
    assert "operator checklist" in TEACH  # paste the checklist

def test_teach_prompt_example_is_labeled():
    assert "illustrative only" in TEACH


# ---- README: the bundled-scripts list ----
def test_readme_lists_all_bundled_scripts():
    for script in (
        "partition.py", "classify_values.py", "prove_runner.py", "recombine.py",
        "check_chain.py", "verify_equivalence.py", "capture_cdp.py", "analyze.py",
        "detect_replayable.py", "probe_auth.py", "run_in_page.py", "teach_insert.py",
    ):
        assert script in README, f"README does not list {script}"

def test_readme_points_to_design_and_playbook():
    assert "docs/DESIGN.md" in README
    assert "docs/operator-playbook.md" in README

def test_readme_verify_receipt_described():
    assert "verify_receipt.json" in README  # the receipt the prove gate emits


# ---- test-plan: labeled internal ----
def test_test_plan_labeled_internal():
    head = TEST_PLAN[:600]
    assert "INTERNAL" in head
    assert "maintainers only" in head
    assert "operator-playbook.md" in head  # points operators away to their doc


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
