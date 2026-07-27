---
description: Configure cc-grammar-coach; subcommands: install-statusline wires grammar feedback into your statusline (one-time; idempotent), mistake-categories chooses which error categories the checker flags
argument-hint: install-statusline | mistake-categories
---

Requested subcommand: $ARGUMENTS

If the subcommand is not exactly `install-statusline` or `mistake-categories`, reply with the supported usage and stop, presenting the commands in a fenced code block exactly like this:

```
/cc-grammar-coach:configure install-statusline    # wire grammar feedback into your statusline
/cc-grammar-coach:configure mistake-categories    # choose which error categories the checker flags
```

# mistake-categories

Let the user choose which error categories the checker flags. The catalog of every defined category is `${CLAUDE_PLUGIN_ROOT}/config/categories.txt` (one `slug: definition` line each). The active selection is the first existing file of `$GRAMMAR_HOME/enabled-categories.txt` (user selection) then `${CLAUDE_PLUGIN_ROOT}/config/enabled-categories.txt` (shipped default), one slug per line. `GRAMMAR_HOME` defaults to `~/.claude/cc-grammar-coach`.

Follow these steps:

1. **Read the state.** Load the catalog and the active selection, noting which file the selection came from (default or user).

2. **Show evidence, not a bare list.** For each catalog category print: enabled or disabled, the definition's opening clause as a gloss, and how many times it appears in `fixes[].category` over the last 200 lines of `$GRAMMAR_HOME/history.jsonl` (0 for never-logged and for disabled categories). Then scan the `rephrase` fields of those lines for recurring corrections matching disabled categories (word reordering for `word-order`, inserted pronouns for `pronouns`, sentence splits for `punctuation`, ...) and mention any pattern you find as a suggestion to enable that category. Skip the suggestion when nothing stands out - do not invent evidence.

3. **Ask what to change** in plain language (enable X, disable Y; multiple changes at once are fine). Warn before disabling a category that has logged mistakes in the window, and warn when enabling `punctuation` that casual chat often omits punctuation deliberately, so it is the noisiest category. If the user changes nothing, stop without writing.

4. **Write the selection** to `$GRAMMAR_HOME/enabled-categories.txt`, one slug per line: exactly the resulting enabled set, only slugs present in the catalog, never an empty file. Creating this file means plugin updates no longer change the user's selection; mention that, and that deleting the file returns them to the shipped default.

5. **Report.** Use exactly this template:

   ```
   ## Checker categories

   - Enabled: <comma-separated slugs>
   - Disabled: <comma-separated slugs>
   - Selection file: <path, or "shipped default (no user selection written)">
   ```

# install-statusline

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

   Feedback appears a few seconds after each English message you send. Raw feedback lives in ~/.claude/cc-grammar-coach/status/<session-id>; the mistake log for /cc-grammar-coach:drill is ~/.claude/cc-grammar-coach/history.jsonl.
   ```
