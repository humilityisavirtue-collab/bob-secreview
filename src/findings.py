"""findings.py — security-review findings data model.

Standard library only. No third-party dependencies.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field

SEVERITY_RANKS: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "info": 0,
}


def validate_severity(value: str) -> str:
    """Return the normalised severity (lowercase). Raise ValueError on an unknown value."""
    normalised = value.lower()
    if normalised not in SEVERITY_RANKS:
        raise ValueError(
            f"Unknown severity {value!r}. Must be one of: {', '.join(SEVERITY_RANKS)}"
        )
    return normalised


@dataclass
class Location:
    file: str
    line_start: int
    line_end: int
    symbol: str | None = None  # function/class name if applicable


@dataclass(frozen=True)
class Finding:
    """A single security finding produced by a review run.

    frozen=True closes ONE door: assignment to `severity`, `rule_id`, and the
    other scalar fields after construction — because `str` is genuinely immutable,
    construction-time validation (via `__post_init__`) is the only validation
    point and cannot be bypassed by later assignment.

    Doors it does NOT close:
    - Mutation through nested mutable objects: `f.location.line_start = 999` still
      works, because `Location` is not frozen. This is a shallow freeze.
    - Hashability: `frozen=True` on a dataclass normally implies `__hash__`, but our
      custom `__eq__` (which compares only severity rank) overrides that. `Finding`
      is intentionally unhashable — do not rely on it being usable in a set or as a
      dict key without a wrapper.
    """

    rule_id: str          # e.g. "sql-injection", "null-deref"
    severity: str         # one of SEVERITY_RANKS
    location: Location
    title: str = ""
    detail: str = ""
    recommendation: str = ""

    def __post_init__(self) -> None:
        # frozen=True blocks plain assignment; bypass via object.__setattr__
        object.__setattr__(self, "severity", validate_severity(self.severity))

    # NOTE: __lt__ is implemented so that sorted() works without a key=.
    # Most severe first means a higher rank comes before a lower rank, so we
    # reverse the usual comparison (higher rank → "less than" for sort order).
    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Finding):
            return NotImplemented
        return SEVERITY_RANKS[self.severity] > SEVERITY_RANKS[other.severity]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Finding):
            return NotImplemented
        return SEVERITY_RANKS[self.severity] == SEVERITY_RANKS[other.severity]

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Finding):
            return NotImplemented
        return SEVERITY_RANKS[self.severity] >= SEVERITY_RANKS[other.severity]

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Finding):
            return NotImplemented
        return SEVERITY_RANKS[self.severity] < SEVERITY_RANKS[other.severity]

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Finding):
            return NotImplemented
        return SEVERITY_RANKS[self.severity] <= SEVERITY_RANKS[other.severity]


@dataclass
class ScanResult:
    """Aggregated result of a review run.

    Spend reporting
    ---------------
    `total_cost` records the sum of all per-call costs actually incurred during
    this run. `max_cost` records the cap that was passed to the engine.

    The honest guarantee is: **no call is started that could not be afforded, and
    the total is reported here.** We do NOT claim the cap is never exceeded in
    absolute terms — a token-billed provider cannot be pre-limited exactly; only
    the pre-call affordability check (`remaining >= per_call_ceiling`) and the
    provider's own per-call limit (forwarded as `per_call_cap`) enforce the bound.
    The mechanism is that combination; `total_cost` and `max_cost` make the outcome
    auditable after the fact.
    """

    file: str
    findings: list[Finding] = field(default_factory=list)
    model_used: str = ""
    error: str | None = None
    chunks_total: int = 0        # how many chunks the source was split into
    chunks_reviewed: int = 0     # how many were actually reviewed
    chunks_failed: int = 0       # how many chunks failed (client raised or parse error)
    truncated: bool = False      # True if the review stopped before covering the whole source
    total_cost: float = 0.0      # sum of all per-call costs incurred in this run
    max_cost: float = 0.0        # the spend cap that was passed to the engine

    def as_dict(self) -> dict:
        """Return a plain dict that json.dumps() accepts without a custom encoder."""
        return {
            "file": self.file,
            "findings": [
                {
                    "rule_id": f.rule_id,
                    "severity": f.severity,
                    "location": {
                        "file": f.location.file,
                        "line_start": f.location.line_start,
                        "line_end": f.location.line_end,
                        "symbol": f.location.symbol,
                    },
                    "title": f.title,
                    "detail": f.detail,
                    "recommendation": f.recommendation,
                }
                for f in self.findings
            ],
            "model_used": self.model_used,
            "error": self.error,
            "chunks_total": self.chunks_total,
            "chunks_reviewed": self.chunks_reviewed,
            "chunks_failed": self.chunks_failed,
            "truncated": self.truncated,
            "total_cost": self.total_cost,
            "max_cost": self.max_cost,
        }

    def may_report_clean(self) -> bool:
        """True ONLY when the whole source was reviewed with no failures."""
        return (
            self.chunks_failed == 0
            and self.chunks_reviewed + self.chunks_failed == self.chunks_total
        )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    failures = 0

    def check(name: str, condition: bool) -> None:
        global failures
        status = "PASS" if condition else "FAIL"
        if not condition:
            failures += 1
        print(f"{status}: {name}")

    # 1. Severity ordering — sorted() places most severe first without key=
    loc = Location(file="a.py", line_start=1, line_end=1)
    findings = [
        Finding(rule_id="r1", severity="low",      location=loc),
        Finding(rule_id="r2", severity="critical",  location=loc),
        Finding(rule_id="r3", severity="medium",    location=loc),
        Finding(rule_id="r4", severity="high",      location=loc),
        Finding(rule_id="r5", severity="info",      location=loc),
    ]
    ordered = sorted(findings)
    check(
        "severity ordering (critical, high, medium, low, info)",
        [f.severity for f in ordered] == ["critical", "high", "medium", "low", "info"],
    )

    # 2. Ties must not raise
    try:
        tie = sorted([
            Finding(rule_id="x", severity="high", location=loc),
            Finding(rule_id="y", severity="high", location=loc),
        ])
        check("ties do not raise", True)
    except Exception as exc:
        check(f"ties do not raise (raised {exc!r})", False)

    # 3. Unknown severity raises ValueError
    raised = False
    try:
        validate_severity("unknown_sev")
    except ValueError:
        raised = True
    check("unknown severity raises ValueError", raised)

    # 4. Case-insensitive normalisation
    check("validate_severity is case-insensitive ('HIGH' -> 'high')", validate_severity("HIGH") == "high")
    check("validate_severity is case-insensitive ('Critical' -> 'critical')", validate_severity("Critical") == "critical")

    # 5. as_dict() is JSON-serialisable
    result = ScanResult(
        file="scan_target.py",
        findings=[
            Finding(
                rule_id="sql-injection",
                severity="critical",
                location=Location(file="scan_target.py", line_start=42, line_end=44, symbol="get_user"),
                title="SQL Injection",
                detail="Unsanitised input.",
                recommendation="Use parameterised queries.",
            )
        ],
        model_used="gpt-4o",
        error=None,
    )
    try:
        serialised = json.dumps(result.as_dict())
        check("as_dict() is JSON-serialisable", isinstance(serialised, str) and len(serialised) > 0)
    except (TypeError, ValueError) as exc:
        check(f"as_dict() is JSON-serialisable (raised {exc!r})", False)

    # 6. as_dict() contains no dataclass objects
    d = result.as_dict()
    no_dataclasses = all(
        not hasattr(v, "__dataclass_fields__")
        for v in (d, d.get("findings", [{}])[0], d.get("findings", [{}])[0].get("location", {}))
    )
    check("as_dict() contains no dataclass objects", no_dataclasses)

    sys.exit(0 if failures == 0 else 1)
