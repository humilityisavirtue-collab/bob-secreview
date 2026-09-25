# bob-secreview

An AI code reviewer that must **earn** a clean verdict before it is allowed to
report one — and that must prove it can catch a planted vulnerability before any
clean result from it counts.

Built during the IBM Bob 2.0 Hackathon (2026-09-25 .. 2026-09-27) with IBM Bob as
the reviewing intelligence.

Status: **in progress.**

## The judging artifact

Per the hackathon rule, the Bob IDE task-session report is exported for judging. It
lives in `bob_sessions/` in two renderings, and **the JSON is the record**:

| File | What it is |
|---|---|
| `bob_sessions/bob-tasks-secreview-bob-2026-09-25.json` | **The complete record.** 8 sessions, 346 messages. Read this one. |
| `bob_sessions/bob-tasks-secreview-bob-2026-09-25.md` | The readable view. Partial — **omits tool outputs and system messages.** |

The Markdown is easier to read and the JSON is complete; the Markdown's omissions are
described in [`DISCLOSURE.md`](DISCLOSURE.md). If you only follow one pointer, follow
the JSON.

## Verifying what is actually published

A green `git push` reports that a push happened. It does **not** report what a judge
receives. The served bytes are the artifact — compare them, and check the repo the way
someone with no session sees it:

Three checks, in order of authority:

```bash
# 1. Did the push land?  The remote REF is authoritative.
git ls-remote origin refs/heads/master            # must equal your local HEAD

# 2. Is the remote tree what you committed?
git fetch -q origin master
git cat-file -p origin/master:src/chunk.py | sha256sum
sha256sum src/chunk.py                            # must match

# 3. Is the repo public?  A logged-in session sees what a judge cannot.
curl -sS -o /dev/null -w '%{http_code}\n' \
     https://github.com/humilityisavirtue-collab/bob-secreview     # must be 200
```

⚠ **`raw.githubusercontent.com` is eventually consistent and serves the PREVIOUS revision
for a period after a push** — query-string cache-busters do not defeat it.

Measured 2026-09-25: a served-bytes comparison (`curl` the raw URL and `sha256sum` it) reported
a difference that was **purely propagation lag**. `ls-remote`, the fetched remote tree, and the
GitHub API all agreed with local throughout; only the raw CDN was stale, and it stayed stale
across three attempts. Use the raw URL to *inspect* content; **do not use it to conclude a push
failed.**

## Proving a check can fail

`tests/arms.py` asserts two invariants that `src/` must satisfy. A check that cannot fail
proves nothing, so the harness is run against **two** subjects — the current code, and an
earlier unfixed revision recovered from git history:

```bash
mkdir -p /tmp/prefix
git show b7a3ecb:src/findings.py > /tmp/prefix/findings.py
git show 8eb7be3:src/chunk.py    > /tmp/prefix/chunk.py

python tests/arms.py src          # must pass
python tests/arms.py /tmp/prefix  # must FAIL, and name the arm
```

A pass on the fixed code alone cannot distinguish *"the fix works"* from *"the harness
stopped looking."* The failure on the unfixed revision is the only thing that makes the
pass mean anything.
