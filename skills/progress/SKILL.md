---
name: progress
description: Render a local web page charting grammar mistake frequency by category over time from the grammar-check hook's mistake log. Invoke when the user asks about their grammar progress, mistake trends, frequency charts, or grammar statistics.
---

# Progress

Chart the mistake log over time: a column chart of all mistakes, a small-multiple panel per category, and a table view. Nothing is authored and nothing is built - the dashboard reads `$GRAMMAR_HOME/history.jsonl` and computes the whole view when the page loads, so this skill only opens it on the progress route.

To practice the logged mistakes instead of charting them, use the `drill` skill; to learn a new topic, use the `learn` skill.

1. Resolve grammar home (it defaults to `~/.claude/cc-grammar-coach` and is overridden by `$GRAMMAR_HOME`) and open the dashboard on the progress view:

   ```
   GRAMMAR_HOME="${GRAMMAR_HOME:-$HOME/.claude/cc-grammar-coach}"
   ```

   ```
   python3 "$GRAMMAR_HOME/dashboard/server.py" --url-path "#progress"
   ```

   Launch it with the Bash tool's background mode - the server serves until interrupted, so a foreground call would hang the skill. It prints the URL it serves at, opens the browser itself, and exits immediately when a dashboard is already running on the port. If `$GRAMMAR_HOME/dashboard/server.py` does not exist yet (the checker hook copies it there on the first message of a session and may not have run), launch `${CLAUDE_PLUGIN_ROOT}/dashboard/server.py` instead this once and say so in the reply.

2. Reply with exactly this template, using the URL the server printed:

   ```
   Progress ready: http://127.0.0.1:<port>/#progress
   ```

   The page states its own counts; do not read the log yourself to summarize them in the reply.

The counts are raw flagged mistakes: a day with more written English naturally shows more of them, so a spike means volume, not regression. The page states this caveat in its footer; do not editorialize about trends beyond it. When the log holds no dated mistakes the page says so itself - relay that rather than fabricating numbers.
