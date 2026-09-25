# BUILD REQUIREMENTS — cumulative brief

This file is the brief for everything built in this workspace, and it is committed as the
honest record of **what was asked for**, increment by increment, in order.

**Only the increment marked ⬅ ACTIVE is your task.** Earlier increments are included as
context: they describe interfaces that already exist under `src/`, and later modules should
conform to those rather than invent their own.

Increment 11 is currently ACTIVE.

---

# ⬅ ACTIVE — Increment 11: `src/report.py` — the front door

## Why

Every `src/*.py` `__main__` today is a self-test with a **fake** client. **There is no command that
runs a real review and prints a verdict.** The demo needs one. This is that command.

`src/bob_client.py` is now in the repo — the transport, built in-window, selftest green. **`report.py`
wires it to `review` and `prove_bites`.**

## Deliverable — `src/report.py`

Two invocations must work, run from the repo root:

```
python -m src.report --target <file> --twin <path-outside-repo> --planted <rule_id> \
       --max-cost 2 --per-call-ceiling 1
python -m src.report --target <file> --max-cost 2 --per-call-ceiling 1
```

⚠ **`python src/report.py …` must also work.** The other modules load siblings by path; `-m` changes
`__package__`. Both forms, or the camera points at a command that does not run.

| flag | required | meaning |
|---|---|---|
| `--target PATH` | ✅ | the file to review — read from disk |
| `--twin PATH` | optional | the clean twin, **read from a path the caller supplies, outside this repo** |
| `--planted RULE_ID` | optional | the rule planted in the target |
| `--max-cost N` | 🔒 ✅ | total spend cap, **no default** |
| `--per-call-ceiling N` | 🔒 ✅ | max cost of any single call, **no default** |
| `--max-turns N` | optional | passed through to the provider |
| `--workspace DIR` | optional | the workspace the provider session runs in |

🔒 **THE CAPS ARE REQUIRED AND HAVE NO DEFAULT.** Omitting either → a **usage error naming the
missing flag**, exit non-zero, **and no call is made**. Every chunk is a paid call; a reviewer that
silently spends is worse than one that refuses to start.

## The bridge to the client — and it is load-bearing

The review client protocol is `(prompt: str, per_call_cap: float) -> (text: str, cost: float)`.
`bob_client.chat(...)` returns **text only**, and its cost lands in `bob_client.LAST_STATS`.

Write a small adapter that:
- calls `bob_client.chat([{"role":"user","content":prompt}], max_cost=per_call_cap, …)`
- returns `(text, LAST_STATS.get("session_costs", 0.0))`

🔒 **Pass `per_call_cap` to the provider.** That is what makes the cap real — the provider enforces
it. **A client-side check with no provider limit promises nothing.**
⚠ **Import `bob_client` LAZILY**, inside the function that builds the client — so the self-test and
any `--help` path never require a key.

## The output — written for a 3-minute video, and these are requirements

1. **One screen, no scrolling.**
2. 🔒 **The verdict appears as a LITERAL WORD: `BITES`, `DOES_NOT_BITE` or `INCONCLUSIVE`.** Not a
   colour, not a symbol, not a paraphrase. Judges read words.
3. 🔒 **`twin_ratio` AND `twin_ratio_baseline` both print**, with the margin between them.
4. **The withheld case must be reachable on camera** — running with no `--twin`, or with a
   degenerate one, prints `INCONCLUSIVE` and says why. That is a feature, not an error path.
5. Print the findings the review returned: `rule_id`, `severity`, `file:line`, title.
6. Print the coverage fields (`chunks_reviewed` / `chunks_failed` / `chunks_total`, `truncated`,
   `may_report_clean()`, `total_cost`) — **a partial review must not read as a complete one.**
7. **Diagnostics to stderr; the report to stdout.**

## Self-test (required)

`if __name__ == "__main__":`, **a fake client, no real call, no key, no spend.** Cover:

- omitting `--max-cost` → usage error naming the flag, non-zero exit
- omitting `--per-call-ceiling` → same
- a fake review that finds the planted rule on the target and not on the twin → the output
  **contains the literal `BITES`**, and prints both ratios
- **no `--twin`** → the output contains the literal `INCONCLUSIVE`
- a truncated/failed review → the output does **not** read as clean
- the adapter passes the per-call cap through (assert it reaches the client)

## THE PROOF OBLIGATION

