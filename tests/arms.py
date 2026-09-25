"""tests/arms.py — conformance harness for findings.py, chunk.py, and review.py.

Usage:
    python tests/arms.py <path>

<path> may be a file or a directory containing findings.py, chunk.py, and
review.py. The modules are imported from that path; standard library only.

Exit 0 only if all arms pass.

Manifest and contamination check (Increment 8)
-----------------------------------------------
When <path> is a directory, the harness builds a manifest of every module file
it finds there and compares each against the same-named file in src/.  A file
that differs from src/ is *mutated* and must be declared in a MUTANT.json in
that directory; otherwise the harness REFUSES to run any arms (non-zero exit,
no arm output).

The src/ subject itself needs no MUTANT.json (nothing is mutated), but the
manifest is still printed.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json as _json_stdlib
import os
import sys


# ---------------------------------------------------------------------------
# Manifest and contamination check — Part A of Increment 8
# ---------------------------------------------------------------------------

# The set of module files the harness knows about.
_MODULE_FILES = ("findings.py", "chunk.py", "review.py", "prove_bites.py", "report.py")


def _sha256(path: str) -> str:
    """Return the hex SHA-256 digest of the file at *path*."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _check_manifest(subject_dir: str) -> bool:
    """Print the manifest for *subject_dir* and refuse if any undeclared mutation exists.

    Returns True if the arms may proceed, False if they must be refused.

    Rules:
    - For every module file present in subject_dir, compare its content (by
      sha256) against the same-named file in src/.
    - Files that match src/ are labelled IDENTICAL.
    - Files that differ from src/ are labelled DECLARED-MUTATED if they appear
      in MUTANT.json, or UNDECLARED-MUTATION otherwise.
    - Any UNDECLARED-MUTATION → print the offending file, the declared set, and
      return False (refuse to run arms).
    - A missing MUTANT.json on a directory that has any mutation is also a
      refusal.
    - The src/ directory itself needs no MUTANT.json (nothing is mutated).
    """
    # Locate src/ relative to this script's own directory.
    arms_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.abspath(os.path.join(arms_dir, "..", "src"))

    # Load MUTANT.json if present.
    mutant_json_path = os.path.join(subject_dir, "MUTANT.json")
    declared_files: set[str] = set()
    if os.path.isfile(mutant_json_path):
        try:
            with open(mutant_json_path, encoding="utf-8") as fh:
                mutant_data = _json_stdlib.load(fh)
            for entry in mutant_data.get("mutations", []):
                declared_files.add(entry.get("file", ""))
        except Exception as exc:
            print(f"ERROR: could not parse MUTANT.json in {subject_dir!r}: {exc}")
            return False

    print("=== MANIFEST ===")
    undeclared: list[str] = []

    for fname in _MODULE_FILES:
        subject_file = os.path.join(subject_dir, fname)
        src_file = os.path.join(src_dir, fname)

        if not os.path.isfile(subject_file):
            # File not present in subject dir — skip it.
            continue

        sha = _sha256(subject_file)

        if not os.path.isfile(src_file):
            # No src/ counterpart — treat as IDENTICAL (no basis for comparison).
            print(f"  {fname}  sha256={sha[:16]}...  IDENTICAL (no src counterpart)")
            continue

        src_sha = _sha256(src_file)

        if sha == src_sha:
            print(f"  {fname}  sha256={sha[:16]}...  IDENTICAL")
        elif fname in declared_files:
            print(f"  {fname}  sha256={sha[:16]}...  DECLARED-MUTATED")
        else:
            print(f"  {fname}  sha256={sha[:16]}...  UNDECLARED-MUTATION")
            undeclared.append(fname)

    print("=== END MANIFEST ===")

    if undeclared:
        print()
        print("REFUSE: the following file(s) differ from src/ but are NOT declared in MUTANT.json:")
        for fname in undeclared:
            print(f"  {fname}")
        print(f"Declared set: {sorted(declared_files) if declared_files else '(MUTANT.json absent or empty)'}")
        print("No arms were run.")
        return False

    return True


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


