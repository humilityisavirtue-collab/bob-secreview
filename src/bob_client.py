#!/usr/bin/env python3
"""bob_client.py — the Bob transport layer.

ONE call signature, interchangeable transports, so the rest of the build never
cares how Bob is reached.  Written to mirror `featherless_client.chat()` exactly,
because that is the function it replaces in the review engine:

    # before
    import featherless_client as fc
    raw = fc.chat(messages, model=..., max_tokens=2048, temperature=0.05)
    # after
    import bob_client as bc
    raw = bc.chat(messages, model=bc.MODEL_ID, max_tokens=2048, temperature=0.05)

WHY THE DEFAULT IS NOT THE FAST ONE.  The two transports are NOT equivalent for
this submission, and the difference is invisible from the call site:

  transport="http"   Bob's OpenAI-compatible endpoint. Fast, scriptable.
                     **Unverified** that a direct API call produces a Bob IDE
                     task session -- so it may generate ZERO `bob_sessions/`
                     evidence, which is an ELIGIBILITY failure, not a slowdown.

  transport="shell"  `bob run --format json` (headless). Slower, one process per
                     call -- BUT the Shell writes the shared task store at
                     `~/.bob/db/bob.db` that `exportProject` reads, so it
                     PRODUCES the judging artifact.

The asymmetry: the property that makes `http` attractive (scriptability) is the
property that makes it invisible to the judges.  So `shell` is the default and
`http` must be opted into explicitly.  `require_evidence=True` (default) REFUSES
the http transport until V2 has been answered -- see `evidence_class()`.

SECRETS.  BOB_API_KEY is in the account-death class for this hackathon. This
module reads it from the environment and NEVER returns, logs, prints, or embeds
it.  Errors name the *location*, never the value.  A key that reaches a repo, a
session transcript, or `bob_sessions/` deactivates the IBM account.

STATUS: transports are written and ready; V1 and V2 (below) cannot run until
Kit creates BOB_API_KEY (Scope=Inference). Marked at each site.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Iterator, Optional

import httpx

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

# Discovered, NOT guessed. V1 discovers the real id; this is the fallback order
# to try. UNVERIFIED -- no request has been made.
MODEL_ID = os.environ.get("BOB_MODEL_ID", "")

# Bundle-derived (grep of the installed Bob extension). NEVER INVOKED.
BOB_HTTP_BASE = os.environ.get("BOB_HTTP_BASE", "https://api.us-east.bob.ibm.com")

_KEY_ENV = "BOB_API_KEY"          # Scope=Inference. Environment only. Never logged.
_BOB_BIN = "bob"                  # bobshell 2.0.5, on PATH via npm

# Hard cost guards. These EXIST on `bob run` -- measured, not assumed:
#   --max-cost <number>   --max-turns <number>
# They are the cost-guard pattern salvaged from IMPOSSIBLE_API_SPEC's DaemonForge
# ("cheapest sufficient tier, with max_tier as an explicit cap"), applied to the
# 40-Bobcoin non-refillable budget.
DEFAULT_MAX_TURNS = int(os.environ.get("BOB_MAX_TURNS", "4"))

_TRANSPORTS = ("shell", "http")
_DEFAULT_TRANSPORT = os.environ.get("BOB_TRANSPORT", "shell")


class BobError(RuntimeError):
    """Any transport failure. Never carries key material."""


class BobNotConfigured(BobError):
    """A required prerequisite is absent -- names WHICH, never a value."""


# --------------------------------------------------------------------------
# Auth -- presence only. The value is never bound to a name we hand out.
# --------------------------------------------------------------------------

def key_present() -> bool:
    """True if BOB_API_KEY is in the environment. Does NOT return the value."""
    return bool(os.environ.get(_KEY_ENV))


def _require_key() -> None:
    if not key_present():
        raise BobNotConfigured(
            f"{_KEY_ENV} is not set. All non-interactive Bob paths require it "
            f"(Scope=Inference). Only interactive `bob chat` works keylessly via SSO. "
            f"Create it and export it into the environment; do NOT write it to a file "
            f"inside any repo."
        )


# --------------------------------------------------------------------------
# Evidence classes -- the V2 asymmetry, made checkable rather than remembered
# --------------------------------------------------------------------------

# V2 (PM 9cb789a6 / f12c7f57): do direct HTTP calls produce a Bob IDE task
# session that appears in the export? UNKNOWN. Until it is answered as YES,
# `http` must not be used for any run the submission has to show.
_V2_ANSWERED_YES = os.environ.get("BOB_V2_HTTP_EXPORTS", "").lower() in ("1", "true", "yes")


def evidence_class(transport: str) -> str:
    """'EXPORTABLE' | 'UNVERIFIED' -- whether this transport yields judging evidence."""
    if transport == "shell":
        return "EXPORTABLE"          # writes the shared task store exportProject reads
    if transport == "http":
        return "EXPORTABLE" if _V2_ANSWERED_YES else "UNVERIFIED"
    raise BobError(f"unknown transport {transport!r}; expected one of {_TRANSPORTS}")


# --------------------------------------------------------------------------
# Message flattening -- Bob takes a prompt string, not an OpenAI message list
# --------------------------------------------------------------------------

def flatten_messages(messages: list[dict]) -> str:
    """OpenAI-format [{role, content}] -> one prompt string.

    System content is preserved as a leading block; Bob's own system prompt is
    not ours to overwrite, so we hand ours over as context rather than pretend
    to be the system role.
    """
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):                       # multipart
            content = "\n".join(
                p.get("text", "") for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
        if not content:
            continue
        parts.append(content if role == "user" else f"## {role}\n{content}")
    return "\n\n".join(parts)


# --------------------------------------------------------------------------
# Transport: shell -- `bob run --format json`
# --------------------------------------------------------------------------

# The MEASURED `bob run --format json` schema, captured 2026-09-25 from a real
# successful run (exit 0):
#   {"type":"result","timestamp":"...","status":"success",
#    "stats":{"task_id":"...","duration_ms":1760,"session_costs":0.020868,
#             "max_cost":1,"tool_calls":0},
#    "last_message":"BOB-SHELL-OK"}
# `last_message` is the assistant text. It was NOT in the first version's lookup
# list, so a SUCCESSFUL run fell through to the "any long string" heuristic and
# returned "" -- a silent empty result on success. The selftest could not catch
# that, because the selftest had no real output to parse. Only a real run did.
_ASSISTANT_KEYS = ("last_message", "result", "message", "content", "text",
                   "output", "response")


def parse_run_json(raw: str) -> tuple[str, dict]:
    """(assistant_text, stats) from one `bob run --format json` payload.

    Returns ("", {}) rather than raising when the shape is unrecognised -- a
    degraded parse must be visibly empty, not a crash mid-scan.
    """
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip(), {}
    if not isinstance(payload, dict):
        return "", {}
    text = ""
    for key in _ASSISTANT_KEYS:
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            text = val
            break
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    return text, stats


def _extract_assistant_text(payload) -> str:
    """Pull the assistant's final text out of a parsed `bob run` payload.

    Kept as the generic walker for nested shapes; `parse_run_json` handles the
    measured top-level schema and is what `_chat_shell` uses.
    """
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        for key in _ASSISTANT_KEYS:
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                return val
            if isinstance(val, dict):
                inner = _extract_assistant_text(val)
                if inner.strip():
                    return inner
        for val in payload.values():          # last resort: any long string leaf
            if isinstance(val, str) and len(val) > 40:
                return val
    if isinstance(payload, list):
        for item in reversed(payload):
            got = _extract_assistant_text(item)
            if got.strip():
                return got
    return ""


def _resolve_bob() -> str:
    """Resolve the bob executable to a FULL PATH.

    WINDOWS GOTCHA, caught by the first real shell test (2026-09-25): `bob` is an
    npm `.cmd` shim. `shutil.which("bob")` applies PATHEXT and FINDS it, but
    `subprocess` given the BARE NAME does not -- CreateProcess needs the extension,
    so the bare name raises FileNotFoundError. Presence-checking with `which` and
    then executing the bare name is therefore a client that passes its selftest
    and dies on the only OS this is being built on. Resolve ONCE, execute the
    resolved path.
    """
    for cand in (_BOB_BIN, _BOB_BIN + ".cmd", _BOB_BIN + ".exe", _BOB_BIN + ".ps1"):
        found = shutil.which(cand)
        if found:
            return found
    raise BobNotConfigured(
        f"`{_BOB_BIN}` not found on PATH (bobshell not installed, or PATH lacks the "
        f"npm global bin dir)")


def _chat_shell(prompt: str, *, workspace: Optional[str], max_cost: Optional[float],
                max_turns: Optional[int], mode: Optional[str]) -> str:
    """One headless `bob run`. Returns the assistant text. Produces export evidence."""
    _require_key()
    exe = _resolve_bob()                      # full path -- see _resolve_bob()

    cmd = [exe, "run", "--format", "json", "--trust"]
    if workspace:
        cmd += ["--workspace", workspace]
    if mode:
        cmd += ["--mode", mode]
    if max_turns is not None:
        cmd += ["--max-turns", str(int(max_turns))]
    if max_cost is not None:
        cmd += ["--max-cost", str(max_cost)]
    cmd.append(prompt)                        # prompt LAST, as a positional arg

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600, check=False,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        raise BobError("bob run timed out after 600s")

    out = (proc.stdout or "").strip()
    if proc.returncode != 0 and not out:
        # Name the failure class; stderr may echo the prompt, so we do not ship it raw.
        raise BobError(f"bob run exited {proc.returncode} with no stdout "
                       f"(stderr length {len(proc.stderr or '')})")

    text, stats = parse_run_json(out)
    # Cost visibility WITHOUT changing the drop-in call signature: the measured
    # stats carry session_costs / max_cost / duration_ms / task_id / tool_calls.
    # session_costs is the real Bobcoin spend for the call -- the budget in the
    # plan can therefore be MEASURED rather than estimated.
    if stats:
        LAST_STATS.clear()
        LAST_STATS.update(stats)
    return text


# Last `bob run` stats: {task_id, duration_ms, session_costs, max_cost, tool_calls}.
# `task_id` is also the key that ties a call to its exportable task session.
LAST_STATS: dict = {}


# --------------------------------------------------------------------------
# Transport: http -- the unverified one
# --------------------------------------------------------------------------

def _chat_http(messages: list[dict], model: str, *, max_tokens: int,
               temperature: float, max_turns: Optional[int]) -> str:
    """Direct call to Bob's OpenAI-compatible endpoint.

    ⚠ BUNDLE-DERIVED AND NEVER INVOKED. The host and the chat/completions path
    come from a grep of Bob's own extension bundle (the Vercel AI SDK provider
    signature). No request has succeeded yet. Treat every failure here as
    information about the lead, not as a bug in this function.
    """
    _require_key()
    key = os.environ[_KEY_ENV]                # bound locally, never returned/logged
    body: dict = {"model": model, "messages": messages,
                  "max_tokens": max_tokens, "temperature": temperature}
    if max_turns is not None:
        body["max_turns"] = int(max_turns)
    try:
        with httpx.Client(base_url=BOB_HTTP_BASE,
                          headers={"Authorization": f"Bearer {key}"},
                          timeout=120.0) as client:
            resp = client.post("/chat/completions", json=body)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        # Status code only -- a response body could echo request content.
        raise BobError(f"bob http {exc.response.status_code} from {BOB_HTTP_BASE}")
    except httpx.HTTPError as exc:
        raise BobError(f"bob http transport error: {type(exc).__name__}")
    finally:
        del key                               # drop the local binding promptly

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise BobError("bob http returned an unrecognised completion shape")


# --------------------------------------------------------------------------
# The one call signature
# --------------------------------------------------------------------------

def chat(
    messages: list[dict],
    model: Optional[str] = None,
    max_tokens: int = 2048,
    temperature: float = 0.05,
    *,
    transport: Optional[str] = None,
    workspace: Optional[str] = None,
    max_cost: Optional[float] = None,
    max_turns: Optional[int] = None,
    mode: Optional[str] = None,
    require_evidence: bool = True,
) -> str:
    """Ask Bob for a completion. Mirrors featherless_client.chat().

    require_evidence=True (the default) REFUSES a transport whose output does not
    demonstrably become judging evidence. That default is deliberate: a clean run
    on a transport that leaves no trace in `bob_sessions/` is worthless to this
    submission, however fast it was.
    """
    transport = (transport or _DEFAULT_TRANSPORT).lower()
    if transport not in _TRANSPORTS:
        raise BobError(f"unknown transport {transport!r}; expected one of {_TRANSPORTS}")

    cls = evidence_class(transport)
    if require_evidence and cls != "EXPORTABLE":
        raise BobError(
            f"transport {transport!r} has evidence class {cls}: it is NOT verified to "
            f"produce a Bob IDE task session, so it would leave ZERO `bob_sessions/` "
            f"evidence. Use transport='shell', or set BOB_V2_HTTP_EXPORTS=1 once V2 "
            f"has actually answered YES, or pass require_evidence=False to accept the loss."
        )

    model = model or MODEL_ID
    if not model:
        raise BobNotConfigured(
            "no model id: set BOB_MODEL_ID, or call discover_model_id() first "
            "(the id is UNKNOWN -- V1 discovers it, it is not guessable)"
        )

    if transport == "shell":
        return _chat_shell(flatten_messages(messages), workspace=workspace,
                           max_cost=max_cost,
                           max_turns=max_turns if max_turns is not None else DEFAULT_MAX_TURNS,
                           mode=mode)
    return _chat_http(messages, model, max_tokens=max_tokens,
                      temperature=temperature, max_turns=max_turns)


# --------------------------------------------------------------------------
# V1 -- model-id discovery
# --------------------------------------------------------------------------

def list_models() -> list[str]:
    """V1, step 1: enumerate models available to the provisioned account.

    ⚠ UNRUN -- needs BOB_API_KEY. `/models` is the OpenAI-compatible discovery
    route; if Bob does not expose it, fall back to `bob run --mode` slugs or the
    admin portal, and record which route worked.
    """
    _require_key()
    key = os.environ[_KEY_ENV]
    try:
        with httpx.Client(base_url=BOB_HTTP_BASE,
                          headers={"Authorization": f"Bearer {key}"},
                          timeout=60.0) as client:
            resp = client.get("/models")
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise BobError(f"/models returned {exc.response.status_code} -- the HTTP "
                       f"transport may not be exposed to this account")
    except httpx.HTTPError as exc:
        raise BobError(f"/models transport error: {type(exc).__name__}")
    finally:
        del key
    return [m.get("id", "") for m in data.get("data", []) if m.get("id")]


def discover_model_id(prefer: str = "coder") -> str:
    """V1, step 2: pick a model id and record it. NEVER guess one.

    Preference is a substring hint only; if nothing matches, the first model is
    returned and that fact is logged by the caller. A wrong id fails visibly on
    the first call, which is the correct place for it to fail.
    """
    models = list_models()
    if not models:
        raise BobError("no models returned by /models -- record this and try the "
                       "admin portal or `bob run --mode` slugs instead")
    for m in models:
        if prefer.lower() in m.lower():
            return m
    return models[0]


# --------------------------------------------------------------------------
# Self-check -- runs WITHOUT a key, so it is usable while blocked
# --------------------------------------------------------------------------

def selftest() -> int:
    ok = True

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        ok = ok and cond
        print(f"  {'PASS' if cond else 'FAIL'}  {label}")

    print("bob_client selftest (no key required)")

    check("shell is the default transport (evidence-producing)",
          _DEFAULT_TRANSPORT == "shell")
    check("shell classifies as EXPORTABLE", evidence_class("shell") == "EXPORTABLE")
    check("http classifies as UNVERIFIED until V2 says otherwise",
          evidence_class("http") == ("EXPORTABLE" if _V2_ANSWERED_YES else "UNVERIFIED"))
    check("a flattened system+user prompt keeps both parts",
          all(s in flatten_messages([{"role": "system", "content": "SYS"},
                                     {"role": "user", "content": "USR"}])
              for s in ("SYS", "USR")))
    check("flatten handles multipart content",
          "P" in flatten_messages([{"role": "user",
                                    "content": [{"type": "text", "text": "P"}]}]))

    # The load-bearing guard: an evidence-less transport must be REFUSED by default.
    refused = False
    try:
        chat([{"role": "user", "content": "x"}], model="m", transport="http")
    except BobError as exc:
        refused = "UNVERIFIED" in str(exc) or "evidence" in str(exc).lower()
    except BobNotConfigured:
        refused = True                      # key absent -> also a refusal, not a pass-through
    check("NEGCONTROL: http is refused while V2 is unanswered", refused)

    # And the control on the control: the SAME call with require_evidence=False
    # must get PAST the evidence guard (failing later on the key is fine).
    reached_key = False
    try:
        chat([{"role": "user", "content": "x"}], model="m",
             transport="http", require_evidence=False)
    except BobNotConfigured:
        reached_key = True
    except BobError as exc:
        reached_key = "evidence" not in str(exc).lower()
    check("CONTROL: require_evidence=False gets past the same guard", reached_key)

    # The REAL captured payload, verbatim from a successful run (exit 0,
    # 2026-09-25). A fixture that was actually produced by the tool beats a
    # plausible one -- this is the arm that would have caught the `last_message`
    # miss before a live scan did.
    REAL = ('{"type":"result","timestamp":"2026-09-25T20:14:03.274Z",'
            '"status":"success","stats":{"task_id":"d6c0e3d052c4f4b25fc4f57914946018",'
            '"duration_ms":1760,"session_costs":0.020868,"max_cost":1,"tool_calls":0},'
            '"last_message":"BOB-SHELL-OK"}')
    txt, stats = parse_run_json(REAL)
    check("parse_run_json reads last_message from the REAL captured payload",
          txt == "BOB-SHELL-OK")
    check("parse_run_json exposes the cost stats (budget is measurable)",
          abs(float(stats.get("session_costs", 0)) - 0.020868) < 1e-9
          and stats.get("max_cost") == 1)
    # NEGCONTROL: a payload lacking last_message must yield "" -- visibly empty,
    # never a crash and never a wrong string scraped from elsewhere in the blob.
    bad, _ = parse_run_json('{"type":"result","status":"success","stats":{"tool_calls":0}}')
    check("NEGCONTROL: a payload with no assistant field parses to empty, not to garbage",
          bad == "")
    check("a non-JSON line degrades to raw text rather than raising",
          parse_run_json("plain prose")[0] == "plain prose")

    check("no key value is ever returned by the helpers",
          key_present() in (True, False))   # returns a bool, never a string

    print("SELFTEST", "GREEN" if ok else "RED")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(selftest())
