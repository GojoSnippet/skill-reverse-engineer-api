#!/usr/bin/env python3
# verify_equivalence.py — THE teach-time gate.
#
# "A file was produced" is NOT success. "The API's output equals the UI's output, on an instance we did
# NOT set up by hand" is. This compares the API artifact against the UI golden at the CONTENT level
# (PDFs carry volatile metadata, so naive byte-equality is wrong) and exits:
#   0  -> MATCH      (ship it as API)
#   1  -> MISMATCH   (keep UI — the chain does not faithfully reproduce the UI)
#   3  -> INCONCLUSIVE (no text extractor available; a human must eyeball both artifacts)
#
# Usage:
#   python verify_equivalence.py --api /tmp/api_out.pdf --golden /tmp/ui_golden.pdf [--threshold 0.9]

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

MATCH, MISMATCH, INCONCLUSIVE = 0, 1, 3


def file_info(path: str) -> dict:
    data = open(path, "rb").read()
    return {
        "path": path,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest()[:16],
        "magic": data[:5].decode("latin-1"),
    }


def is_pdf(path: str) -> bool:
    with open(path, "rb") as f:
        return f.read(5) == b"%PDF-"


def pdf_text(path: str) -> str | None:
    """Extract text via poppler's pdftotext, else pypdf. None if neither is available."""
    try:
        out = subprocess.run(["pdftotext", "-q", path, "-"], capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            return out.stdout
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass
    try:
        from pypdf import PdfReader  # type: ignore

        return "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
    except Exception:
        return None


def norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def token_jaccard(a: str | None, b: str | None) -> float:
    """Overlap of word sets — robust to reordering/metadata, sensitive to different CONTENT."""
    ta, tb = set(norm(a).split()), set(norm(b).split())
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def size_ratio(a: int, b: int) -> float:
    hi = max(a, b)
    return round(min(a, b) / hi, 3) if hi else 1.0


def compare(api: str, golden: str, threshold: float) -> dict:
    ai, gi = file_info(api), file_info(golden)
    res: dict = {"api": ai, "golden": gi, "sizeRatio": size_ratio(ai["bytes"], gi["bytes"])}

    if ai["sha256"] == gi["sha256"]:
        return {**res, "verdict": "MATCH", "method": "sha256", "reason": "byte-identical"}

    if is_pdf(api) and is_pdf(golden):
        ta, tg = pdf_text(api), pdf_text(golden)
        if ta is None or tg is None:
            return {
                **res,
                "verdict": "INCONCLUSIVE",
                "method": "none",
                "reason": "no pdf text extractor (install poppler-utils or pypdf); size-only is not proof — "
                "OPEN both PDFs and confirm the same fields by eye before shipping",
            }
        ov = round(token_jaccard(ta, tg), 3)
        return {
            **res,
            "verdict": "MATCH" if ov >= threshold else "MISMATCH",
            "method": "pdf-text-jaccard",
            "overlap": ov,
            "threshold": threshold,
            "reason": f"text token overlap {ov} {'>=' if ov >= threshold else '<'} {threshold}",
        }

    # Non-PDF, not byte-identical: generic artifacts must match exactly.
    return {
        **res,
        "verdict": "MISMATCH",
        "method": "bytes",
        "reason": "not byte-identical and not both PDF; generic artifacts must be identical to count as equivalent",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True, help="artifact produced by the API replay (on a FRESH instance)")
    ap.add_argument("--golden", required=True, help="artifact produced by the UI on that same fresh instance")
    ap.add_argument("--threshold", type=float, default=0.9, help="min PDF text overlap to count as a match")
    args = ap.parse_args()
    for p in (args.api, args.golden):
        if not os.path.exists(p):
            sys.exit(f"missing file: {p}")
    res = compare(args.api, args.golden, args.threshold)
    print(json.dumps(res, indent=2))
    sys.exit({"MATCH": MATCH, "MISMATCH": MISMATCH, "INCONCLUSIVE": INCONCLUSIVE}[res["verdict"]])


if __name__ == "__main__":
    main()
