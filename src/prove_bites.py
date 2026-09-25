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
``clean_source`` using SequenceMatcher.

MARGIN TEST — no constant
--------------------------
The twin is a usable control only if it is **measurably closer** to the source
than a self-generated baseline is.  The baseline is the SequenceMatcher ratio
between ``source`` and a **deterministic shuffle of its own lines**.  It is
computed entirely from the inputs, requires no calibration, and re-runs
reproducibly.

Two properties are required of the rearrangement.  The second is easy to miss:

1. **NO FIXED POINTS** — the rearrangement must not be able to equal the source's
   own order.  An earlier form compared the source against its own lines sorted
   ascending: the identity for an already-ascending file, baseline 1.0, margin
   permanently unsatisfiable, every reviewer refused.  The next form used
   reverse-sort, which is the identity for a DESCENDING file — the same failure,
   relocated one notch over.  **Every fixed permutation has inputs it maps to
   themselves.**  So the shuffle is generated and then VERIFIED non-identity, with
   reversal and rotation as checked fallbacks, and 1.0 (fail closed) only when
   every line is identical and there is no order to perturb.
2. **DISCRIMINATION, NOT WIDTH** — the baseline must sit high enough that a twin
   which is not a near-copy fails to clear it.  A reversal is maximally
   dissimilar (~0.03), which reads as a wide margin and is in fact a permissive
   one: an unrelated file sharing a single line clears it and is then accepted as
   a usable control.  A shuffle holds the multiset of lines fixed, giving ~0.3 —
   above an unrelated file, below a genuine near-copy at 0.95+.

    twin_ratio > twin_ratio_baseline  →  margin exists, control is usable
    twin_ratio ≤ twin_ratio_baseline  →  INCONCLUSIVE; the twin cannot be
                                         distinguished from coincidence

Both values are exposed on ``BiteProof`` and printed in every diagnostic so the
separation is auditable from the transcript alone.

⚠ A fixed floor has been deliberately removed.  There is nothing to tune.

``twin_hunks`` counts how many groups of differing lines exist between
``source`` and ``clean_source``.  It is exposed for informational purposes.
If the twin differs by more than the planted hunk the verdict is
unattributable — the module measures every other difference too.  The module
does **not** change the verdict on this; it exposes the count.

Standard library only.  No network calls, no third-party dependencies.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
import random
from difflib import SequenceMatcher
from typing import Callable


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BiteProof:
    """Result of a discrimination proof.

    ``status``               — "BITES" | "DOES_NOT_BITE" | "INCONCLUSIVE"
    ``planted_rule``         — the rule_id under test
    ``found_rule_ids``       — rule_ids reported on *source* (the flawed file)
    ``twin_rule_ids``        — rule_ids reported on *clean_source* (the twin)
    ``twin_hunks``           — number of groups of differing lines between source
                               and clean_source (-1 when no twin was supplied).
                               Exposed for informational purposes; not the
                               degeneracy guard (see module docstring).
    ``twin_ratio``           — SequenceMatcher line-similarity between source and
                               clean_source (0.0 ... 1.0; -1.0 when no twin).
    ``twin_ratio_baseline``  — self-generated baseline: SequenceMatcher ratio of
                               source against its own lines in reverse-sorted order
                               (sorted(lines, reverse=True)).
                               The twin is only usable when twin_ratio > baseline.
                               baseline < 1.0 for any source not already in
                               descending order with 2+ distinct lines, because
                               ascending and descending orderings differ.
                               (-1.0 when no twin was supplied.)
    ``twin_lines_kept``      — number of matching lines between source and twin
                               (-1 when no twin).
    ``reason``               — human-readable explanation (populated on
                               DOES_NOT_BITE and INCONCLUSIVE)
    """

    status: str                        # "BITES" | "DOES_NOT_BITE" | "INCONCLUSIVE"
    planted_rule: str
    found_rule_ids: tuple[str, ...]    # rule_ids reported on the SOURCE
    twin_rule_ids: tuple[str, ...]     # rule_ids reported on the TWIN
    twin_hunks: int = -1               # how many line groups differ between source and twin
    twin_ratio: float = -1.0           # SequenceMatcher line-similarity (-1.0 if no twin)
    twin_ratio_baseline: float = -1.0  # self-generated baseline (-1.0 if no twin)
    twin_lines_kept: int = -1          # matching lines between source and twin (-1 if no twin)
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

