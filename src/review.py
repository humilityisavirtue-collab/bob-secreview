"""src/review.py — review engine for source files.

Chunks a source file, sends each chunk out for review via a callable client,
and maps chunk-relative findings back to absolute line numbers.

Spend-cap guarantee
-------------------
The total cost of a review run never exceeds `max_cost`. This is enforced by
two complementary mechanisms:

1. **Pre-call affordability check**: before every chunk call the engine
   computes the remaining budget (`max_cost - total_cost`). If that remainder
   is strictly less than `per_call_ceiling`, the call does not begin and the
   result is marked truncated. The call is *refused*, not started-then-capped.

2. **Per-call provider limit**: the engine passes
   `per_call_cap = min(per_call_ceiling, max_cost - total_cost)` to the
   client as its second argument. The client is expected to forward this as the
   provider's own per-call spend limit (e.g. OpenAI's `max_tokens` budget or
   an equivalent hard ceiling). The provider enforces it at the call boundary.
   This is the mechanism — naming an outcome without the mechanism was the
   defect this design replaces.

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
# Type alias: a client is any callable (prompt, per_call_cap) -> (response_text, cost_in_coins)
# ---------------------------------------------------------------------------

ReviewClient = Callable[["str, float"], "tuple[str, float]"]

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
    per_call_ceiling: float,
    chunk_lines: int = 300,
    overlap_lines: int = 30,
) -> "ScanResult":
    """
    Review `source` by chunking it and sending each chunk to `client`.

    `max_cost` is required and keyword-only. Raises ValueError if None or <= 0.
    `per_call_ceiling` is required and keyword-only. Raises ValueError if None or <= 0.
    It is the maximum a single call is allowed to cost; the engine refuses to
    start any call for which the worst case cannot be afforded.

    The client signature is: (prompt: str, per_call_cap: float) -> (response_text, cost).
    `per_call_cap = min(per_call_ceiling, max_cost - total_cost)` is passed on
    every call so the provider can enforce it at its boundary.
    """
    if max_cost is None or max_cost <= 0:
        raise ValueError(f"max_cost must be > 0, got {max_cost!r}")
    if per_call_ceiling is None or per_call_ceiling <= 0:
        raise ValueError(f"per_call_ceiling must be > 0, got {per_call_ceiling!r}")

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
    chunks_failed: int = 0

    for chunk in chunks:
        # Pre-call affordability check: refuse if the worst case cannot be afforded.
        # If the remaining budget is less than per_call_ceiling, the call does not begin.
        remaining = max_cost - total_cost
        if remaining < per_call_ceiling:
            result.truncated = True
            break

        per_call_cap = min(per_call_ceiling, remaining)
        prompt = _build_prompt(chunk, file)
        try:
            response_text, cost = client(prompt, per_call_cap)
        except Exception as exc:
            # A failing chunk is NOT zero findings — record incomplete state.
            # A failure is not a review: increment chunks_failed, not chunks_reviewed.
            chunks_failed += 1
            error_msg = f"chunk {chunk.index} failed: {exc}"
            result.error = (result.error + "; " + error_msg) if result.error else error_msg
            continue

        total_cost += cost

        try:
            new_findings = _parse_findings(response_text, chunk, file)
        except Exception as exc:
            # Parse failure: the response was received but we cannot extract findings from it.
            # This counts as a failure, not as a review — a client returning prose rather than
            # JSON must not produce a result that appears fully reviewed with zero findings.
            # NOTE: `error` is intentionally left set here and is NOT redundant: it is the
            # clause that keeps an unparseable run legible as incomplete. Do not remove it
            # as "tidying" — that would silently re-open the vacuous-clean path this module
            # exists to prevent.
            chunks_failed += 1
            error_msg = f"chunk {chunk.index} parse error: {exc}"
            result.error = (result.error + "; " + error_msg) if result.error else error_msg
            continue

        # Only count a chunk as reviewed once we actually hold its parsed output.
        chunks_reviewed += 1

        for f in new_findings:
            key = (f.rule_id, f.location.line_start, f.title)
            if key not in seen:
                seen.add(key)
                result.findings.append(f)

    result.chunks_reviewed = chunks_reviewed
    result.chunks_failed = chunks_failed
    result.total_cost = total_cost
    result.max_cost = max_cost

    return result


def review_file(
    path: "str | os.PathLike",
    client: ReviewClient,
    *,
    max_cost: float,
    per_call_ceiling: float,
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
        per_call_ceiling=per_call_ceiling,
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

    def fake_client_absolute(prompt: str, per_call_cap: float) -> tuple[str, float]:
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
                               per_call_ceiling=1.0,
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
    # Both chunks report a finding at their relative line that maps to abs-31.
    # chunk0 rel-31 -> abs-31; chunk1 rel-1 -> abs-31 → deduplicated.

    def fake_client_dedup(prompt: str, per_call_cap: float) -> tuple[str, float]:
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
                                 per_call_ceiling=1.0,
                                 chunk_lines=40, overlap_lines=10)
    dup_findings = [f for f in result_dedup.findings
                    if f.rule_id == "dup-rule" and f.location.line_start == 31]
    check("overlap de-duplication: dup finding reported once",
          len(dup_findings) == 1)

    # ------------------------------------------------------------------
    # Test 3: budget stop sets truncated=True and chunks_reviewed < chunks_total
    # ------------------------------------------------------------------
    # 3+ chunks; each call costs 1.0; cap = 1.5, per_call_ceiling=1.0
    # After first chunk (cost 1.0), remaining = 0.5 < per_call_ceiling=1.0 → stop.
    src_budget = make_source(120)  # 120 lines → multiple chunks (40-line, overlap 10)

    costs_incurred: list[float] = []

    def fake_client_costly(prompt: str, per_call_cap: float) -> tuple[str, float]:
        costs_incurred.append(1.0)
        return "[]", 1.0

    result_budget = review_source(src_budget, fake_client_costly,
                                  file="test.py", max_cost=1.5,
                                  per_call_ceiling=1.0,
                                  chunk_lines=40, overlap_lines=10)
    check("budget stop: truncated is True",
          result_budget.truncated is True)
    check("budget stop: chunks_reviewed < chunks_total",
          result_budget.chunks_reviewed < result_budget.chunks_total)
    check("budget stop: cap not exceeded",
          sum(costs_incurred) <= 1.5)

    # ------------------------------------------------------------------
    # Test 4: failing client leaves result NOT reading as clean
    # ------------------------------------------------------------------
    def fake_client_raises(prompt: str, per_call_cap: float) -> tuple[str, float]:
        raise RuntimeError("Simulated client failure")

    result_fail = review_source(make_source(10), fake_client_raises,
                                file="test.py", max_cost=10.0,
                                per_call_ceiling=1.0,
                                chunk_lines=40, overlap_lines=10)
    check("failing client: error field is set (not None/empty)",
          bool(result_fail.error))
    check("failing client: chunks_failed == chunks_total",
          result_fail.chunks_failed == result_fail.chunks_total)
    check("failing client: chunks_reviewed == 0",
          result_fail.chunks_reviewed == 0)
    check("failing client: may_report_clean() is False",
          result_fail.may_report_clean() is False)

    # ------------------------------------------------------------------
    # Test 5: may_report_clean() is True only for a complete, failure-free review
    # ------------------------------------------------------------------
    def fake_client_ok(prompt: str, per_call_cap: float) -> tuple[str, float]:
        return "[]", 0.01

    result_clean = review_source(make_source(10), fake_client_ok,
                                 file="test.py", max_cost=10.0,
                                 per_call_ceiling=1.0,
                                 chunk_lines=40, overlap_lines=10)
    check("may_report_clean(): True when complete and no failures",
          result_clean.may_report_clean() is True)

    # ------------------------------------------------------------------
    # Test 6: max_cost and per_call_ceiling validation
    # ------------------------------------------------------------------
    raised_none = False
    try:
        review_source("x", fake_client_ok, file="t.py", max_cost=None,  # type: ignore
                      per_call_ceiling=1.0)
    except ValueError:
        raised_none = True
    check("max_cost=None raises ValueError", raised_none)

    raised_neg = False
    try:
        review_source("x", fake_client_ok, file="t.py", max_cost=-1.0,
                      per_call_ceiling=1.0)
    except ValueError:
        raised_neg = True
    check("max_cost<=0 raises ValueError", raised_neg)

    raised_pcc_none = False
    try:
        review_source("x", fake_client_ok, file="t.py", max_cost=1.0,
                      per_call_ceiling=None)  # type: ignore
    except ValueError:
        raised_pcc_none = True
    check("per_call_ceiling=None raises ValueError", raised_pcc_none)

    raised_pcc_neg = False
    try:
        review_source("x", fake_client_ok, file="t.py", max_cost=1.0,
                      per_call_ceiling=0.0)
    except ValueError:
        raised_pcc_neg = True
    check("per_call_ceiling<=0 raises ValueError", raised_pcc_neg)

    print()
    if failures:
        print(f"{failures} check(s) FAILED.")
        sys.exit(1)
    else:
        print("All checks passed.")
        sys.exit(0)
