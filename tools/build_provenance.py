#!/usr/bin/env python3
"""Build public/provenance.json -- a small summary of the Bob task sessions.

WHY A BUILD STEP AND NOT A FETCH.  The two exports in bob_sessions/ total
~8.2 MB.  Serving them to a browser to render a summary would make the page
slow for no gain, and putting a serverless function in front of them would
re-read 8 MB per request.  This reduces them once, at build time, to a few KB
that the static page can fetch.

WHY BOTH FILES, ALWAYS.  Bob's task store forked into two project_id case
variants (`file:C:\\secreview-bob` and `file:c:\\secreview-bob`), so the IDE's
own export captured only one bucket -- 8 of 20 tasks.  Summarising a single
file would understate the Bob work by more than half, in the exact place the
page exists to show it.  This script therefore takes EVERY *.json in
bob_sessions/ and fails loudly if it finds fewer than two.

WHAT THIS IS NOT.  No model call, no key, no network.  It reads committed JSON
and writes JSON.  The page it feeds reports the recorded sessions; it does not
claim the deployed harness calls Bob, because the harness deliberately does not.

    python tools/build_provenance.py            # writes public/provenance.json
    python tools/build_provenance.py --check    # verify the committed file is current
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSIONS = ROOT / "bob_sessions"
OUT = ROOT / "public" / "provenance.json"

TITLE_CAP = 96          # keep the payload small and the page legible
MIN_EXPORTS = 2         # the case-fork means one file is never the whole record


def _ms(epoch_ms: int | None) -> str | None:
    if not epoch_ms:
        return None
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).isoformat(
        timespec="seconds")


def build() -> dict:
    files = sorted(SESSIONS.glob("*.json"))
    if len(files) < MIN_EXPORTS:
        raise SystemExit(
            f"error: found {len(files)} export(s) in {SESSIONS}, expected at least "
            f"{MIN_EXPORTS}. The task store forked into two project_id case variants; "
            f"summarising one bucket understates the record. Export both, then re-run."
        )

    sessions: list[dict] = []
    sources: list[dict] = []

    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        tasks = payload.get("tasks") or []
        n_msgs = sum(len(t.get("messages") or []) for t in tasks)
        sources.append({
            "file": path.name,
            "workspace": payload.get("workspace"),
            "exported_at": _ms(payload.get("exportedAt")),
            "tasks": len(tasks),
            "messages": n_msgs,
        })
        for entry in tasks:
            task = entry.get("task") or {}
            title = (task.get("title") or task.get("firstMessage") or "").strip()
            title = " ".join(title.split())          # collapse newlines for one line
            sessions.append({
                "id": (task.get("id") or "")[:12],
                "title": title[:TITLE_CAP] + ("…" if len(title) > TITLE_CAP else ""),
                "status": task.get("status") or "unknown",
                "cost": round(float((task.get("costs") or {}).get("cost") or 0.0), 4),
                "tokens": int((task.get("costs") or {}).get("contextTokens") or 0),
                "messages": len(entry.get("messages") or []),
                "created_at": _ms(task.get("createdAt")),
            })

    sessions.sort(key=lambda s: s["created_at"] or "")
    stamps = [s["created_at"] for s in sessions if s["created_at"]]

    return {
        "generated_by": "tools/build_provenance.py",
        "note": ("Summary of IBM Bob task sessions recorded during the hackathon "
                 "window, reduced from the exports in bob_sessions/. Recorded "
                 "sessions, not a live call: the deployed harness makes no model "
                 "call by design."),
        "sources": sources,
        "totals": {
            "exports": len(sources),
            "sessions": len(sessions),
            "messages": sum(s["messages"] for s in sessions),
            "cost": round(sum(s["cost"] for s in sessions), 4),
            "tokens": sum(s["tokens"] for s in sessions),
            "first": stamps[0] if stamps else None,
            "last": stamps[-1] if stamps else None,
        },
        "sessions": sessions,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="build_provenance")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the committed file differs from a fresh build")
    args = ap.parse_args(argv)

    data = build()
    text = json.dumps(data, indent=1, ensure_ascii=False) + "\n"
    t = data["totals"]

    if args.check:
        if not OUT.is_file():
            print(f"STALE: {OUT.relative_to(ROOT)} does not exist")
            return 1
        current = OUT.read_text(encoding="utf-8")
        if current != text:
            print(f"STALE: {OUT.relative_to(ROOT)} differs from a fresh build "
                  f"({len(current)} B on disk vs {len(text)} B rebuilt)")
            return 1
        print(f"CURRENT: {OUT.relative_to(ROOT)} matches a fresh build "
              f"({t['sessions']} sessions, {t['messages']} messages)")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}  ({len(text):,} B)")
    print(f"  {t['exports']} exports · {t['sessions']} sessions · "
          f"{t['messages']} messages · {t['cost']} coins · {t['tokens']:,} tokens")
    for s in data["sources"]:
        print(f"    {s['tasks']:>3} tasks / {s['messages']:>4} msgs  {s['file']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
