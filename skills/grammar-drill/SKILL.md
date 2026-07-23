---
name: grammar-drill
description: Build a personalized English grammar lesson and interactive quiz as a local web page, drilling the grammar-check hook's mistake log or teaching the next new topic from a weekly syllabus. Invoke when the user asks for a grammar drill, quiz, practice on their mistakes, or to learn a new grammar topic.
---

# Grammar Drill

Turn the mistakes logged by the grammar-check hook into a lesson-plus-quiz web page grounded in the user's own sentences.

The user's native language is `${user_config.native_language}`. When it is set, contrast English rules with the habits that language causes (for example a language with no articles, freer word order, or aspect instead of tense variety). When it is empty, give generic English lessons and do not assume any nationality.

Two modes: Drill (default) practices the user's logged mistakes; Learn teaches the next new topic from the syllabus - use it when the user asks to learn something new, a new topic, or the next topic.

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

## Drill mode (default)

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

2. Pull the lesson material for the chosen categories. Read `$GRAMMAR_HOME/history.jsonl` again and collect, per chosen category, the `wrong`/`fix` pairs and the surrounding `message` from lines whose `fixes[]` include that category. Skip messages that read as deliberate mistake-planting to test the checker (long unnatural strings of stacked errors). These are the pool for lesson examples.

3. Build the drill data (schema below). Use plain ASCII punctuation in all generated text (straight quotes, hyphens, three dots) - this environment flags em dashes, arrows, and other typographic symbols in written files.
   - Per topic: a lesson with a 2-4 sentence rule explanation aimed at a speaker of the user's native language (generic if it is unset), and 2-4 `examples` taken from the user's own logged mistakes (shorten long sentences to the relevant fragment). `count` is the number of fixes you counted for that topic in the ranking window (not lifetime).
   - 4-6 `questions` per topic, mixing `choice` and `rewrite`. Write fresh sentences that exercise the same rule in new contexts (similar register - casual dev chat - but different vocabulary); at most one question per topic may reuse a logged sentence verbatim.
   - Make `choice` questions genuinely hard: 3-4 options differing by one word or morpheme, over sentences with 2-3 decision points, so only one option gets every point right. Each distractor must be wrong in exactly one subtle way drawn from the user's error patterns. Prefer testing which form fits (a vs the, in vs into vs to, does...have vs does...has) over whether a form is merely present, and include over-correction traps (an article on an uncountable or a generic plural, a double-marked verb after 'does'). When the right article depends on shared knowledge, set the scene in the prompt ("First message in a thread:").
4. Write the data to a JSON file in the scratchpad, then run the builder from the plugin root:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/grammar-drill/scripts/build_drill.py" <data.json>
   ```

   The script validates the data, inlines `assets/duo.css` into `assets/drill-template.html`, writes `$GRAMMAR_HOME/drills/drill-<date>-<HHMM>.html`, and prints the path. It never opens the page, so rebuilding to inspect the markup does not spawn a browser. Then open the printed path portably - `open` on macOS, `xdg-open` on Linux, and if neither exists just report the path:

   ```
   if command -v open >/dev/null 2>&1; then open "<path>"
   elif command -v xdg-open >/dev/null 2>&1; then xdg-open "<path>"
   else echo "Open this in a browser: <path>"; fi
   ```

5. Reply with exactly this template:

   ```
   Drill ready: <output path>
   Topics: <label> (<N> logged mistakes), <label> (<N>), ...
   Questions: <total count>
   ```

If `history.jsonl` has fewer than 5 usable grammar fixes overall, do not fabricate a generic lesson - say the log is too small and suggest writing more English first.

## Learn mode (new weekly topic)

1. Get the ISO week (`date +%G-W%V`) and read `$GRAMMAR_HOME/curriculum.tsv` (lines: `<iso-week>\t<topic-id>`; the file may not exist yet).
2. If a line for the current week exists, review that week's topic with a fresh quiz - the pace is one new topic per week, enforced here, not by a scheduler. Otherwise take the first topic from `references/syllabus.md` not yet listed in the file and append `<iso-week>\t<topic-id>` (create the file and its parent dir if missing).
3. Personalize: scan `history.jsonl` for the topic's constructions - both `fixes[]` on that category and `message` text using or conspicuously avoiding it - to see whether the user misuses or avoids the construction, and work that evidence into the lesson.
4. Build the same data as Drill mode step 3 under the same question-hardness rules, with two Learn-mode differences: the single topic gets `count: 0` (the page renders it as "new topic") and a longer 3-5 sentence lesson (new material needs more setup than remediation), with 6-8 questions. When the log has no usable evidence for the topic, invent examples showing the typical error a speaker of the user's native language makes instead - do not present invented sentences as the user's own. Then continue with Drill mode steps 4-5, replacing the reply's `Topics:` line with `New topic: <label> (<iso-week>)` or `Review: <label> (<iso-week>)`.

## Drill data schema

```json
{
  "date": "2026-07-15",
  "topics": [
    {
      "id": "articles",
      "label": "Articles",
      "count": 14,
      "lesson": {
        "summary": "English marks singular countable nouns with an article ... (2-4 sentences)",
        "examples": [
          {
            "wrong": "create skill",
            "right": "create a skill",
            "note": "singular countable noun needs an article"
          }
        ]
      }
    }
  ],
  "questions": [
    {
      "topic": "articles",
      "type": "choice",
      "prompt": "Pick the correct sentence:",
      "options": [
        "Let's write test for parser",
        "Let's write a test for the parser"
      ],
      "answer": 1,
      "explain": "Both nouns are singular and countable."
    },
    {
      "topic": "articles",
      "type": "rewrite",
      "prompt": "Fix this sentence: I pushed fix to repo",
      "answers": ["I pushed a fix to the repo", "I pushed the fix to the repo"],
      "explain": "'fix' and 'repo' both need articles."
    }
  ]
}
```

`topic` must match a topic `id`. `answer` is a 0-based index into `options`. `answers` lists every acceptable rewrite; comparison ignores only case, extra spaces, and end punctuation, so enumerate variants yourself - contraction and full forms (We've / We have), and each valid article or tense choice. Distractors in `choice` options must be wrong in every standard variety of English - skip a tempting distractor if American usage accepts it (e.g. 'already' with past simple).
