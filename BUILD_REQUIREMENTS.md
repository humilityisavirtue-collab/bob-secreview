# BUILD REQUIREMENTS — cumulative brief

This file is the brief for everything built in this workspace, and it is committed as the
honest record of **what was asked for**, increment by increment, in order.

**Only the increment marked ⬅ ACTIVE is your task.** Earlier increments are included as
context: they describe interfaces that already exist under `src/`, and later modules should
conform to those rather than invent their own.

---

# ⬅ ACTIVE — Increment 2: `src/chunk.py`

## Why this exists (the problem, stated plainly)

A reviewer that reads an entire file in one pass is bounded by how much source it can take
in at once. So a large file gets split into **overlapping chunks**, and each chunk is sent
for review on its own.

The consequence: **anything a chunk reports comes back with a line number relative to that
chunk.** A finding's only use to a person is its line number in the file they actually open.
So the chunker has to be able to carry a chunk-relative line back to the file.

**The failure mode this must prevent:** a mapping that is off by one, or that mishandles the
overlap, reports the **wrong line for every finding** — inside a report that otherwise looks
entirely correct. Nothing crashes. The user is simply sent to the wrong place.

## Deliverable

**File:** `src/chunk.py`

Pure module. Standard library only — no network, no third-party packages, no file I/O.

## Required public API — exact names and shapes

```python
@dataclass
class Chunk:
    text: str          # this chunk's own source text
    start_line: int    # 1-based ABSOLUTE line number of this chunk's first line in the file
    end_line: int      # 1-based ABSOLUTE line number of this chunk's last line in the file
    index: int         # 0-based position of this chunk within the file

def chunk_text(source: str, chunk_lines: int = 300, overlap_lines: int = 30) -> list[Chunk]:
    """Split source into overlapping chunks. Returns [] for empty source."""

def to_absolute(chunk: Chunk, relative_line: int) -> int:
    """Map a 1-based line number RELATIVE to `chunk` into an ABSOLUTE line number."""
```

## Required behaviour

1. **All line numbers are 1-based and absolute.** No exceptions, no 0-based anywhere in the
   public surface.
2. A chunk never contains a partial line: its boundaries fall on line boundaries of `source`.
3. **Overlap arithmetic.** If a chunk starts at absolute line `s` and spans `chunk_lines`
   lines, the next chunk starts at `s + chunk_lines - overlap_lines`. A further chunk is
   produced only while there is source left to cover.
4. `Chunk.text` must be exactly the source lines `start_line .. end_line` — the invariant is
   `chunk.text.splitlines() == source.splitlines()[start_line-1 : end_line]`.
5. `to_absolute(chunk, r)` is valid for `1 <= r <= chunk.end_line - chunk.start_line + 1`.
   Outside that range it raises `ValueError`.
6. **Argument guard:** `chunk_lines >= 1` and `0 <= overlap_lines < chunk_lines`. Anything
   else raises `ValueError`. (The guard matters: `overlap_lines >= chunk_lines` describes a
   chunker that does not advance.)
7. **Every line of a non-empty source is covered by at least one chunk.** No line may be
   skipped by the chunk boundaries.
8. **Edge cases, all required:**
   - empty source (`""`) → `[]`
   - source shorter than `chunk_lines` → exactly one chunk, covering `1 .. N`
   - final chunk shorter than `chunk_lines` → still ends on the file's last line
   - a source whose length is an exact multiple of the step → no empty trailing chunk
9. **Line-counting convention (pinned so it is not ambiguous):** line counts follow
   `str.splitlines()`. A trailing newline does **not** create an extra empty line.

## Self-test (required)

`if __name__ == "__main__":` — one `PASS`/`FAIL` line per check, exit **0 if all pass**,
**non-zero if any fails**. It must cover, at minimum: the `to_absolute` mapping, the overlap
arithmetic, the coverage property (every line covered), and each of the four edge cases in
point 8.

⚠ **Note what a test of this module can quietly fail to test.** `sorted()` over one element
performs zero comparisons; likewise a check that only ever exercises a single chunk cannot
distinguish a correct chunker from one that is off by one. **A check must be able to fail.**
Where you test arithmetic, use inputs where the correct answer is not also the trivial one.

## Acceptance

- `python src/chunk.py` exits 0.
- Importing the module requires nothing outside the standard library.
- No other file is created or modified.

---

# Increment 1: the findings data model — ✅ DONE

Delivered at `src/findings.py`. Retained below as context: it is the shape later modules
conform to. Do not rewrite it.

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
