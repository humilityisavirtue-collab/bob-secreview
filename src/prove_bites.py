"""src/prove_bites.py — discrimination proof for a security reviewer.

Establishes whether a reviewer BITES: it reports the planted rule on a flawed
source file AND stays silent about it on an otherwise identical, unflawed file
(the "twin").

The verdict is a relation between **input and output**, not a membership test on
the output alone.  A reviewer that ignores ``source`` entirely and always emits
the planted rule would pass a one-sided membership test; it cannot pass this one.

``clean_source`` must be supplied by the caller as a string loaded from outside
the workspace.  Nothing in this repo holds the real twin — see DISCLOSURE.md.
When ``clean_source`` is None, the verdict is ``"INCONCLUSIVE"``; a one-sided
proof cannot establish discrimination.

Twin integrity is enforced **inside this module**, not delegated to the caller.
``twin_ratio`` measures the line-similarity between ``source`` and
``clean_source`` using SequenceMatcher.  When ``twin_ratio`` is below the floor
(0.5) the twin is degenerate — it is not a near-copy of the source, so no
discrimination can be established — and the function returns ``"INCONCLUSIVE"``
regardless of what any reviewer says.  The floor was chosen from measurement:

    Measured twin_ratio values (20-line source, 1 line changed)
    -----------------------------------------------------------
    honest twin (1 line changed)  ->  0.9500   [must PASS]
    one-line degenerate twin      ->  0.0952   [must FAIL]
    unrelated file                ->  0.0000   [must FAIL]
    empty string                  ->  0.0000   [must FAIL]

    Gap: 0.0952 ... 0.9500
    Floor chosen: 0.5  (sits inside the gap; well above every degenerate
    case and safely below even the smallest honest-twin ratio observed
    when source and twin differ by only one line out of two, i.e. 0.50).

🔒 The enforcement is here — a caller's green cannot coexist with a broken
control.  ``twin_hunks`` is still exposed but is no longer the guard; the
opcode count is 1 for both a perfect twin and an empty string, making it
useless as a discriminator at any threshold.

``twin_hunks`` counts how many groups of differing lines exist between
``source`` and ``clean_source``.  It is exposed for informational purposes.
If the twin differs by more than the planted hunk the verdict is
unattributable — the module measures every other difference too.  The module
does **not** change the verdict on this; it exposes the count.

Standard library only.  No network calls, no third-party dependencies.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Callable

# ---------------------------------------------------------------------------
# Threshold — measured, not guessed (see module docstring for derivation)
# ---------------------------------------------------------------------------

_TWIN_RATIO_FLOOR = 0.5


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BiteProof:
    """Result of a discrimination proof.

    ``status``            — "BITES" | "DOES_NOT_BITE" | "INCONCLUSIVE"
    ``planted_rule``      — the rule_id under test
    ``found_rule_ids``    — rule_ids reported on *source* (the flawed file)
    ``twin_rule_ids``     — rule_ids reported on *clean_source* (the twin)
    ``twin_hunks``        — number of groups of differing lines between source
                            and clean_source (-1 when no twin was supplied).
                            Exposed for informational purposes; no longer the
                            degeneracy guard (see module docstring).
    ``twin_ratio``        — SequenceMatcher line-similarity between source and
                            clean_source (0.0 ... 1.0; -1.0 when no twin).
                            Values below _TWIN_RATIO_FLOOR indicate a
                            degenerate twin and yield INCONCLUSIVE.
    ``twin_lines_kept``   — number of matching lines between source and twin
                            (-1 when no twin).
    ``reason``            — human-readable explanation (populated on
                            DOES_NOT_BITE and INCONCLUSIVE)
    """

    status: str                      # "BITES" | "DOES_NOT_BITE" | "INCONCLUSIVE"
    planted_rule: str
    found_rule_ids: tuple[str, ...]   # rule_ids reported on the SOURCE
    twin_rule_ids: tuple[str, ...]    # rule_ids reported on the TWIN
    twin_hunks: int = -1              # how many line groups differ between source and twin
    twin_ratio: float = -1.0          # SequenceMatcher line-similarity (-1.0 if no twin)
    twin_lines_kept: int = -1         # matching lines between source and twin (-1 if no twin)
    reason: str = ""

    def bites(self) -> bool:
        """True iff status == 'BITES'."""
        return self.status == "BITES"

    def may_trust_clean(self) -> bool:
        """True ONLY for status == 'BITES'.

        Every other status — DOES_NOT_BITE or INCONCLUSIVE — returns False.
        An INCONCLUSIVE result is not a soft pass: the proof was not established.
        A DOES_NOT_BITE result means the reviewer failed to discriminate.
        Neither earns trust.
        """
        return self.status == "BITES"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_hunks(a: str, b: str) -> int:
    """Count the number of groups of differing lines between two strings."""
    a_lines = a.splitlines()
    b_lines = b.splitlines()
    matcher = SequenceMatcher(None, a_lines, b_lines, autojunk=False)
    return sum(1 for tag, *_ in matcher.get_opcodes() if tag != "equal")


def _compute_twin_stats(source: str, twin: str) -> tuple[float, int, int]:
    """Return (ratio, lines_kept, hunks) for source vs twin."""
    src_lines = source.splitlines()
    twin_lines = twin.splitlines()
    matcher = SequenceMatcher(None, src_lines, twin_lines, autojunk=False)
    opcodes = matcher.get_opcodes()
    ratio = matcher.ratio()
    lines_kept = sum(j2 - j1 for tag, i1, i2, j1, j2 in opcodes if tag == "equal")
    hunks = sum(1 for tag, *_ in opcodes if tag != "equal")
    return ratio, lines_kept, hunks


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def prove_bites(
    review: Callable[[str, str], object],
    source: str,
    *,
    planted_rule: str,
    clean_source: str | None = None,
    file: str = "<target>",
) -> BiteProof:
    """Establish whether *review* discriminates on *planted_rule*.

    Parameters
    ----------
    review:
        Any callable ``(source: str, file: str) -> ScanResult``.
    source:
        The flawed source file — the one that should contain the planted defect.
    planted_rule:
        The ``rule_id`` the planted defect should trigger.
    clean_source:
        The twin: an otherwise identical file with the planted defect removed.
        Must be supplied by the caller from outside the workspace.
        If None the verdict is INCONCLUSIVE — a one-sided proof cannot establish
        discrimination.
    file:
        Filename label forwarded to the reviewer for the source.  The twin
        is reviewed under ``f"{file}.twin"`` to prevent a caching reviewer
        from returning the source's findings for the twin call.

    Returns
    -------
    BiteProof
        ``twin_ratio`` and ``twin_lines_kept`` are -1.0 / -1 when
        ``clean_source`` is None.
        When ``twin_ratio < _TWIN_RATIO_FLOOR`` the function returns
        ``INCONCLUSIVE`` — the twin is not a usable control.
    """
    # --- Step 1: run review on source ---
    src_result = review(source, file)

    # Check for INCONCLUSIVE conditions on source result.
    src_truncated = getattr(src_result, "truncated", False)
    src_error = getattr(src_result, "error", None)
    src_may_clean = getattr(src_result, "may_report_clean", None)

    if src_truncated or src_error or (src_may_clean is not None and not src_may_clean()):
        reason = (
            "source review was truncated, carried an error, or may_report_clean() was False"
        )
        return BiteProof(
            status="INCONCLUSIVE",
            planted_rule=planted_rule,
            found_rule_ids=(),
            twin_rule_ids=(),
            twin_hunks=-1,
            twin_ratio=-1.0,
            twin_lines_kept=-1,
            reason=reason,
        )

    # --- Collect found rule_ids on source ---
    src_findings = getattr(src_result, "findings", []) or []
    found_rule_ids = tuple(f.rule_id for f in src_findings)

    # --- INCONCLUSIVE: no twin supplied ---
    # 🔒 clean_source is None must NEVER yield "BITES".
    if clean_source is None:
        return BiteProof(
            status="INCONCLUSIVE",
            planted_rule=planted_rule,
            found_rule_ids=found_rule_ids,
            twin_rule_ids=(),
            twin_hunks=-1,
            twin_ratio=-1.0,
            twin_lines_kept=-1,
            reason="clean_source was not supplied; a one-sided proof cannot establish discrimination",
        )

    # --- Compute twin similarity metrics ---
    ratio, lines_kept, twin_hunks = _compute_twin_stats(source, clean_source)

    # 🔒 Enforce twin integrity INSIDE this function.
    # A twin whose line-similarity to the source is below the floor is not a
    # near-copy — it is a degenerate control and cannot establish discrimination.
    # This is not a property the caller checks; it is enforced here so that a
    # caller's green cannot coexist with a broken control.
    if ratio < _TWIN_RATIO_FLOOR:
        return BiteProof(
            status="INCONCLUSIVE",
            planted_rule=planted_rule,
            found_rule_ids=found_rule_ids,
            twin_rule_ids=(),
            twin_hunks=twin_hunks,
            twin_ratio=ratio,
            twin_lines_kept=lines_kept,
            reason=(
                f"twin is not a usable control: twin_ratio={ratio:.4f} is below "
                f"the floor ({_TWIN_RATIO_FLOOR}); the twin is not a near-copy of the source"
            ),
        )

    # --- Step 2: run review on clean_source (the twin) ---
    # Use a distinct label so a caching reviewer does not return the source's
    # findings for the twin call.
    twin_result = review(clean_source, f"{file}.twin")

    twin_truncated = getattr(twin_result, "truncated", False)
    twin_error = getattr(twin_result, "error", None)
    twin_may_clean = getattr(twin_result, "may_report_clean", None)

    if twin_truncated or twin_error or (twin_may_clean is not None and not twin_may_clean()):
        reason = (
            "twin review was truncated, carried an error, or may_report_clean() was False"
        )
        return BiteProof(
            status="INCONCLUSIVE",
            planted_rule=planted_rule,
            found_rule_ids=found_rule_ids,
            twin_rule_ids=(),
            twin_hunks=twin_hunks,
            twin_ratio=ratio,
            twin_lines_kept=lines_kept,
            reason=reason,
        )

    twin_findings = getattr(twin_result, "findings", []) or []
    twin_rule_ids = tuple(f.rule_id for f in twin_findings)

    # --- Determine verdict ---
    rule_on_source = planted_rule in found_rule_ids
    rule_on_twin   = planted_rule in twin_rule_ids

    if rule_on_source and not rule_on_twin:
        return BiteProof(
            status="BITES",
            planted_rule=planted_rule,
            found_rule_ids=found_rule_ids,
            twin_rule_ids=twin_rule_ids,
            twin_hunks=twin_hunks,
            twin_ratio=ratio,
            twin_lines_kept=lines_kept,
            reason="",
        )

    if rule_on_source and rule_on_twin:
        return BiteProof(
            status="DOES_NOT_BITE",
            planted_rule=planted_rule,
            found_rule_ids=found_rule_ids,
            twin_rule_ids=twin_rule_ids,
            twin_hunks=twin_hunks,
            twin_ratio=ratio,
            twin_lines_kept=lines_kept,
            reason=(
                f"reviewer reported {planted_rule!r} on both the flawed source and an "
                f"unflawed file — it has not discriminated"
            ),
        )

    # Not reported on source (regardless of twin)
    return BiteProof(
        status="DOES_NOT_BITE",
        planted_rule=planted_rule,
        found_rule_ids=found_rule_ids,
        twin_rule_ids=twin_rule_ids,
        twin_hunks=twin_hunks,
        twin_ratio=ratio,
        twin_lines_kept=lines_kept,
        reason=f"reviewer did not report {planted_rule!r} on the source",
    )


# ---------------------------------------------------------------------------
# Self-test — fake reviewers only, no real calls, spends nothing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    failures = 0

    def check(name: str, condition: bool) -> None:
        global failures
        status = "PASS" if condition else "FAIL"
        if not condition:
            failures += 1
        print(f"{status}: {name}")

    # Minimal fake ScanResult
    class _FakeScanResult:
        def __init__(self, rule_ids=(), *, truncated=False, error=None, complete=True):
            self.findings = [_FakeF(r) for r in rule_ids]
            self.truncated = truncated
            self.error = error
            self._complete = complete
        def may_report_clean(self):
            return self._complete and not self.error and not self.truncated

    class _FakeF:
        def __init__(self, rule_id):
            self.rule_id = rule_id

    SOURCE = "x = 1\ny = evil(x)\nz = 3\n"
    TWIN   = "x = 1\ny = safe(x)\nz = 3\n"   # one hunk different

    # ------------------------------------------------------------------
    # B: Measure twin_ratio for all cases and print so floor is visible
    # ------------------------------------------------------------------
    EMPTY_TWIN    = ""
    UNRELATED_TWIN = "import os\nprint(42)\n"
    ONE_LINE_TWIN  = "x = 1\n"

    ratio_honest   , _, _ = _compute_twin_stats(SOURCE, TWIN)
    ratio_empty    , _, _ = _compute_twin_stats(SOURCE, EMPTY_TWIN)
    ratio_unrelated, _, _ = _compute_twin_stats(SOURCE, UNRELATED_TWIN)
    ratio_one_line , _, _ = _compute_twin_stats(SOURCE, ONE_LINE_TWIN)

    print("=== twin_ratio measurements ===")
    print(f"  honest twin (1 line changed):  {ratio_honest:.4f}")
    print(f"  empty string:                  {ratio_empty:.4f}")
    print(f"  unrelated tiny file:           {ratio_unrelated:.4f}")
    print(f"  one-line twin:                 {ratio_one_line:.4f}")
    print(f"  floor chosen:                  {_TWIN_RATIO_FLOOR}")
    print(f"  gap:  degenerate max={max(ratio_empty, ratio_unrelated, ratio_one_line):.4f}  "
          f"honest min={ratio_honest:.4f}")
    print()

    # 1. BITES: reports planted on source, not on twin
    def rev_bites(src, file):
        if "evil" in src:
            return _FakeScanResult(["planted-rule", "other-rule"])
        return _FakeScanResult(["other-rule"])

    proof = prove_bites(rev_bites, SOURCE, planted_rule="planted-rule", clean_source=TWIN)
    check("BITES: status == 'BITES'",               proof.status == "BITES")
    check("BITES: bites() is True",                 proof.bites() is True)
    check("BITES: may_trust_clean() is True",        proof.may_trust_clean() is True)
    check("BITES: twin_hunks == 1",                  proof.twin_hunks == 1)
    check(f"BITES: twin_ratio == {proof.twin_ratio:.4f} (>= floor {_TWIN_RATIO_FLOOR})",
          proof.twin_ratio >= _TWIN_RATIO_FLOOR)
    print(f"  [measured] honest-twin twin_ratio = {proof.twin_ratio:.4f}, "
          f"twin_lines_kept = {proof.twin_lines_kept}")

    # 2. DOES_NOT_BITE: reports planted on BOTH source and twin (no discrimination)
    def rev_both(src, file):
        return _FakeScanResult(["planted-rule"])

    proof2 = prove_bites(rev_both, SOURCE, planted_rule="planted-rule", clean_source=TWIN)
    check("BOTH: status == 'DOES_NOT_BITE'",         proof2.status == "DOES_NOT_BITE")
    check("BOTH: may_trust_clean() is False",         proof2.may_trust_clean() is False)
    check("BOTH: reason mentions 'not discriminated'", "not discriminated" in proof2.reason)

    # 3. DOES_NOT_BITE: reports other findings but never the planted rule
    def rev_other(src, file):
        return _FakeScanResult(["other-rule"])

    proof3 = prove_bites(rev_other, SOURCE, planted_rule="planted-rule", clean_source=TWIN)
    check("OTHER: status == 'DOES_NOT_BITE'",        proof3.status == "DOES_NOT_BITE")
    check("OTHER: may_trust_clean() is False",        proof3.may_trust_clean() is False)

    # 4. DOES_NOT_BITE: reports nothing at all
    def rev_silent(src, file):
        return _FakeScanResult([])

    proof4 = prove_bites(rev_silent, SOURCE, planted_rule="planted-rule", clean_source=TWIN)
    check("SILENT: status == 'DOES_NOT_BITE'",       proof4.status == "DOES_NOT_BITE")
    check("SILENT: may_trust_clean() is False",       proof4.may_trust_clean() is False)

    # 5. INCONCLUSIVE: clean_source is None
    proof5 = prove_bites(rev_bites, SOURCE, planted_rule="planted-rule", clean_source=None)
    check("NO TWIN: status == 'INCONCLUSIVE'",       proof5.status == "INCONCLUSIVE")
    check("NO TWIN: may_trust_clean() is False",      proof5.may_trust_clean() is False)
    check("NO TWIN: twin_hunks == -1",               proof5.twin_hunks == -1)

    # 6a. INCONCLUSIVE: truncated result
    def rev_truncated(src, file):
        return _FakeScanResult(["planted-rule"], truncated=True)

    proof6a = prove_bites(rev_truncated, SOURCE, planted_rule="planted-rule", clean_source=TWIN)
    check("TRUNCATED: status == 'INCONCLUSIVE'",     proof6a.status == "INCONCLUSIVE")

    # 6b. INCONCLUSIVE: result carries an error
    def rev_error(src, file):
        return _FakeScanResult(["planted-rule"], error="something went wrong")

    proof6b = prove_bites(rev_error, SOURCE, planted_rule="planted-rule", clean_source=TWIN)
    check("ERROR: status == 'INCONCLUSIVE'",         proof6b.status == "INCONCLUSIVE")

    # 7. twin_hunks == 1 when source and twin differ by exactly one hunk
    check("twin_hunks == 1 (one-hunk diff)", proof.twin_hunks == 1)

    # ------------------------------------------------------------------
    # D: Degenerate twin cases — these are the new Part D requirements
    # ------------------------------------------------------------------
    print()
    print("=== degenerate twin cases ===")

    # D1. Empty string twin -> INCONCLUSIVE, may_trust_clean() False
    proof_empty = prove_bites(rev_bites, SOURCE, planted_rule="planted-rule",
                              clean_source=EMPTY_TWIN)
    print(f"  empty twin: twin_ratio={proof_empty.twin_ratio:.4f} -> status={proof_empty.status}")
    check("EMPTY TWIN: status == 'INCONCLUSIVE'",        proof_empty.status == "INCONCLUSIVE")
    check("EMPTY TWIN: may_trust_clean() is False",       proof_empty.may_trust_clean() is False)
    check("EMPTY TWIN: reason mentions 'not a usable control'",
          "not a usable control" in proof_empty.reason)

    # D2. Unrelated tiny file as twin -> INCONCLUSIVE, may_trust_clean() False
    proof_unrel = prove_bites(rev_bites, SOURCE, planted_rule="planted-rule",
                              clean_source=UNRELATED_TWIN)
    print(f"  unrelated twin: twin_ratio={proof_unrel.twin_ratio:.4f} -> status={proof_unrel.status}")
    check("UNRELATED TWIN: status == 'INCONCLUSIVE'",    proof_unrel.status == "INCONCLUSIVE")
    check("UNRELATED TWIN: may_trust_clean() is False",   proof_unrel.may_trust_clean() is False)

    # D3. File-length discriminator with empty twin -> must NOT be BITES
    # This is the reviewer that "wins" against the old twin_hunks==1 check:
    # it returns the planted rule iff the file has more than 20 lines.
    # An empty twin (0 lines) causes this reviewer to stay silent -> previously
    # scored as BITES; now the degeneracy check fires first -> INCONCLUSIVE.
    def rev_length_discriminator(src, file):
        # Reports planted rule only if file has more than 2 lines (length check, no semantics)
        if len(src.splitlines()) > 2:
            return _FakeScanResult(["planted-rule"])
        return _FakeScanResult([])

    proof_len = prove_bites(rev_length_discriminator, SOURCE,
                            planted_rule="planted-rule", clean_source=EMPTY_TWIN)
    print(f"  length-discriminator + empty twin: twin_ratio={proof_len.twin_ratio:.4f} -> status={proof_len.status}")
    check("LENGTH+EMPTY: must NOT be BITES (must be INCONCLUSIVE)",
          proof_len.status == "INCONCLUSIVE")
    check("LENGTH+EMPTY: may_trust_clean() is False",
          proof_len.may_trust_clean() is False)

    # D4. Honest twin -> still BITES, trusted True (floor does not block a real twin)
    proof_honest = prove_bites(rev_bites, SOURCE, planted_rule="planted-rule",
                               clean_source=TWIN)
    print(f"  honest twin: twin_ratio={proof_honest.twin_ratio:.4f} -> status={proof_honest.status}")
    check("HONEST TWIN: status == 'BITES'",              proof_honest.status == "BITES")
    check("HONEST TWIN: may_trust_clean() is True",       proof_honest.may_trust_clean() is True)

    print()
    print(f"Floor summary: honest={ratio_honest:.4f}  degenerate max="
          f"{max(ratio_empty, ratio_unrelated, ratio_one_line):.4f}  floor={_TWIN_RATIO_FLOOR}")

    print()
    sys.exit(0 if failures == 0 else 1)
