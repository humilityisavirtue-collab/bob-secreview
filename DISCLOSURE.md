# Disclosure

**Authority: the Official Rules** (`Official Rules IBM Hackathon May 2026.pdf`), which state
expressly that *"IN THE EVENT OF A DISCREPANCY BETWEEN ANY INFORMATION AND/OR COMMUNICATION, THESE
OFFICIAL RULES SHALL GOVERN."* An event-page note, a Discord message or a briefing is a
*communication*, and the Rules outrank communications by their own terms. **This disclosure is
written to the stricter reading and does not depend on any carve-out.**

Two clauses govern, and they apply to different things:

- **Entry requirements** — the Submission must be *"original to the Contest (i.e. was not developed
  in any substantive form/format prior to the Contest)."*
- **Intellectual Property Rights** — *"Your team may bring to the Event any pre-developed or
  licensed Technology that you plan to use in connection with your prototype."*

**This submission satisfies both.** All of `src/**` — every module the reviewer actually runs — was
built during the hackathon window. The material below is a **pre-prepared synthetic sample**,
disclosed as such, and brought in under the IP-Rights clause. **No submission logic is
prior-developed.**

## Pre-existing, disclosed

| Path | Origin | Role | Class |
|---|---|---|---|
| `demo/vulnerable_app.py` | pre-prepared synthetic sample | the planted-vulnerability target | synthetic sample code |

⚠ **A second row was removed from this table, and the reason is the point.** It listed
`demo/test_vulnerable_app.py` — *"harness proving the target is catchable."* **A harness that proves
the target is catchable NAMES THE FLAW.** Shipping it in `demo/` would put the answer in the same
directory as the subject and hand it to every reviewer that reads the tree. Both it and the twin
live **outside this repository**:

| Artifact | Where | Why there |
|---|---|---|
| the target | `demo/vulnerable_app.py` — **here** | it is the subject, and it names nothing |
| the twin | outside, `C:\secreview-twin\` | two files in one tree make `diff` on the pair the answer key |
| the catchability proof | outside, `C:\secreview-twin\` | it names the flaw in plain words |

`prove_bites` takes the twin as a **string supplied by the caller**, who reads it from outside.
**The rule: an artifact that describes a graded target's defect is not reachable from the graded
target's own repository** — by path, by import, or by `diff`.

## Built during the hackathon window

`src/**` — all core project logic. `bob_sessions/**` — Bob IDE task-session exports.

## The two submission requirements, and which half we have

The entry requirements ask for **both** an **exported IBM Bob report** of all relevant
tasks/sessions **and** **screenshots**. They are two requirements, not one.

- **Export — ✅ present:** `bob_sessions/`, below. Produced by Bob IDE's own Export Task History.
- **Screenshots — ⏳ outstanding:** session captures are taken separately and belong in
  `bob_sessions/` alongside the exports.

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
