---
name: learn
description: Teach the next new English grammar topic from a weekly syllabus as a lesson-plus-quiz session in the local dashboard. Invoke when the user asks to learn a new grammar topic, the next topic, or a fresh grammar lesson beyond their logged mistakes.
---

# Learn

Teach the next new topic from the weekly syllabus as a lesson-plus-quiz dashboard session, personalized with evidence from the grammar-check hook's mistake log.

The user's native language is `${user_config.native_language}`. When it is set, contrast English rules with the habits that language causes (for example a language with no articles, freer word order, or aspect instead of tense variety). When it is empty, give generic English lessons and do not assume any nationality.

To practice the user's logged mistakes instead of teaching new material, use the `drill` skill; to chart mistake frequency over time, use the `progress` skill.

## Where the data lives

Grammar home defaults to `~/.claude/cc-grammar-coach` and is overridden by `$GRAMMAR_HOME`. Bash tool calls do not share shell state, so it is resolved inside every command that needs it, never in a call of its own:

```
GRAMMAR_HOME="${GRAMMAR_HOME:-$HOME/.claude/cc-grammar-coach}"
```

- `$GRAMMAR_HOME/history.jsonl` - the checker hook's mistake log, one JSON object per non-clean message: `{"ts", "message", "fixes": [{"category", "wrong", "fix", "rule"}], "rephrase"?}`. Used here only to personalize the lesson.
- `$GRAMMAR_HOME/curriculum.tsv` - one `<iso-week>\t<topic-id>` line per taught topic; may not exist yet.

## Building the lesson

1. Get the ISO week (`date +%G-W%V`) and read `$GRAMMAR_HOME/curriculum.tsv`.

2. If a line for the current week exists, review that week's topic with a fresh quiz - the pace is one new topic per week, enforced here, not by a scheduler. Otherwise take the first topic from `references/syllabus.md` not yet listed in the file and append `<iso-week>\t<topic-id>` (create the file and its parent dir if missing).

3. Personalize: scan `history.jsonl` for the topic's constructions - both `fixes[]` on that category and `message` text using or conspicuously avoiding it - to see whether the user misuses or avoids the construction, and work that evidence into the lesson.

4. Build the drill data. Read `${CLAUDE_PLUGIN_ROOT}/skills/drill/references/authoring.md` for the data schema and question-writing rules, then author:
   - The single topic gets `count: 0` (the page renders it as "new topic") and a 3-5 sentence lesson - new material needs more setup than remediation - with 6-8 `questions`.
   - Lesson `examples` come from the user's logged sentences when the log has usable evidence for the topic. When it does not, invent examples showing the typical error a speaker of the user's native language makes instead - do not present invented sentences as the user's own.

5. Write the data to a JSON file in the scratchpad, then run the prepare script from the plugin root:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/drill/scripts/prepare_drill.py" --kind learn <data.json>
   ```

   The script validates the data, stamps `"kind": "learn"` (the dashboard badges the session as a lesson rather than a drill) and today's date, writes `$GRAMMAR_HOME/drills/drill-<date>-<HHMMSS>.json`, and prints that file name - pass the printed name to the next step, never a reconstructed one. It writes nothing when validation fails, so fix the reported error and rerun.

6. Open the lesson in the dashboard, passing the printed file name as the hash route:

   ```
   GRAMMAR_HOME="${GRAMMAR_HOME:-$HOME/.claude/cc-grammar-coach}"
   python3 "$GRAMMAR_HOME/dashboard/server.py" --url-path "#drill=<file>"
   ```

   Launch it with the Bash tool's background mode - the server serves until interrupted, so a foreground call would hang the skill. It prints the URL it serves at, opens the browser itself, and exits immediately when a dashboard is already running on the port. If `$GRAMMAR_HOME/dashboard/server.py` does not exist (the checker hook copies it there on every message, so this only happens when that hook has not run at all), launch `${CLAUDE_PLUGIN_ROOT}/dashboard/server.py` instead this once and say so in the reply.

   Background mode returns no output in the tool result, so poll the launch with `BashOutput` until it has printed a line, and read that line before replying - it has four outcomes and only the first two mean the page is usable:
   - `serving the cc-grammar-coach dashboard at <url>` - it started; reply with the template below.
   - `dashboard already running at <url>` - an identical server was already up; reply with the template below.
   - `dashboard already running at <url> with version <v> ... stop it (Ctrl+C in its terminal, or pkill -f dashboard/server.py) and relaunch to pick up the update` - a server from an older plugin version holds the port and will serve the old dashboard. Relay that whole sentence instead of the plain URL line, so the user knows to restart it.
   - a nonzero exit - the port cannot serve this dashboard: a foreign program holds it, a dashboard on it serves a different grammar home, or `GRAMMAR_DASHBOARD_PORT` is not a port number. Relay the message and stop; do not report a URL, it would point at something other than the lesson.

7. Reply with exactly this template, using the URL the server printed. The dashboard titles the page "New Lesson", so the reply says lesson, not drill:

   ```
   Lesson ready: http://127.0.0.1:<port>/#drill=<file>
   New topic: <label> (<iso-week>)
   Questions: <total count>
   ```

   When step 2 found a line for the current week and this is that week's review rather than a new topic, keep the same three lines and swap the middle one for:

   ```
   Review: <label> (<iso-week>)
   ```