`tests/arms.py` gains **`ARM-5`**, asserted against the `report.py` at the given path, driving
`main()` in-process with a fake client. It asserts: a missing cap is refused with **no call made**;
the verdict word is literal; both ratios print. Then:

- **a mutant that gives the caps a default** (so the command runs without them) → **ARM-5 must
  FAIL.** Declare it in that directory's `MUTANT.json`, and verify the mutation is present before
  running.

Report every run with its exit code, and **paste the CLI's actual output for one real invocation
shape** — the fake-client one, so it costs nothing.

## Acceptance

- `python src/report.py --help` exits 0 and **spends nothing**
- `python -m src.report` and `python src/report.py` both resolve
- `python tests/arms.py src` → all arms PASS, exit 0; the defaulting mutant → non-zero
- Standard library only

---

# Increment 10b: the baseline's rearrangement must not be able to be the identity — ✅ DONE

## The defect, measured

Increment 10's baseline compares `source` against its own lines **sorted lexicographically**. That
rearrangement is **the identity whenever the source is already in sorted order.** Measured:

| source | baseline | `twin_ratio` | verdict |
|---|---|---|---|
| lines already in sorted order | **1.0000** | 0.9750 | **INCONCLUSIVE** |
| same lines, shuffled order | 0.0750 | 0.9750 | **BITES** |

`twin_ratio > baseline` is therefore **unsatisfiable** for any sorted source, and the module refuses
**every** reviewer permanently — **including a perfect one.** Measured at 5, 50 and 200 lines:
baseline **1.0000** in all three. **A sorted import list is enough.** This is not a small-file edge
case; it is any file whose lines happen to be in order.

⚠ **The direction matters: this is a FALSE NEGATIVE — it weakens the proof and turns away a correct
reviewer.** It is the failure mode the increment exists to prevent, arriving from the other side.

🔒 **And all of the module's own tests passed, both times.** The suite uses unsorted fixtures; the
property lives on the sorted axis. **A green suite over a permanent refusal.**

## The fix

**A rearrangement that can be the identity is not a rearrangement.**

1. The baseline's rearrangement must **not be able to equal the source's own order** for any source
   with two or more distinct lines. Reverse, rotate, or shuffle with a fixed seed — your choice —
   **but state why it cannot be the identity**, and **assert it in the self-test**: for a **sorted**
   source, `baseline < 1.0`.
2. Keep it self-generated and deterministic (same inputs → same answer).
3. Keep exposing both values and printing them.

⚠ **Do not fix this by special-casing sorted input** — that is the defect wearing a condition. **Fix
the rearrangement.**

## Regression test (required — this is the point of the increment)

- a **sorted** source with an honest twin → **`BITES`**, trusted True. *(Currently `INCONCLUSIVE`.)*
- a **shuffled-order** source with an honest twin → still `BITES`
- **a sorted source's baseline `< 1.0`** — asserted directly, so the identity-collapse is caught
  even if some other case masks it
- empty-string twin → `INCONCLUSIVE`; unrelated twin → `INCONCLUSIVE`; length discriminator → not `BITES`
- **the 2-line case is expected to remain `INCONCLUSIVE`** — that was increment 10's correct result
  and it must not regress back to acceptance

## THE PROOF OBLIGATION

1. `python tests/arms.py src` → all PASS, exit 0. **ARM-4 adds the sorted-source case** so the arm
   itself can fail on this.
2. **A mutant that restores the sorted-copy baseline** → **ARM-4 must FAIL.** Declare it in that
   directory's `MUTANT.json` and verify the mutation is present in the copy before running.
3. Report every run with its exit code, and **print the sorted-source baseline**.

## Acceptance

- `python src/prove_bites.py` exits 0 and **spends nothing**
- `python tests/arms.py src` exits **0**; the restored-baseline mutant → **non-zero**
- no constant, and **no rearrangement that can be the identity**

---

# Increment 10: the twin's usability is a MARGIN, not a threshold — ⚠ DO NOT SUBMIT AS-IS

## Why — the floor we chose still has a zero-margin acceptance

`prove_bites` currently rejects a degenerate twin by comparing `twin_ratio` against a **fixed floor**.
Measured today, honest-twin ratios by source size: **2-line 0.5000**, 3-line 0.6667, 5-line 0.8000,
10-line 0.8000 — against a floor of **0.5**.

