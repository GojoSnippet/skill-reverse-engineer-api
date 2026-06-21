#!/usr/bin/env python3
# lint_skill — enforce the reverse-engineer-api artifact pattern on a client workflow skill.
# Run as a REQUIRED CI check in every client skill repo. Exit 0 = clean, 1 = violations.
#
#   python lint_skill.py <skill-dir>        # e.g. .../wave
#
# Statically-checkable rules are enforced here; rules that are inherently diff-/PR-time
# (normalized-capture re-approval, .gitattributes honored by the review tool) are noted and left to CI.

from __future__ import annotations

import json
import os
import re
import sys

from run_in_page import CONTRACT_VERSION, classify

# Closed Model union (sub_agents.py / domain.persona). A glob is NOT acceptable.
_MODEL_BASES = ("claude-sonnet-4-6", "claude-opus-4-6", "claude-opus-4-7", "gpt-5.5", "gpt-5.4", "gpt-5.4-mini")
_MODEL_EFFORTS = ("", "-low", "-medium", "-high", "-xhigh")
VALID_MODELS = {b + e for b in _MODEL_BASES for e in _MODEL_EFFORTS}

CAPTURE_RUN_RE = re.compile(r"^cap_\d{8}T\d{4}Z_[A-Za-z0-9]{4,}$")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
LITERAL_BEARER_RE = re.compile(r"Bearer\s+(?!\$\{|\{\{)[A-Za-z0-9._\-]{16,}")
SIGNED_URL_RE = re.compile(r"[?&](X-Amz-Signature|Signature|sig|token)=[A-Za-z0-9%._\-]{16,}", re.I)
SECRET_ASSIGN_RE = re.compile(
    r"""(authorization|bearer|cookie|x-[a-z-]*token|api[_-]?key|password|secret)\s*[:=]\s*["'](?!\$\{|\{\{)[A-Za-z0-9+/=._\-]{12,}["']""",
    re.I,
)
OPAQUE_LITERAL_RE = re.compile(r"""["'`]([A-Za-z0-9+/=_\-]{40,})["'`]""")


class V:  # a violation
    def __init__(self, rule: str, where: str, msg: str) -> None:
        self.rule, self.where, self.msg = rule, where, msg

    def __str__(self) -> str:
        return f"[{self.rule}] {self.where}: {self.msg}"


def _parse_frontmatter(md: str) -> tuple[dict, str]:
    m = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", md, re.DOTALL)
    if not m:
        raise ValueError("missing YAML frontmatter")
    import yaml
    raw = yaml.safe_load(m.group(1))
    if not isinstance(raw, dict):
        raise ValueError("frontmatter is not a mapping")
    return raw, md[m.end():]


def _scan_secrets(rule: str, where: str, text: str) -> list[V]:
    out: list[V] = []
    for label, rx in (("email", EMAIL_RE), ("literal-bearer", LITERAL_BEARER_RE),
                      ("signed-url", SIGNED_URL_RE), ("secret-assign", SECRET_ASSIGN_RE)):
        if rx.search(text):
            out.append(V(rule, where, f"possible {label} literal — secrets/identity must never be committed"))
    for m in OPAQUE_LITERAL_RE.finditer(text):
        tok = m.group(1)
        # allow placeholders and obvious non-secrets
        if "{{" in tok or tok.count("-") >= 4 or set(tok) <= set("0123456789"):
            continue
        out.append(V(rule, where, f"long opaque literal {tok[:12]}… — looks like a token; use a live re-source recipe"))
    return out


def lint_skill(skill_dir: str) -> list[V]:
    out: list[V] = []
    skill_md = os.path.join(skill_dir, "SKILL.md")
    steps_dir = os.path.join(skill_dir, "steps")
    if not os.path.exists(skill_md):
        return [V("structure", skill_dir, "no SKILL.md")]

    try:
        fm, _body = _parse_frontmatter(open(skill_md).read())
    except ValueError as e:
        return [V("frontmatter", "SKILL.md", str(e))]

    # skill-hygiene
    name = fm.get("name", "")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", str(name)):
        out.append(V("skill-hygiene", "SKILL.md", f"name {name!r} must match [A-Za-z0-9._-], <=64"))
    if len(str(fm.get("description", ""))) > 1024:
        out.append(V("skill-hygiene", "SKILL.md", "description > 1024 chars"))

    declared = fm.get("steps", {}) or {}
    # model-enum-exact
    for sname, spec in declared.items():
        mdl = (spec or {}).get("model")
        if mdl is not None and mdl not in VALID_MODELS:
            out.append(V("model-enum-exact", "SKILL.md", f"step {sname}: model {mdl!r} not in the closed Model union"))

    if not os.path.isdir(steps_dir):
        out.append(V("structure", skill_dir, "no steps/ dir"))
        return out

    # every-step-declared / no-undeclared-sibling / sidecars-not-steps
    for fn in sorted(os.listdir(steps_dir)):
        if fn.endswith(".ui.md") or fn.endswith(".capture.json"):
            base = fn.rsplit(".ui.md", 1)[0] if fn.endswith(".ui.md") else fn.rsplit(".capture.json", 1)[0]
            if base in declared:  # ok — sidecar of a declared step
                continue
            out.append(V("sidecars-not-steps", fn, f"sidecar for undeclared step {base!r}"))
            continue
        if not fn.endswith(".md"):
            continue
        if fn.endswith("-api.md"):
            out.append(V("no-undeclared-sibling", fn, "forbidden -api.md sibling (inline the API into the declared step)"))
            continue
        step = fn[:-3]
        if step not in declared:
            out.append(V("every-step-declared", fn, f"step file not declared under SKILL.md steps:"))

    # per declared step
    for step, spec in declared.items():
        out += _lint_step(steps_dir, step, spec or {})

    # capture-not-collapsed
    ga = os.path.join(skill_dir, ".gitattributes")
    if os.path.exists(ga):
        txt = open(ga).read()
        if re.search(r"\.capture\.json.*linguist-generated", txt) or re.search(r"steps/.*\.md.*linguist-generated", txt):
            out.append(V("capture-not-collapsed", ".gitattributes", "must not collapse step/capture executable fields in review"))
    return out


