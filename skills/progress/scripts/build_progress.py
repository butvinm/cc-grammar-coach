#!/usr/bin/env python3
"""Build the grammar progress page from the mistake log.

Usage: build_progress.py [output.html]

Reads $GRAMMAR_HOME/history.jsonl (GRAMMAR_HOME defaults to ~/.claude/cc-grammar-coach), buckets every logged fix by day, ISO week, or month depending on the log's span, and injects the aggregate into assets/progress-template.html together with the drill skill's duo.css - the design system is shared, so it lives in one place. Writes $GRAMMAR_HOME/progress.html (an explicit output path overrides) and prints two lines: the path and a one-line summary. The page is a pure function of the log, so it is overwritten on every run rather than accumulating like drills do. Stdlib only.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

CSS_PLACEHOLDER = "__DUO_CSS__"
DATA_PLACEHOLDER = "__PROGRESS_DATA__"


def fail(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def humanize(slug: str) -> str:
    return (slug[:1].upper() + slug[1:]).replace("-", " ")


def bucket_of(d, unit):
    if unit == "day":
        return d
    if unit == "week":
        return d - timedelta(days=d.weekday())
    return d.replace(day=1)


def bucket_seq(first, last, unit):
    seq = []
    b = bucket_of(first, unit)
    end = bucket_of(last, unit)
    while b <= end:
        seq.append(b)
        if unit == "day":
            b += timedelta(days=1)
        elif unit == "week":
            b += timedelta(days=7)
        else:
            b = (b.replace(day=28) + timedelta(days=4)).replace(day=1)
    return seq


def main() -> None:
    home = Path(os.environ.get("GRAMMAR_HOME", Path.home() / ".claude" / "cc-grammar-coach"))
    history = home / "history.jsonl"
    try:
        lines = history.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        fail(f"cannot read the mistake log: {exc}")

    events = []
    undated = 0
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        categories = [f["category"] for f in row.get("fixes") or [] if f.get("category")]
        if not categories:
            continue
        try:
            ts = datetime.fromisoformat(row["ts"])
            if ts.tzinfo is None:
                ts = ts.astimezone()
        except (KeyError, TypeError, ValueError):
            undated += len(categories)
            continue
        events.extend((ts, c) for c in categories)

    if not events:
        fail("no dated mistakes in the log yet - write more English first")

    first = min(ts for ts, _ in events).date()
    last = max(ts for ts, _ in events).date()
    span_days = (last - first).days
    unit = "day" if span_days <= 60 else "week" if span_days <= 420 else "month"
    unit_label = {"day": "daily", "week": "weekly", "month": "monthly"}[unit]

    buckets = bucket_seq(first, last, unit)
    index = {b: i for i, b in enumerate(buckets)}
    counts = defaultdict(lambda: [0] * len(buckets))
    total = [0] * len(buckets)
    for ts, category in events:
        i = index[bucket_of(ts.date(), unit)]
        counts[category][i] += 1
        total[i] += 1

    categories = [
        {"label": humanize(c), "counts": counts[c], "total": sum(counts[c])}
        for c in sorted(counts, key=lambda c: (-sum(counts[c]), c))
    ]

    label_fmt = "%b %Y" if unit == "month" else "%b %d"
    cutoff = datetime.now().astimezone() - timedelta(days=7)
    span_start = first.strftime("%b %d" if first.year == last.year else "%b %d, %Y")
    data = {
        "unit": unit,
        "unitLabel": unit_label,
        "span": f"{span_start} - {last.strftime('%b %d, %Y')}",
        "labels": [b.strftime(label_fmt) for b in buckets],
        "total": total,
        "categories": categories,
        "stats": {
            "mistakes": len(events),
            "last7": sum(1 for ts, _ in events if ts >= cutoff),
            "categories": len(categories),
        },
        "undated": undated,
    }

    assets = Path(__file__).parent.parent / "assets"
    duo_css = Path(__file__).parent.parent.parent / "drill" / "assets" / "duo.css"
    template = (assets / "progress-template.html").read_text(encoding="utf-8")
    page = template.replace(CSS_PLACEHOLDER, duo_css.read_text(encoding="utf-8"))
    # Escaping '</' keeps any '</script>' inside category slugs from ending the script tag.
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = page.replace(DATA_PLACEHOLDER, payload)

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else home / "progress.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(out)
    print(f"{len(events)} mistakes in {len(categories)} categories, {data['span']}, {unit_label} buckets")


if __name__ == "__main__":
    main()