So a **2-line** source's honest twin sits **exactly at the floor** and is accepted by a margin of
**zero**, and any twin engineered to score exactly the floor is accepted as a usable control.

⚠ **A fixed floor must be calibrated, defended, and re-calibrated whenever the corpus changes.** It
was measured, not guessed — but a constant is still a number someone has to maintain.

## 🔒 The fix: compare against a SELF-GENERATED baseline, so there is nothing to tune

Replace the fixed floor with a **relative** test:

1. Compute `twin_ratio = similarity(source, clean_source)` as now.
2. Compute a **baseline** from the data at hand — e.g. the similarity between `source` and a
   **shuffled copy of itself**, or against an unrelated text of matched length. **It must be
   generated from the inputs, deterministic (so the same inputs give the same answer, and a re-run
   reproduces it), and require no constant.**
3. **The twin is a usable control only if it is measurably closer to the source than the baseline
   is.** If it is not, return **`INCONCLUSIVE`** — never `BITES`.
4. **Expose BOTH values** on `BiteProof` (e.g. `twin_ratio` and `twin_ratio_baseline`), and put both
   numbers in the `reason` and in the self-test output.

🔒 **Print the two values you compared, not just the verdict.** *A margin you cannot see is a
threshold you cannot audit.*

⚠ **Expect tiny sources to become `INCONCLUSIVE`, and that is correct rather than a regression.** On
a 2-line file the similarity metric cannot distinguish a genuine near-copy from coincidence. **The
honest verdict there is "this control cannot be established", not a zero-margin acceptance.** The
demo target is a real file of hundreds of lines where the honest twin measures 0.95+; the margin
exists for the small-source case, which is where the zero-margin acceptance lives.

⚠ **Do NOT reintroduce a constant** — including a "small" one, a minimum-margin epsilon, or a
size cutoff below which the check is skipped. **Skipping the check for small sources is the defect
wearing a size condition.** If a form genuinely cannot work without a constant, say so and stop
rather than shipping one quietly.

## Self-test (required)

`if __name__ == "__main__":`, fake reviewers only, **no spend**. Add:

- a **2-line** source with an honest twin → `INCONCLUSIVE` (the zero-margin case, now refused)
- a **large** source with an honest twin → still `BITES`, trusted True, **with both ratios printed**
- empty-string twin → `INCONCLUSIVE`; unrelated-file twin → `INCONCLUSIVE`
- the **file-length discriminator** → still must NOT earn `BITES`
- **print every `twin_ratio` and its baseline** so the separation is visible in the output

## THE PROOF OBLIGATION

1. **`tests/arms.py src`** → all arms PASS, exit 0. **ARM-4 keeps asserting** a degenerate twin →
   `INCONCLUSIVE`, and **adds**: a **2-line** source with an honest twin → `INCONCLUSIVE`.
2. **A mutant that removes the margin comparison** (so any twin is accepted as a control) →
   **ARM-4 must FAIL.** Name the mutation, verify it is present in the copy, and declare it in that
   directory's `MUTANT.json` — **a mutant with no declaration is refused by the harness, and a
   mutant you did not verify landed is a mutant you did not run.**
3. Report every run verbatim with its exit code, and **state the measured ratios and the baseline
   you compare against.**

## Acceptance

- `python src/prove_bites.py` exits 0 and **spends nothing**
- `python tests/arms.py src` exits **0**; the margin mutant → **non-zero**
- Standard library only; no constant floor remains

---

# Increment 9: the twin's integrity must be ENFORCED, not delegated — ✅ DONE

## The defect, measured against the built module

`prove_bites` decides whether the reviewer **discriminates** between a flawed file and a clean twin.
If the "twin" it is handed is not actually a near-copy — an empty string, an unrelated file — then
**the comparison proves nothing**, and the reviewer is being measured against a control that isn't a
control.

**Measured today, my instrument, on the shipped module:**

| twin handed in | `twin_hunks` | status for a reviewer that only counts file LENGTH |
|---|---|---|
| honest twin (1 line changed) | 1 | DOES_NOT_BITE |
| **empty string** | **1** | **BITES, `may_trust_clean()` TRUE** |
| **unrelated tiny file** | **1** | **BITES, `may_trust_clean()` TRUE** |

A reviewer with **no capability whatsoever** — it returns the planted rule iff the file has more
than 20 lines — earns **`BITES`** and a trusted verdict, **while the check the caller was told to
make (`twin_hunks == 1`) reads GREEN.**

