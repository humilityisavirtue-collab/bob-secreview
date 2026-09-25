# bob-secreview

An AI code reviewer that must **earn** a clean verdict before it is allowed to
report one — and that must prove it can catch a planted vulnerability before any
clean result from it counts.

Built during the IBM Bob 2.0 Hackathon (2026-09-25 .. 2026-09-27) with IBM Bob as
the reviewing intelligence.

Status: **in progress.**

## Verifying what is actually published

A green `git push` reports that a push happened. It does **not** report what a judge
receives. The served bytes are the artifact — compare them, and check the repo the way
someone with no session sees it:

```bash
R=https://raw.githubusercontent.com/humilityisavirtue-collab/bob-secreview/master
curl -sS "$R/src/chunk.py" -o served.py && sha256sum served.py src/chunk.py   # must match
curl -sS -o /dev/null -w '%{http_code}\n' \
     https://github.com/humilityisavirtue-collab/bob-secreview                 # must be 200
```

Run this before claiming anything is published. "The URL resolved" and "the content is
current" are different claims.

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
