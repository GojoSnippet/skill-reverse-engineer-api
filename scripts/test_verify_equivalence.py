#!/usr/bin/env python3
# Tests for verify_equivalence.py — dependency-free (no poppler/pypdf needed).
import os
import tempfile

import verify_equivalence as v


def _w(d: str, name: str, data: bytes) -> str:
    p = os.path.join(d, name)
    open(p, "wb").write(data)
    return p


def test_token_jaccard() -> None:
    assert v.token_jaccard("a b c", "a b c") == 1.0
    assert v.token_jaccard("a b c", "x y z") == 0.0
    assert v.token_jaccard("", "") == 1.0
    assert v.token_jaccard("a b", "") == 0.0
    assert 0.0 < v.token_jaccard("a b c d", "a b x y") < 1.0
    # robust to whitespace/case/order
    assert v.token_jaccard("James  GOOGLE\nEngineer", "engineer james google") == 1.0


def test_size_ratio() -> None:
    assert v.size_ratio(100, 100) == 1.0
    assert v.size_ratio(45, 107) < 0.5
    assert v.size_ratio(0, 0) == 1.0


def test_is_pdf_and_file_info() -> None:
    with tempfile.TemporaryDirectory() as d:
        pdf = _w(d, "a.pdf", b"%PDF-1.7\n...stuff...")
        txt = _w(d, "a.txt", b"hello")
        assert v.is_pdf(pdf) and not v.is_pdf(txt)
        fi = v.file_info(pdf)
        assert fi["bytes"] == len(b"%PDF-1.7\n...stuff...") and len(fi["sha256"]) == 16


def test_byte_identical_is_match() -> None:
    with tempfile.TemporaryDirectory() as d:
        a = _w(d, "a.bin", b"\x89PNG identical bytes")
        b = _w(d, "b.bin", b"\x89PNG identical bytes")
        r = v.compare(a, b, 0.9)
        assert r["verdict"] == "MATCH" and r["method"] == "sha256"


def test_non_pdf_different_is_mismatch() -> None:
    with tempfile.TemporaryDirectory() as d:
        a = _w(d, "a.bin", b"one")
        b = _w(d, "b.bin", b"two different")
        r = v.compare(a, b, 0.9)
        assert r["verdict"] == "MISMATCH" and r["method"] == "bytes"


def test_pdf_same_text_is_match(monkeypatch) -> None:  # type: ignore
    with tempfile.TemporaryDirectory() as d:
        a = _w(d, "a.pdf", b"%PDF-1.7 aaaa")
        b = _w(d, "b.pdf", b"%PDF-1.7 bbbb")  # different bytes, same extracted text
        monkeypatch.setattr(v, "pdf_text", lambda p: "James Google Engineer California")
        r = v.compare(a, b, 0.9)
        assert r["verdict"] == "MATCH" and r["method"] == "pdf-text-jaccard" and r["overlap"] == 1.0


def test_pdf_different_text_is_mismatch(monkeypatch) -> None:  # type: ignore
    with tempfile.TemporaryDirectory() as d:
        a = _w(d, "a.pdf", b"%PDF-1.7 aaaa")
        b = _w(d, "b.pdf", b"%PDF-1.7 bbbb")
        texts = {"a.pdf": "this is not a valid profile go back",  # the canary junk
                 "b.pdf": "james google software engineer california salary career highlights techster"}
        monkeypatch.setattr(v, "pdf_text", lambda p: texts.get(os.path.basename(p), ""))
        r = v.compare(a, b, 0.9)
        assert r["verdict"] == "MISMATCH" and r["method"] == "pdf-text-jaccard"


def test_pdf_no_extractor_is_inconclusive(monkeypatch) -> None:  # type: ignore
    with tempfile.TemporaryDirectory() as d:
        a = _w(d, "a.pdf", b"%PDF-1.7 aaaa")
        b = _w(d, "b.pdf", b"%PDF-1.7 bbbbbbbb")
        monkeypatch.setattr(v, "pdf_text", lambda p: None)
        r = v.compare(a, b, 0.9)
        assert r["verdict"] == "INCONCLUSIVE"


if __name__ == "__main__":
    # tiny runner so it works with or without pytest (matches the other test files)
    import types

    class _MP:
        def __init__(self) -> None:
            self._undo: list = []

        def setattr(self, obj: object, name: str, val: object) -> None:
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)

        def undo(self) -> None:
            for obj, name, old in reversed(self._undo):
                setattr(obj, name, old)
            self._undo.clear()

    passed = 0
    for fn_name, fn in sorted(globals().items()):
        if not fn_name.startswith("test_") or not isinstance(fn, types.FunctionType):
            continue
        mp = _MP()
        try:
            if "monkeypatch" in fn.__code__.co_varnames[: fn.__code__.co_argcount]:
                fn(mp)
            else:
                fn()
            passed += 1
        finally:
            mp.undo()
    print(f"verify_equivalence: {passed} tests passed")