⚠ **`twin_hunks` counts SequenceMatcher OPCODES, not differing lines — and a TOTAL mismatch is ONE
opcode.** So it is 1 for a perfect twin *and* 1 for an empty string. **It cannot distinguish the two
at any threshold.**

## A 🔒 Enforce it INSIDE, and drop the proxy

1. **Compute `twin_ratio`** — the line-similarity between `source` and `clean_source` — **inside
   `prove_bites`**, and return **`INCONCLUSIVE`** (never `BITES`) when the twin is **degenerate**:
   the control is not a near-copy of the target, so no discrimination can be established.
   `reason` must say the twin was not a usable control.
2. **Expose `twin_ratio: float` and `twin_lines_kept: int` on `BiteProof`.**
3. 🔒 **Enforcement lives inside the module, not in a number the caller must remember to check.**
   ⚠ **A count the caller has to inspect, sitting one step away from the degeneracy that breaks it,
   is exactly the shape already fixed twice in this build.** The caller's green must not be able to
   coexist with a broken control.
4. ⚠ **Do NOT "fix" this by tightening `twin_hunks`.** An opcode count is **the wrong quantity at
   any threshold** — it is 1 for an empty string and 1 for a perfect twin. Tightening it moves a
   number without adding discrimination. **Leave `twin_hunks` exposed and stop relying on it.**

## B 🔒 Measure the floor — do not adopt one

Choose the threshold **from measurement**, and **print the value you chose**:

- measure `twin_ratio` for **the honest twin** (the case that must pass)
- measure it for **each degenerate case** (empty, unrelated, one line)
- **state the gap and where the floor sits inside it**

⚠ **A floor of "about a half" is a guess**; the honest-twin value is the thing to calibrate against.
**A threshold you cannot show separates the two populations is the same defect as an unmeasured one.**
Carry the measured numbers in the self-test's output so the floor is visible, not asserted.

## C 🔒 The twin call must not reuse the source's `file` label

Measured: `review(clean_source, file)` passes the **source's** label, so the reviewer sees
`['x.py', 'x.py']`. **A reviewer that caches by filename returns the source's findings for the twin
call** — and the module then reports a **correct** reviewer as `DOES_NOT_BITE`.

⚠ **That is a false negative — the direction that WEAKENS the proof**, and it turns a good reviewer
away. Give the twin its own label (`f"{file}.twin"` is fine).

## D Self-test (required)

`if __name__ == "__main__":`, fake reviewers only, **no spend**. Add:

- an **empty-string** twin → **`INCONCLUSIVE`**, `may_trust_clean()` False
- an **unrelated tiny file** as twin → **`INCONCLUSIVE`**, trusted False
- a **file-length discriminator** with an empty twin → **must NOT be `BITES`** *(this is the
  reviewer that currently wins)*
- the honest twin → still `BITES`, trusted True, and print its `twin_ratio`
- **print every measured `twin_ratio` and the floor** so the separation is visible in the output

## E THE PROOF OBLIGATION

1. **`tests/arms.py src`** → all arms PASS, exit 0. **ARM-4 must additionally assert** that a
   degenerate twin yields `INCONCLUSIVE` and `may_trust_clean()` False — **so the arm can fail on
   this**, not just the self-test.
2. **A mutant that removes the degeneracy check** (so a degenerate twin is scored normally) →
   **ARM-4 must FAIL.** Name the mutation, verify it is present in the copy before running.
3. Report every run with its exit code.

## Acceptance

- `python src/prove_bites.py` exits 0 and **spends nothing**
- `python tests/arms.py src` exits **0**; the degeneracy mutant → **non-zero**
- Standard library only

---

# Increment 12 (deferred): `src/mcp_server.py`

The brief below is written and ready; **it is not the current task.** Full text retained.

---

# Increment 9 (superseded brief): `src/mcp_server.py` — the review engine as an MCP server

## Why

The engine is currently only reachable by importing it. An MCP server makes it a **tool** any
agent host can call — which is how the reviewer gets used by anything other than a person.

## Deliverable — `src/mcp_server.py`

A **JSON-RPC 2.0 server over stdin/stdout**, standard library only, implementing the MCP handshake
and tools surface:

- `initialize` → protocol version, server info, and a `tools` capability
- `tools/list` → one tool, `scan_file`
- `tools/call` → dispatch, and an **MCP error** (not a crash, not a silent default) for anything
  malformed

`scan_file` input schema — **`max_cost` and `per_call_ceiling` are `required`**:

| param | type | required |
|---|---|---|
| `path` | string | ✅ |
| `max_cost` | number | 🔒 ✅ |
| `per_call_ceiling` | number | 🔒 ✅ |
| `chunk_lines` | integer | optional |

🔒 **THE RUNTIME CAP IS REQUIRED ON EVERY ENTRY POINT, AND THERE IS NO SERVER-SIDE DEFAULT.**
Every chunk is a **paid call**. A reviewer that silently spends is a worse failure than one that
refuses to start, and it is the only failure here that costs money while nobody is watching.
**`required` in the schema AND validated in the handler** — a schema is documentation to a client
that ignores it, so the handler must refuse too. A missing, null, zero or negative cap → **MCP
error**, naming which parameter.

### The server must not own a review client

`build_server(client)` takes a **client factory** and the server never imports one itself. The
transport is testable without a provider, and **the self-test must never spend anything**.

### A non-clean result must not come back reading clean

The `tools/call` result must carry, for every scan: `chunks_total`, `chunks_reviewed`,
`chunks_failed`, `truncated`, `total_cost`, `may_report_clean()`, and the findings. 🔒 **A result
that is not clean must be visibly not clean in what the tool returns** — the caller must not have
to know to ask. **Summarise nothing away.**

### Errors

- unknown method → JSON-RPC error `-32601`
- unknown tool → MCP error, not a traceback
- a bad or missing `path` → error naming it
- an exception inside the review → an MCP error carrying the message; **never a crash of the
  server loop, and never a clean-looking result**

⚠ **One JSON object per line on stdout.** Anything written to stdout that is not a protocol frame
corrupts the stream — **diagnostics go to stderr.**

## Self-test (required)

`if __name__ == "__main__":` — one `PASS`/`FAIL` per check, exit 0 only if all pass. **Drive the
server over in-memory pipes with a fake client; make no real call and spend nothing.** Cover:

- `initialize` and `tools/list` return well-formed frames
- `scan_file` **without `max_cost`** → error, and **the fake client was never called**
- `scan_file` **without `per_call_ceiling`** → error, client never called
- `scan_file` with a zero/negative cap → error, client never called
- a successful scan returns the coverage fields, and `may_report_clean()` agrees with the result
- a scan whose review was truncated/failed is **not** reported as clean
- an unknown method → `-32601`; an unknown tool → error
- **an exception inside a scan does not kill the loop** — a following request still gets an answer
- stdout carries protocol frames only

## Acceptance

- `python src/mcp_server.py` exits 0 and **spends nothing**
- `python tests/arms.py src` still exits **0** (this increment does not change the other modules)
- Standard library only; new file `src/mcp_server.py`

---

# Increment 8: the harness must fail closed on a contaminated tree — ✅ DONE

Both changes are in `tests/arms.py`. **No `src/` behaviour changes.**

## Why — a real failure from this build, not a hypothetical

The proof for the last increment pointed `tests/arms.py` at a mutant directory which **still held a
mutant of a DIFFERENT module from the previous increment.** The arm for the old module failed, for
reasons that had nothing to do with the module under test, and **the failure looked like a
legitimate red.** The verdict was produced from a tree nobody had declared.

Two distinct harms, and the second is worse:
- a **leak** costs you the demo — something can read the answer;
- a **stale mutant** costs you the **finding** — silently, by making an arm fail for an unrelated
  reason, and **no amount of re-reading the instrument reveals it**, because the instrument is fine
  and its *subject* is not what the caller believes.

## A 🔒 A non-`src` subject must DECLARE its mutations, and be refused if it does not

When `tests/arms.py <path>` is given a directory, the harness must:

1. **Build a manifest of the subject** — for every module file in `<path>`, compare it **by content**
   against the same-named file in `src/`.
2. **If every file matches `src/`** — run normally.
3. **If a file differs from `src/`** — that file is *mutated*, and it must be **declared** in a
   `MUTANT.json` in that directory:
   ```json
   {"mutations": [{"file": "prove_bites.py", "change": "may_trust_clean forced True"}]}
   ```