def _compute_baseline(source: str) -> float:
    """Return the self-generated baseline for *source*.

    The baseline is the SequenceMatcher ratio of *source* against a copy of its
    own lines in REVERSED order.  It is deterministic, derived entirely from the
    input, and requires no constant.

    The property that matters is NOT which rearrangement is chosen -- it is that
    the rearrangement has NO FIXED POINTS.  Every fixed permutation has inputs it
    maps to themselves: an ascending sort is the identity for ascending input, a
    descending sort is the identity for descending input, a reversal is the
    identity for a palindrome.  A baseline of 1.0 then makes ``twin_ratio >
    baseline`` unsatisfiable and the module refuses every reviewer permanently,
    including a perfect one.

    So: reverse, and if the reversal IS the identity (a palindromic line list),
    rotate by one instead.  An input survives both only when every line is
    identical, in which case there is no order to perturb and the margin cannot
    be established at all -- reported as 1.0, which fails closed.

    Why a shuffle and not a reversal: the baseline must DISCRIMINATE, not merely
    sit low. A reversal of an ordered file is maximally dissimilar (ratio ~0.03),
    which sounds like a wide margin but is a permissive one -- an unrelated twin
    sharing a single line clears it and is then accepted as a usable control. A
    shuffle holds the multiset of lines fixed and reorders it, giving a baseline
    high enough (~0.3) that an unrelated file does not clear it while a genuine
    near-copy (0.95+) does. Reversal is kept as a fallback, not as the primary.
    """
    src_lines = source.splitlines()
    if len(src_lines) < 2:
        return 1.0

    # Generate, then VERIFY the rearrangement is not the identity, falling back
    # deterministically. Rotation is NOT used as the primary fallback: a rotation
    # leaves an (n-1)-line matching block, so its similarity stays high and a
    # legitimate twin would not clear it.
    rearranged = list(src_lines)
    random.Random(0).shuffle(rearranged)              # deterministic shuffle
    if rearranged == src_lines:                       # collision, or one line
        rearranged = list(reversed(src_lines))
    if rearranged == src_lines:                       # palindromic
        rearranged = src_lines[1:] + src_lines[:1]    # rotate by one
    if rearranged == src_lines:                       # every line identical
        return 1.0                                    # no order to perturb: fail closed

    return SequenceMatcher(None, src_lines, rearranged, autojunk=False).ratio()


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

_RULE_SEPARATORS = re.compile(r"[\s._\-]+")


