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

## Prior art

The problem framing was informed by a prior internal code-review tool. **None of
its code is reproduced here**, and it was never placed in IBM Bob's workspace.
Bob worked from a problem statement at requirements level only.