4. 🔒 **ANY file that differs from `src/` and is NOT declared → REFUSE.** Print which file differs,
   print the declared set, **run no arms, and exit non-zero.** A missing `MUTANT.json` on a
   non-`src` subject is a refusal, not a default-allow.
5. **Print the manifest before the arms run** — every subject file, its sha256, and whether it is
   identical or declared-mutated. **The subject must be visible in the output**, so a contaminated
   tree is diagnosable from the transcript and not only from the exit code.

⚠ **A mutant directory with no `MUTANT.json` must NOT be silently accepted.** That is the exact
condition that produced the contaminated verdict, and the whole point of this part is that it
**cannot pass quietly**.
⚠ The `src/` subject needs no `MUTANT.json` (nothing is mutated) — but the manifest must still print.

## B 🔒 ARM-3 must assert `chunks_failed` on the parse path

`chunks_failed` is the field that makes a failed chunk **legible**. Today the arms assert it only for
a client that **raises**; **nothing asserts it when a response fails to PARSE.** A regression that
blanks it there passes every arm we have.

- **A2** (client returns prose) → assert **`chunks_failed == chunks_total`**.
- **A5** (prose, then `[]`) → assert **`chunks_failed == 1`** and **`chunks_reviewed == chunks_total - 1`**.

⚠ **A2 and A5 are different shapes** — a total failure and a partial one — and only one of them
currently has a witness. Assert both, and print the values.

**The property:** the mechanism that *enforces* the verdict is the counter's placement; the field
that *reports* the failure is `chunks_failed`. **Only the enforcing one is tested.** A regression
that blanks the reporter is invisible **at exactly the moment the report is what you need.**

## THE PROOF OBLIGATION

1. **Contamination refusal:** build a mutant directory with a mutation that is **NOT** declared in
   its `MUTANT.json` (or with no `MUTANT.json` at all) → **`tests/arms.py` must REFUSE**: non-zero
   exit, **no arm output**, and it must **name the undeclared file.**
2. **Declared mutant still runs:** the same directory **with** a correct `MUTANT.json` → the arms
   run and produce their normal verdict.
3. **`chunks_failed` arm bites:** mutate `review.py` so the parse handler **does not** increment
   `chunks_failed` → **the A2/A5 assertions must FAIL.**
   ⚠ **Verify this mutation is present in the copy before running** — a mutation that does not land
   is a mutant you did not run.
4. `python tests/arms.py src` → all arms PASS, exit 0.

Report every run verbatim with its exit code, and **state what you changed in each mutant.**

## Acceptance

- `python tests/arms.py src` exits **0**; undeclared-mutation dir → **non-zero with no arms run**
- `python src/review.py` and the other `src/` self-tests still exit 0 and **spend nothing**
- Standard library only; **`tests/arms.py` is the only file changed**

---

# Increment 7: `src/prove_bites.py` — the reviewer must DISCRIMINATE — ✅ DONE

## Why the obvious version of this module is vacuous

The first draft of this brief said: *"BITES — at least one finding has `rule_id == planted_rule`."*
That is a membership test **on the output**, with **no constraint on the input**. A reviewer that
ignores `source` entirely and always emits one finding carrying the planted rule passes it, and every
one of the five arms below would pass too — **five of five**.

The suite varied the **output**; the property is a relation between **input and output**.

So the proof must be one of **discrimination**: the reviewer reports the planted rule on a flawed file
**and stays silent about it on an otherwise identical, unflawed file.**

## Deliverable — `src/prove_bites.py`

```python
@dataclass(frozen=True)
class BiteProof:
    status: str                        # "BITES" | "DOES_NOT_BITE" | "INCONCLUSIVE"
    planted_rule: str
    found_rule_ids: tuple[str, ...]    # rule_ids reported on the SOURCE
    twin_rule_ids: tuple[str, ...]     # rule_ids reported on the TWIN
    twin_hunks: int = -1               # how many line groups differ between source and twin
    reason: str = ""

    def bites(self) -> bool: ...
    def may_trust_clean(self) -> bool: ...   # True ONLY for "BITES"

def prove_bites(review, source: str, *, planted_rule: str,
                clean_source: str | None = None, file: str = "<target>") -> BiteProof: ...
```

`review` is any callable `(source: str, file: str) -> ScanResult`.

## Required behaviour

1. Run `review` on `source`. Collect the `rule_id` of every finding.
2. **`"BITES"`** — the planted rule **is** reported on `source`, **and is NOT reported on `clean_source`.**
   Two conditions. Both required.