def _canon_rule_id(rule: str) -> str:
    """Canonicalise a rule_id for comparison.

    THE REVIEWER OWNS ITS rule_id NAMESPACE, and it does not have to agree with
    ours. This is not speculation -- IBM Bob named the gap himself, in this
    project's own review session (`docs/armA.out.txt`, 2026-09-25):

        "A probe can carry a SQL-injection defect but the agent could detect it
         under a different `rule_id` (e.g. `"sqli"` vs `"sql-injection"`),
         causing a false `CAPABILITY_UNVERIFIED`. ... The spec needs to define
         how `rule_id` values are canonicalized or who owns the namespace."

    An exact string compare therefore makes a CORRECT reviewer score
    DOES_NOT_BITE -- a false negative on the one axis this module exists to
    measure, which is worse than no proof at all, because it is a proof that
    lies in the accusing direction.

    So we compare CANONICAL forms: case, surrounding whitespace, and the
    `-` `_` `.` separators are folded away, so `sql-injection`,
    `sql_injection`, `Sql Injection` and `SQL.INJECTION` are one rule.

    It deliberately does NOT substring-match: `foo` must not match `foobar(`.
    A substring test can confirm a rule that was never reported, which would
    make this proof vacuous in precisely the way it was built to detect. The
    comparison stays EXACT; only the spelling is folded.
    """
    return _RULE_SEPARATORS.sub("", str(rule).strip().casefold())


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
        ``twin_ratio``, ``twin_ratio_baseline``, and ``twin_lines_kept`` are
        -1.0 / -1 when ``clean_source`` is None.
        When ``twin_ratio <= twin_ratio_baseline`` the function returns
        ``INCONCLUSIVE`` — the twin is not measurably closer to the source
        than a shuffled copy of the source itself, so it is not a usable
        control.  Both values are included in ``reason`` so the margin (or
        lack of it) is visible without looking at the code.
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
            twin_ratio_baseline=-1.0,
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
            twin_ratio_baseline=-1.0,
            twin_lines_kept=-1,
            reason="clean_source was not supplied; a one-sided proof cannot establish discrimination",
        )

    # --- Compute twin similarity metrics and self-generated baseline ---
    ratio, lines_kept, twin_hunks = _compute_twin_stats(source, clean_source)
    baseline = _compute_baseline(source)

    # 🔒 Enforce twin integrity INSIDE this function via the margin test.
    # The twin is a usable control ONLY if it is measurably closer to the
    # source than the self-generated baseline is.  The baseline (source vs
    # its own lines in reverse-sorted order) requires no constant and is
    # derived entirely from the inputs.  A twin that does not beat the
    # baseline is indistinguishable from a reverse-sorted copy of the source
    # and cannot establish discrimination.
    # Both values appear in reason so the margin is auditable from the output.
    if ratio <= baseline:
        return BiteProof(
            status="INCONCLUSIVE",
            planted_rule=planted_rule,
            found_rule_ids=found_rule_ids,
            twin_rule_ids=(),
            twin_hunks=twin_hunks,
            twin_ratio=ratio,
            twin_ratio_baseline=baseline,
            twin_lines_kept=lines_kept,
            reason=(
                f"twin is not a usable control: twin_ratio={ratio:.4f} does not exceed "
                f"baseline={baseline:.4f} (margin={ratio - baseline:.4f}); "
                f"the twin cannot be distinguished from a reverse-sorted copy of the source"
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
            twin_ratio_baseline=baseline,
            twin_lines_kept=lines_kept,
            reason=reason,
        )

    twin_findings = getattr(twin_result, "findings", []) or []
    twin_rule_ids = tuple(f.rule_id for f in twin_findings)

    # --- Determine verdict ---
    # Canonical membership, NOT exact string equality -- the reviewer spells its
    # own rule_id namespace (see _canon_rule_id). An exact compare turns a
    # correct reviewer that says "sql_injection" into a false DOES_NOT_BITE.
    canon_planted  = _canon_rule_id(planted_rule)
    rule_on_source = canon_planted in {_canon_rule_id(r) for r in found_rule_ids}
    rule_on_twin   = canon_planted in {_canon_rule_id(r) for r in twin_rule_ids}

    if rule_on_source and not rule_on_twin:
        return BiteProof(
            status="BITES",
            planted_rule=planted_rule,
            found_rule_ids=found_rule_ids,
            twin_rule_ids=twin_rule_ids,
            twin_hunks=twin_hunks,
            twin_ratio=ratio,
            twin_ratio_baseline=baseline,
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
            twin_ratio_baseline=baseline,
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
        twin_ratio_baseline=baseline,
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

    # A realistic "large" source (20 lines) — honest twin differs by one line
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

    # A 2-line source — the zero-margin case from Increment 9
    TWO_LINE_SOURCE = "x = 1\ny = evil(x)\n"
    TWO_LINE_TWIN   = "x = 1\ny = safe(x)\n"

    # Increment 10b: a SORTED source — lines already in lexicographic order.
    # With the old sorted-copy baseline this gave baseline==1.0 (identity),
    # making the margin test permanently unsatisfiable → INCONCLUSIVE even for
    # an honest twin.  With the reversed baseline that cannot happen.
    SORTED_SOURCE = "\n".join([
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
    # Verify the fixture is actually sorted (so the test is meaningful).
    assert SORTED_SOURCE.splitlines() == sorted(SORTED_SOURCE.splitlines()), \
        "SORTED_SOURCE fixture is not in sorted order — fix the fixture"
    SORTED_TWIN = SORTED_SOURCE.replace("        return evil(self.x)",
                                        "        return safe(self.x)")

    # The SAME lines in DESCENDING order. An ascending sort is not the identity
    # for this file; a REVERSE sort is. This fixture is the regression guard for
    # the failure that shipped when the baseline used reverse-sort: baseline
    # collapsed to 1.0 and every reviewer was refused permanently.
    DESCENDING_SOURCE = "\n".join(reversed(SORTED_SOURCE.splitlines()))
    DESCENDING_TWIN = DESCENDING_SOURCE.replace("        return evil(self.x)",
                                                "        return safe(self.x)")

    # Same lines as SORTED_SOURCE but in shuffled (non-sorted) order —
    # concrete Python structure that happens to be in unsorted line order.
    SHUFFLED_SOURCE = "\n".join([
        "class Foo:",
        "    def bar(self):",
        "        return evil(self.x)",
        "    def baz(self):",
        "        return self.x + 1",
        "def main():",
        "    foo = Foo()",
        "    foo.bar()",
        "    foo.baz()",
        "import os",
        "import sys",
    ]) + "\n"
    SHUFFLED_TWIN = SHUFFLED_SOURCE.replace("        return evil(self.x)",
                                            "        return safe(self.x)")

    # Degenerate twins
    EMPTY_TWIN    = ""
    UNRELATED_TWIN = "import os\nprint(42)\n"

    # ------------------------------------------------------------------
    # Print the measured ratios and baselines so the margin is visible
    # ------------------------------------------------------------------
    ratio_large  , _, _ = _compute_twin_stats(LARGE_SOURCE, LARGE_TWIN)
    baseline_large       = _compute_baseline(LARGE_SOURCE)
    ratio_2line  , _, _ = _compute_twin_stats(TWO_LINE_SOURCE, TWO_LINE_TWIN)
    baseline_2line       = _compute_baseline(TWO_LINE_SOURCE)
    ratio_sorted , _, _ = _compute_twin_stats(SORTED_SOURCE, SORTED_TWIN)
    baseline_sorted      = _compute_baseline(SORTED_SOURCE)
    ratio_shuffled,_, _ = _compute_twin_stats(SHUFFLED_SOURCE, SHUFFLED_TWIN)
    baseline_shuffled    = _compute_baseline(SHUFFLED_SOURCE)
    ratio_empty  , _, _ = _compute_twin_stats(LARGE_SOURCE, EMPTY_TWIN)
    ratio_unrelated, _, _ = _compute_twin_stats(LARGE_SOURCE, UNRELATED_TWIN)

    print("=== twin_ratio measurements and baselines ===")
    print(f"  large source   — honest twin:    twin_ratio={ratio_large:.4f}  "
          f"baseline={baseline_large:.4f}  margin={ratio_large - baseline_large:.4f}")
    print(f"  sorted source  — honest twin:    twin_ratio={ratio_sorted:.4f}  "
          f"baseline={baseline_sorted:.4f}  margin={ratio_sorted - baseline_sorted:.4f}  "
          f"(baseline MUST be < 1.0)")
    print(f"  shuffled src   — honest twin:    twin_ratio={ratio_shuffled:.4f}  "
          f"baseline={baseline_shuffled:.4f}  margin={ratio_shuffled - baseline_shuffled:.4f}")
    print(f"  2-line source  — honest twin:    twin_ratio={ratio_2line:.4f}  "
          f"baseline={baseline_2line:.4f}  margin={ratio_2line - baseline_2line:.4f}")
    print(f"  large source   — empty twin:     twin_ratio={ratio_empty:.4f}  "
          f"baseline={baseline_large:.4f}")
    print(f"  large source   — unrelated twin: twin_ratio={ratio_unrelated:.4f}  "
          f"baseline={baseline_large:.4f}")
    print()

    # ------------------------------------------------------------------
    # Reviewers
    # ------------------------------------------------------------------
    def rev_bites_large(src, file):
        if "evil" in src:
            return _FakeScanResult(["planted-rule", "other-rule"])
        return _FakeScanResult(["other-rule"])

    def rev_bites_2line(src, file):
        if "evil" in src:
            return _FakeScanResult(["planted-rule"])
        return _FakeScanResult([])

    # ------------------------------------------------------------------
    # T1. 2-line source with honest twin → INCONCLUSIVE (zero-margin case)
    # ------------------------------------------------------------------
    print("--- T1: 2-line source, honest twin ---")
    proof_2line = prove_bites(rev_bites_2line, TWO_LINE_SOURCE,
                              planted_rule="planted-rule", clean_source=TWO_LINE_TWIN)
    print(f"  twin_ratio={proof_2line.twin_ratio:.4f}  "
          f"baseline={proof_2line.twin_ratio_baseline:.4f}  "
          f"margin={proof_2line.twin_ratio - proof_2line.twin_ratio_baseline:.4f}  "
          f"status={proof_2line.status}")
    check("T1: 2-line honest twin -> INCONCLUSIVE",
          proof_2line.status == "INCONCLUSIVE")
    check("T1: may_trust_clean() is False",
          proof_2line.may_trust_clean() is False)
    check("T5b: DESCENDING source baseline < 1.0 (the reverse-sort fixed point)",
          _compute_baseline(DESCENDING_SOURCE) < 1.0)
    check("T1: twin_ratio_baseline exposed",
          proof_2line.twin_ratio_baseline >= 0.0)
    print()

    # ------------------------------------------------------------------
    # R1. The planted rule is matched CANONICALLY, not literally.
    #
    # One-axis control over rev_bites_large, which BITES on
    # LARGE_SOURCE/LARGE_TWIN in T2: the ONLY thing that changes is the
    # SPELLING of the planted rule id.
    # ------------------------------------------------------------------
    print("--- R1: rule_id spelling variants ---")

    def rev_bites_variant(src, file):
        # Same defect, same capability, same findings -- the id is spelled the
        # way ANOTHER tool spells it (our "planted-rule" vs its "Planted_Rule").
        # Bob's armA session named this exact hazard.
        if "evil" in src:
            return _FakeScanResult(["Planted_Rule", "other-rule"])
        return _FakeScanResult(["other-rule"])

    def rev_bites_superstring(src, file):
        # A DIFFERENT, longer rule id. This must NOT earn BITES: accepting it
        # would be a substring match, which this module exists to refuse.
        if "evil" in src:
            return _FakeScanResult(["planted-rule-extended"])
        return _FakeScanResult([])

    check("R1: separator/case variants canonicalise to ONE rule",
          len({_canon_rule_id("sql-injection"), _canon_rule_id("sql_injection"),
               _canon_rule_id("Sql Injection"), _canon_rule_id("SQL.INJECTION")}) == 1)
    check("R1: canonical form is NOT a substring match",
          _canon_rule_id("foo") != _canon_rule_id("foobar")
          and _canon_rule_id("injection") != _canon_rule_id("sql-injection"))

    proof_variant = prove_bites(rev_bites_variant, LARGE_SOURCE,
                                planted_rule="planted-rule", clean_source=LARGE_TWIN)
    print(f"  variant spelling: status={proof_variant.status}  "
          f"found={proof_variant.found_rule_ids}")
    check("R1: differently-spelled rule_id still BITES (no false DOES_NOT_BITE)",
          proof_variant.status == "BITES")

    proof_super = prove_bites(rev_bites_superstring, LARGE_SOURCE,
                              planted_rule="planted-rule", clean_source=LARGE_TWIN)
    print(f"  superstring id  : status={proof_super.status}  "
          f"found={proof_super.found_rule_ids}")
    check("R1: a longer/different rule_id does NOT earn BITES",
          proof_super.status == "DOES_NOT_BITE")
    print()

    # ------------------------------------------------------------------
    # T2. Large source with honest twin → still BITES, both ratios printed
    # ------------------------------------------------------------------
    print("--- T2: large source, honest twin ---")
    proof_large = prove_bites(rev_bites_large, LARGE_SOURCE,
                              planted_rule="planted-rule", clean_source=LARGE_TWIN)
    print(f"  twin_ratio={proof_large.twin_ratio:.4f}  "
          f"baseline={proof_large.twin_ratio_baseline:.4f}  "
          f"margin={proof_large.twin_ratio - proof_large.twin_ratio_baseline:.4f}  "
          f"status={proof_large.status}")
    check("T2: large honest twin -> BITES",
          proof_large.status == "BITES")
    check("T2: may_trust_clean() is True",
          proof_large.may_trust_clean() is True)
    check("T2: twin_ratio > baseline (margin exists)",
          proof_large.twin_ratio > proof_large.twin_ratio_baseline)
    print()

    # ------------------------------------------------------------------
    # T3. Empty-string twin → INCONCLUSIVE
    # ------------------------------------------------------------------
    print("--- T3: empty-string twin ---")
    proof_empty = prove_bites(rev_bites_large, LARGE_SOURCE,
                              planted_rule="planted-rule", clean_source=EMPTY_TWIN)
    print(f"  twin_ratio={proof_empty.twin_ratio:.4f}  "
          f"baseline={proof_empty.twin_ratio_baseline:.4f}  "
          f"status={proof_empty.status}")
    check("T3: empty twin -> INCONCLUSIVE",
          proof_empty.status == "INCONCLUSIVE")
    check("T3: may_trust_clean() is False",
          proof_empty.may_trust_clean() is False)
    print()

    # ------------------------------------------------------------------
    # T4. Unrelated-file twin → INCONCLUSIVE
    # ------------------------------------------------------------------
    print("--- T4: unrelated-file twin ---")
    proof_unrel = prove_bites(rev_bites_large, LARGE_SOURCE,
                              planted_rule="planted-rule", clean_source=UNRELATED_TWIN)
    print(f"  twin_ratio={proof_unrel.twin_ratio:.4f}  "
          f"baseline={proof_unrel.twin_ratio_baseline:.4f}  "
          f"status={proof_unrel.status}")
    check("T4: unrelated twin -> INCONCLUSIVE",
          proof_unrel.status == "INCONCLUSIVE")
    check("T4: may_trust_clean() is False",
          proof_unrel.may_trust_clean() is False)
    print()

    # ------------------------------------------------------------------
    # T5. File-length discriminator → still must NOT earn BITES
    # ------------------------------------------------------------------
    print("--- T5: file-length discriminator + empty twin ---")
    def rev_length_discriminator(src, file):
        if len(src.splitlines()) > 2:
            return _FakeScanResult(["planted-rule"])
        return _FakeScanResult([])

    proof_len = prove_bites(rev_length_discriminator, LARGE_SOURCE,
                            planted_rule="planted-rule", clean_source=EMPTY_TWIN)
    print(f"  twin_ratio={proof_len.twin_ratio:.4f}  "
          f"baseline={proof_len.twin_ratio_baseline:.4f}  "
          f"status={proof_len.status}")
    check("T5: length-discriminator + empty twin -> NOT BITES",
          proof_len.status != "BITES")
    check("T5: may_trust_clean() is False",
          proof_len.may_trust_clean() is False)
    print()

    # ------------------------------------------------------------------
    # T6. Increment 10b — sorted source + honest twin → BITES
    #     (Was INCONCLUSIVE with the old sorted-copy baseline because
    #     sorted(lines)==lines ⟹ baseline==1.0.  With reversed baseline,
    #     baseline < 1.0 and the honest twin beats it.)
    # ------------------------------------------------------------------
    print("--- T6: SORTED source + honest twin (Increment 10b regression) ---")
    def rev_bites_sorted(src, file):
        if "evil" in src:
            return _FakeScanResult(["planted-rule"])
        return _FakeScanResult([])

    proof_sorted = prove_bites(rev_bites_sorted, SORTED_SOURCE,
                               planted_rule="planted-rule", clean_source=SORTED_TWIN)
    print(f"  twin_ratio={proof_sorted.twin_ratio:.4f}  "
          f"baseline={proof_sorted.twin_ratio_baseline:.4f}  "
          f"margin={proof_sorted.twin_ratio - proof_sorted.twin_ratio_baseline:.4f}  "
          f"status={proof_sorted.status}")
    check("T6: sorted source's baseline < 1.0 (rearrangement is not identity)",
          proof_sorted.twin_ratio_baseline < 1.0)
    check("T6: sorted source + honest twin -> BITES",
          proof_sorted.status == "BITES")
    check("T6: may_trust_clean() is True",
          proof_sorted.may_trust_clean() is True)
    print()

    # ------------------------------------------------------------------
    # T7. Increment 10b — shuffled-order source + honest twin → BITES
    # ------------------------------------------------------------------
    print("--- T7: SHUFFLED source + honest twin (Increment 10b regression) ---")
    def rev_bites_shuffled(src, file):
        if "evil" in src:
            return _FakeScanResult(["planted-rule"])
        return _FakeScanResult([])

    proof_shuffled = prove_bites(rev_bites_shuffled, SHUFFLED_SOURCE,
                                 planted_rule="planted-rule", clean_source=SHUFFLED_TWIN)
    print(f"  twin_ratio={proof_shuffled.twin_ratio:.4f}  "
          f"baseline={proof_shuffled.twin_ratio_baseline:.4f}  "
          f"margin={proof_shuffled.twin_ratio - proof_shuffled.twin_ratio_baseline:.4f}  "
          f"status={proof_shuffled.status}")
    check("T7: shuffled source + honest twin -> BITES",
          proof_shuffled.status == "BITES")
    check("T7: may_trust_clean() is True",
          proof_shuffled.may_trust_clean() is True)
    print()

    # ------------------------------------------------------------------
    # Regression checks (using LARGE_SOURCE/LARGE_TWIN)
    # ------------------------------------------------------------------
    def rev_bites_reg(src, file):
        if "evil" in src:
            return _FakeScanResult(["planted-rule", "other-rule"])
        return _FakeScanResult(["other-rule"])

    proof = prove_bites(rev_bites_reg, LARGE_SOURCE, planted_rule="planted-rule",
                        clean_source=LARGE_TWIN)
    check("BITES: status == 'BITES'",               proof.status == "BITES")
    check("BITES: bites() is True",                 proof.bites() is True)
    check("BITES: may_trust_clean() is True",        proof.may_trust_clean() is True)
    check("BITES: twin_hunks == 1",                  proof.twin_hunks == 1)
    print(f"  twin_ratio={proof.twin_ratio:.4f}  "
          f"baseline={proof.twin_ratio_baseline:.4f}  "
          f"margin={proof.twin_ratio - proof.twin_ratio_baseline:.4f}")

    def rev_both_reg(src, file):
        return _FakeScanResult(["planted-rule"])

    proof2 = prove_bites(rev_both_reg, LARGE_SOURCE, planted_rule="planted-rule",
                         clean_source=LARGE_TWIN)
    check("BOTH: status == 'DOES_NOT_BITE'",         proof2.status == "DOES_NOT_BITE")
    check("BOTH: may_trust_clean() is False",         proof2.may_trust_clean() is False)
    check("BOTH: reason mentions 'not discriminated'", "not discriminated" in proof2.reason)

    def rev_other_reg(src, file):
        return _FakeScanResult(["other-rule"])

    proof3 = prove_bites(rev_other_reg, LARGE_SOURCE, planted_rule="planted-rule",
                         clean_source=LARGE_TWIN)
    check("OTHER: status == 'DOES_NOT_BITE'",        proof3.status == "DOES_NOT_BITE")
    check("OTHER: may_trust_clean() is False",        proof3.may_trust_clean() is False)

    def rev_silent_reg(src, file):
        return _FakeScanResult([])

    proof4 = prove_bites(rev_silent_reg, LARGE_SOURCE, planted_rule="planted-rule",
                         clean_source=LARGE_TWIN)
    check("SILENT: status == 'DOES_NOT_BITE'",       proof4.status == "DOES_NOT_BITE")
    check("SILENT: may_trust_clean() is False",       proof4.may_trust_clean() is False)

    proof5 = prove_bites(rev_bites_reg, LARGE_SOURCE, planted_rule="planted-rule",
                         clean_source=None)
    check("NO TWIN: status == 'INCONCLUSIVE'",       proof5.status == "INCONCLUSIVE")
    check("NO TWIN: may_trust_clean() is False",      proof5.may_trust_clean() is False)
    check("NO TWIN: twin_hunks == -1",               proof5.twin_hunks == -1)

    def rev_truncated_reg(src, file):
        return _FakeScanResult(["planted-rule"], truncated=True)

    proof6a = prove_bites(rev_truncated_reg, LARGE_SOURCE, planted_rule="planted-rule",
                          clean_source=LARGE_TWIN)
    check("TRUNCATED: status == 'INCONCLUSIVE'",     proof6a.status == "INCONCLUSIVE")

    def rev_error_reg(src, file):
        return _FakeScanResult(["planted-rule"], error="something went wrong")

    proof6b = prove_bites(rev_error_reg, LARGE_SOURCE, planted_rule="planted-rule",
                          clean_source=LARGE_TWIN)
    check("ERROR: status == 'INCONCLUSIVE'",         proof6b.status == "INCONCLUSIVE")

    check("twin_hunks == 1 (one-hunk diff)", proof.twin_hunks == 1)

    print()
    sys.exit(0 if failures == 0 else 1)
