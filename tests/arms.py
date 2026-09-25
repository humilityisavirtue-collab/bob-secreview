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


def _resolve(arg: str) -> tuple[str, str, str, str]:
    """Return (findings_path, chunk_path, review_path, prove_bites_path) from a file-or-directory argument."""
    arg = os.path.abspath(arg)
    if os.path.isdir(arg):
        findings_path    = os.path.join(arg, "findings.py")
        chunk_path       = os.path.join(arg, "chunk.py")
        review_path      = os.path.join(arg, "review.py")
        prove_bites_path = os.path.join(arg, "prove_bites.py")
    else:
        # A single file was given — derive siblings from the same directory.
        base = os.path.dirname(arg)
        name = os.path.basename(arg)
        if name == "findings.py":
            findings_path    = arg
            chunk_path       = os.path.join(base, "chunk.py")
            review_path      = os.path.join(base, "review.py")
            prove_bites_path = os.path.join(base, "prove_bites.py")
        elif name == "chunk.py":
            chunk_path       = arg
            findings_path    = os.path.join(base, "findings.py")
            review_path      = os.path.join(base, "review.py")
            prove_bites_path = os.path.join(base, "prove_bites.py")
        elif name == "review.py":
            review_path      = arg
            findings_path    = os.path.join(base, "findings.py")
            chunk_path       = os.path.join(base, "chunk.py")
            prove_bites_path = os.path.join(base, "prove_bites.py")
        elif name.startswith("prove_bites"):
            prove_bites_path = arg
            findings_path    = os.path.join(base, "findings.py")
            chunk_path       = os.path.join(base, "chunk.py")
            review_path      = os.path.join(base, "review.py")
        else:
            raise ValueError(
                f"Unrecognised file {arg!r}; expected findings.py, chunk.py, review.py, or prove_bites.py"
            )
    return findings_path, chunk_path, review_path, prove_bites_path


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
    """ARM-3 — budget-stop, cap enforcement, failing-client, and may_report_clean.

    Sub-arms A1–A5 assert the parse-path property: `may_report_clean()` is True
    if and only if the engine actually holds parsed output for every chunk.

        A1  client raises                  -> not clean
        A2  client returns prose           -> not clean  (KEY: parse failure ≠ review)
        A3  client returns []              -> clean      (control: honest empty IS clean)
        A4  client returns fenced JSON     -> clean, findings present
        A5  client returns prose then []   -> not clean  (first chunk unparseable)

    The defect being tested: `chunks_reviewed += 1` placed *before* the parse
    step counts a chunk as reviewed even when its response is unparseable.
    That allows `may_report_clean()` to return True while `error` is populated —
    a vacuous clean. A2 and A5 are the arms that expose it.
    """
    import json as _json

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
    # 120 lines -> 4 chunks; each call costs 1.0; cap=1.5, per_call_ceiling=1.0
    # After first chunk (cost 1.0), remaining=0.5 < per_call_ceiling=1.0 -> stop.
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
    # 3c. A client that always raises -> chunks_failed==chunks_total,
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

    # ------------------------------------------------------------------
    # A1–A5: parse-path sub-arms
    # The single-chunk source (10 lines, chunk_lines=40) produces exactly one
    # chunk, so each fake client is called exactly once.
    # ------------------------------------------------------------------
    small_source = "\n".join(f"line{i}" for i in range(1, 11))  # 10 lines -> 1 chunk
    arm_results: dict[str, bool] = {}

    # A1 — client raises -> not clean (error field set, may_report_clean False)
    def client_a1(prompt: str, cap: float) -> "tuple[str, float]":
        raise RuntimeError("A1 always raises")

    r_a1 = review_source(small_source, client_a1, file="a1.py",
                         max_cost=10.0, per_call_ceiling=1.0,
                         chunk_lines=40, overlap_lines=0)
    a1_ok = (r_a1.may_report_clean() is False) and bool(r_a1.error)
    arm_results["A1"] = a1_ok
    print(f"{'PASS' if a1_ok else 'FAIL'} ARM-3/A1: raises -> not clean "
          f"(may_report_clean={r_a1.may_report_clean()}, error={r_a1.error!r})")

    # A2 — client returns pure prose (unparseable) -> not clean
    # This is the KEY arm: the defect is that chunks_reviewed is incremented
    # even when parsing fails, making may_report_clean() return True while
    # error is populated.
    def client_a2(prompt: str, cap: float) -> "tuple[str, float]":
        return "This is a security assessment. No findings were identified.", 0.01

    r_a2 = review_source(small_source, client_a2, file="a2.py",
                         max_cost=10.0, per_call_ceiling=1.0,
                         chunk_lines=40, overlap_lines=0)
    a2_ok = (r_a2.may_report_clean() is False) and bool(r_a2.error)
    arm_results["A2"] = a2_ok
    print(f"{'PASS' if a2_ok else 'FAIL'} ARM-3/A2: prose -> not clean "
          f"(may_report_clean={r_a2.may_report_clean()}, error={r_a2.error!r})")

    # A3 — client returns bare [] (honest empty review) -> clean, no findings
    # CONTROL: an honest empty review MUST remain clean. A fix that makes every
    # empty response "not clean" has over-tightened — it cannot distinguish an
    # unparseable response from a genuinely clean one.
    def client_a3(prompt: str, cap: float) -> "tuple[str, float]":
        return "[]", 0.01

    r_a3 = review_source(small_source, client_a3, file="a3.py",
                         max_cost=10.0, per_call_ceiling=1.0,
                         chunk_lines=40, overlap_lines=0)
    a3_ok = (r_a3.may_report_clean() is True) and (r_a3.error is None)
    arm_results["A3"] = a3_ok
    print(f"{'PASS' if a3_ok else 'FAIL'} ARM-3/A3: [] -> clean (control) "
          f"(may_report_clean={r_a3.may_report_clean()}, error={r_a3.error!r})")

    # A4 — client returns fenced JSON with findings -> clean (no parse error),
    # findings present. Tests that fenced JSON is tolerated on the way in.
    def client_a4(prompt: str, cap: float) -> "tuple[str, float]":
        payload = _json.dumps([{
            "rule_id": "test-rule", "severity": "high",
            "line": 1, "title": "Test", "detail": "", "recommendation": "",
        }])
        return f"```json\n{payload}\n```", 0.01

    r_a4 = review_source(small_source, client_a4, file="a4.py",
                         max_cost=10.0, per_call_ceiling=1.0,
                         chunk_lines=40, overlap_lines=0)
    a4_ok = (r_a4.may_report_clean() is True) and (len(r_a4.findings) > 0)
    arm_results["A4"] = a4_ok
    print(f"{'PASS' if a4_ok else 'FAIL'} ARM-3/A4: fenced JSON -> clean, findings present "
          f"(may_report_clean={r_a4.may_report_clean()}, findings={len(r_a4.findings)})")

    # A5 — two-chunk source; chunk 0 returns prose (parse error), chunk 1 returns []
    # The first chunk's failure means we do NOT hold parsed output for the whole
    # source -> may_report_clean() must be False.
    two_chunk_source = "\n".join(f"line{i}" for i in range(1, 71))  # 70 lines, chunk=40, overlap=0 -> 2 chunks
    call_count_a5 = [0]

    def client_a5(prompt: str, cap: float) -> "tuple[str, float]":
        call_count_a5[0] += 1
        if call_count_a5[0] == 1:
            # First chunk: return prose (unparseable)
            return "No security issues found in this code.", 0.01
        else:
            # Second chunk: return honest empty JSON
            return "[]", 0.01

    r_a5 = review_source(two_chunk_source, client_a5, file="a5.py",
                         max_cost=10.0, per_call_ceiling=1.0,
                         chunk_lines=40, overlap_lines=0)
    a5_ok = (r_a5.may_report_clean() is False) and bool(r_a5.error)
    arm_results["A5"] = a5_ok
    print(f"{'PASS' if a5_ok else 'FAIL'} ARM-3/A5: prose then [] -> not clean "
          f"(may_report_clean={r_a5.may_report_clean()}, error={r_a5.error!r})")

    if not all(arm_results.values()):
        failed = [k for k, v in arm_results.items() if not v]
        print(f"FAIL ARM-3: sub-arms failed: {', '.join(failed)}")
        return False

    print("PASS ARM-3")
    return True


