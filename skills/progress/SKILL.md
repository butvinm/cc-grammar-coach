---
name: progress
description: Chart grammar mistake frequency by category over time in the local dashboard, from the grammar-check hook's mistake log. Invoke when the user asks about their grammar progress, mistake trends, frequency charts, or grammar statistics.
---

# Progress

Chart the mistake log over time: a column chart of all mistakes, a small-multiple panel per category, and a table view. Nothing is authored and nothing is built - the dashboard reads `$GRAMMAR_HOME/history.jsonl` and computes the whole view when the page loads, so this skill only opens it on the progress route.

To practice the logged mistakes instead of charting them, use the `drill` skill; to learn a new topic, use the `learn` skill.

1. Open the dashboard on the progress view. Grammar home defaults to `~/.claude/cc-grammar-coach` and is overridden by `$GRAMMAR_HOME`; Bash tool calls do not share shell state, so resolving it and launching the server happen in one command, and it is exported - the server reads `GRAMMAR_HOME` from the environment and would serve the default home if a plain shell assignment kept it out of the server's:

   ```
   export GRAMMAR_HOME="${GRAMMAR_HOME:-$HOME/.claude/cc-grammar-coach}"
   python3 "$GRAMMAR_HOME/dashboard/server.py" --url-path "#progress"
   ```

   Launch it with the Bash tool's background mode - the server serves until interrupted, so a foreground call would hang the skill. It prints the URL it serves at, opens the browser itself, and exits immediately when a dashboard is already running on the port. If `$GRAMMAR_HOME/dashboard/server.py` does not exist (the checker hook copies it there on every message, so this only happens when that hook has not run at all), launch `${CLAUDE_PLUGIN_ROOT}/dashboard/server.py` instead this once and say so in the reply.

   The launcher's line appears only after the background command runs, so poll for it before replying: use `BashOutput` when that tool is available, otherwise read the output file whose path the Bash tool reported when it backgrounded the command. That line has four outcomes and only the first two mean the page is usable:
   - `serving the cc-grammar-coach dashboard at <url> (Ctrl+C to stop)` - it started; reply with the template below.
   - `dashboard already running at <url>` - an identical server was already up; reply with the template below.
   - `dashboard already running at <url> with version <v> ...` - a server from an older plugin version holds the port and will serve the old dashboard. Its line ends with the stop instruction that server's own launcher printed; relay the whole line verbatim instead of the plain URL, so the user knows how to restart it, and never substitute a stop command of your own.
   - a nonzero exit - the port cannot serve this dashboard: a foreign program holds it, a dashboard on it serves a different grammar home, or `GRAMMAR_DASHBOARD_PORT` is not a port number. Relay the message and stop; do not report a URL, it would point at something other than the chart.

2. On the first two outcomes, reply with exactly this template - the last two replace it with what they say above, and nothing else may be added. Its line shows the shape of the URL - copy the URL the server printed verbatim in its place:

   ```
   Progress ready: http://127.0.0.1:<port>/#progress
   ```

   The one permitted addition is a line saying you launched the plugin's copy of server.py, and only when `$GRAMMAR_HOME/dashboard/server.py` was missing.

   The page states its own counts; do not read the log yourself to summarize them in the reply.

The counts are raw flagged mistakes: a day with more written English naturally shows more of them, so a spike means volume, not regression. The page states this caveat in its footer; do not editorialize about trends beyond it. When the log holds no dated mistakes the page says so itself - relay that rather than fabricating numbers.
