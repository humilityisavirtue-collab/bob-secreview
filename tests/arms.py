"""tests/arms.py — conformance harness for findings.py, chunk.py, and review.py.

Usage:
    python tests/arms.py <path>

<path> may be a file or a directory containing findings.py, chunk.py, and
review.py. The modules are imported from that path; standard library only.

Exit 0 only if all arms pass.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import os
import sys


def _load_module(name: str, path: str):
    """Load a module by filesystem path."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name!r} from {path!r}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception:
        sys.modules.pop(name, None)
        raise
    return mod


def _resolve(arg: str) -> tuple[str, str, str]:
    """Return (findings_path, chunk_path, review_path) from a file-or-directory argument."""
    arg = os.path.abspath(arg)
    if os.path.isdir(arg):
        findings_path = os.path.join(arg, "findings.py")
        chunk_path = os.path.join(arg, "chunk.py")
        review_path = os.path.join(arg, "review.py")
    else:
        # A single file was given — derive siblings from the same directory.
        base = os.path.dirname(arg)
        name = os.path.basename(arg)
        if name == "findings.py":
            findings_path = arg
            chunk_path = os.path.join(base, "chunk.py")
            review_path = os.path.join(base, "review.py")
        elif name == "chunk.py":
            chunk_path = arg
            findings_path = os.path.join(base, "findings.py")
            review_path = os.path.join(base, "review.py")
        elif name == "review.py":
            review_path = arg
            findings_path = os.path.join(base, "findings.py")
            chunk_path = os.path.join(base, "chunk.py")
        else:
            raise ValueError(
                f"Unrecognised file {arg!r}; expected findings.py, chunk.py, or review.py"
            )
    return findings_path, chunk_path, review_path


# ---------------------------------------------------------------------------
# ARM-1: severity is enforced at construction; Finding is frozen
# ---------------------------------------------------------------------------

def arm1(findings_path: str) -> bool:
    """ARM-1 — severity is enforced at construction; Finding is immutable (frozen)."""
    try:
        findings = _load_module("findings", findings_path)
    except Exception as exc:
        print(f"FAIL ARM-1: could not import findings from {findings_path!r}: {exc}")
        return False

    loc_cls = findings.Location
    finding_cls = findings.Finding
    loc = loc_cls(file="f.py", line_start=1, line_end=1)

    # 1a. An unknown severity must raise ValueError at construction time.
    raised_on_bad = False
    try:
        finding_cls(rule_id="r", severity="nonsense", location=loc)
    except ValueError:
        raised_on_bad = True
    except Exception as exc:
        print(f"FAIL ARM-1: unknown severity raised unexpected {type(exc).__name__}: {exc}")
        return False

    if not raised_on_bad:
        print("FAIL ARM-1: Finding('r', 'nonsense', loc) did not raise ValueError at construction")
        return False

    # 1b. A valid severity must still construct without raising.
    try:
        f_high = finding_cls(rule_id="r", severity="high", location=loc)
        f_low  = finding_cls(rule_id="r", severity="low",  location=loc)
    except Exception as exc:
        print(f"FAIL ARM-1: valid severity raised unexpectedly: {exc}")
        return False

    # 1c. A list of two or more sorts most-severe-first.
    ordered = sorted([f_low, f_high])
    if ordered[0].severity != "high":
        print(f"FAIL ARM-1: sorted([low, high])[0].severity == {ordered[0].severity!r}, expected 'high'")
        return False

    # 1d. Assigning to a Finding field must raise FrozenInstanceError specifically.
    # (FrozenInstanceError subclasses AttributeError; catching only AttributeError would
    # pass vacuously on any attribute typo — we require the exact frozen-dataclass error.)
    try:
        f_high.severity = "low"  # type: ignore[misc]
        print("FAIL ARM-1: assigning to Finding.severity did not raise (Finding is not frozen)")
        return False
    except dataclasses.FrozenInstanceError:
        pass  # correct — the dataclass IS frozen
    except AttributeError as exc:
        # Any other AttributeError (e.g. missing slot) is NOT sufficient proof of frozen
        print(
            f"FAIL ARM-1: assigning to Finding.severity raised AttributeError but not "
            f"FrozenInstanceError — Finding may not be a frozen dataclass: {exc}"
        )
        return False
    except Exception as exc:
        print(f"FAIL ARM-1: assigning to Finding.severity raised unexpected {type(exc).__name__}: {exc}")
        return False

    print("PASS ARM-1")
    return True