def _resolve(arg: str) -> tuple[str, str, str, str, str]:
    """Return (findings_path, chunk_path, review_path, prove_bites_path, report_path) from a file-or-directory argument."""
    arg = os.path.abspath(arg)
    if os.path.isdir(arg):
        findings_path    = os.path.join(arg, "findings.py")
        chunk_path       = os.path.join(arg, "chunk.py")
        review_path      = os.path.join(arg, "review.py")
        prove_bites_path = os.path.join(arg, "prove_bites.py")
        report_path      = os.path.join(arg, "report.py")
    else:
        # A single file was given — derive siblings from the same directory.
        base = os.path.dirname(arg)
        name = os.path.basename(arg)
        if name == "findings.py":
            findings_path    = arg
            chunk_path       = os.path.join(base, "chunk.py")
            review_path      = os.path.join(base, "review.py")
            prove_bites_path = os.path.join(base, "prove_bites.py")
            report_path      = os.path.join(base, "report.py")
        elif name == "chunk.py":
            chunk_path       = arg
            findings_path    = os.path.join(base, "findings.py")
            review_path      = os.path.join(base, "review.py")
            prove_bites_path = os.path.join(base, "prove_bites.py")
            report_path      = os.path.join(base, "report.py")
        elif name == "review.py":
            review_path      = arg
            findings_path    = os.path.join(base, "findings.py")
            chunk_path       = os.path.join(base, "chunk.py")
            prove_bites_path = os.path.join(base, "prove_bites.py")
            report_path      = os.path.join(base, "report.py")
        elif name.startswith("prove_bites"):
            prove_bites_path = arg
            findings_path    = os.path.join(base, "findings.py")
            chunk_path       = os.path.join(base, "chunk.py")
            review_path      = os.path.join(base, "review.py")
            report_path      = os.path.join(base, "report.py")
        elif name == "report.py":
            report_path      = arg
            findings_path    = os.path.join(base, "findings.py")
            chunk_path       = os.path.join(base, "chunk.py")
            review_path      = os.path.join(base, "review.py")
            prove_bites_path = os.path.join(base, "prove_bites.py")
        else:
            raise ValueError(
                f"Unrecognised file {arg!r}; expected findings.py, chunk.py, review.py, "
                f"prove_bites.py, or report.py"
            )
    return findings_path, chunk_path, review_path, prove_bites_path, report_path


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
    # Also asserts chunks_failed == chunks_total (total failure: 1 chunk, 1 parse error).
    def client_a2(prompt: str, cap: float) -> "tuple[str, float]":
        return "This is a security assessment. No findings were identified.", 0.01

    r_a2 = review_source(small_source, client_a2, file="a2.py",
                         max_cost=10.0, per_call_ceiling=1.0,
                         chunk_lines=40, overlap_lines=0)
    a2_chunks_failed = getattr(r_a2, "chunks_failed", None)
    # chunks_failed == chunks_total: every chunk's response failed to parse.
    a2_cf_ok = (a2_chunks_failed is not None) and (a2_chunks_failed == r_a2.chunks_total)
    a2_ok = (r_a2.may_report_clean() is False) and bool(r_a2.error) and a2_cf_ok
    arm_results["A2"] = a2_ok
    print(f"{'PASS' if a2_ok else 'FAIL'} ARM-3/A2: prose -> not clean "
          f"(may_report_clean={r_a2.may_report_clean()}, error={r_a2.error!r}, "
          f"chunks_failed={a2_chunks_failed}, chunks_total={r_a2.chunks_total})")

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
    # Also asserts chunks_failed == 1 and chunks_reviewed == chunks_total - 1 (partial failure).
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
    a5_chunks_failed = getattr(r_a5, "chunks_failed", None)
    # chunks_failed == 1 (first chunk parse error); chunks_reviewed == chunks_total - 1 (second chunk ok).
    a5_cf_ok = (a5_chunks_failed is not None) and (a5_chunks_failed == 1)
    a5_cr_ok = (r_a5.chunks_reviewed == r_a5.chunks_total - 1)
    a5_ok = (r_a5.may_report_clean() is False) and bool(r_a5.error) and a5_cf_ok and a5_cr_ok
    arm_results["A5"] = a5_ok
    print(f"{'PASS' if a5_ok else 'FAIL'} ARM-3/A5: prose then [] -> not clean "
          f"(may_report_clean={r_a5.may_report_clean()}, error={r_a5.error!r}, "
          f"chunks_failed={a5_chunks_failed}, chunks_reviewed={r_a5.chunks_reviewed}, "
          f"chunks_total={r_a5.chunks_total})")

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
    every status except 'BITES'.  twin_ratio_baseline is exposed on every proof that
    has a twin.

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

    # A "large" source (20 lines, non-trivially sorted) used for BITES cases.
    # The lines are NOT in alphabetical order, so reversed(lines) != lines and
    # the self-generated baseline is well below 1.0, allowing an honest
    # one-line-changed twin to beat it with a clear margin.
    LARGE_SOURCE = "\n".join([
        "import os",
        "import sys",
        "def foo(x):",
        "    y = evil(x)",
        "    z = x + 1",
        "    return y + z",
        "def bar(a, b):",
        "    return a * b",
        "class Baz:",
        "    def __init__(self):",
        "        self.value = 0",
        "    def compute(self, n):",
        "        return self.value + n",
        "def main():",
        "    obj = Baz()",
        "    result = foo(obj.compute(10))",
        "    bar(result, 2)",
        "    print(result)",
        "if __name__ == '__main__':",
        "    main()",
    ]) + "\n"
    LARGE_TWIN = LARGE_SOURCE.replace("    y = evil(x)", "    y = safe(x)")

    # A 2-line source — lines are alphabetically ordered, so sorted(lines)==lines,
    # but with the reversed-baseline the ratio is not 1.0 (reversed != original
    # for two distinct lines), so this correctly yields INCONCLUSIVE because the
    # honest twin's ratio does not beat the reversed baseline by a margin.
    TWO_LINE_SOURCE = "x = 1\ny = evil(x)\n"
    TWO_LINE_TWIN   = "x = 1\ny = safe(x)\n"

    # Increment 10b: a SORTED source (lines already in lexicographic order).
    # The OLD sorted-copy baseline gave baseline==1.0 here (identity), turning
    # every sorted file into a permanent INCONCLUSIVE.  The FIX (reversed
    # baseline) must give baseline < 1.0 so an honest twin can earn BITES.
    SORTED_SOURCE_4K = "\n".join([
        "        return evil(self.x)",
        "        return self.x + 1",
        "    def bar(self):",
        "    def baz(self):",
        "    foo = Foo()",
        "    foo.bar()",
        "    foo.baz()",
        "class Foo:",
        "def main():",
        "import os",
        "import sys",
    ]) + "\n"
    # Fixture guard: the lines must actually be sorted so this test is meaningful.
    assert SORTED_SOURCE_4K.splitlines() == sorted(SORTED_SOURCE_4K.splitlines()), \
        "ARM-4 SORTED_SOURCE_4K fixture is not in sorted order"
    SORTED_TWIN_4K = SORTED_SOURCE_4K.replace(
        "        return evil(self.x)", "        return safe(self.x)"
    )

    # ------------------------------------------------------------------
    # 4a. BITES: planted on source, absent on twin (large source)
    # ------------------------------------------------------------------
    def rev_bites(src, file):
        if "evil" in src:
            return _FakeScanResult(["planted-rule"])
        return _FakeScanResult([])

    proof_bites = prove_bites_fn(rev_bites, LARGE_SOURCE, planted_rule="planted-rule",
                                 clean_source=LARGE_TWIN)
    if proof_bites.status != "BITES":
        print(f"FAIL ARM-4/4a: expected BITES, got {proof_bites.status!r} "
              f"(twin_ratio={getattr(proof_bites, 'twin_ratio', 'N/A'):.4f}, "
              f"baseline={getattr(proof_bites, 'twin_ratio_baseline', 'N/A'):.4f})")
        return False
    if not proof_bites.may_trust_clean():
        print("FAIL ARM-4/4a: BITES proof has may_trust_clean()==False")
        return False
    # twin_ratio_baseline must be exposed and < twin_ratio (margin exists)
    baseline_a = getattr(proof_bites, "twin_ratio_baseline", None)
    if baseline_a is None:
        print("FAIL ARM-4/4a: BiteProof has no twin_ratio_baseline field")
        return False
    if not (proof_bites.twin_ratio > baseline_a):
        print(
            f"FAIL ARM-4/4a: twin_ratio={proof_bites.twin_ratio:.4f} is not > "
            f"twin_ratio_baseline={baseline_a:.4f}; no margin"
        )
        return False
    print(
        f"  ARM-4/4a: twin_ratio={proof_bites.twin_ratio:.4f}  "
        f"baseline={baseline_a:.4f}  "
        f"margin={proof_bites.twin_ratio - baseline_a:.4f}  status={proof_bites.status}"
    )

    # ------------------------------------------------------------------
    # 4b. DOES_NOT_BITE: planted on BOTH (no discrimination, large source)
    # ------------------------------------------------------------------
    def rev_both(src, file):
        return _FakeScanResult(["planted-rule"])

    proof_both = prove_bites_fn(rev_both, LARGE_SOURCE, planted_rule="planted-rule",
                                clean_source=LARGE_TWIN)
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

    proof_other = prove_bites_fn(rev_other, LARGE_SOURCE, planted_rule="planted-rule",
                                 clean_source=LARGE_TWIN)
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

    proof_silent = prove_bites_fn(rev_silent, LARGE_SOURCE, planted_rule="planted-rule",
                                  clean_source=LARGE_TWIN)
    if proof_silent.status != "DOES_NOT_BITE":
        print(f"FAIL ARM-4/4d: expected DOES_NOT_BITE, got {proof_silent.status!r}")
        return False
    if proof_silent.may_trust_clean() is not False:
        print(f"FAIL ARM-4/4d: DOES_NOT_BITE has may_trust_clean()=={proof_silent.may_trust_clean()!r}")
        return False

    # ------------------------------------------------------------------
    # 4e. INCONCLUSIVE: clean_source is None
    # ------------------------------------------------------------------
    proof_no_twin = prove_bites_fn(rev_bites, LARGE_SOURCE, planted_rule="planted-rule",
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

    proof_trunc = prove_bites_fn(rev_trunc, LARGE_SOURCE, planted_rule="planted-rule",
                                 clean_source=LARGE_TWIN)
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

    proof_err = prove_bites_fn(rev_err, LARGE_SOURCE, planted_rule="planted-rule",
                               clean_source=LARGE_TWIN)
    if proof_err.status != "INCONCLUSIVE":
        print(f"FAIL ARM-4/4g: expected INCONCLUSIVE on error result, got {proof_err.status!r}")
        return False
    if proof_err.may_trust_clean() is not False:
        print(f"FAIL ARM-4/4g: INCONCLUSIVE has may_trust_clean()=={proof_err.may_trust_clean()!r}")
        return False

    # ------------------------------------------------------------------
    # 4h. twin_hunks == 1 for a single-hunk diff (large source, one line changed)
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

    # ------------------------------------------------------------------
    # 4j. Degenerate twin: INCONCLUSIVE, may_trust_clean() False
    #
    # 🔒 This arm enforces that the margin check lives INSIDE the module.
    # A twin that does not beat the self-generated baseline must yield
    # INCONCLUSIVE regardless of what the reviewer says.
    #
    # Four cases:
    #   j1 — empty string twin (large source)
    #   j2 — unrelated tiny file as twin (large source)
    #   j3 — file-length discriminator with empty twin (must NOT be BITES)
    #   j4 — 2-line source with honest twin → INCONCLUSIVE (the zero-margin
    #         case: sorted(lines)==lines so baseline==1.0, no twin can win)
    # ------------------------------------------------------------------
    EMPTY_TWIN_4J    = ""
    UNRELATED_TWIN_4J = "import os\nprint(42)\n"

    # j1: empty string twin (large source)
    proof_empty = prove_bites_fn(rev_bites, LARGE_SOURCE, planted_rule="planted-rule",
                                 clean_source=EMPTY_TWIN_4J)
    if proof_empty.status != "INCONCLUSIVE":
        print(
            f"FAIL ARM-4/4j1: empty-string twin expected INCONCLUSIVE, "
            f"got {proof_empty.status!r}"
        )
        return False
    if proof_empty.may_trust_clean() is not False:
        print(
            f"FAIL ARM-4/4j1: empty-string twin INCONCLUSIVE has "
            f"may_trust_clean()=={proof_empty.may_trust_clean()!r}; expected False"
        )
        return False
    print(
        f"  ARM-4/4j1: empty twin -> status={proof_empty.status}, "
        f"twin_ratio={getattr(proof_empty, 'twin_ratio', 'N/A'):.4f}, "
        f"baseline={getattr(proof_empty, 'twin_ratio_baseline', 'N/A'):.4f}"
    )

    # j2: unrelated tiny file as twin (large source)
    proof_unrel = prove_bites_fn(rev_bites, LARGE_SOURCE, planted_rule="planted-rule",
                                 clean_source=UNRELATED_TWIN_4J)
    if proof_unrel.status != "INCONCLUSIVE":
        print(
            f"FAIL ARM-4/4j2: unrelated-file twin expected INCONCLUSIVE, "
            f"got {proof_unrel.status!r}"
        )
        return False
    if proof_unrel.may_trust_clean() is not False:
        print(
            f"FAIL ARM-4/4j2: unrelated-file twin INCONCLUSIVE has "
            f"may_trust_clean()=={proof_unrel.may_trust_clean()!r}; expected False"
        )
        return False
    print(
        f"  ARM-4/4j2: unrelated twin -> status={proof_unrel.status}, "
        f"twin_ratio={getattr(proof_unrel, 'twin_ratio', 'N/A'):.4f}, "
        f"baseline={getattr(proof_unrel, 'twin_ratio_baseline', 'N/A'):.4f}"
    )

    # j3: file-length discriminator with empty twin — must NOT be BITES
    def rev_len_disc(src, file):
        if len(src.splitlines()) > 1:
            return _FakeScanResult(["planted-rule"])
        return _FakeScanResult([])

    proof_len = prove_bites_fn(rev_len_disc, LARGE_SOURCE, planted_rule="planted-rule",
                               clean_source=EMPTY_TWIN_4J)
    if proof_len.status == "BITES":
        print(
            "FAIL ARM-4/4j3: file-length discriminator + empty twin must NOT be BITES; "
            f"got {proof_len.status!r} with may_trust_clean()=={proof_len.may_trust_clean()!r}"
        )
        return False
    if proof_len.may_trust_clean() is not False:
        print(
            f"FAIL ARM-4/4j3: file-length discriminator + empty twin: "
            f"may_trust_clean()=={proof_len.may_trust_clean()!r}; expected False"
        )
        return False
    print(
        f"  ARM-4/4j3: length-discriminator + empty twin -> status={proof_len.status} "
        f"(not BITES, may_trust_clean=False)"
    )

    # j4: 2-line source with honest twin → INCONCLUSIVE
    # The 2-line source "x = 1\ny = evil(x)\n" has lines in alphabetical order.
    # With the reversed baseline, the baseline is NOT 1.0 (reversing two distinct
    # lines does not produce the identity), but the honest twin's ratio still does
    # not beat it by a margin: both lines change the same relative position, so the
    # twin ratio is also below the baseline.  The result is INCONCLUSIVE — the
    # zero-margin case that Increment 10 correctly refuses, and that must not regress.
    proof_2line = prove_bites_fn(rev_bites, TWO_LINE_SOURCE, planted_rule="planted-rule",
                                 clean_source=TWO_LINE_TWIN)
    if proof_2line.status != "INCONCLUSIVE":
        print(
            f"FAIL ARM-4/4j4: 2-line source with honest twin expected INCONCLUSIVE, "
            f"got {proof_2line.status!r} "
            f"(twin_ratio={getattr(proof_2line, 'twin_ratio', 'N/A'):.4f}, "
            f"baseline={getattr(proof_2line, 'twin_ratio_baseline', 'N/A'):.4f})"
        )
        return False
    if proof_2line.may_trust_clean() is not False:
        print(
            f"FAIL ARM-4/4j4: 2-line honest twin has "
            f"may_trust_clean()=={proof_2line.may_trust_clean()!r}; expected False"
        )
        return False
    print(
        f"  ARM-4/4j4: 2-line source + honest twin -> status={proof_2line.status}, "
        f"twin_ratio={getattr(proof_2line, 'twin_ratio', 'N/A'):.4f}, "
        f"baseline={getattr(proof_2line, 'twin_ratio_baseline', 'N/A'):.4f} "
        f"(zero-margin case, correctly refused)"
    )

    # ------------------------------------------------------------------
    # 4k. Increment 10b — sorted source + honest twin → BITES
    #
    # The OLD sorted-copy baseline was the identity for sorted sources
    # (baseline == 1.0), making the margin test permanently unsatisfiable and
    # every sorted file a permanent INCONCLUSIVE.  The FIX (reversed baseline)
    # gives baseline < 1.0, letting an honest twin earn BITES.
    #
    # k1: baseline < 1.0 — the direct assertion that catches identity-collapse
    # k2: sorted source + honest twin → BITES  (was INCONCLUSIVE with old code)
    # ------------------------------------------------------------------
    def rev_bites_sorted(src, file):
        if "evil" in src:
            return _FakeScanResult(["planted-rule"])
        return _FakeScanResult([])

    proof_sorted = prove_bites_fn(rev_bites_sorted, SORTED_SOURCE_4K,
                                  planted_rule="planted-rule",
                                  clean_source=SORTED_TWIN_4K)
    sorted_baseline = getattr(proof_sorted, "twin_ratio_baseline", None)
    sorted_ratio    = getattr(proof_sorted, "twin_ratio", None)
    print(
        f"  ARM-4/4k: sorted source -> twin_ratio={sorted_ratio:.4f}  "
        f"baseline={sorted_baseline:.4f}  "
        f"margin={sorted_ratio - sorted_baseline:.4f}  "
        f"status={proof_sorted.status}"
    )

    # k1: baseline must be strictly less than 1.0 — the rearrangement is not
    # the identity.  This assertion catches the defect even if k2 masks it.
    if sorted_baseline is None or sorted_baseline >= 1.0:
        print(
            f"FAIL ARM-4/4k1: sorted source's baseline must be < 1.0 "
            f"(got {sorted_baseline!r}); the rearrangement is the identity "
            f"— sorted-copy rearrangement has been restored"
        )
        return False

    # k2: sorted source + honest twin → BITES
    if proof_sorted.status != "BITES":
        print(
            f"FAIL ARM-4/4k2: sorted source + honest twin expected BITES, "
            f"got {proof_sorted.status!r} "
            f"(twin_ratio={sorted_ratio:.4f}, baseline={sorted_baseline:.4f})"
        )
        return False
    if proof_sorted.may_trust_clean() is not True:
        print(
            f"FAIL ARM-4/4k2: sorted source BITES proof has "
            f"may_trust_clean()=={proof_sorted.may_trust_clean()!r}; expected True"
        )
        return False

    print("PASS ARM-4")
    return True


# ---------------------------------------------------------------------------
# ARM-5: report.py -- caps are required; verdict word is literal; ratios print
# ---------------------------------------------------------------------------

def arm5(report_path: str) -> bool:
    """ARM-5 -- report.py enforces required caps and emits correct verdict words.

    Drives main() in-process with a fake client.  No real calls, no key, no spend.

    Assertions:
      5a. Missing --max-cost     -> non-zero exit, no client call made.
      5b. Missing --per-call-ceiling -> non-zero exit, no client call made.
      5c. Fake BITES review      -> verdict word is the literal string "BITES",
                                    twin_ratio and twin_ratio_baseline both print.
      5d. No --twin              -> verdict word is the literal "INCONCLUSIVE".
    """
    import importlib.util as _ilu
    import io
    import json as _json
    import tempfile as _tmp
    import os as _os

    # Load the report module from the given path.
    spec = importlib.util.spec_from_file_location("report_arm5", report_path)
    if spec is None or spec.loader is None:
        print(f"FAIL ARM-5: cannot load report from {report_path!r}")
        return False
    try:
        report_mod = importlib.util.module_from_spec(spec)
        # Ensure the module can find its siblings via __file__.
        spec.loader.exec_module(report_mod)  # type: ignore[union-attr]
    except Exception as exc:
        print(f"FAIL ARM-5: error loading report from {report_path!r}: {exc}")
        return False

    main_fn = getattr(report_mod, "main", None)
    if main_fn is None:
        print("FAIL ARM-5: report module has no main() function")
        return False

    # A fake client that records calls.
    class _CallTracker:
        def __init__(self, responses):
            self.calls = []
            self._responses = iter(responses)

        def __call__(self, prompt: str, cap: float):
            self.calls.append((prompt, cap))
            return next(self._responses)

    # A realistic source written to a temp file.
    LARGE_SOURCE = "\n".join([
        "import os",
        "import sys",
        "def foo(x):",
        "    y = evil(x)",
        "    z = x + 1",
        "    return y + z",
        "def bar(a, b):",
        "    return a * b",
        "class Baz:",
        "    def __init__(self):",
        "        self.value = 0",
        "    def compute(self, n):",
        "        return self.value + n",
        "def main():",
        "    obj = Baz()",
        "    result = foo(obj.compute(10))",
        "    bar(result, 2)",
        "    print(result)",
        "if __name__ == '__main__':",
        "    main()",
    ]) + "\n"
    LARGE_TWIN = LARGE_SOURCE.replace("    y = evil(x)", "    y = safe(x)")

    tmp_target = _tmp.NamedTemporaryFile(mode="w", suffix=".py",
                                         delete=False, encoding="utf-8")
    tmp_target.write(LARGE_SOURCE)
    tmp_target.close()

    tmp_twin = _tmp.NamedTemporaryFile(mode="w", suffix=".py",
                                       delete=False, encoding="utf-8")
    tmp_twin.write(LARGE_TWIN)
    tmp_twin.close()

    ok = True

    def _fail(msg: str) -> None:
        nonlocal ok
        ok = False
        print(f"FAIL ARM-5: {msg}")

    try:
        old_stderr = sys.stderr
        old_stdout = sys.stdout

        # ------------------------------------------------------------------
        # 5a. Missing --max-cost -> non-zero exit, no client call
        # ------------------------------------------------------------------
        tracker_5a = _CallTracker([])
        sys.stderr = io.StringIO()
        sys.stdout = io.StringIO()
        rc_5a = main_fn(
            ["--target", tmp_target.name, "--per-call-ceiling", "1",
             "--planted", "planted-rule"],
            _client=tracker_5a,
        )
        err_5a = sys.stderr.getvalue()
        sys.stderr = old_stderr
        sys.stdout = old_stdout
        if rc_5a == 0:
            _fail(f"5a: missing --max-cost should be non-zero exit, got {rc_5a}")
        if tracker_5a.calls:
            _fail(f"5a: client was called {len(tracker_5a.calls)} time(s) despite missing cap")
        if "--max-cost" not in err_5a:
            _fail(f"5a: stderr does not name --max-cost: {err_5a!r}")
        if ok:
            print(f"  ARM-5/5a: missing --max-cost -> exit {rc_5a}, no calls, stderr names flag  PASS")

        # ------------------------------------------------------------------
        # 5b. Missing --per-call-ceiling -> non-zero exit, no client call
        # ------------------------------------------------------------------
        tracker_5b = _CallTracker([])
        sys.stderr = io.StringIO()
        sys.stdout = io.StringIO()
        rc_5b = main_fn(
            ["--target", tmp_target.name, "--max-cost", "2",
             "--planted", "planted-rule"],
            _client=tracker_5b,
        )
        err_5b = sys.stderr.getvalue()
        sys.stderr = old_stderr
        sys.stdout = old_stdout
        if rc_5b == 0:
            _fail(f"5b: missing --per-call-ceiling should be non-zero exit, got {rc_5b}")
        if tracker_5b.calls:
            _fail(f"5b: client was called {len(tracker_5b.calls)} time(s) despite missing cap")
        if "--per-call-ceiling" not in err_5b:
            _fail(f"5b: stderr does not name --per-call-ceiling: {err_5b!r}")
        if ok:
            print(f"  ARM-5/5b: missing --per-call-ceiling -> exit {rc_5b}, no calls  PASS")

        # ------------------------------------------------------------------
        # 5c. Fake BITES review -> literal "BITES" in output, both ratios print
        # ------------------------------------------------------------------
        def _bites_response(prompt, cap):
            if "evil" in prompt:
                return _json.dumps([{
                    "rule_id": "planted-rule", "severity": "high",
                    "line": 4, "title": "Evil call", "detail": "", "recommendation": "",
                }]), 0.1
            return "[]", 0.1

        tracker_5c = _CallTracker(
            [_bites_response(p, 1) for p in ["evil prompt", "safe prompt"]]
        )
        # Use a proper iterator-based client that uses the real function
        def _real_bites_client(prompt: str, cap: float) -> tuple:
            return _bites_response(prompt, cap)

        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        rc_5c = main_fn(
            ["--target", tmp_target.name, "--twin", tmp_twin.name,
             "--planted", "planted-rule",
             "--max-cost", "2", "--per-call-ceiling", "1"],
            _client=_real_bites_client,
        )
        out_5c = sys.stdout.getvalue()
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        if rc_5c != 0:
            _fail(f"5c: expected exit 0, got {rc_5c}")
        if "BITES" not in out_5c:
            _fail(f"5c: literal 'BITES' not found in output")
        if "twin_ratio" not in out_5c:
            _fail(f"5c: 'twin_ratio' not printed")
        if "twin_ratio_baseline" not in out_5c:
            _fail(f"5c: 'twin_ratio_baseline' not printed")
        if ok:
            print(f"  ARM-5/5c: BITES verdict present, both ratios printed  PASS")

        # ------------------------------------------------------------------
        # 5d. No --twin -> literal "INCONCLUSIVE" in output
        # ------------------------------------------------------------------
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        rc_5d = main_fn(
            ["--target", tmp_target.name,
             "--planted", "planted-rule",
             "--max-cost", "2", "--per-call-ceiling", "1"],
            _client=_real_bites_client,
        )
        out_5d = sys.stdout.getvalue()
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        if rc_5d != 0:
            _fail(f"5d: expected exit 0, got {rc_5d}")
        if "INCONCLUSIVE" not in out_5d:
            _fail(f"5d: literal 'INCONCLUSIVE' not found in output")
        if ok:
            print(f"  ARM-5/5d: INCONCLUSIVE verdict present  PASS")

    finally:
        sys.stderr = old_stderr
        sys.stdout = old_stdout
        _os.unlink(tmp_target.name)
        _os.unlink(tmp_twin.name)

    if ok:
        print("PASS ARM-5")
    return ok


# ---------------------------------------------------------------------------
# ARM-6: the CLI ENTRYPOINT, invoked as a real process
# ---------------------------------------------------------------------------
# ARM-5 drives main() in-process. That cannot see whether __main__ routes to main()
# AT ALL -- and it did not: __main__ WAS the self-test, so every argument list
# silently ran the self-test and exited 0, including an unknown flag. A green arm
# over an unreachable CLI. An arm whose subject is the function is blind to the
# entrypoint; this one runs the file the way a user does.

def arm6(report_path: str) -> bool:
    """ARM-6 — the entrypoint refuses a missing/unknown argument, as a subprocess."""
    import subprocess

    ok = True
    cases = [
        ("no caps",          ["--target", report_path]),
        ("no per-call-ceil", ["--target", report_path, "--max-cost", "2"]),
        ("unknown flag",     ["--bogus-flag"]),
    ]
    for label, args in cases:
        p = subprocess.run([sys.executable, report_path] + args,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if p.returncode == 0:
            print(f"FAIL ARM-6 [{label}]: exit 0 - the entrypoint did not refuse")
            ok = False
        elif "SELFTEST GREEN" in (p.stdout or ""):
            print(f"FAIL ARM-6 [{label}]: ran the SELF-TEST instead of refusing")
            ok = False
    if ok:
        print("PASS ARM-6")
    return ok


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <path>", file=sys.stderr)
        sys.exit(2)

    try:
        findings_path, chunk_path, review_path, prove_bites_path, report_path = _resolve(sys.argv[1])
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    # Manifest + contamination check (Part A, Increment 8).
    # Only runs when the argument is a directory; a single-file argument bypasses it.
    subject_arg = os.path.abspath(sys.argv[1])
    if os.path.isdir(subject_arg):
        if not _check_manifest(subject_arg):
            sys.exit(1)
        print()  # blank line between manifest and arm output

    results = [
        arm1(findings_path),
        arm2(chunk_path),
        arm3(review_path),
        arm4(prove_bites_path),
        arm5(report_path),
        arm6(report_path),
    ]

    sys.exit(0 if all(results) else 1)
