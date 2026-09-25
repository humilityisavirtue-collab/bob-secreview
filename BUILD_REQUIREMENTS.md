# BUILD REQUIREMENTS — cumulative brief

This file is the brief for everything built in this workspace, and it is committed as the
honest record of **what was asked for**, increment by increment, in order.

**Only the increment marked ⬅ ACTIVE is your task.** Earlier increments are included as
context: they describe interfaces that already exist under `src/`, and later modules should
conform to those rather than invent their own.

Increment 6 is currently ACTIVE.

---

# ⬅ ACTIVE — Increment 6: `chunks_reviewed` must mean "we hold its output"

A chunk whose response we **cannot parse** is still counted as reviewed. So a client that returns
prose rather than JSON produces a result that reports **complete coverage with zero findings** —
while `error` is populated. The gate and the evidence disagree, and the gate is what decides.

## A — `src/review.py`

`chunks_reviewed` must mean **"chunks whose output we actually hold."** The increment currently
sits **above** the parse step, so it has already run by the time parsing fails.

- Move the `chunks_reviewed += 1` so it happens only **after** the response has been successfully parsed.
- Increment **`chunks_failed`** in the parse-failure handler, exactly as the raise handler does.

⚠ **Do NOT "fix" this by adding a second check somewhere else.** One property, **one site**. A
redundant backstop that no test reaches makes an individual mutant invisible — that is the defect
this replaces, not the fix for it.

⚠ **Leave `error` set on a parse failure, and leave the field in place.** It is not redundant:
it is the clause that keeps an unparseable run legible as incomplete, and removing it as
"tidying" would silently re-open a vacuous clean inside the module that exists to prevent vacuous
cleans. **Note that in the code, so nobody deletes it.**

## B — `src/findings.py`: make the spend reportable

`ScanResult` gains **`total_cost: float = 0.0`** and **`max_cost: float = 0.0`** (defaults, and in
`as_dict()`). Today an over-spend is **recorded nowhere** — a client returning 1.0, 0.99 or 5.0
against a cap of 1.0 produces an indistinguishable result.

⚠ **State the guarantee you can actually make, and name the mechanism.** The honest promise is
*"no call is started that could not be afforded, and the total is reported."* Do **not** claim
"the cap is never exceeded" — a token-billed provider cannot be pre-limited exactly. **A spec that
names an outcome and omits the mechanism is the defect this project exists to find; do not write
one in the fix.**

## C — name the doors the freeze closes (documentation, in the module)

`Finding` is frozen. **Say which door that closes and which it does not**, in the docstring:

- **Closed:** assignment to `severity` and the other fields — a `str` is genuinely immutable, so the
  construction-time validation cannot be bypassed by later assignment.
- **NOT closed:** it is a **shallow** freeze — `f.location.line_start = 999` still mutates through,
  because `Location` is not frozen. And `Finding` is **unhashable**, since `frozen=True` implies
  hashability that the `Location` field cannot honour.

⚠ **Do not describe the freeze as closing *the* door. Say which door.** A guarantee described as
total but delivered partially is the same shape as everything else this project fixes.

## D — `tests/arms.py`: reach the parse path

**ARM-3 gains the arms that were missing.** A client returning **prose instead of JSON** must yield
`may_report_clean() is False`. Assert the whole set and print it:

| arm | client returns | required |
|---|---|---|
| A1 | raises | not clean |
| A2 | **prose** (unparseable) | 🔒 **not clean** |
| A3 | `[]` (honest empty) | **clean** — this one is CORRECT and must stay clean |
| A4 | fenced JSON with findings | clean, findings present |
| A5 | prose then `[]` | 🔒 **not clean** |

⚠ **A3 is the control on the arm set.** A test that calls every empty result "vacuous" cannot tell
an honest empty review from an unparseable one. **The defect is specifically `may_report_clean()`
True *while* `error` is populated** — assert that pair, not "no findings".

## THE PROOF OBLIGATION — two-sided, and it must be tight

- **Forward mutant:** move `chunks_reviewed += 1` back **above** the parse step → **A2 and A5 must
  fail.** Put it in `<mutant-dir>/`, verify the mutation is present in the copy **before** running.
- **The bar is symmetric:** after the fix, **A2 and A5 flip to not-clean, and A1 and A3 are
  UNCHANGED.** A fix that flips three arms is over-tightened; one that flips one is incomplete.
  **Report which arms moved and which did not** — the unchanged ones are the evidence that you
  fixed the property and not the test.
- `python tests/arms.py src` → all arms PASS, exit 0; `python tests/arms.py <mutant-dir>` → non-zero.

⚠ **Name the mutant you did NOT run.** If there is a second way to break this property that your
mutant does not cover, say so rather than implying the one mutant exhausts the space.

## Acceptance

- `python src/review.py`, `src/findings.py`, `src/chunk.py` exit 0 and **spend nothing**
- `python tests/arms.py src` exits **0**; `python tests/arms.py <mutant-dir>` exits **non-zero**
- Standard library only

---

# Increment 7 (NEXT, not yet active): `src/prove_bites.py`