# ---------------------------------------------------------------------------
# ARM-4: prove_bites discrimination proof
# ---------------------------------------------------------------------------

def arm4(prove_bites_path: str) -> bool:
    """ARM-4 — prove_bites discriminates correctly; may_trust_clean() is False for
    every status except 'BITES'.

    Uses fake reviewers only.  No real calls, no real spending.
    """
    try:
        pb_mod = _load_module("prove_bites", prove_bites_path)
    except Exception as exc:
        print(f"FAIL ARM-4: could not import prove_bites from {prove_bites_path!r}: {exc}")
        return False

    prove_bites_fn = getattr(pb_mod, "prove_bites", None)
    BiteProof_cls  = getattr(pb_mod, "BiteProof",   None)
    if prove_bites_fn is None:
        print("FAIL ARM-4: prove_bites module has no prove_bites function")
        return False
    if BiteProof_cls is None:
        print("FAIL ARM-4: prove_bites module has no BiteProof class")
        return False

    # ------------------------------------------------------------------
    # Fake helpers
    # ------------------------------------------------------------------
    class _FakeScanResult:
        def __init__(self, rule_ids=(), *, truncated=False, error=None):
            self.findings = [_FakeF(r) for r in rule_ids]
            self.truncated = truncated
            self.error = error
        def may_report_clean(self):
            return not self.truncated and not self.error

    class _FakeF:
        def __init__(self, rid):
            self.rule_id = rid

    SOURCE = "x = evil()\ny = 1\n"
    TWIN   = "x = safe()\ny = 1\n"  # one hunk different

    # ------------------------------------------------------------------
    # 4a. BITES: planted on source, absent on twin
    # ------------------------------------------------------------------
    def rev_bites(src, file):
        if "evil" in src:
            return _FakeScanResult(["planted-rule"])
        return _FakeScanResult([])

    proof_bites = prove_bites_fn(rev_bites, SOURCE, planted_rule="planted-rule",
                                 clean_source=TWIN)
    if proof_bites.status != "BITES":
        print(f"FAIL ARM-4/4a: expected BITES, got {proof_bites.status!r}")
        return False
    if not proof_bites.may_trust_clean():
        print("FAIL ARM-4/4a: BITES proof has may_trust_clean()==False")
        return False

    # ------------------------------------------------------------------
    # 4b. DOES_NOT_BITE: planted on BOTH (no discrimination)
    # ------------------------------------------------------------------
    def rev_both(src, file):
        return _FakeScanResult(["planted-rule"])

    proof_both = prove_bites_fn(rev_both, SOURCE, planted_rule="planted-rule",
                                clean_source=TWIN)
    if proof_both.status != "DOES_NOT_BITE":
        print(f"FAIL ARM-4/4b: expected DOES_NOT_BITE, got {proof_both.status!r}")
        return False
    if proof_both.may_trust_clean() is not False:
        print(f"FAIL ARM-4/4b: DOES_NOT_BITE has may_trust_clean()=={proof_both.may_trust_clean()!r}; expected False")
        return False
    if "not discriminated" not in proof_both.reason:
        print(f"FAIL ARM-4/4b: reason does not mention 'not discriminated': {proof_both.reason!r}")
        return False

    # ------------------------------------------------------------------
    # 4c. DOES_NOT_BITE: planted never reported (other findings present)
    # ------------------------------------------------------------------
    def rev_other(src, file):
        return _FakeScanResult(["other-rule"])

    proof_other = prove_bites_fn(rev_other, SOURCE, planted_rule="planted-rule",
                                 clean_source=TWIN)
    if proof_other.status != "DOES_NOT_BITE":
        print(f"FAIL ARM-4/4c: expected DOES_NOT_BITE, got {proof_other.status!r}")
        return False
    if proof_other.may_trust_clean() is not False:
        print(f"FAIL ARM-4/4c: DOES_NOT_BITE has may_trust_clean()=={proof_other.may_trust_clean()!r}")
        return False

    # ------------------------------------------------------------------
    # 4d. DOES_NOT_BITE: silent reviewer (no findings at all)
    # ------------------------------------------------------------------
    def rev_silent(src, file):
        return _FakeScanResult([])

    proof_silent = prove_bites_fn(rev_silent, SOURCE, planted_rule="planted-rule",
                                  clean_source=TWIN)
    if proof_silent.status != "DOES_NOT_BITE":
        print(f"FAIL ARM-4/4d: expected DOES_NOT_BITE, got {proof_silent.status!r}")
        return False
    if proof_silent.may_trust_clean() is not False:
        print(f"FAIL ARM-4/4d: DOES_NOT_BITE has may_trust_clean()=={proof_silent.may_trust_clean()!r}")
        return False

    # ------------------------------------------------------------------
    # 4e. INCONCLUSIVE: clean_source is None
    # ------------------------------------------------------------------
    proof_no_twin = prove_bites_fn(rev_bites, SOURCE, planted_rule="planted-rule",
                                   clean_source=None)
    if proof_no_twin.status != "INCONCLUSIVE":
        print(f"FAIL ARM-4/4e: expected INCONCLUSIVE when clean_source=None, got {proof_no_twin.status!r}")
        return False
    if proof_no_twin.may_trust_clean() is not False:
        print(f"FAIL ARM-4/4e: INCONCLUSIVE has may_trust_clean()=={proof_no_twin.may_trust_clean()!r}")
        return False

    # ------------------------------------------------------------------
    # 4f. INCONCLUSIVE: truncated result
    # ------------------------------------------------------------------
    def rev_trunc(src, file):
        return _FakeScanResult(["planted-rule"], truncated=True)

    proof_trunc = prove_bites_fn(rev_trunc, SOURCE, planted_rule="planted-rule",
                                 clean_source=TWIN)
    if proof_trunc.status != "INCONCLUSIVE":
        print(f"FAIL ARM-4/4f: expected INCONCLUSIVE on truncated, got {proof_trunc.status!r}")
        return False
    if proof_trunc.may_trust_clean() is not False:
        print(f"FAIL ARM-4/4f: INCONCLUSIVE has may_trust_clean()=={proof_trunc.may_trust_clean()!r}")
        return False

    # ------------------------------------------------------------------
    # 4g. INCONCLUSIVE: result carries an error
    # ------------------------------------------------------------------
    def rev_err(src, file):
        return _FakeScanResult(["planted-rule"], error="simulated error")

    proof_err = prove_bites_fn(rev_err, SOURCE, planted_rule="planted-rule",
                               clean_source=TWIN)
    if proof_err.status != "INCONCLUSIVE":
        print(f"FAIL ARM-4/4g: expected INCONCLUSIVE on error result, got {proof_err.status!r}")
        return False
    if proof_err.may_trust_clean() is not False:
        print(f"FAIL ARM-4/4g: INCONCLUSIVE has may_trust_clean()=={proof_err.may_trust_clean()!r}")
        return False

    # ------------------------------------------------------------------
    # 4h. twin_hunks == 1 for a single-hunk diff
    # ------------------------------------------------------------------
    if proof_bites.twin_hunks != 1:
        print(f"FAIL ARM-4/4h: expected twin_hunks == 1, got {proof_bites.twin_hunks!r}")
        return False

    # ------------------------------------------------------------------
    # 4i. may_trust_clean() is False for DOES_NOT_BITE and INCONCLUSIVE
    #     (explicit exhaustive check across all non-BITES statuses)
    # ------------------------------------------------------------------
    non_bites = [proof_both, proof_other, proof_silent, proof_no_twin, proof_trunc, proof_err]
    for p in non_bites:
        if p.may_trust_clean() is not False:
            print(
                f"FAIL ARM-4/4i: proof with status={p.status!r} has "
                f"may_trust_clean()=={p.may_trust_clean()!r}; expected False"
            )
            return False

    print("PASS ARM-4")
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <path>", file=sys.stderr)
        sys.exit(2)

    try:
        findings_path, chunk_path, review_path, prove_bites_path = _resolve(sys.argv[1])
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    results = [
        arm1(findings_path),
        arm2(chunk_path),
        arm3(review_path),
        arm4(prove_bites_path),
    ]

    sys.exit(0 if all(results) else 1)
