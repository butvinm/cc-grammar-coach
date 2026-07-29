---
name: drill
description: Build a personalized English grammar lesson and interactive quiz as a local web page from the grammar-check hook's mistake log. Invoke when the user asks for a grammar drill, quiz, or practice on their mistakes.
---

# Drill

Turn the mistakes logged by the grammar-check hook into a lesson-plus-quiz web page grounded in the user's own sentences.

The user's native language is `${user_config.native_language}`. When it is set, contrast English rules with the habits that language causes (for example a language with no articles, freer word order, or aspect instead of tense variety). When it is empty, give generic English lessons and do not assume any nationality.

To teach a new topic from the weekly syllabus instead of drilling logged mistakes, use the `learn` skill; to chart mistake frequency over time, use the `progress` skill.

## Where the data lives

Grammar home defaults to `~/.claude/cc-grammar-coach` and is overridden by `$GRAMMAR_HOME`. Resolve it once:

```
GRAMMAR_HOME="${GRAMMAR_HOME:-$HOME/.claude/cc-grammar-coach}"
```

The mistake log is `$GRAMMAR_HOME/history.jsonl` - one JSON object per line, appended by the checker hook, one line per non-clean message. There is no other log; do not grep any legacy file. Each line:

```json
{
  "ts": "2026-07-22T00:54:06+03:00",
  "message": "<the user's raw message>",
  "fixes": [
    {
      "category": "articles",
      "wrong": "create skill",
      "fix": "create a skill",
      "rule": "<why, short>"
    }
  ],
  "rephrase": "<a more natural rewrite of the whole message, or the key is absent>"
}
```

Use it two ways: `fixes[].category` ranks recent weak spots, and a line's presence pre-filters which messages actually contained mistakes. Re-read `message` (with its `fixes`) as the source material for lesson examples.

## Building the drill

1. Rank recent weak spots by counting `fixes[].category` over a recency window, not lifetime totals - the user's weak spots move, and a topic they have already stopped getting flagged on must stop being drilled. Run exactly this ranking, which prints `<count>\t<category>` lines in descending order:

   ```
   python3 - "$GRAMMAR_HOME/history.jsonl" <<'PY'
   import collections, datetime, json, sys
   path = sys.argv[1]
   try:
       rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
   except FileNotFoundError:
       rows = []
   cutoff = datetime.datetime.now().astimezone() - datetime.timedelta(days=7)
   def in_window(r):
       try:
           return datetime.datetime.fromisoformat(r["ts"]) >= cutoff
       except (KeyError, ValueError):
           return False
   window = [r for r in rows if in_window(r)]
   # Widen to the last 200 lines when the 7-day window holds fewer than 30 fixes;
   # line order is the only recency signal for entries without a usable ts.
   if sum(len(r.get("fixes", [])) for r in window) < 30:
       window = rows[-200:]
   counts = collections.Counter(f["category"] for r in window for f in r.get("fixes", []))
   for cat, n in counts.most_common():
       print(f"{n}\t{cat}")
   PY
   ```

   Pick the top 2-3 categories from that ordering. Skip typo/spelling categories and any non-grammar category (for example `other`) - they are not grammar topics. If two categories tie on count, the earlier-printed one ranks first (the counter breaks ties by first appearance).

   When several `verb-*` slugs rank high but none alone has at least 3 fixes in the window, merge the closest siblings into one topic instead of teaching a thin lesson per slug.

2. Pull the lesson material for the chosen categories. Read `$GRAMMAR_HOME/history.jsonl` again and collect, per chosen category, the `wrong`/`fix` pairs and the surrounding `message` from lines whose `fixes[]` include that category. Skip messages that read as deliberate mistake-planting to test the checker (long unnatural strings of stacked errors). These are the pool for lesson examples.

3. Build the drill data. Read `${CLAUDE_PLUGIN_ROOT}/skills/drill/references/authoring.md` for the data schema and question-writing rules, then author:
   - Per topic: a lesson with a 2-4 sentence rule explanation aimed at a speaker of the user's native language (generic if it is unset), and 2-4 `examples` taken from the user's own logged mistakes (shorten long sentences to the relevant fragment). `count` is the number of fixes you counted for that topic in the ranking window (not lifetime).
   - 4-6 `questions` per topic.

4. Write the data to a JSON file in the scratchpad, then run the prepare script from the plugin root:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/drill/scripts/prepare_drill.py" --kind drill <data.json>
   ```

   The script validates the data, stamps `"kind": "drill"`, writes `$GRAMMAR_HOME/drills/drill-<date>-<HHMM>.json`, and prints that file name. It writes nothing when validation fails, so fix the reported error and rerun.

5. Open the drill in the dashboard, passing the printed file name as the hash route:

   ```
   python3 "$GRAMMAR_HOME/dashboard/server.py" --url-path "#drill=<file>"
   ```

   Launch it with the Bash tool's background mode - the server serves until interrupted, so a foreground call would hang the skill. It prints the URL it serves at, opens the browser itself, and exits immediately when a dashboard is already running on the port. If `$GRAMMAR_HOME/dashboard/server.py` does not exist yet (the checker hook copies it there on the first message of a session and may not have run), launch `${CLAUDE_PLUGIN_ROOT}/dashboard/server.py` instead this once and say so in the reply.

6. Reply with exactly this template, using the URL the server printed:

   ```
   Drill ready: http://127.0.0.1:<port>/#drill=<file>
   Topics: <label> (<N> logged mistakes), <label> (<N>), ...
   Questions: <total count>
   ```

If `history.jsonl` has fewer than 5 usable grammar fixes overall, do not fabricate a generic lesson - say the log is too small and suggest writing more English first.