def _lint_step(steps_dir: str, step: str, spec: dict) -> list[V]:
    out: list[V] = []
    here = lambda *p: os.path.join(steps_dir, *p)
    step_md_p, ui_p, cap_p = here(f"{step}.md"), here(f"{step}.ui.md"), here(f"{step}.capture.json")

    if not os.path.exists(step_md_p):
        return [V("structure", f"{step}.md", "declared step has no file")]
    step_md = open(step_md_p).read()

    # An API-backed step has a run-in-page §1; a plain UI-only step is allowed (no sidecars required).
    is_api = "run-in-page" in step_md
    if not is_api:
        return out  # UI-only step: nothing more to enforce

    # fallback-baseline-preserved
    if not (os.path.exists(ui_p) and open(ui_p).read().strip()):
        out.append(V("fallback-baseline-preserved", f"{step}.ui.md", "API step must keep a non-empty UI baseline"))
    if "## 2. UI fallback" not in step_md:
        out.append(V("one-call-one-branch", f"{step}.md", "missing '## 2. UI fallback' section"))
    elif os.path.exists(ui_p):
        sec2 = step_md.split("## 2. UI fallback", 1)[1].split("\n", 1)[1]
        norm = lambda s: "\n".join(l.rstrip() for l in s.strip().splitlines())
        if norm(sec2) != norm(open(ui_p).read()):
            out.append(V("fallback-baseline-preserved", f"{step}.md", "§2 diverges from the .ui.md baseline"))

    # §1 body only — the EXECUTABLE attempt, excluding the header comment (whose prose may name the
    # capture sidecar as a provenance pointer, which is fine and must not trip the repo-path rule).
    if "## 1. API attempt" in step_md:
        sec1 = step_md.split("## 1. API attempt", 1)[1].split("## 2. UI fallback", 1)[0]
    else:
        out.append(V("one-call-one-branch", f"{step}.md", "API step missing '## 1. API attempt' section"))
        sec1 = step_md.split("## 2. UI fallback", 1)[0]

    # one-call-one-branch / helper-by-name-only / no-runtime-repo-paths
    n_calls = len(re.findall(r"(?m)^\s*run-in-page\b", sec1)) + sec1.count(" run-in-page ")
    if "run-in-page" not in sec1:
        out.append(V("helper-by-name-only", f"{step}.md", "§1 must invoke run-in-page"))
    if "/agent/skills/" in step_md or "replay_in_page" in step_md:
        out.append(V("helper-by-name-only", f"{step}.md", "skill-relative helper path — call run-in-page by name"))
    for bad in ("--js-file", ".capture.json", "/tmp/", "-result.json"):
        if bad in sec1:
            out.append(V("no-runtime-repo-paths", f"{step}.md", f"§1 references {bad!r} — inline JS, no repo/file handoff"))
    if re.search(r"--vars-json[^\n]*\$[A-Za-z_]", sec1) or re.search(r"--js[^\n]*\$[A-Za-z_]\w*(?![\w{])", sec1) and "${" not in sec1:
        pass  # (shell-var heuristic handled below)
    if re.search(r"\$[A-Z_]{2,}\b", sec1):
        out.append(V("inputs-exported-not-envvars", f"{step}.md", "shell $VAR in §1 — step_inputs are not env vars; build --vars-json"))
    if "base64" in sec1.lower() and "--out" not in sec1:
        out.append(V("one-call-one-branch", f"{step}.md", "base64 payload without --out (helper writes binaries to --out)"))

    # extract the --js body for classification + secret scan
    jm = re.search(r"--js\s+'(.*?)'\s*```", sec1, re.DOTALL) or re.search(r"--js\s+'(.*)", sec1, re.DOTALL)
    js = jm.group(1) if jm else sec1
    out += _scan_secrets("no-secrets-no-identity", f"{step}.md", step_md)

    # helper-contract-pinned
    cm = re.search(r"--contract\s+(\d+)", sec1)
    if not cm:
        out.append(V("helper-contract-pinned", f"{step}.md", "§1 missing --contract N"))

    # capture.json
    if not os.path.exists(cap_p):
        out.append(V("structure", f"{step}.capture.json", "API step missing its capture sidecar"))
        return out
    try:
        cap = json.load(open(cap_p))
    except json.JSONDecodeError as e:
        return out + [V("sidecars-not-steps", f"{step}.capture.json", f"invalid JSON: {e}")]

    if cap.get("schema") != "reverse-engineer-api/capture@1":
        out.append(V("sidecars-not-steps", f"{step}.capture.json", "wrong/missing schema"))
    for fld in ("class", "approved_by", "validated", "success_predicate", "helper_contract", "auth"):
        if not cap.get(fld):
            out.append(V("success-predicate-required" if fld == "success_predicate" else "sidecars-not-steps",
                         f"{step}.capture.json", f"missing {fld}"))
    if cap.get("capture_run") and not CAPTURE_RUN_RE.match(str(cap["capture_run"])):
        out.append(V("skill-hygiene", f"{step}.capture.json", f"capture_run {cap['capture_run']!r} != cap_<ISO>_<hash>"))

    # helper-contract-pinned: step --contract == capture.helper_contract == installed CONTRACT_VERSION
    if cm and cap.get("helper_contract") is not None:
        if int(cm.group(1)) != cap["helper_contract"]:
            out.append(V("helper-contract-pinned", f"{step}", "--contract != capture.helper_contract"))
        if cap["helper_contract"] != CONTRACT_VERSION:
            out.append(V("helper-contract-pinned", f"{step}", f"helper_contract {cap['helper_contract']} != installed {CONTRACT_VERSION}"))

    # class-derived-from-body (single source of truth = the helper's classifier)
    derived = classify(js)
    cap_class = cap.get("class")
    if cap_class not in ("read", "write"):
        out.append(V("class-derived-from-body", f"{step}.capture.json", f"class {cap_class!r} must be read|write"))
    elif derived == "read" and cap_class == "write":
        pass  # conservative over-label is allowed (write is the safe direction)
    elif derived in ("write", "unknown") and cap_class == "read":
        out.append(V("class-derived-from-body", f"{step}", f"capture says read but body derives {derived} (mutation/unclassified)"))
    # header class echo must match capture class
    hm = re.search(r"class:\s*(READ|WRITE)", step_md, re.I)
    if hm and hm.group(1).lower() != str(cap_class).lower():
        out.append(V("class-derived-from-body", f"{step}.md", "header class echo != capture class"))

    # write-requires-approval-and-bare-flag
    has_bare_flag = bool(re.search(r"(?<!=)--allow-mutation(?:\s|$|\\)", sec1)) and "--allow-mutation=" not in sec1
    if cap_class == "write" or derived in ("write", "unknown"):
        if not str(cap.get("approved_by", "")).strip():
            out.append(V("write-requires-approval", f"{step}.capture.json", "WRITE step needs a non-empty approved_by"))
        if not has_bare_flag:
            out.append(V("write-requires-approval", f"{step}.md", "WRITE step must pass a bare --allow-mutation flag"))
    elif cap_class == "read" and has_bare_flag:
        out.append(V("write-requires-approval", f"{step}.md", "READ step must not pass --allow-mutation"))

    # validated-state-honest
    if cap_class == "write" and re.search(r"\bproduction\b", str(cap.get("validated", "")), re.I) and "not validated" not in str(cap.get("validated", "")).lower():
        out.append(V("validated-state-honest", f"{step}.capture.json", "a WRITE validated against production is forbidden"))

    # inputs-declared-and-referenced
    declared_inputs = set((spec.get("required_step_inputs") or {}).keys())
    used_vars = set(re.findall(r"\{\{\s*([A-Za-z_]\w*)\s*\}\}", step_md))
    for v in sorted(used_vars - declared_inputs):
        out.append(V("inputs-declared-and-referenced", f"{step}.md", f"uses {{{{{v}}}}} but it is not a required_step_input"))
    if (cap_class == "write" or derived in ("write", "unknown")) and "allow_mutation" not in declared_inputs:
        out.append(V("inputs-declared-and-referenced", "SKILL.md", f"WRITE step {step} should declare an allow_mutation input"))

    out += _scan_secrets("no-secrets-no-identity", f"{step}.capture.json", json.dumps(cap))
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: lint_skill.py <skill-dir>", file=sys.stderr)
        return 2
    violations = lint_skill(argv[0])
    for v in violations:
        print(str(v))
    print(f"\n{'CLEAN' if not violations else f'{len(violations)} VIOLATION(S)'} — {argv[0]}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
