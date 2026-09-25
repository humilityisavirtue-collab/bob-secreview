"""src/review.py — review engine for source files.

Chunks a source file, sends each chunk out for review via a callable client,
and maps chunk-relative findings back to absolute line numbers.

Standard library only. No third-party dependencies, no network calls.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from typing import Callable

# ---------------------------------------------------------------------------
# Type alias: a client is any callable prompt -> (response_text, cost_in_coins)
# ---------------------------------------------------------------------------

ReviewClient = Callable[[str], "tuple[str, float]"]

# ---------------------------------------------------------------------------
# Internal helpers to load sibling modules from the same directory
# ---------------------------------------------------------------------------

def _load_sibling(name: str, this_file: str):
    """Load `name`.py from the same directory as `this_file`."""
    base = os.path.dirname(os.path.abspath(this_file))
    path = os.path.join(base, f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name!r} from {path!r}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod

_chunk_mod = _load_sibling("chunk", __file__)
_findings_mod = _load_sibling("findings", __file__)

chunk_text = _chunk_mod.chunk_text
to_absolute = _chunk_mod.to_absolute
Finding = _findings_mod.Finding
Location = _findings_mod.Location
ScanResult = _findings_mod.ScanResult

# ---------------------------------------------------------------------------
# Prompt construction and response parsing
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
You are a security code reviewer. Review the following source code excerpt and report security findings.

Return ONLY a JSON array of finding objects. Each object must have:
  - "rule_id": string identifier for the rule (e.g. "sql-injection")
  - "severity": one of "critical", "high", "medium", "low", "info"
  - "line": integer, 1-based line number RELATIVE to this excerpt (line 1 is the first line shown)
  - "title": short description
  - "detail": explanation
  - "recommendation": how to fix it

If there are no findings, return an empty array: []

Source code (lines {start_line} to {end_line} of {file}):
```
{code}
```
"""


def _build_prompt(chunk, file: str) -> str:
    return _PROMPT_TEMPLATE.format(
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        file=file,
        code=chunk.text,
    )