3. **`"DOES_NOT_BITE"`** — either the planted rule was not reported on `source`; **or** it was
   reported on `source` **and also on the twin** — a reviewer that says the same thing about a flawed
   and an unflawed file **has not discriminated**, and `reason` must say so in those words.
4. **`"INCONCLUSIVE"`** — the proof could not be established:
   - `clean_source is None`; **or**
   - either review is `truncated`, carries an `error`, or `may_report_clean()` is False.

   🔒 **`clean_source is None` must NEVER yield `"BITES"`.** A one-sided proof cannot establish
   discrimination. **A claim that cannot be falsified is not a proof** — and this module's own
   philosophy, turned on itself.

   🔒 **`"INCONCLUSIVE"` is not a soft pass, and it is not a failure of the reviewer.** Do not fold
   it into either other status.
5. **`may_trust_clean()` is True if and only if `status == "BITES"`.**
6. **The twin assertion is SCOPED to the planted rule.** The reviewer **may** legitimately report
   other findings on the twin; that is not a failure. ⚠ A rule of *"must report nothing on the twin"*
   would call a correct reviewer broken and **manufacture a false `DOES_NOT_BITE`**.
7. **`twin_hunks`** counts how many groups of lines differ between `source` and `clean_source`.
   Compute it and expose it. **If the twin differs by more than the planted hunk, the verdict is
   unattributable** — the module measures every other difference too. The module does **not** change
   the verdict on this; it **prints/exposes the count**, and the arm asserts it. Say in the docstring
   that a caller must check it.

## The twin must NOT live in the workspace

🔴 **The twin names the defect by its diff.** Two files in the same tree means `diff` on the pair
returns the answer key in one command — to the reviewer, to a Bob session, to anyone with the
workspace. **It is a derivation, not an annotation, so no grep for a defect finds it.**

- `prove_bites` takes `clean_source` as **a string supplied by the caller**, who reads it from
  **outside the workspace**. Nothing in this repo may contain the real twin.
- The module must run correctly when the twin is **absent** → `"INCONCLUSIVE"`.
- **`DISCLOSURE.md` states that a twin exists, at requirements level, without naming the flaw.**
- ⚠ **Do NOT create any file holding the real planted target or its twin in this workspace.**

## Self-test (required)

`if __name__ == "__main__":` — one `PASS`/`FAIL` per check, exit 0 only if all pass. **Fake reviewers
only; make no real call and spend nothing.** Use in-memory fixtures. Cover:

- a reviewer that reports the planted rule on the source and not on the twin → `BITES`, trusted True
- a reviewer that reports the planted rule on **BOTH** → `DOES_NOT_BITE` (no discrimination), trusted False
- a reviewer that reports findings but never the planted rule → `DOES_NOT_BITE`, trusted False
- a reviewer that reports **nothing at all** → `DOES_NOT_BITE`, trusted False
- **`clean_source=None`** → `INCONCLUSIVE`, trusted False
- a **truncated** result → `INCONCLUSIVE`; a result carrying an **error** → `INCONCLUSIVE`
- the twin differing from the source by **one** hunk → `twin_hunks == 1`

## THE PROOF OBLIGATION — TWO mutants, and name the one you do not run

`tests/arms.py` gains **`ARM-4`**, asserting the above against the `prove_bites.py` at the given path,
**including that `may_trust_clean()` is False for every status except `BITES`.**

Then run **both** mutants in `<mutant-dir>/`, each a **single named change**, each verified present in
its copy **before** the arm runs:

- **M-gate** — `may_trust_clean()` returns `True` unconditionally → **ARM-4 must FAIL.**
- **M-detector** — `prove_bites()` returns `"BITES"` unconditionally → **ARM-4 must FAIL.**

⚠ **These are different mutants and only one of them tests the thing that matters.** M-gate tests the
**gate**; M-detector tests the **detector**. A mutant that leaves the gate honest and makes the
detector always say BITES passes a gate-only arm unchanged. **If you run only one, name the one you
did not run** — do not imply the set is exhaustive.

## Acceptance

- `python src/prove_bites.py` exits 0 and **spends nothing**
- `python tests/arms.py src` exits **0**; against either mutant → **non-zero**
- Standard library only

---

# Increment 6: `chunks_reviewed` must mean "we hold its output" — ✅ DONE

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
