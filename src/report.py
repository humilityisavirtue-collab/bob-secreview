"""src/report.py -- the front door: run a real review and print a verdict.

Two invocations, both from the repo root:

    python -m src.report --target <file> --twin <path> --planted <rule_id> \
           --max-cost 2 --per-call-ceiling 1
    python -m src.report --target <file> --max-cost 2 --per-call-ceiling 1

``python src/report.py ...`` also works (the module resolves siblings by path).

 --max-cost and --per-call-ceiling are required with NO default.  Omitting
either -> usage error naming the missing flag, non-zero exit, no call made.

Standard library only.  No third-party dependencies.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys


# ---------------------------------------------------------------------------
# Sibling loader -- works whether invoked as `python src/report.py` or
# `python -m src.report` (the latter changes __package__ and __file__).
# ---------------------------------------------------------------------------

def _load_sibling(name: str) -> object:
    """Load `name`.py from the same directory as THIS file."""
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name!r} from {path!r}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Bob-client adapter -- imported LAZILY inside build_bob_client() so that
# --help, the self-test, and any path that never calls the provider can run
# without a key and without importing bob_client at module load time.
# ---------------------------------------------------------------------------

def build_bob_client(
    *,
    max_turns: int | None = None,
    workspace: str | None = None,
) -> "tuple[object, callable]":
    """Return (bob_client_module, adapter).

    The adapter matches the ReviewClient protocol:
        (prompt: str, per_call_cap: float) -> (text: str, cost: float)

    per_call_cap is passed to the provider as max_cost so the provider
    enforces the per-call ceiling -- a client-side check alone promises nothing.
    """
    import importlib  # standard library -- already imported above, but explicit here
    bc = importlib.import_module("src.bob_client")  # try package import first
    # Fall back to sibling-path load if the package import fails (e.g. when
    # invoked as `python src/report.py` with no package context).
    if bc is None:
        bc = _load_sibling("bob_client")

    def adapter(prompt: str, per_call_cap: float) -> "tuple[str, float]":
        # Pass per_call_cap to the provider via max_cost so the provider
        # enforces the limit.  A check that never reaches the provider is
        # not a limit.
        text = bc.chat(
            [{"role": "user", "content": prompt}],
            max_cost=per_call_cap,
            max_turns=max_turns,
            workspace=workspace,
        )
        cost = float(bc.LAST_STATS.get("session_costs", 0.0))
        return text, cost

    return bc, adapter


# ---------------------------------------------------------------------------
# Argument parsing -- required caps have no default
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="report",
        description="Run a real security review and print a verdict.",
    )
    p.add_argument("--target",          required=True,
                   help="File to review (read from disk).")
    p.add_argument("--twin",            default=None,
                   help="Clean twin file path (outside the repo). Optional.")
    p.add_argument("--planted",         default=None,
                   help="Rule ID planted in the target. Optional.")
    p.add_argument("--max-cost",        dest="max_cost",    type=float, default=None,
                   help="[REQUIRED] Total spend cap.")
    p.add_argument("--per-call-ceiling", dest="per_call_ceiling", type=float, default=None,
                   help="[REQUIRED] Max cost of any single call.")
    p.add_argument("--max-turns",       dest="max_turns",   type=int, default=None,
                   help="Max turns passed to the provider. Optional.")
    p.add_argument("--workspace",       default=None,
                   help="Workspace directory for the provider session. Optional.")
    return p


def _check_required_caps(args: argparse.Namespace) -> list[str]:
    """Return a list of error messages for missing required cap flags."""
    errors = []
    if args.max_cost is None:
        errors.append("--max-cost is required (no default; every chunk is a paid call)")
    if args.per_call_ceiling is None:
        errors.append("--per-call-ceiling is required (no default; every chunk is a paid call)")
    return errors


# ---------------------------------------------------------------------------
# Report formatter -- writes to stdout; diagnostics to stderr
# ---------------------------------------------------------------------------

def _print_report(
    *,
    target: str,
    planted: str | None,
    scan_result: object,
    proof: object | None,
) -> None:
    """Write the one-screen report to stdout."""
    lines = []

    lines.append("=" * 72)
    lines.append(f"SECURITY REVIEW REPORT")
    lines.append(f"  target : {target}")
    lines.append("=" * 72)

    # --- Verdict ---
    if proof is not None:
        verdict = proof.status            # "BITES" | "DOES_NOT_BITE" | "INCONCLUSIVE"
        reason  = getattr(proof, "reason", "")
    else:
        # No prove_bites run (no --planted); show the scan summary only.
        verdict = "N/A"
        reason  = "no --planted rule specified"

    lines.append("")
    lines.append(f"VERDICT : {verdict}")
    if reason:
        lines.append(f"  reason: {reason}")

    # --- Twin ratios (always print when proof was run) ---
    if proof is not None:
        twin_ratio     = getattr(proof, "twin_ratio", -1.0)
        twin_baseline  = getattr(proof, "twin_ratio_baseline", -1.0)
        if twin_ratio >= 0.0 and twin_baseline >= 0.0:
            margin = twin_ratio - twin_baseline
            lines.append("")
            lines.append("TWIN SIMILARITY")
            lines.append(f"  twin_ratio          : {twin_ratio:.4f}")
            lines.append(f"  twin_ratio_baseline : {twin_baseline:.4f}")
            lines.append(f"  margin              : {margin:+.4f}")
        else:
            lines.append("")
            lines.append("TWIN SIMILARITY : not computed (no twin or INCONCLUSIVE before twin step)")

    # --- Findings ---
    findings = getattr(scan_result, "findings", []) or []
    lines.append("")
    lines.append(f"FINDINGS ({len(findings)})")
    if findings:
        for f in sorted(findings):
            loc = f.location
            lines.append(
                f"  [{f.severity.upper():8s}] {f.rule_id}  "
                f"{loc.file}:{loc.line_start}  {f.title}"
            )
    else:
        lines.append("  (none)")

    # --- Coverage ---
    lines.append("")
    lines.append("COVERAGE")
    lines.append(f"  chunks_reviewed : {scan_result.chunks_reviewed}"
                 f" / {scan_result.chunks_total}  (failed: {scan_result.chunks_failed})")
    lines.append(f"  truncated       : {scan_result.truncated}")
    lines.append(f"  may_report_clean: {scan_result.may_report_clean()}")
    lines.append(f"  total_cost      : {scan_result.total_cost:.6f}")
    lines.append(f"  max_cost cap    : {scan_result.max_cost:.6f}")

    if not scan_result.may_report_clean():
        lines.append("")
        lines.append("  WARNING: PARTIAL REVIEW - result must not be read as a complete clean bill.")
        if scan_result.error:
            lines.append(f"     error: {scan_result.error}")

    lines.append("")
    lines.append("=" * 72)

    print("\n".join(lines))


# ---------------------------------------------------------------------------
# main() -- can be driven in-process for testing
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None, *, _client=None) -> int:
    """Entry point.  Returns the exit code.

    _client: injectable ReviewClient adapter for testing (skips bob_client import).
    If _client is None and the real provider is needed, build_bob_client() is called.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    #  Cap validation -- fail immediately, name the missing flag, make no call.
    cap_errors = _check_required_caps(args)
    if cap_errors:
        for msg in cap_errors:
            print(f"error: {msg}", file=sys.stderr)
        print("usage: see --help", file=sys.stderr)
        return 2

    # Load the review and prove_bites modules.
    review_mod      = _load_sibling("review")
    prove_bites_mod = _load_sibling("prove_bites")

    review_source = review_mod.review_source
    prove_bites   = prove_bites_mod.prove_bites

    # Read target file.
    try:
        with open(args.target, encoding="utf-8", errors="replace") as fh:
            source = fh.read()
    except OSError as exc:
        print(f"error: cannot read --target {args.target!r}: {exc}", file=sys.stderr)
        return 1

    # Read twin file if given.
    clean_source: str | None = None
    if args.twin is not None:
        try:
            with open(args.twin, encoding="utf-8", errors="replace") as fh:
                clean_source = fh.read()
        except OSError as exc:
            print(f"error: cannot read --twin {args.twin!r}: {exc}", file=sys.stderr)
            return 1

    # Build the client -- lazy import, so --help and self-test never need a key.
    if _client is None:
        try:
            _bc, client = build_bob_client(
                max_turns=args.max_turns,
                workspace=args.workspace,
            )
        except Exception as exc:
            print(f"error: cannot initialise bob client: {exc}", file=sys.stderr)
            return 1
    else:
        client = _client

    print(f"[report] reviewing {args.target!r} ...", file=sys.stderr)

    # Run the review.
    try:
        scan_result = review_source(
            source,
            client,
            file=args.target,
            max_cost=args.max_cost,
            per_call_ceiling=args.per_call_ceiling,
        )
    except Exception as exc:
        print(f"error: review failed: {exc}", file=sys.stderr)
        return 1

    # Run prove_bites if --planted was given.
    proof = None
    if args.planted is not None:

        def _review_fn(src: str, file: str):
            return review_source(
                src,
                client,
                file=file,
                max_cost=args.max_cost,
                per_call_ceiling=args.per_call_ceiling,
            )

        try:
            proof = prove_bites(
                _review_fn,
                source,
                planted_rule=args.planted,
                clean_source=clean_source,
                file=args.target,
            )
        except Exception as exc:
            print(f"error: prove_bites failed: {exc}", file=sys.stderr)
            return 1
    elif clean_source is not None:
        # Twin given but no --planted: just note it, don't run prove_bites.
        print("[report] --twin given without --planted; twin is not used.", file=sys.stderr)

    _print_report(
        target=args.target,
        planted=args.planted,
        scan_result=scan_result,
        proof=proof,
    )

    return 0


