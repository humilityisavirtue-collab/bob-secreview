# Disclosure

Per the hackathon rule that pre-prepared **synthetic sample code** and **demo UI
templates** may be used **if clearly disclosed**, and that **all core Bob analysis
and project logic must be built during the hackathon window**:

## Pre-existing, disclosed

| Path | Origin | Role | Class |
|---|---|---|---|
| `demo/vulnerable_app.py` | pre-prepared synthetic sample | the planted-vulnerability target | synthetic sample code |
| `demo/test_vulnerable_app.py` | pre-prepared synthetic sample | harness proving the target is catchable | synthetic sample code |

## Built during the hackathon window

`src/**` — all core project logic. `bob_sessions/**` — Bob IDE task-session exports.

## The Bob task-session exports (`bob_sessions/`)

Produced by Bob IDE's own **Export Task History** command. Two renderings of the same
eight sessions, and **they are not equivalent**.

**`bob-tasks-secreview-bob-2026-09-25.json` is the complete record.** It is the
artifact to read when assessing this work.

**`bob-tasks-secreview-bob-2026-09-25.md` is the readable view.** It is partial: the
Markdown rendering includes user and assistant turns and **omits tool outputs and
system messages**. Measured against the JSON — 8/8 user turns and 163/163 assistant
turns are rendered; of the 167 tool messages and 8 system messages, **none** are.

That omission is not cosmetic. The tool outputs carry the self-test stdout and exit
codes for every proof command. **The Markdown shows the agent's narrative; the JSON
carries the evidence it produced.** Where the two disagree, the JSON is authoritative.

### Curation

The exported sessions are curated for length and for third-party material, in the
ordinary sense that any artifact is curated before publication.

One paragraph, in three tool-output messages, was removed during curation. Those
messages are absent from the Markdown rendering in any case, so the redaction appears
only in the JSON, as `[redacted]` (3 occurrences). **The redaction is applied to the
JSON, which is the record — it is not inherited by the Markdown.**

## Twin (prove_bites — Increment 7)

`src/prove_bites.py` establishes a **discrimination proof**: the reviewer must
report the planted rule on the flawed target **and stay silent about it on an
otherwise identical, unflawed file** (the "twin").

The twin exists.  It is **not stored in this workspace** — `prove_bites` takes
`clean_source` as a string supplied by the caller from outside the repo.
Nothing here names the flaw or contains the corrected source; the twin is a
derivation, not an annotation, so no grep for the defect finds it here.

When `clean_source` is `None` the verdict is `INCONCLUSIVE`.  A one-sided proof
cannot establish discrimination, and this module turns that philosophy on itself.

## Prior art

The problem framing was informed by a prior internal code-review tool. **None of
its code is reproduced here**, and it was never placed in IBM Bob's workspace.
Bob worked from a problem statement at requirements level only.
