---
name: progress
description: Render a local web page charting grammar mistake frequency by category over time from the grammar-check hook's mistake log. Invoke when the user asks about their grammar progress, mistake trends, frequency charts, or grammar statistics.
---

# Progress

Chart the mistake log over time: a column chart of all mistakes, a small-multiple panel per category, and a table view. Nothing is authored and nothing is built - the dashboard reads `$GRAMMAR_HOME/history.jsonl` and computes the whole view when the page loads, so this skill only opens it on the progress route.

To practice the logged mistakes instead of charting them, use the `drill` skill; to learn a new topic, use the `learn` skill.

1. Open the dashboard on the progress view. Grammar home defaults to `~/.claude/cc-grammar-coach` and is overridden by `$GRAMMAR_HOME`; Bash tool calls do not share shell state, so resolving it and launching the server happen in one command:

   ```
   GRAMMAR_HOME="${GRAMMAR_HOME:-$HOME/.claude/cc-grammar-coach}"
   python3 "$GRAMMAR_HOME/dashboard/server.py" --url-path "#progress"
   ```

   Launch it with the Bash tool's background mode - the server serves until interrupted, so a foreground call would hang the skill. It prints the URL it serves at, opens the browser itself, and exits immediately when a dashboard is already running on the port. If `$GRAMMAR_HOME/dashboard/server.py` does not exist yet (the checker hook copies it there on the first message of a session and may not have run), launch `${CLAUDE_PLUGIN_ROOT}/dashboard/server.py` instead this once and say so in the reply.

   Read the launcher's output before replying - it has four outcomes and only the first two mean the page is usable:
   - `serving the cc-grammar-coach dashboard at <url>` - it started; reply with the template below.
   - `dashboard already running at <url>` - an identical server was already up; reply with the template below.
   - `dashboard already running at <url> with version <v> ... stop it with Ctrl+C and relaunch to pick up the update` - a server from an older plugin version holds the port and will serve the old dashboard. Relay that whole sentence instead of the plain URL line, so the user knows to restart it.
   - a nonzero exit (`port <n> is in use by another program ...` or `cannot bind ...`) - a foreign program holds the port. Relay the message and stop; do not report a URL, it would point at that program, not at the chart.

2. Reply with exactly this template, using the URL the server printed:

   ```
   Progress ready: http://127.0.0.1:<port>/#progress
   ```

   The page states its own counts; do not read the log yourself to summarize them in the reply.

The counts are raw flagged mistakes: a day with more written English naturally shows more of them, so a spike means volume, not regression. The page states this caveat in its footer; do not editorialize about trends beyond it. When the log holds no dated mistakes the page says so itself - relay that rather than fabricating numbers.
