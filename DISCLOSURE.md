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
| the twin | **outside this repository** | two files in one tree make `diff` on the pair the answer key |
| the catchability proof | **outside this repository** | it names the flaw in plain words |

**Their location is deliberately not recorded here.** Naming a path is a pointer, and a pointer into
the answer key is reachable from inside the working tree even when the file is not in the repository
— a session running in this workspace can open an absolute path. *Gitignoring protects the
repository; it does not protect the instrument.* The twin exists, it is maintained outside, and
`prove_bites` takes it as a **string supplied by the caller**.

**The rule: an artifact that describes a graded target's defect must not be reachable from the
graded target's own repository** — not by path, not by import, and not by `diff`.

## Built during the hackathon window

`src/**` — all core project logic. `bob_sessions/**` — Bob IDE task-session exports and
consumption-summary screenshots.

### Which parts were Bob task sessions, and which were in-window hand work

**The split is stated plainly rather than summarised, because it is checkable against the
export and a flat claim would be false.** Every Bob session is a row in Bob's own task
store, and its transcript is in `bob_sessions/`.

**Bob task sessions.** Increments 1–7 of the build were carried out as Bob sessions —
`findings.py`, `chunk.py`, the paired defect fixes, `review.py`, the coverage hardening,
the parse-path fix, and `prove_bites.py`. Each is a distinct task with its own transcript,
and all of them are **inside the exported record**.

**Bob was also the author of the problem analysis.** A High-severity weakness — one we had
not identified — was found by Bob while reviewing our work, and was corrected in this
window. That finding is Bob's, not ours, and it is the clearest evidence in this submission
that Bob did analysis rather than transcription.

**In-window hand work.** A number of later changes were written directly, in the hackathon
window, without a Bob session:

| Change | Why it is hand work |
|---|---|
| the margin/baseline repair in `prove_bites.py` | the corresponding Bob runs terminated on the cost cap before producing it |
| the `report.py` entry-point dispatch fix | found after its session ended |
| the `bob_client` model-id guard | found by running the client, not by a session |
| `ARM-6`, the subprocess entry-point arm | added with the dispatch fix |
| the twin and the catchability proof | `demo/`-independent, and deliberately **outside this repository** |
| canonical `rule_id` comparison (`_canon_rule_id`) | written in-window; the hazard it closes was **named by Bob** |

**Why this does not affect eligibility.** The Official Rules constrain *when* code was
written — it must not have existed in substantive form before the Contest — not *which tool
typed it*. In-window hand work satisfies that on the same footing as a session, and Bob
remains the core component of the submission either way.

**There are two session records, and they are not the same kind of artifact.**

The IDE's own Export Task History produced the **first**. It **cannot produce the second**:
Windows paths are case-insensitive, so the IDE resolves both spellings of this workspace to
the one registered project, and Bob Shell 2.0.5 exposes no export command (`chat`, `run`,
`mcp`, `acp`). Three separate attempts each returned the same first bucket. **That is a
property of the tool, not a defect in the work.**

So the second is **rendered** from Bob's own task store — `~/.bob/db/bob.db`, the same source
`exportProject` reads — carrying the same rows and messages the IDE would have emitted.
⚠ **Nothing was renamed in that store.** Merging the buckets by editing `project_id` would
have altered Bob's own record and destroyed the very fork that makes this explanation true.

**The rendering is verified, not asserted.** Pointed at the *first* bucket, the renderer
reproduces the IDE's own export **field-exact: zero value differences across all 8 tasks and
346 messages, with only the top-level export timestamp differing** — necessarily, since that
timestamp is generated at render time.

⚠ **The claim is "field-exact", not "byte-for-byte", and the difference is worth stating.**
Canonicalised as `sha256(json.dumps(tasks, sort_keys=True))` the two tasks arrays are equal —
`62153495433172022415d6a9931ea3a7ad05b4b4` — but the two writers emit **dict keys in different
insertion orders**, so the raw file bytes are *not* identical. A byte comparison would fail
while the data is the same. **The equality is by field; that is the claim a reader can check,
and the stronger one would not survive being checked.**

Two independent instruments agree on this: the author's, and an independent reproduction by a
second seat on a copy of the renderer (never the original), compared in memory before the write,
because pointed at the first bucket the renderer's own sweep correctly refuses to write.

| file | kind | tasks | messages |
|---|---|---|---|
| `bob-tasks-secreview-bob-2026-09-25.json` | **IDE export** | 8 | 346 |
| `bob-tasks-secreview-bob-CAPITAL-C_rendered.json` | **rendered** from Bob's store | 12 | 460 |

**Together: all 20 sessions and 806 messages of Bob work.**

⚠ **The second record includes four tasks that ended in `error`, three of them
`MaxCostReachedError`.** These are **deliberately kept.** They are the spend cap doing the
thing it claims to do, in Bob's own artifact: the runs stopped because they reached the
limit they were given. Removing them would leave a gap that looks like concealment; keeping
them shows a guard that fired. A record is not tidied.

## The two submission requirements, and which half we have

The entry requirements ask for **both** an **exported IBM Bob report** of all relevant
tasks/sessions **and** **screenshots**. They are two requirements, not one.

- **Export — ✅ present:** `bob_sessions/`, below. Produced by Bob IDE's own Export Task History.
- **Screenshots — ✅ present:** `bob_sessions/captures/` — **16 PNGs**, one per task, each a
  capture of the IDE's own "task session consumption summary" panel. Of the sessions in this
  workspace, 20 produced a consumption summary; **4 were transport smoke tests** with no work
  in them and are excluded. Each frame was paired to its task by reading the panel's own
  `Task Id` and `Workspace` fields — **not by capture order** — and `captures_manifest.csv`
  records the task id, workspace, coins and sha256 of every frame.

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
