"""src/prove_bites.py — discrimination proof for a security reviewer.

Establishes whether a reviewer BITES: it reports the planted rule on a flawed
source file AND stays silent about it on an otherwise identical, unflawed file
(the "twin").

The verdict is a relation between **input and output**, not a membership test on
the output alone.  A reviewer that ignores `source` entirely and always emits the
planted rule would pass a one-sided membership test; it cannot pass this one.

``clean_source`` must be supplied by the caller as a string loaded from outside
the workspace.  Nothing in this repo holds the real twin — see DISCLOSURE.md.
When ``clean_source`` is None, the verdict is ``"INCONCLUSIVE"``; a one-sided
proof cannot establish discrimination.

``twin_hunks`` counts how many groups of differing lines exist between ``source``
and ``clean_source``.  **Callers must check this value.**  If the twin differs by
more than the planted hunk the verdict is unattributable — every difference is
measured, not only the planted one.  The module exposes the count and does not
change the verdict on this; the caller is responsible for asserting it.

Standard library only.  No network calls, no third-party dependencies.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Callable


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BiteProof:
    """Result of a discrimination proof.

    ``status``         — "BITES" | "DOES_NOT_BITE" | "INCONCLUSIVE"
    ``planted_rule``   — the rule_id under test
    ``found_rule_ids`` — rule_ids reported on *source* (the flawed file)
    ``twin_rule_ids``  — rule_ids reported on *clean_source* (the twin)
    ``twin_hunks``     — number of groups of differing lines between source
                         and clean_source (-1 when no twin was supplied).
                         **Callers must check this**: if twin_hunks > 1 the
                         verdict is unattributable because the module measures
                         every difference between the pair, not only the
                         planted hunk.
    ``reason``         — human-readable explanation (populated on DOES_NOT_BITE
                         and INCONCLUSIVE)
    """

    status: str                      # "BITES" | "DOES_NOT_BITE" | "INCONCLUSIVE"
    planted_rule: str
    found_rule_ids: tuple[str, ...]   # rule_ids reported on the SOURCE
    twin_rule_ids: tuple[str, ...]    # rule_ids reported on the TWIN
    twin_hunks: int = -1              # how many line groups differ between source and twin
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
        Filename label forwarded to the reviewer.

    Returns
    -------
    BiteProof
        ``twin_hunks`` is -1 when ``clean_source`` is None.
        **Callers must check ``twin_hunks``**: if it is > 1 the planted hunk is
        not the only difference measured, and the verdict is unattributable.
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
            reason="clean_source was not supplied; a one-sided proof cannot establish discrimination",
        )

    # --- Count hunks between source and twin ---
    twin_hunks = _count_hunks(source, clean_source)

    # --- Step 2: run review on clean_source (the twin) ---
    twin_result = review(clean_source, file)

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
            reason="",
        )

    if rule_on_source and rule_on_twin:
        return BiteProof(
            status="DOES_NOT_BITE",
            planted_rule=planted_rule,
            found_rule_ids=found_rule_ids,
            twin_rule_ids=twin_rule_ids,
            twin_hunks=twin_hunks,
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
    # (already verified in case 1; add an explicit assertion here for clarity)
    check("twin_hunks == 1 (one-hunk diff)", proof.twin_hunks == 1)

    print()
    sys.exit(0 if failures == 0 else 1)
