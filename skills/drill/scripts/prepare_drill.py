#!/usr/bin/env python3
"""Validate authored drill data and store it for the dashboard.

Usage: prepare_drill.py --kind drill|learn <data.json>

Validates the authored data, stamps the `kind` badge the dashboard shows and the `date` the dashboard displays, writes the result to $GRAMMAR_HOME/drills/drill-<date>-<HHMMSS>.json (GRAMMAR_HOME defaults to ~/.claude/cc-grammar-coach) and prints the file name. Both stamps come from the script, not from the authored data: the file name is a path component and the dashboard sorts sessions by it, so an authored date could name any file and order the list wrong. Seconds in the name keep every name the same length, so the lexical sort the dashboard does is chronological. The file is created with an exclusive open, so two runs never overwrite each other. Nothing is written when validation fails. The dashboard reads the file over its /api/drills endpoints, so opening it is the launcher's job. Stdlib only.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def fail(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def validate(data: dict) -> None:
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
            if not isinstance(q.get("answer"), int) or not 0 <= q["answer"] < len(opts):
                fail(f"choice question needs a valid 'answer' index: {q['prompt']}")
        elif q["type"] == "rewrite":
            if not isinstance(q.get("answers"), list) or not q["answers"]:
                fail(f"rewrite question needs a non-empty 'answers' list: {q['prompt']}")
        else:
            fail(f"unknown question type '{q['type']}': {q['prompt']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="validate authored drill data and store it for the dashboard")
    parser.add_argument("--kind", required=True, choices=("drill", "learn"), help="which skill authored the data")
    parser.add_argument("data", metavar="data.json", help="path to the authored drill data")
    args = parser.parse_args()

    try:
        data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read drill data: {exc}")
    if not isinstance(data, dict):
        fail("drill data must be a JSON object")
    validate(data)
    stamp = datetime.now()
    data["kind"] = args.kind
    data["date"] = f"{stamp:%Y-%m-%d}"

    home = Path(os.environ.get("GRAMMAR_HOME", Path.home() / ".claude" / "cc-grammar-coach"))
    out_dir = home / "drills"
    name = f"drill-{stamp:%Y-%m-%d-%H%M%S}.json"
    body = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / name, "x", encoding="utf-8") as f:
            f.write(body)
    except FileExistsError:
        fail(f"{name} already exists in {out_dir}, so this second already has a session; wait a second and rerun to get a fresh name")
    except OSError as exc:
        fail(f"cannot write {out_dir / name}: {exc}")
    print(name)


if __name__ == "__main__":
    main()
