---
name: progress
description: Render a local web page charting grammar mistake frequency by category over time from the grammar-check hook's mistake log. Invoke when the user asks about their grammar progress, mistake trends, frequency charts, or grammar statistics.
---

# Progress

Chart the mistake log over time: a column chart of all mistakes, a small-multiple panel per category, and a table view. The page is deterministic - nothing is authored; build it and open it.

To practice the logged mistakes instead of charting them, use the `drill` skill; to learn a new topic, use the `learn` skill.

1. Run the builder:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/progress/scripts/build_progress.py"
   ```

   It reads `$GRAMMAR_HOME/history.jsonl` (`GRAMMAR_HOME` defaults to `~/.claude/cc-grammar-coach`), aggregates every logged fix into day, week, or month buckets depending on the log's span, writes `$GRAMMAR_HOME/progress.html` - overwritten on every run, the page is a pure function of the log - and prints the output path followed by a one-line summary. If it fails with "no dated mistakes", relay that message instead of fabricating a page.

2. Open the printed path portably - `open` on macOS, `xdg-open` on Linux, and if neither exists just report the path:

   ```
   if command -v open >/dev/null 2>&1; then open "<path>"
   elif command -v xdg-open >/dev/null 2>&1; then xdg-open "<path>"
   else echo "Open this in a browser: <path>"; fi
   ```

3. Reply with exactly this template, quoting the two lines the builder printed:

   ```
   Progress page ready: <output path>
   <summary line>
   ```

The counts are raw flagged mistakes: a day with more written English naturally shows more of them, so a spike means volume, not regression. The page states this caveat in its footer; do not editorialize about trends beyond it.
