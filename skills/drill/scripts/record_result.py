#!/usr/bin/env python3
"""Append one finished quiz to the results log.

Usage: record_result.py <session.json> <topic-id>=<correct>/<total> [...]

Example: record_result.py "$GRAMMAR_HOME/drills/drill-2026-08-06-1230.json" articles=4/5 prepositions=3/5

Scoring happens in the session - the model grades each answer against the rule, not against a string - so the only thing that has to survive the conversation is the tally. Totals are summed from the per-topic scores rather than passed separately, so a run cannot record a total that disagrees with its own breakdown. Appends one JSON object to $GRAMMAR_HOME/results.jsonl and prints the summary line. Stdlib only.
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

SCORE_RE = re.compile(r"^([a-z][a-z0-9-]*)=(\d+)/(\d+)$")


def fail(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if len(sys.argv) < 3:
        fail("usage: record_result.py <session.json> <topic-id>=<correct>/<total> [...]")
    session_path = Path(sys.argv[1])
    try:
        session = json.loads(session_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read the drill session: {exc}")
    known = {t["id"] for t in session.get("topics", []) if isinstance(t, dict) and "id" in t}

    by_topic = {}
    for arg in sys.argv[2:]:
        m = SCORE_RE.match(arg)
        if not m:
            fail(f"bad score {arg!r}: expected <topic-id>=<correct>/<total>")
        topic, good, total = m.group(1), int(m.group(2)), int(m.group(3))
        if topic not in known:
            fail(f"topic '{topic}' is not in {session_path.name} (has: {', '.join(sorted(known)) or 'none'})")
        if topic in by_topic:
            fail(f"topic '{topic}' scored twice")
        if total == 0:
            fail(f"topic '{topic}' has a zero total")
        if good > total:
            fail(f"topic '{topic}' scored {good} of {total}")
        by_topic[topic] = {"good": good, "total": total}

    correct = sum(v["good"] for v in by_topic.values())
    asked = sum(v["total"] for v in by_topic.values())
    row = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "drill": session_path.name,
        "kind": session.get("kind", "drill"),
        "total": asked,
        "correct": correct,
        "byTopic": by_topic,
    }

    home = Path(os.environ.get("GRAMMAR_HOME", Path.home() / ".claude" / "cc-grammar-coach"))
    home.mkdir(parents=True, exist_ok=True)
    with open(home / "results.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{correct}/{asked} recorded to {home / 'results.jsonl'}")


if __name__ == "__main__":
    main()