**Do not build this yet.** It is being re-specified: as first written it could be satisfied by a
reviewer that ignores its input entirely and always emits the planted rule. It now requires a
**second, clean source** so the proof is one of *discrimination* rather than of emitting a known
string. Full brief follows this increment.

---

# Increment 6 (superseded brief): `src/prove_bites.py` — a reviewer must EARN its verdict

## Why this exists

A review engine's **clean** result is worth something only if the engine has demonstrated it can
**find** a known defect. Otherwise "no findings" is indistinguishable from "not looking."

So: before any clean result from a reviewer is accepted, the reviewer must be shown a target with a
**known planted flaw**, and must be shown to **report that flaw**. That is what this module decides.

## Deliverable — `src/prove_bites.py`

```python
@dataclass(frozen=True)
class BiteProof:
    status: str                        # exactly "BITES" | "DOES_NOT_BITE" | "INCONCLUSIVE"
    planted_rule: str                  # the rule_id that was planted in the target
    found_rule_ids: tuple[str, ...]    # rule_ids the reviewer actually reported
    reason: str = ""

    def bites(self) -> bool: ...            # True ONLY for "BITES"
    def may_trust_clean(self) -> bool: ...  # True ONLY for "BITES"

def prove_bites(review, source: str, *, planted_rule: str, file: str = "<target>") -> BiteProof: ...
```

`review` is any callable `(source: str, file: str) -> ScanResult` — the wired review engine.

## Required behaviour

1. Run `review(source, file)`. Collect the `rule_id` of every finding it returns.
2. **`"BITES"`** — at least one finding has `rule_id == planted_rule`. The reviewer found the
   planted flaw.
3. **`"DOES_NOT_BITE"`** — the review ran to completion, reported findings or none, and **none of
   them was the planted rule.** The reviewer looked and did not find it.
4. **`"INCONCLUSIVE"`** — the review could not have reached the flaw: the `ScanResult` is
   `truncated`, or it carries an `error`, or `may_report_clean()` is False. 🔒 **These are NOT
   failures of the reviewer and must NOT be scored as `DOES_NOT_BITE`** — the flaw may simply never
   have been examined. Scoring that as "does not bite" blames the reviewer for our own budget stop.
5. 🔒 **`may_trust_clean()` returns True if and only if `status == "BITES"`.** A reviewer whose
   bite proof is `DOES_NOT_BITE` **or** `INCONCLUSIVE` has **not** earned a clean verdict, and a
   clean result from it must be withheld. **`INCONCLUSIVE` is not a soft pass.**
6. The three statuses are the **exact** strings above — callers compare on them.

## Self-test (required)

`if __name__ == "__main__":` — one `PASS`/`FAIL` per check, exit 0 only if all pass.
**Use fake reviewers; make no real call and spend nothing.** Cover, at minimum:

- a reviewer that reports the planted rule → `BITES`, and `may_trust_clean()` is True
- a reviewer that reports findings but not the planted rule → `DOES_NOT_BITE`, `may_trust_clean()` False
- a reviewer that reports **nothing at all** → `DOES_NOT_BITE`, `may_trust_clean()` False
  ⚠ **This must be a real check: a reviewer that returns no findings has NOT bitten.** If your
  comparison cannot distinguish "found nothing" from "found the flaw", say so plainly.
- a **truncated** result → `INCONCLUSIVE`, `may_trust_clean()` False
- a result carrying an **error** → `INCONCLUSIVE`, `may_trust_clean()` False

## THE PROOF OBLIGATION

`tests/arms.py` gains **`ARM-4`**, asserting against the `prove_bites.py` found at the given path:
a reviewer that finds the planted rule yields `BITES`; one that returns nothing yields
`DOES_NOT_BITE`; a truncated result yields `INCONCLUSIVE`; and **`may_trust_clean()` is False for
every status except `BITES`.**

Then the mutant, **one named change**:
- make `may_trust_clean()` return `True` unconditionally → **ARM-4 must FAIL.**
- Put it in `<mutant-dir>/`, **verify the mutation is present in the copy before running**, and run
  `python tests/arms.py src` → all arms PASS, exit 0.

Report every run verbatim with its exit code.

## Acceptance

- `python src/prove_bites.py` exits 0 and **spends nothing**
- `python tests/arms.py src` exits **0**; `python tests/arms.py <mutant-dir>` exits **non-zero**
- Standard library only. New file `src/prove_bites.py`; `tests/arms.py` extended.

---

# Increment 5: make the engine's guarantees real — ✅ DONE

Four changes, all in the same two files. **Each one is a guarantee that is currently stated
but not enforced**, which is the only kind of change this project exists to make.

## A — `src/findings.py`: freeze `Finding`

`Finding` becomes `@dataclass(frozen=True)`. Construction is then the only door, which makes
the existing validation the *only* validation point rather than a narrow one.

⚠ **`__post_init__` currently assigns** (`self.severity = validate_severity(...)`), and a frozen
dataclass blocks that — including from its own constructor. Use `object.__setattr__`, or move
normalisation so it happens before the instance exists. **Grep for any existing assignment to a
`Finding` field first**; a freeze that breaks a caller is a red pointing at the wrong person.

