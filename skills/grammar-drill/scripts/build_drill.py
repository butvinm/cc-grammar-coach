#!/usr/bin/env python3
"""Build a grammar drill page from drill data JSON.

Usage: build_drill.py <data.json> [output.html]

Validates the drill data, injects it into assets/drill-template.html along with
assets/duo.css, writes the page to $GRAMMAR_HOME/drills/drill-<date>-<HHMM>.html
(GRAMMAR_HOME defaults to ~/.claude/cc-grammar-coach; an explicit output path
overrides both), and prints the path. Opening the page is the caller's job, so
that building it can be scripted without spawning a browser. Stdlib only.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

PLACEHOLDER = "__DRILL_DATA__"
CSS_PLACEHOLDER = "__DUO_CSS__"


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
    if len(sys.argv) < 2:
        fail("usage: build_drill.py <data.json> [output.html]")
    data_path = Path(sys.argv[1])
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read drill data: {exc}")
    data.setdefault("date", datetime.now().strftime("%Y-%m-%d"))
    validate(data)

    assets = Path(__file__).parent.parent / "assets"
    template = (assets / "drill-template.html").read_text(encoding="utf-8")
    # duo.css is inlined rather than linked: the page is written to a different
    # directory than the assets and has to stand alone.
    page = template.replace(CSS_PLACEHOLDER, (assets / "duo.css").read_text(encoding="utf-8"))
    # Escaping '</' keeps any '</script>' inside drill strings from ending the script tag.
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = page.replace(PLACEHOLDER, payload)

    if len(sys.argv) > 2:
        out = Path(sys.argv[2])
    else:
        home = Path(os.environ.get("GRAMMAR_HOME", Path.home() / ".claude" / "cc-grammar-coach"))
        out_dir = home / "drills"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"drill-{data['date']}-{datetime.now().strftime('%H%M')}.html"
    out.write_text(page, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
