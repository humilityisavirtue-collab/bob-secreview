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
