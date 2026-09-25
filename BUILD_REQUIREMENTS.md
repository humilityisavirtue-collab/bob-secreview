# BUILD REQUIREMENTS — increment 1: the findings data model

Implement exactly this. Write the file at the path given. This is a pure module:
no network, no third-party packages, standard library only.

## Deliverable

**File:** `src/findings.py`

## Required public API — exact names and shapes

```python
SEVERITY_RANKS: dict[str, int]      # "critical"=4, "high"=3, "medium"=2, "low"=1, "info"=0

@dataclass
class Location:
    file: str
    line_start: int
    line_end: int
    symbol: str | None = None       # function/class name if applicable

@dataclass
class Finding:
    rule_id: str                    # e.g. "sql-injection", "null-deref"
    severity: str                   # one of SEVERITY_RANKS
    location: Location
    title: str = ""
    detail: str = ""
    recommendation: str = ""
    # Ordering: a list of Findings sorts MOST SEVERE FIRST.

@dataclass
class ScanResult:
    file: str
    findings: list[Finding] = field(default_factory=list)
    model_used: str = ""
    error: str | None = None
    def as_dict(self) -> dict: ...  # plain dict, JSON-serialisable
```

Also required:

```python
def validate_severity(value: str) -> str:
    """Return the normalised severity. Raise ValueError on an unknown value."""
```

## Required behaviour

1. `Location` and `Finding` must be constructible with keyword arguments and with
   positional arguments for the required fields.
2. **Sorting:** `sorted(findings)` must place the most severe first, using
   `SEVERITY_RANKS`. Ties must not raise. `sorted()` must work without a `key=`.
3. **`validate_severity`** is case-insensitive on input (`"HIGH"` → `"high"`) and
   raises `ValueError` for anything not in `SEVERITY_RANKS`. It must NOT silently
   coerce an unknown severity to `"info"` — an unknown severity is an error, and
   silently downgrading it would hide a defect in the thing that produced it.
4. **`ScanResult.as_dict()`** returns a plain `dict` (no dataclass objects left in
   it) that `json.dumps()` accepts without a custom encoder.
5. **`Finding` carries its own location.** Do not put line numbers on `Finding`
   directly; they live on `Location`.

## Self-test (required)

Include `if __name__ == "__main__":` which exercises the module and prints one
`PASS`/`FAIL` line per check, then exits with status **0 if all pass** and
**non-zero if any fails**. It must cover, at minimum: severity ordering, that an
unknown severity raises, that `as_dict()` is JSON-serialisable, and the
case-insensitive normalisation.

## Acceptance

- `python src/findings.py` exits 0.
- Importing the module requires nothing outside the standard library.
- No other file is created or modified.

## On the reviewer's output contract (context, not a task)

This module defines the shape every later part of the system conforms to. Where
this document is silent, prefer the smallest thing that satisfies it, and say in
a `# NOTE:` comment when you have had to make a judgement call.
