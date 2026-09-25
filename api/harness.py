"""Serverless demo of the non-vacuity harness, running the SHIPPED modules.

Imports src/prove_bites.py and src/findings.py from the repository rather than
reimplementing them. A demo that reimplements the thing it demonstrates is
evidence of nothing.

Deliberately free of any model call: the reviewers below are injected callables
returning the real ScanResult type, so a click costs nothing, returns in
milliseconds, and is deterministic. The point is the HARNESS, not a model.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

IMPORT_ERROR = None
try:
    from src.findings import Finding, Location, ScanResult  # type: ignore
    from src.prove_bites import prove_bites                  # type: ignore
except Exception as exc:  # noqa: BLE001 - surfaced to the caller on purpose
    Finding = Location = ScanResult = prove_bites = None
    IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

PLANTED_RULE = "unvalidated-redirect"

# ---------------------------------------------------------------------------
# A deliberately small, deliberately synthetic pair. This is NOT the pair used
# for the recorded demo; it exists to exercise the harness in a browser.
# ---------------------------------------------------------------------------

SOURCE = '''"""redirect helper"""

ALLOWED_HOSTS = ["docs.example.com", "api.example.com"]


def redirect_target(request):
    """Pick the host to send the client to."""
    host = request.args.get("next_host", ALLOWED_HOSTS[0])
    return "https://" + host + request.args.get("path", "/")


def build_response(request):
    target = redirect_target(request)
    return {"status": 302, "location": target}
'''

TWIN = '''"""redirect helper"""

ALLOWED_HOSTS = ["docs.example.com", "api.example.com"]


def redirect_target(request):
    """Pick the host to send the client to."""
    host = request.args.get("next_host", ALLOWED_HOSTS[0])
    if host not in ALLOWED_HOSTS:
        raise ValueError("redirect host is not allowlisted")
    return "https://" + host + request.args.get("path", "/")


def build_response(request):
    target = redirect_target(request)
    return {"status": 302, "location": target}
'''


def _coverage(file, findings):
    """A ScanResult that reports FULL coverage and no failures.

    may_report_clean() is True only when chunks_failed == 0 AND
    chunks_reviewed + chunks_failed == chunks_total. A stub that omits the
    coverage fields returns False and the proof comes back INCONCLUSIVE.
    """
    return ScanResult(file=file, findings=list(findings),
                      chunks_total=1, chunks_reviewed=1, chunks_failed=0)


def _finding(rule_id):
    return Finding(rule_id=rule_id, severity="high",
                   location=Location(file="redirect_helper.py", line_start=9, line_end=9),
                   title="planted rule")


# --- the reviewers -----------------------------------------------------------

def honest_reviewer(source, file):
    """Reports the planted rule on the flawed file, nothing on the clean one."""
    if "if host not in ALLOWED_HOSTS" in source:
        return _coverage(file, [])
    return _coverage(file, [_finding(PLANTED_RULE)])


def constant_reviewer(source, file):
    """Emits the planted rule on EVERY input. Cannot read code at all."""
    return _coverage(file, [_finding(PLANTED_RULE)])


def length_reviewer(source, file):
    """Reports the rule iff the file is longer than 12 lines. Cannot read code."""
    if len(source.splitlines()) > 12:
        return _coverage(file, [_finding(PLANTED_RULE)])
    return _coverage(file, [])


def partial_reviewer(source, file):
    """A reviewer that failed a chunk and covered none of the file.

    chunks_reviewed=0, chunks_failed=1 -> may_report_clean() is False. This is
    the engine refusing to certify a review that never happened.
    """
    result = _coverage(file, [])
    result.chunks_reviewed = 0
    result.chunks_failed = 1
    result.error = "chunk 0 parse error: could not extract findings"
    return result


REVIEWERS = [
    ("honest", honest_reviewer,
     "Reports the rule on the flawed file and nothing on the clean twin."),
    ("constant", constant_reviewer,
     "Emits the planted rule on every input. Cannot read code at all."),
    ("length", length_reviewer,
     "Reports the rule when the file is longer than 12 lines. Cannot read code."),
    ("partial", partial_reviewer,
     "Reviewed nothing and failed a chunk. Reports no findings at all."),
]


def _row(name, proof, blurb):
    return {
        "name": name,
        "blurb": blurb,
        "status": proof.status,
        "trusted": proof.may_trust_clean(),
        "found_rule_ids": list(proof.found_rule_ids),
        "twin_rule_ids": list(proof.twin_rule_ids),
        "twin_hunks": proof.twin_hunks,
        "twin_ratio": round(proof.twin_ratio, 4),
        "twin_ratio_baseline": round(proof.twin_ratio_baseline, 4),
        "twin_lines_kept": proof.twin_lines_kept,
        "reason": proof.reason,
    }


def run_all():
    rows = []
    for name, reviewer, blurb in REVIEWERS:
        p = prove_bites(reviewer, SOURCE, planted_rule=PLANTED_RULE,
                        clean_source=TWIN, file="redirect_helper.py")
        rows.append(_row(name, p, blurb))
    return rows


def one_sided():
    """The same honest reviewer, with no twin supplied."""
    p = prove_bites(honest_reviewer, SOURCE, planted_rule=PLANTED_RULE,
                    clean_source=None, file="redirect_helper.py")
    return _row("honest, no twin", p,
                "Identical reviewer, but the caller supplied no control.")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if IMPORT_ERROR is not None:
            body = json.dumps({"error": "harness module could not be imported",
                               "detail": IMPORT_ERROR}, indent=2).encode()
            self.send_response(500)
        else:
            try:
                payload = {"planted_rule": PLANTED_RULE,
                           "results": run_all(),
                           "one_sided": one_sided()}
                body = json.dumps(payload, indent=2).encode()
                self.send_response(200)
            except Exception as exc:  # noqa: BLE001
                body = json.dumps({"error": type(exc).__name__,
                                   "detail": str(exc)}, indent=2).encode()
                self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=60")
        self.end_headers()
        self.wfile.write(body)
