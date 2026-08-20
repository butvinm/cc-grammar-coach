#!/usr/bin/env python3
"""Validate authored drill data and store it as a session file.

Usage: prepare_drill.py <data.json> [output.json]

The quiz itself runs in the Claude Code session, not in a browser, so this script no longer renders anything: it checks the data the model authored, then writes it to $GRAMMAR_HOME/drills/<kind>-<date>-<HHMM>.json (GRAMMAR_HOME defaults to ~/.claude/cc-grammar-coach; an explicit output path overrides both) and prints the path. The file is what outlives the conversation - the session can be resumed, re-run, or reported on later. Stdlib only.
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

KINDS = ("drill", "learn")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def fail(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def validate(data: dict) -> None:
    # 'date' reaches a filename, so it is constrained here rather than trusted: it arrives from an LLM, and a value carrying a slash would write outside drills/.
    if not DATE_RE.match(str(data.get("date", ""))):
        fail(f"'date' must be YYYY-MM-DD, got {data.get('date')!r}")
    if data.get("kind") not in KINDS:
        fail(f"'kind' must be one of {', '.join(KINDS)}, got {data.get('kind')!r}")
    if not isinstance(data.get("topics"), list) or not data["topics"]:
        fail("'topics' must be a non-empty list")
    if not isinstance(data.get("questions"), list) or not data["questions"]:
        fail("'questions' must be a non-empty list")
    topic_ids = set()
    for t in data["topics"]:
        for key in ("id", "label", "count", "lesson"):
            if key not in t:
                fail(f"topic missing '{key}': {t}")
        if not isinstance(t["count"], int) or t["count"] < 0:
            fail(f"topic '{t['id']}' 'count' must be a non-negative integer")
        if not isinstance(t["lesson"], dict):
            fail(f"topic '{t['id']}' 'lesson' must be an object")
        if not t["lesson"].get("summary") or not t["lesson"].get("examples"):
            fail(f"topic '{t['id']}' lesson needs 'summary' and 'examples'")
        for e in t["lesson"]["examples"]:
            for key in ("wrong", "right", "note"):
                if key not in e:
                    fail(f"example in topic '{t['id']}' missing '{key}'")
        topic_ids.add(t["id"])
    for q in data["questions"]:
        for key in ("topic", "type", "prompt", "explain"):
            if key not in q:
                fail(f"question missing '{key}': {q}")
        if q["topic"] not in topic_ids:
            fail(f"question topic '{q['topic']}' has no matching topic id")
        if q["type"] == "choice":
            opts = q.get("options")
            if not isinstance(opts, list) or len(opts) < 2:
                fail(f"choice question needs >= 2 options: {q['prompt']}")
            # isinstance(True, int) is True in Python, and a bool index would silently grade against option 0 or 1.
            if isinstance(q.get("answer"), bool) or not isinstance(q.get("answer"), int) or not 0 <= q["answer"] < len(opts):
                fail(f"choice question needs a valid 'answer' index: {q['prompt']}")
        elif q["type"] == "rewrite":
            answers = q.get("answers")
            if not isinstance(answers, list) or not answers:
                fail(f"rewrite question needs a non-empty 'answers' list: {q['prompt']}")
            if not all(isinstance(a, str) and a.strip() for a in answers):
                fail(f"rewrite 'answers' must all be non-empty strings: {q['prompt']}")
        else:
            fail(f"unknown question type '{q['type']}': {q['prompt']}")


def main() -> None:
    if len(sys.argv) < 2:
        fail("usage: prepare_drill.py <data.json> [output.json]")
    data_path = Path(sys.argv[1])
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read drill data: {exc}")
    if not isinstance(data, dict):
        fail("drill data must be a JSON object")
    data.setdefault("date", datetime.now().strftime("%Y-%m-%d"))
    data.setdefault("kind", "drill")
    validate(data)

    if len(sys.argv) > 2:
        out = Path(sys.argv[2])
    else:
        home = Path(os.environ.get("GRAMMAR_HOME", Path.home() / ".claude" / "cc-grammar-coach"))
        out_dir = home / "drills"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{data['kind']}-{data['date']}-{datetime.now().strftime('%H%M')}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