# ---------------------------------------------------------------------------
# ARM-2: chunk round-trip invariant over varied sources
# ---------------------------------------------------------------------------

def arm2(chunk_path: str) -> bool:
    """ARM-2 — chunk round-trip: point-4 invariant and full coverage."""
    try:
        chunk_mod = _load_module("chunk", chunk_path)
    except Exception as exc:
        print(f"FAIL ARM-2: could not import chunk from {chunk_path!r}: {exc}")
        return False

    chunk_text_fn = chunk_mod.chunk_text

    def _check_source(label: str, source: str, chunk_lines: int = 40, overlap_lines: int = 10) -> bool:
        chunks = chunk_text_fn(source, chunk_lines=chunk_lines, overlap_lines=overlap_lines)
        all_lines = source.splitlines()
        total = len(all_lines)

        # point-4 invariant for every chunk
        for ch in chunks:
            expected = all_lines[ch.start_line - 1 : ch.end_line]
            actual = ch.text.splitlines()
            if actual != expected:
                print(
                    f"FAIL ARM-2 [{label}]: chunk {ch.index} text invariant broken\n"
                    f"  expected {expected!r}\n"
                    f"  got      {actual!r}"
                )
                return False

        # every line of a non-empty source is covered
        if total > 0:
            covered = set()
            for ch in chunks:
                for ln in range(ch.start_line, ch.end_line + 1):
                    covered.add(ln)
            if covered != set(range(1, total + 1)):
                missing = sorted(set(range(1, total + 1)) - covered)
                print(f"FAIL ARM-2 [{label}]: lines not covered: {missing}")
                return False

        return True

    cases = [
        # (label, source, chunk_lines, overlap_lines)
        ("plain 100 lines",      "\n".join(f"line{i}" for i in range(1, 101)), 40, 10),
        ("trailing newline",     "a\nb\nc\n",                                   10,  2),
        ("blank line in middle", "a\nb\n\nc\nd",                                10,  2),
        # The critical case: source with a blank line at the very END of a slice.
        # 6 lines: a, b, (blank), c, d, (blank) — with chunk_lines=3, overlap=1
        # chunk 0: lines 1-3 = ["a", "b", ""], chunk 1: lines 3-5 = ["", "c", "d"], etc.
        ("blank line at chunk boundary", "a\nb\n\nc\nd\n\n",                    3,   1),
        ("single line no newline",       "hello",                               10,  2),
        ("single line with newline",     "hello\n",                             10,  2),
        ("exact multiple of step",       "\n".join(f"z{i}" for i in range(1, 61)), 40, 10),
        ("windows line endings",         "a\r\nb\r\nc\r\n",                    10,  2),
        ("55 lines partial final chunk", "\n".join(f"x{i}" for i in range(1, 56)), 40, 10),
    ]

    for label, src, cl, ol in cases:
        if not _check_source(label, src, cl, ol):
            return False

    print("PASS ARM-2")
    return True


# ---------------------------------------------------------------------------
# ARM-3: budget-stop, spend-cap, failing-client, and may_report_clean invariants
# ---------------------------------------------------------------------------

