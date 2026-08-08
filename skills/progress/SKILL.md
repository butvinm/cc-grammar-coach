---
name: progress
description: Report how the user's English is trending from the grammar-check hook's mistake log and their past quiz scores. Invoke when the user asks about their progress, whether they are improving, their weak spots over time, or their grammar stats.
---

# Progress

Read the log the checker has been filling and tell the user what it says about their English over time.

The user's native language is `${user_config.native_language}`. When it is set, explain a persistent category in terms of the habit that language causes. When it is empty, stay language-neutral.

## Where the data lives

Grammar home defaults to `~/.claude/cc-grammar-coach` and is overridden by `$GRAMMAR_HOME`. Resolve it once:

```
GRAMMAR_HOME="${GRAMMAR_HOME:-$HOME/.claude/cc-grammar-coach}"
```

- `$GRAMMAR_HOME/history.jsonl` - one JSON object per reviewed message: `{"ts", "message", "fixes": [{"category", "wrong", "fix", "rule"}], "rephrase"?, "praise"?}`. Clean messages are logged too, with an empty `fixes` list and a `praise` key, so they are the denominator for any rate.
- `$GRAMMAR_HOME/results.jsonl` - one line per finished quiz: `{"ts", "drill", "kind", "total", "correct", "byTopic"}`.

## Reporting

1. Run the summary from the plugin root:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/progress/scripts/summarize_progress.py"
   ```

   It prints the coverage line, a week-by-week table of messages, fixes and fixes-per-message, a category table comparing the last 7 days with the 7 before and with lifetime, and the last 10 quiz scores. If it reports no reviewed messages, say the log is empty and stop - there is nothing to trend.

2. Read the numbers back as a short report, not as a dump of the table. Lead with the rate, not the raw count: message volume swings week to week, so fixes-per-message is the only line that answers "am I getting better". Then name at most three things:
   - What improved. A category that fell to zero after a high lifetime count is the strongest result available and deserves to be said out loud.
   - What regressed or persists. A category whose last 7 days beat the 7 before is moving the wrong way even when its lifetime count is small.
   - Whether quiz scores line up with the log. A topic drilled at 5/5 that keeps getting flagged means the quiz was too easy, not that the user learned it - say so.

3. Ground the persistent categories in the user's own sentences. Read `history.jsonl` for two or three recent `wrong`/`fix` pairs in the top category and quote them, so the report names an actual habit rather than a slug.

4. Close by offering the drill, naming the category it would open on. Do not run it - wait for the user to ask.

Do not invent a target, a streak, or a grade. The log has counts and dates; anything else is decoration.
