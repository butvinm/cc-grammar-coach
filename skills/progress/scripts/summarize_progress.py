#!/usr/bin/env python3
"""Summarize the mistake log and the quiz results as plain text.

Usage: summarize_progress.py [history.jsonl] [results.jsonl]

Both paths default to $GRAMMAR_HOME (itself defaulting to ~/.claude/cc-grammar-coach). The numbers are computed here and read out in the session, so this prints tables rather than a chart: the interpretation is the model's job and does not need pixels. Stdlib only.
"""

import collections
import datetime
import json
import os
import sys
from pathlib import Path

WEEKS = 8
BAR_WIDTH = 20


def load(path: Path) -> tuple:
    """Return (rows, skipped). A malformed line is skipped rather than fatal: the log is appended by a backgrounded subshell, and one truncated write must not cost the user their whole history. The count is returned so the damage is reported instead of hidden."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return [], 0
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        sys.exit(1)
    rows, skipped = [], 0
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            skipped += 1
    return rows, skipped


def ts_of(row: dict):
    try:
        return datetime.datetime.fromisoformat(row["ts"])
    except (KeyError, TypeError, ValueError):
        return None


def bar(value: float, peak: float) -> str:
    # Bars are scaled to the largest bucket rather than an absolute rate, because the question a week-over-week table answers is "worse or better than my own other weeks", not "worse than some fixed standard".
    if peak <= 0:
        return ""
    return "#" * max(1, round(BAR_WIDTH * value / peak)) if value > 0 else ""


def main() -> None:
    home = Path(os.environ.get("GRAMMAR_HOME", Path.home() / ".claude" / "cc-grammar-coach"))
    history, damaged = load(Path(sys.argv[1]) if len(sys.argv) > 1 else home / "history.jsonl")
    results, _ = load(Path(sys.argv[2]) if len(sys.argv) > 2 else home / "results.jsonl")
    if damaged:
        print(f"Note: {damaged} unreadable line(s) in the mistake log were skipped.\n")

    now = datetime.datetime.now().astimezone()
    stamped = [(ts_of(r), r) for r in history]
    dated = [(t, r) for t, r in stamped if t is not None]

    total_msgs = len(history)
    total_fixes = sum(len(r.get("fixes", [])) for r in history)
    clean = sum(1 for r in history if not r.get("fixes"))
    if not total_msgs:
        # Falling through rather than returning: a home with quiz results but no reviewed messages is not an empty home, and the Quizzes section below still has something to say.
        print("No reviewed messages logged yet.")
    else:
        span = ""
        if dated:
            span = f", {min(t for t, _ in dated).date()} to {max(t for t, _ in dated).date()}"
        print(f"Messages reviewed: {total_msgs}{span}")
        print(f"Clean: {clean} ({100 * clean // total_msgs}%)   Mistakes logged: {total_fixes}")
        if not dated:
            print("\nNo timestamps in the log, so no trend is available.")

    if dated:
        print(f"\nLast {WEEKS} weeks")
        print(f"{'week':<10}{'msgs':>6}{'fixes':>7}{'per msg':>9}  trend")
        weeks = collections.OrderedDict()
        for i in range(WEEKS - 1, -1, -1):
            day = now - datetime.timedelta(weeks=i)
            weeks["%s-W%02d" % day.isocalendar()[:2]] = [0, 0]
        for t, r in dated:
            key = "%s-W%02d" % t.isocalendar()[:2]
            if key in weeks:
                weeks[key][0] += 1
                weeks[key][1] += len(r.get("fixes", []))
        rates = [f / m for m, f in weeks.values() if m]
        peak = max(rates) if rates else 0
        for label, (msgs, fixes) in weeks.items():
            if not msgs:
                print(f"{label:<10}{'-':>6}{'-':>7}{'-':>9}")
                continue
            rate = fixes / msgs
            print(f"{label:<10}{msgs:>6}{fixes:>7}{rate:>9.2f}  {bar(rate, peak)}")

        cutoff = now - datetime.timedelta(days=7)
        prev_cutoff = now - datetime.timedelta(days=14)
        recent = collections.Counter(f["category"] for t, r in dated if t >= cutoff for f in r.get("fixes", []))
        prev = collections.Counter(f["category"] for t, r in dated if prev_cutoff <= t < cutoff for f in r.get("fixes", []))
        lifetime = collections.Counter(f["category"] for r in history for f in r.get("fixes", []))
        if lifetime:
            print("\nCategories (last 7 days vs the 7 before, then lifetime)")
            print(f"{'category':<26}{'7d':>5}{'prev':>6}{'life':>6}")
            # Ordered by the recent count first so the table opens on what is currently going wrong; categories that have gone quiet sink to the bottom but stay visible, because a zero after a high lifetime count is the result the user is working for.
            for cat, life in sorted(lifetime.items(), key=lambda kv: (-recent[kv[0]], -kv[1])):
                print(f"{cat:<26}{recent[cat]:>5}{prev[cat]:>6}{life:>6}")

    print("\nQuizzes")
    if not results:
        print("None recorded yet.")
    else:
        for r in results[-10:]:
            when = str(r.get("ts", ""))[:10]
            topics = " ".join(f"{k} {v.get('good')}/{v.get('total')}" for k, v in sorted(r.get("byTopic", {}).items()))
            print(f"{when}  {r.get('kind', 'drill'):<6}{r.get('correct')}/{r.get('total'):<4} {topics}")


if __name__ == "__main__":
    main()