def arm3(review_path: str) -> bool:
    """ARM-3 — budget-stop, cap enforcement, failing-client, and may_report_clean."""
    try:
        review_mod = _load_module("review", review_path)
    except Exception as exc:
        print(f"FAIL ARM-3: could not import review from {review_path!r}: {exc}")
        return False

    review_source = getattr(review_mod, "review_source", None)
    if review_source is None:
        print("FAIL ARM-3: review module has no review_source function")
        return False

    # ------------------------------------------------------------------
    # 3a. Budget-stop: truncated=True and chunks_reviewed < chunks_total
    # ------------------------------------------------------------------
    # chunk_lines=40, overlap=10, step=30
    # 120 lines → 4 chunks; each call costs 1.0; cap=1.5, per_call_ceiling=1.0
    # After first chunk (cost 1.0), remaining=0.5 < per_call_ceiling=1.0 → stop.
    source = "\n".join(f"line{i}" for i in range(1, 121))  # 120 lines

    costs_incurred: list[float] = []

    def fake_client(prompt: str, per_call_cap: float) -> "tuple[str, float]":
        costs_incurred.append(1.0)
        return "[]", 1.0

    try:
        result = review_source(
            source, fake_client,
            file="arm3.py",
            max_cost=1.5,
            per_call_ceiling=1.0,
            chunk_lines=40,
            overlap_lines=10,
        )
    except Exception as exc:
        print(f"FAIL ARM-3: review_source raised unexpectedly: {exc}")
        return False

    if not result.truncated:
        print(
            f"FAIL ARM-3: expected truncated=True but got truncated={result.truncated!r} "
            f"(chunks_reviewed={result.chunks_reviewed}, chunks_total={result.chunks_total})"
        )
        return False

    if result.chunks_reviewed >= result.chunks_total:
        print(
            f"FAIL ARM-3: expected chunks_reviewed < chunks_total but got "
            f"chunks_reviewed={result.chunks_reviewed}, chunks_total={result.chunks_total}"
        )
        return False

    # 3b. Cap was not exceeded: sum of costs <= max_cost
    total_spent = sum(costs_incurred)
    if total_spent > 1.5:
        print(
            f"FAIL ARM-3: cap exceeded — total spent {total_spent} > max_cost 1.5"
        )
        return False

    # 3b2. A truncated (budget-stopped) result must NOT be reportable as clean.
    # may_report_clean() must be False when coverage was not earned.
    may_clean_trunc = getattr(result, "may_report_clean", None)
    if may_clean_trunc is None:
        print("FAIL ARM-3: result has no may_report_clean() method")
        return False
    if may_clean_trunc() is not False:
        print(
            f"FAIL ARM-3: truncated result has may_report_clean()=={may_clean_trunc()!r}; "
            f"expected False (chunks_reviewed={result.chunks_reviewed}, "
            f"chunks_total={result.chunks_total}, chunks_failed={getattr(result, 'chunks_failed', '?')})"
        )
        return False

    # ------------------------------------------------------------------
    # 3c. A client that always raises → chunks_failed==chunks_total,
    #     chunks_reviewed==0, and may_report_clean() is False.
    # ------------------------------------------------------------------
    def always_raises(prompt: str, per_call_cap: float) -> "tuple[str, float]":
        raise RuntimeError("always fails")

    try:
        result_fail = review_source(
            source, always_raises,
            file="arm3_fail.py",
            max_cost=100.0,
            per_call_ceiling=1.0,
            chunk_lines=40,
            overlap_lines=10,
        )
    except Exception as exc:
        print(f"FAIL ARM-3: review_source raised unexpectedly on always-raises client: {exc}")
        return False

    chunks_total = result_fail.chunks_total
    chunks_failed = getattr(result_fail, "chunks_failed", None)
    chunks_reviewed = result_fail.chunks_reviewed

    if chunks_failed is None:
        print("FAIL ARM-3: result has no chunks_failed field")
        return False

    if chunks_failed != chunks_total:
        print(
            f"FAIL ARM-3: expected chunks_failed == chunks_total ({chunks_total}) "
            f"but got chunks_failed={chunks_failed}"
        )
        return False

    if chunks_reviewed != 0:
        print(
            f"FAIL ARM-3: expected chunks_reviewed == 0 but got chunks_reviewed={chunks_reviewed}"
        )
        return False

    may_clean = getattr(result_fail, "may_report_clean", None)
    if may_clean is None:
        print("FAIL ARM-3: result has no may_report_clean() method")
        return False

    if may_clean() is not False:
        print(
            f"FAIL ARM-3: expected may_report_clean() to be False after all-failing client, "
            f"got {may_clean()!r}"
        )
        return False

    print("PASS ARM-3")
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <path>", file=sys.stderr)
        sys.exit(2)

    try:
        findings_path, chunk_path, review_path = _resolve(sys.argv[1])
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    results = [
        arm1(findings_path),
        arm2(chunk_path),
        arm3(review_path),
    ]

    sys.exit(0 if all(results) else 1)
