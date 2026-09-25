# BUILD REQUIREMENTS — cumulative brief

This file is the brief for everything built in this workspace, and it is committed as the
honest record of **what was asked for**, increment by increment, in order.

**Only the increment marked ⬅ ACTIVE is your task.** Earlier increments are included as
context: they describe interfaces that already exist under `src/`, and later modules should
conform to those rather than invent their own.

Increment 4 is currently ACTIVE.

---

# ⬅ ACTIVE — Increment 4: `src/review.py`, the review engine

Chunks a source file, sends each chunk out for review, and turns what comes back into `Finding`
objects whose line numbers point at **the file the reader will actually open**.

## Deliverable A — a small additive change to `src/findings.py`

`ScanResult` gains three fields, each with a default so existing construction still works:

```python
chunks_total: int = 0        # how many chunks the source was split into
chunks_reviewed: int = 0     # how many were actually reviewed
truncated: bool = False      # True if the review stopped before covering the whole source
```

`as_dict()` must include them. **Nothing else about `findings.py` changes.**

> **Why these exist, and this is the heart of the increment.** A review that stopped early must
> be **legible as partial**. If a caller cannot tell "no findings" from "we only got through a
> third of the file", then a truncated run reads as a clean bill of health — and a result that
> *reads* correct while being unverified is the precise failure this whole project exists to
> prevent. Do not let that failure into our own engine.

## Deliverable B — `src/review.py`

```python
# A client is any callable: prompt -> (response_text, cost_in_coins)
ReviewClient = Callable[[str], tuple[str, float]]

def review_source(source: str, client: ReviewClient, *, file: str = "<memory>",
                  max_cost: float, chunk_lines: int = 300, overlap_lines: int = 30) -> ScanResult: ...

def review_file(path: str | os.PathLike, client: ReviewClient, *, max_cost: float, ...) -> ScanResult: ...
```

**`max_cost` is required and has NO default.** It is keyword-only, so omitting it is a `TypeError`
at the call site; additionally raise `ValueError` if it is `None` or `<= 0`.

> **Why it is required rather than defaulted:** every chunk is a **paid call**. A reviewer that
> silently spends is a worse failure than one that refuses to start, and it is the only failure
> here that costs money while nobody is watching. **The cap must be impossible to forget, not
> merely documented.** This is a product decision, not a build one.

### Required behaviour

1. Split the source with `chunk.py` (`chunk_text`). `chunks_total` is how many chunks come back.
2. For each chunk, build a prompt that contains the chunk's text and **states the required output
   contract explicitly** — a JSON array of finding objects. Where the contract is silent, be
   tolerant on the way in: expect the model's format to drift, strip code fences, and extract the
   first `[...]` if the response is not bare JSON.
3. Each finding comes back with a line number **relative to its chunk**. Map every one to an
   absolute line using `chunk.to_absolute`. A finding is useless to a reader at a wrong line.
4. Call `client` once per chunk. Add its returned cost to a running total **before** the next call.
   **Stop before a call that would take the total past `max_cost`** and set `truncated = True`.
   Never exceed the cap.
5. Findings from **overlapping** chunks will repeat. De-duplicate on (rule_id, absolute line,
   title) so one defect is reported once.
6. `model_used` records the client's identity if it exposes one; otherwise leave it empty.
7. **A chunk that fails — the client raises, or the response cannot be parsed — is NOT zero
   findings.** Record it. A failure must leave the result legible as incomplete; it must never
   be reported as a file with nothing wrong in it.

### Self-test (required)

`if __name__ == "__main__":` — one `PASS`/`FAIL` line per check, exit 0 only if all pass.
**Use a FAKE client. The self-test must never make a real call or spend anything.**

It must cover, at minimum: findings come back with **absolute** line numbers; a finding reported in
the overlap is de-duplicated; the budget stop sets `truncated=True` with
`chunks_reviewed < chunks_total`; and a client that raises leaves the result **not** reading as
clean.

## Deliverable C — `tests/arms.py` gains `ARM-3`

Same harness, same argv path. `ARM-3` asserts the budget-stop invariant against the `review.py`
**found at the given path**: with a fake client and a cap too small to cover the source, the result
has `truncated is True` and `chunks_reviewed < chunks_total`, and the cap was not exceeded.

## THE PROOF OBLIGATION — this time there is no pre-fix revision

`review.py` is new, so git history holds no unfixed copy of it. **An arm that has never been shown
to fail has not been proven**, so construct the known-bad subject:

1. Copy `src/review.py` to `<mutant-dir>/review.py`.
2. Remove **only** the truncation marking — the line(s) that set `truncated = True` when the budget
   stops the review. Change nothing else.
3. Run `python tests/arms.py <mutant-dir>` → **ARM-3 MUST FAIL.** If it passes, the arm is vacuous
   and the fix is unproven.
4. `python tests/arms.py src` → **all arms PASS.**

Report all four results verbatim, with exit codes, and state explicitly what you changed in the
mutant — one named change, nothing else.

⚠ **A mutant whose anchor has gone stale tests nothing.** Assert the change you made is present in
the mutant copy before you run the arm.

## Acceptance

- `python src/review.py` exits 0 and **spends nothing**
- `python src/findings.py` exits 0 · `python src/chunk.py` exits 0
- `python tests/arms.py src` exits **0**; `python tests/arms.py <mutant-dir>` exits **non-zero**
- Standard library only. New file: `tests/arms.py` is extended; `src/review.py` is new.

---

# Increment 3: two conformance fixes, each with a PROVEN can-fail arm — ✅ DONE

Two behaviours under `src/` do **not** satisfy the requirements already written for them. Find them,
fix them, and **prove the fix**. The proof is the deliverable — the fix is the easy half.

**Both failures are the same requirement, stated once:** *a stated invariant must be enforced where
the invalid state can first exist, and must be tested against an input that can actually fail it.*

## Deliverable A — `src/findings.py`

**Requirement:** an unrecognised severity must be rejected **when the object is constructed**, not
deferred to a later comparison. Today `Finding("r", "nonsense", loc)` constructs successfully and the
failure surfaces much later, at comparison time, as an error that names no requirement.

A guard that only fires at comparison time is *in the wrong place*. The invalid state must be
**unconstructible**.

## Deliverable B — `src/chunk.py`

**Requirement:** the point-4 invariant —

```python
chunk.text.splitlines() == source.splitlines()[chunk.start_line-1 : chunk.end_line]
```

— must hold for **every** input, not merely for the inputs the current self-test happens to visit.
**It currently does not.** Find an input where it breaks, fix it, and keep the fix.

## Deliverable C — `tests/arms.py` — the harness that proves it

A standalone harness. It takes **one argument: a path**, so it can be pointed at a copy of the module
that is *not* the one in `src/`.

```
python tests/arms.py <path>
```

`<path>` may be a file or a directory containing `findings.py` and `chunk.py`. The harness imports the
module(s) **from that path** and asserts:

- **ARM-1 — severity is enforced at construction.** Constructing a `Finding` with an unknown severity
  raises `ValueError`. A valid severity still constructs, and a list of two or more sorts
  most-severe-first.
- **ARM-2 — the chunk round trip.** Over several sources and argument combinations, every chunk
  satisfies the point-4 invariant above, and every line of a non-empty source is covered.

Print one `PASS`/`FAIL` line per arm and exit **0 only if all pass**, non-zero otherwise. Standard
library only.

⚠ **A check must be able to fail.** An arm that passes against both the fixed and the unfixed code has
proved nothing — it has only performed the appearance of a check.

## THE PROOF OBLIGATION — this is the deliverable

The two unfixed revisions are in git history and are **immutable**. Extract them and run the *same*
harness against each:

```
git show b7a3ecb:src/findings.py   > <prefix-dir>/findings.py     # the unfixed findings.py
git show 8eb7be3:src/chunk.py      > <prefix-dir>/chunk.py        # the unfixed chunk.py
python tests/arms.py <prefix-dir>        # MUST FAIL, and MUST name which arm failed
python tests/arms.py src                 # MUST PASS
```

**Report all four results verbatim**, including each exit code. Note that `git show` writes to stdout —
redirect it to a file. Use an **absolute path** for anything Python opens.

**Why this is required and not a nicety:** *a green run against the fixed code alone cannot
distinguish "the fix works" from "the harness stopped looking."* The failure against the unfixed
revision is the only thing that makes the pass mean anything.

## Acceptance

- `python src/findings.py` exits 0 · `python src/chunk.py` exits 0
- `python tests/arms.py src` exits **0**
- `python tests/arms.py <prefix-dir>` exits **non-zero**
- Standard library only. `src/findings.py` and `src/chunk.py` keep their existing public API;
  `tests/arms.py` is the only new file.

---

# Increment 2: overlapping chunker + offset mapping — ✅ DONE

Delivered at `src/chunk.py`. Retained below as context: it is the interface later modules conform to.

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