# ---------------------------------------------------------------------------
# Self-test -- fake client only, no real call, no key, no spend
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # DISPATCH FIRST -- the self-test below is a fallback for a bare invocation,
    # not the entrypoint. Without this the CLI is UNREACHABLE: every argument
    # list, including an unknown flag, silently runs the self-test and exits 0,
    # which reads as success while doing nothing.
    import sys as _sys

    if _sys.argv[1:] and "--selftest" not in _sys.argv[1:]:
        _sys.exit(main(_sys.argv[1:]))

    import json as _json

    _failures = 0

    def _check(label: str, cond: bool) -> None:
        global _failures
        status = "PASS" if cond else "FAIL"
        if not cond:
            _failures += 1
        print(f"{status}: {label}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    # Re-use the sibling loader so we can build real ScanResult objects.
    _review_mod      = _load_sibling("review")
    _prove_bites_mod = _load_sibling("prove_bites")
    _findings_mod    = _load_sibling("findings")

    ScanResult  = _findings_mod.ScanResult
    Finding     = _findings_mod.Finding
    Location    = _findings_mod.Location

    # A realistic source (20+ lines) and honest twin differing by one line.
    _LARGE_SOURCE = "\n".join([
        "import os",
        "import sys",
        "def foo(x):",
        "    y = evil(x)",
        "    z = x + 1",
        "    return y + z",
        "def bar(a, b):",
        "    return a * b",
        "class Baz:",
        "    def __init__(self):",
        "        self.value = 0",
        "    def compute(self, n):",
        "        return self.value + n",
        "def main():",
        "    obj = Baz()",
        "    result = foo(obj.compute(10))",
        "    bar(result, 2)",
        "    print(result)",
        "if __name__ == '__main__':",
        "    main()",
    ]) + "\n"
    _LARGE_TWIN = _LARGE_SOURCE.replace("    y = evil(x)", "    y = safe(x)")

    import tempfile, os as _os

    # Write source to a temp file so --target path is real.
    _tmp_target = tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                              delete=False, encoding="utf-8")
    _tmp_target.write(_LARGE_SOURCE)
    _tmp_target.close()

    _tmp_twin = tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                            delete=False, encoding="utf-8")
    _tmp_twin.write(_LARGE_TWIN)
    _tmp_twin.close()

    # ------------------------------------------------------------------
    # ST-1: omitting --max-cost -> usage error naming the flag, non-zero exit
    # ------------------------------------------------------------------
    print("--- ST-1: omit --max-cost ---")
    import io
    _old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    _rc = main(["--target", _tmp_target.name, "--per-call-ceiling", "1",
                "--planted", "planted-rule"],
               _client=lambda p, c: ("[]", 0.0))
    _err1 = sys.stderr.getvalue()
    sys.stderr = _old_stderr
    print(f"  stderr: {_err1.strip()!r}")
    _check("ST-1: exit non-zero", _rc != 0)
    _check("ST-1: stderr mentions --max-cost", "--max-cost" in _err1)
    print()

    # ------------------------------------------------------------------
    # ST-2: omitting --per-call-ceiling -> usage error naming the flag
    # ------------------------------------------------------------------
    print("--- ST-2: omit --per-call-ceiling ---")
    sys.stderr = io.StringIO()
    _rc = main(["--target", _tmp_target.name, "--max-cost", "2",
                "--planted", "planted-rule"],
               _client=lambda p, c: ("[]", 0.0))
    _err2 = sys.stderr.getvalue()
    sys.stderr = _old_stderr
    print(f"  stderr: {_err2.strip()!r}")
    _check("ST-2: exit non-zero", _rc != 0)
    _check("ST-2: stderr mentions --per-call-ceiling", "--per-call-ceiling" in _err2)
    print()

    # ------------------------------------------------------------------
    # ST-3: fake BITES review -- planted found on target, not on twin
    #        -> output contains literal BITES, both ratios print
    # ------------------------------------------------------------------
    print("--- ST-3: fake BITES review ---")

    def _fake_bites_client(prompt: str, cap: float) -> tuple:
        # Return planted-rule finding if 'evil' is in the prompt, else empty.
        if "evil" in prompt:
            return _json.dumps([{
                "rule_id": "planted-rule", "severity": "high",
                "line": 4, "title": "Evil call", "detail": "", "recommendation": "",
            }]), 0.1
        return "[]", 0.1

    # Capture stdout
    _old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    _rc = main(["--target", _tmp_target.name,
                "--twin", _tmp_twin.name,
                "--planted", "planted-rule",
                "--max-cost", "2", "--per-call-ceiling", "1"],
               _client=_fake_bites_client)
    _out3 = sys.stdout.getvalue()
    sys.stdout = _old_stdout
    print(_out3)
    _check("ST-3: exit 0", _rc == 0)
    _check("ST-3: output contains literal BITES",    "BITES" in _out3)
    _check("ST-3: twin_ratio prints",                "twin_ratio" in _out3)
    _check("ST-3: twin_ratio_baseline prints",       "twin_ratio_baseline" in _out3)
    print()

    # ------------------------------------------------------------------
    # ST-4: no --twin -> INCONCLUSIVE
    # ------------------------------------------------------------------
    print("--- ST-4: no --twin ---")
    sys.stdout = io.StringIO()
    _rc = main(["--target", _tmp_target.name,
                "--planted", "planted-rule",
                "--max-cost", "2", "--per-call-ceiling", "1"],
               _client=_fake_bites_client)
    _out4 = sys.stdout.getvalue()
    sys.stdout = _old_stdout
    print(_out4)
    _check("ST-4: exit 0", _rc == 0)
    _check("ST-4: output contains literal INCONCLUSIVE", "INCONCLUSIVE" in _out4)
    print()

    # ------------------------------------------------------------------
    # ST-5: truncated/failed review -> must not read as clean
    # Use a 700-line source so chunk_lines=300 produces >=3 chunks.
    # Each call costs 1.0; max-cost=1.5 -> after 1 call remaining=0.5 < 1.0 -> truncated.
    # ------------------------------------------------------------------
    print("--- ST-5: truncated review (budget stop) ---")

    _tmp_big = tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                           delete=False, encoding="utf-8")
    _tmp_big.write("\n".join(f"line{i} = {i}" for i in range(1, 701)))
    _tmp_big.close()

    def _fake_costly_client(prompt: str, cap: float) -> tuple:
        return "[]", 1.0   # each call costs 1.0; after 1 call, remaining < 1 -> truncated

    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()
    _rc = main(["--target", _tmp_big.name,
                "--max-cost", "1.5", "--per-call-ceiling", "1"],
               _client=_fake_costly_client)
    _out5 = sys.stdout.getvalue()
    sys.stdout = _old_stdout
    sys.stderr = _old_stderr
    _os.unlink(_tmp_big.name)
    print(_out5)
    _check("ST-5: truncated review -> PARTIAL or 'truncated: True' visible",
           "PARTIAL" in _out5 or "truncated       : True" in _out5)
    _check("ST-5: may_report_clean is False (partial review cannot read as clean)",
           "may_report_clean: False" in _out5)
    print()

    # ------------------------------------------------------------------
    # ST-6: adapter passes per_call_cap to the client
    # ------------------------------------------------------------------
    print("--- ST-6: adapter passes per-call cap ---")
    _received_caps = []

    def _cap_recording_client(prompt: str, cap: float) -> tuple:
        _received_caps.append(cap)
        return "[]", 0.01

    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()
    _rc = main(["--target", _tmp_target.name,
                "--max-cost", "5", "--per-call-ceiling", "0.75"],
               _client=_cap_recording_client)
    sys.stdout = _old_stdout
    sys.stderr = _old_stderr
    _check("ST-6: exit 0", _rc == 0)
    _check("ST-6: per_call_cap passed to client",
           len(_received_caps) > 0 and all(c <= 0.75 for c in _received_caps))
    print(f"  received caps: {_received_caps}")
    print()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    _os.unlink(_tmp_target.name)
    _os.unlink(_tmp_twin.name)

    print()
    if _failures:
        print(f"SELFTEST RED -- {_failures} check(s) FAILED.")
        sys.exit(1)
    else:
        print("SELFTEST GREEN")
        sys.exit(0)