⚠ **Do NOT make the comparators total** (e.g. `SEVERITY_RANKS.get(sev, -1)`). That converts a
loud failure into a silent one: a bad severity would sort as lowest, a wrong order with no
signal anywhere. **Keep them strict.**

## B — `src/review.py`: a clean result must EARN its coverage

Today a chunk that **fails** still counts as reviewed. Fix it structurally, not by adjusting a
number:

1. **A failed chunk does not increment `chunks_reviewed`.** A failure is not a review.
2. **Add `chunks_failed: int = 0` to `ScanResult`** (and to `as_dict()`). A failure must live in
   a **field**, not only in a free-text message — `error` is a message, not a field, and a caller
   who reads the fields designed for this question is currently being told something false.
3. 🔒 **And the structural half: a clean report must require complete coverage.** Add

   ```python
   def may_report_clean(self) -> bool:
       """True ONLY when the whole source was reviewed with no failures."""
   ```

   true **only** when `chunks_failed == 0` **and**
   `chunks_reviewed + chunks_failed == chunks_total`.

   **Fixing the counter and leaving a clean result reachable is the same defect with better
   bookkeeping.** The verdict must not be available until coverage has been earned.
   *Precedent for the shape: a failed target call currently emits a verified-clean verdict in the
   guard spec — this is that fix, applied here.*
4. `truncated` is set on any failure — but **(3) is the enforcement; `truncated` is a signal.**
   Do not let the signal do the enforcing.

## C — `src/review.py`: make the spend cap actually hold

The cap cannot be guaranteed while a call's price is unknown. It can be guaranteed if the
**provider** enforces a per-call limit — so route it there.

- **`ReviewClient` takes the per-call cap:** `Callable[[str, float], tuple[str, float]]` —
  `(prompt, per_call_cap) -> (response_text, cost)`.
- **`review_source` gains a required keyword-only `per_call_ceiling: float`** — the most a single
  call is allowed to cost. No default (`TypeError` if omitted); `ValueError` if `None` or `<= 0`.
- **Refuse to start a call when `max_cost - total_cost < per_call_ceiling`.** Refuse — do **not**
  start the call and truncate its output. If the worst case cannot be afforded, the call does not
  begin.
- Otherwise compute `per_call_cap = min(per_call_ceiling, max_cost - total_cost)` and **pass it to
  the client**, which passes it to the provider's own per-call limit and lets the provider enforce it.

🔒 **In the module docstring, state the guarantee AND the mechanism that makes it true.** Name the
provider's per-call limit explicitly. **The defect being fixed here was a specification that named
an outcome and omitted the mechanism — do not repeat it in the fix for it.**

## D — `src/review.py`: one invariant, one enforcement site

Once (B) fixes the counters at the source, the derived fallback that re-sets `truncated` after the
loop **is no longer needed — remove it.**

⚠ **A defended invariant with an untested backstop is weaker than a single one, because it hides a
mutant:** a mutant at either site alone is invisible, so an arm passes while the invariant is
broken. **One invariant, one site, individually falsifiable.**

## E — `tests/arms.py`: close the gaps these fixes expose

- **ARM-1** additionally asserts that assigning to a `Finding` field raises
  **`dataclasses.FrozenInstanceError` specifically** — it subclasses `AttributeError`, so a bare
  `except AttributeError` would pass vacuously on any attribute typo. Keep the ≥2-element sort arm.
- **ARM-3** additionally asserts **the cap was not exceeded** (sum of the fake client's costs
  `<= max_cost`), and that a client which **always raises** yields
  `chunks_failed == chunks_total`, `chunks_reviewed == 0`, and **`may_report_clean()` is `False`**.
  Update the fake clients to the new two-argument protocol.

## Self-tests

`python src/review.py`, `python src/findings.py`, `python src/chunk.py` all exit 0, and
**`review.py`'s self-test still spends nothing.**

## THE PROOF OBLIGATION

`tests/arms.py <path>` against a known-bad copy — **one mutant per guarantee**, and each mutant
changes **exactly one named thing**:

1. **`may_report_clean`** made to ignore coverage → ARM-3 must FAIL.
2. **the pre-call affordability refusal** removed → ARM-3's cap assertion must FAIL.
3. **`frozen=True`** removed from `Finding` → ARM-1's freeze assertion must FAIL.

Put the three mutants in `<mutant-dir>/`, and run `python tests/arms.py src` → all PASS and exit 0.
**Report every run verbatim with its exit code, and state what you changed in each mutant.**
⚠ Confirm each mutation is actually present in its copy **before** running the arm — a mutant
whose anchor went stale tests nothing, and reports as a verified arm.

## Acceptance

- `python tests/arms.py src` exits **0**; `python tests/arms.py <mutant-dir>` exits **non-zero**
- Standard library only; `tests/arms.py` and the three `src/` modules are the only files touched

---

# Increment 4: `src/review.py`, the review engine — ✅ DONE

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
