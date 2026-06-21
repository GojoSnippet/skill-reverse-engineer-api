#!/usr/bin/env python3
# teach_insert.py — mechanically perform the surgical insert that turns a mission-style UI-only step
# into an API-backed step, editing ONLY the target file.
#
# Why this exists: when the agent hand-edited the step it churned the UI (parameterised the login email),
# touched an unrelated step's file, and drifted the section names. This script removes that freedom: the
# agent supplies ONLY the `## API attempt` body; everything else is mechanical and guaranteed —
#   - the provenance header goes on top,
#   - `## API attempt` is inserted ABOVE the original instructions,
#   - the original `Instructions:` block is preserved BYTE-FOR-BYTE under `## UI instructions`,
#   - `method` is added to `Return value`,
#   - Mission / Inputs / Important are untouched,
#   - and NO other file is written (single-file by construction).
#
# Usage:  teach_insert.py --step steps/<STEP>.md --header "<provenance, no comment markers>" --api <file>
#         (or pipe the API body on stdin and omit --api)

from __future__ import annotations

import argparse
import sys


def transform(step_md: str, header: str, api_body: str) -> str:
    if "## API attempt" in step_md:
        raise ValueError("already has a '## API attempt' section — regenerate from a clean UI-only baseline")
    if "Instructions:" not in step_md:
        raise ValueError("not a mission-style UI step (no 'Instructions:' heading)")
    if "Return value:" not in step_md:
        raise ValueError("not a mission-style UI step (no 'Return value:' block)")

    before, after = step_md.split("Instructions:", 1)  # `after` = the numbered steps, kept verbatim
    api_block = f"## API attempt\n\n{api_body.strip()}\n\n## UI instructions"
    body = before + api_block + after

    # record which path ran: add `method` as the first Return value bullet (once)
    head, sep, tail = body.partition("Return value:")  # tail starts with "\n- ..."
    if "method:" not in tail.split("\n\n", 1)[0]:
        body = head + sep + '\n- method: "api" or "ui".' + tail

    return f"<!-- {header.strip()} -->\n" + body


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="teach_insert")
    ap.add_argument("--step", required=True, help="path to the mission-style UI-only steps/<STEP>.md")
    ap.add_argument("--header", required=True, help="provenance line WITHOUT the <!-- --> markers")
    ap.add_argument("--api", default=None, help="file with the ## API attempt body; omit to read stdin")
    args = ap.parse_args(argv)

    with open(args.step) as f:
        step_md = f.read()
    api_body = open(args.api).read() if args.api else sys.stdin.read()
    if not api_body.strip():
        print("error: empty API body", file=sys.stderr)
        return 2

    try:
        out = transform(step_md, args.header, api_body)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    with open(args.step, "w") as f:
        f.write(out)
    print(f"inserted ## API attempt into {args.step}")
    print("now verify ONLY this file changed:  git -C <skill> diff --name-only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