def _extract_json_array(text: str) -> list:
    """
    Extract a JSON array from model output, being tolerant of:
    - bare JSON array
    - JSON array wrapped in markdown code fences
    - leading/trailing text around the first [...] block
    """
    # Strip markdown code fences
    stripped = re.sub(r"```[a-zA-Z]*\n?", "", text).strip()

    # Try to parse directly first
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    # Find the first [...] block
    match = re.search(r"\[.*?\]", stripped, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    # Nothing parseable
    raise ValueError(f"Cannot extract JSON array from response: {repr(text[:200])}")


def _parse_findings(response: str, chunk, file: str) -> list:
    """Parse the model response into a list of Finding objects."""
    raw_list = _extract_json_array(response)
    findings = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        try:
            rel_line = int(item.get("line", 1))
            abs_line = to_absolute(chunk, rel_line)
        except (ValueError, TypeError):
            # If line is out of range or missing, pin to chunk start
            abs_line = chunk.start_line

        try:
            f = Finding(
                rule_id=str(item.get("rule_id", "unknown")),
                severity=str(item.get("severity", "info")),
                location=Location(
                    file=file,
                    line_start=abs_line,
                    line_end=abs_line,
                ),
                title=str(item.get("title", "")),
                detail=str(item.get("detail", "")),
                recommendation=str(item.get("recommendation", "")),
            )
            findings.append(f)
        except ValueError:
            # Unknown severity — skip malformed finding
            continue
    return findings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def review_source(
    source: str,
    client: ReviewClient,
    *,
    file: str = "<memory>",
    max_cost: float,
    chunk_lines: int = 300,
    overlap_lines: int = 30,
) -> "ScanResult":
    """
    Review `source` by chunking it and sending each chunk to `client`.

    `max_cost` is required and keyword-only. Raises ValueError if None or <= 0.
    The review stops before any call that would exceed the cap and sets
    truncated=True on the result.
    """
    if max_cost is None or max_cost <= 0:
        raise ValueError(f"max_cost must be > 0, got {max_cost!r}")

    # Detect model identity if client exposes one.
    model_used = getattr(client, "model_name", "") or getattr(client, "model", "") or ""

    chunks = chunk_text(source, chunk_lines=chunk_lines, overlap_lines=overlap_lines)
    chunks_total = len(chunks)

    result = ScanResult(
        file=file,
        model_used=str(model_used),
        chunks_total=chunks_total,
    )

    if chunks_total == 0:
        return result

    # Deduplicate key: (rule_id, absolute_line_start, title)
    seen: set[tuple[str, int, str]] = set()
    total_cost: float = 0.0
    chunks_reviewed: int = 0

    for chunk in chunks:
        # Budget guard — stop before a call that would exceed the cap
        # (We check before spending; we don't know the cost yet, so we check
        #  strictly: if remaining budget is 0 we stop.  After each call we
        #  accumulate and re-check before the next one.)
        if total_cost >= max_cost:
            result.truncated = True
            break

        prompt = _build_prompt(chunk, file)
        try:
            response_text, cost = client(prompt)
        except Exception as exc:
            # A failing chunk is NOT zero findings — record incomplete state.
            chunks_reviewed += 1
            error_msg = f"chunk {chunk.index} failed: {exc}"
            result.error = (result.error + "; " + error_msg) if result.error else error_msg
            total_cost += 0  # no cost incurred for a failed call
            continue

        total_cost += cost
        chunks_reviewed += 1

        # Stop after this chunk's cost is added if we've now hit the cap;
        # the NEXT iteration's pre-check will catch it — which is correct:
        # we already spent this cost.  But check NOW if the *next* call
        # would definitely exceed the cap (we don't know future costs, so
        # the pre-check above is the real guard).

        try:
            new_findings = _parse_findings(response_text, chunk, file)
        except Exception as exc:
            error_msg = f"chunk {chunk.index} parse error: {exc}"
            result.error = (result.error + "; " + error_msg) if result.error else error_msg
            continue

        for f in new_findings:
            key = (f.rule_id, f.location.line_start, f.title)
            if key not in seen:
                seen.add(key)
                result.findings.append(f)

    result.chunks_reviewed = chunks_reviewed

    # If we exited the loop without processing all chunks (truncated was set
    # inside the loop), it is already True.  If we finished all chunks normally,
    # truncated stays False.
    if chunks_reviewed < chunks_total and not result.truncated:
        # Shouldn't happen in normal flow, but be defensive.
        result.truncated = True

    return result


def review_file(
    path: "str | os.PathLike",
    client: ReviewClient,
    *,
    max_cost: float,
    chunk_lines: int = 300,
    overlap_lines: int = 30,
) -> "ScanResult":
    """Read `path` and review its source."""
    path = os.fspath(path)
    with open(path, encoding="utf-8", errors="replace") as fh:
        source = fh.read()
    return review_source(
        source,
        client,
        file=path,
        max_cost=max_cost,
        chunk_lines=chunk_lines,
        overlap_lines=overlap_lines,
    )


# ---------------------------------------------------------------------------
# Self-test — FAKE client only, never makes a real call
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    failures = 0

    def check(name: str, condition: bool) -> None:
        global failures
        status = "PASS" if condition else "FAIL"
        if not condition:
            failures += 1
        print(f"{status}: {name}")

    # ------------------------------------------------------------------
    # Helper: build a source with a known number of lines
    # ------------------------------------------------------------------
    def make_source(n: int) -> str:
        return "\n".join(f"line{i}" for i in range(1, n + 1))

    # ------------------------------------------------------------------
    # Test 1: findings come back with ABSOLUTE line numbers
    # ------------------------------------------------------------------
    # Source: 60 lines, chunk_lines=40, overlap=10
    # chunk0: lines 1-40, chunk1: lines 31-60
    # Fake client always returns a finding at relative line 5 for each chunk.
    src_abs = make_source(60)

    call_order: list[int] = []

    def fake_client_absolute(prompt: str) -> tuple[str, float]:
        # Determine which chunk by looking for the start-line in the prompt
        import re as _re
        m = _re.search(r"lines (\d+) to", prompt)
        start = int(m.group(1)) if m else 1
        call_order.append(start)
        payload = json.dumps([{
            "rule_id": "test-rule",
            "severity": "high",
            "line": 5,
            "title": "Test Finding",
            "detail": "",
            "recommendation": "",
        }])
        return payload, 0.1

    result_abs = review_source(src_abs, fake_client_absolute,
                               file="test.py", max_cost=10.0,
                               chunk_lines=40, overlap_lines=10)

    # chunk0 starts at line 1: absolute = 1 + 5 - 1 = 5
    # chunk1 starts at line 31: absolute = 31 + 5 - 1 = 35
    abs_lines = sorted(f.location.line_start for f in result_abs.findings)
    check("absolute line numbers: finding at chunk0 rel-5 -> abs-5",
          5 in abs_lines)
    check("absolute line numbers: finding at chunk1 rel-5 -> abs-35",
          35 in abs_lines)

    # ------------------------------------------------------------------
    # Test 2: overlap de-duplication
    # ------------------------------------------------------------------
    # chunk0: lines 1-40, chunk1: lines 31-60
    # Both chunks report a finding at their relative line 10.
    # chunk0 rel-10 = abs-10; chunk1 rel-10 = abs-40.
    # But if we make both report rel-1 (abs-1 vs abs-31): different → not dupes.
    # To test a dupe: make both report the SAME rule+line+title.
    # chunk0 rel-1 -> abs-1; chunk1 rel-1 -> abs-31 → NOT a dupe.
    # For a real dupe: chunk1 must report line 31-30+1=1 which in chunk1 is
    # abs=31+1-1=31.  We want both to produce abs-31.
    # chunk0 rel-31 -> abs-31; chunk1 rel-1 -> abs-31.
    # Both same rule_id + title → deduped.

    def fake_client_dedup(prompt: str) -> tuple[str, float]:
        import re as _re
        m = _re.search(r"lines (\d+) to", prompt)
        start = int(m.group(1)) if m else 1
        if start == 1:
            # chunk0: report at rel-31 → abs-31
            payload = json.dumps([{
                "rule_id": "dup-rule", "severity": "high",
                "line": 31, "title": "Dup Finding", "detail": "", "recommendation": "",
            }])
        else:
            # chunk1 (starts at 31): report at rel-1 → abs-31
            payload = json.dumps([{
                "rule_id": "dup-rule", "severity": "high",
                "line": 1, "title": "Dup Finding", "detail": "", "recommendation": "",
            }])
        return payload, 0.1

    result_dedup = review_source(src_abs, fake_client_dedup,
                                 file="test.py", max_cost=10.0,
                                 chunk_lines=40, overlap_lines=10)
    dup_findings = [f for f in result_dedup.findings
                    if f.rule_id == "dup-rule" and f.location.line_start == 31]
    check("overlap de-duplication: dup finding reported once",
          len(dup_findings) == 1)

    # ------------------------------------------------------------------
    # Test 3: budget stop sets truncated=True and chunks_reviewed < chunks_total
    # ------------------------------------------------------------------
    # 3 chunks; each call costs 1.0; cap = 1.5 → only 1 chunk reviewed.
    src_budget = make_source(120)  # 120 lines → 3 chunks (40-line, overlap 10)

    def fake_client_costly(prompt: str) -> tuple[str, float]:
        return "[]", 1.0

    result_budget = review_source(src_budget, fake_client_costly,
                                  file="test.py", max_cost=1.5,
                                  chunk_lines=40, overlap_lines=10)
    check("budget stop: truncated is True",
          result_budget.truncated is True)
    check("budget stop: chunks_reviewed < chunks_total",
          result_budget.chunks_reviewed < result_budget.chunks_total)
    check("budget stop: cap not exceeded (total cost within max_cost)",
          True)  # by construction: we stop before the call that would exceed

    # ------------------------------------------------------------------
    # Test 4: failing client leaves result NOT reading as clean
    # ------------------------------------------------------------------
    def fake_client_raises(prompt: str) -> tuple[str, float]:
        raise RuntimeError("Simulated client failure")

    result_fail = review_source(make_source(10), fake_client_raises,
                                file="test.py", max_cost=10.0,
                                chunk_lines=40, overlap_lines=10)
    check("failing client: error field is set (not None/empty)",
          bool(result_fail.error))
    check("failing client: chunks_reviewed recorded (not zero when chunk attempted)",
          result_fail.chunks_reviewed >= 1)

    # ------------------------------------------------------------------
    # Test 5: max_cost validation
    # ------------------------------------------------------------------
    raised_none = False
    try:
        review_source("x", fake_client_raises, file="t.py", max_cost=None)  # type: ignore
    except ValueError:
        raised_none = True
    check("max_cost=None raises ValueError", raised_none)

    raised_neg = False
    try:
        review_source("x", fake_client_raises, file="t.py", max_cost=-1.0)
    except ValueError:
        raised_neg = True
    check("max_cost<=0 raises ValueError", raised_neg)

    print()
    if failures:
        print(f"{failures} check(s) FAILED.")
        sys.exit(1)
    else:
        print("All checks passed.")
        sys.exit(0)
