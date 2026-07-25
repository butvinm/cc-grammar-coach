---
description: Wire grammar feedback into your statusline (one-time; idempotent)
---

Wire the cc-grammar-coach feedback segment into the user's Claude Code statusline. Work against the stable copies in `$GRAMMAR_HOME` (default `~/.claude/cc-grammar-coach`), never against the versioned plugin cache path: the cache path changes on every plugin update, while the hook refreshes the `GRAMMAR_HOME` copies automatically, so wiring done here survives updates.

Follow these steps:

1. **Seed the stable copies.** Create `$GRAMMAR_HOME` if missing, then copy `${CLAUDE_PLUGIN_ROOT}/statusline/render-grammar.sh` and `${CLAUDE_PLUGIN_ROOT}/statusline/grammar-statusline.sh` into it and make them executable. Do this unconditionally: the hook also refreshes these copies on every prompt, but this command must work immediately after install, before the hook has ever fired.

2. **Inspect the current statusline.** Read `statusLine` from `~/.claude/settings.json` and branch:

   - **Already wired** - the configured command (or the script file it points to) references `render-grammar.sh`, `grammar-statusline.sh`, or `GRAMMAR_HOME`: report that the wiring is already in place, run the verification in step 3, and stop. Never append a second copy.

   - **No statusline configured**: confirm with the user, then set `statusLine` in `~/.claude/settings.json` to:

     ```json
     {
       "type": "command",
       "command": "~/.claude/cc-grammar-coach/grammar-statusline.sh",
       "padding": 0
     }
     ```

   - **Existing statusline script**: read the script it points to and append the grammar segment at the end, adapted to how that script already handles stdin (statusline commands receive a JSON object on stdin whose `session_id` field is the key; the script may have it captured in a variable, e.g. `input=$(cat)`, or you may need to capture it first). Before writing, save a backup next to the script as `<name>.bak` and show the user the exact addition. The canonical form to adapt:

     ```bash
     GRAMMAR_SID=$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("session_id") or "default")' 2>/dev/null)
     if [ -f "$HOME/.claude/cc-grammar-coach/render-grammar.sh" ]; then
         . "$HOME/.claude/cc-grammar-coach/render-grammar.sh"
         render_grammar "${GRAMMAR_SID:-default}"
     fi
     ```

     `render_grammar` prints nothing when there is no feedback for the session, and the `-f` guard keeps the script safe if the plugin is uninstalled, so the segment is harmless to leave in permanently.

   - **Inline command string** (a command that is not a path to an editable script file): do not try to splice into it. Explain the situation and ask the user whether to move the inline command into a script file (e.g. `~/.claude/statusline.sh`, referenced from settings) and wire that, or to leave things unchanged.

3. **Verify end to end.** Write a one-line test file `$GRAMMAR_HOME/status/statusline-test` containing `[articles] status line → the status line (rule: missing definite article)`, pipe `{"session_id":"statusline-test"}` into the configured statusline command, and check the output contains `status line`. Delete the test file afterwards. If verification fails, say so plainly and show the output - do not report success.

4. **Report.** Use exactly this template:

   ```
   ## Statusline wiring

   - Mode: <standalone installed | appended to existing script | already wired | declined>
   - Statusline: <path or command from settings.json>
   - Backup: <path, or "none">
   - Verification: <passed | FAILED: reason>

   Feedback appears a few seconds after each English message you send. Raw feedback lives in ~/.claude/cc-grammar-coach/status/<session-id>; the mistake log for /cc-grammar-coach:grammar-drill is ~/.claude/cc-grammar-coach/history.jsonl.
   ```
