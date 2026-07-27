# Statusline wiring and state reference

The checker shows its feedback through the Claude Code statusline. A statusline command runs outside the plugin sandbox and `statusLine` is a single user setting, so the plugin cannot inject the grammar segment silently; wiring is a one-time step performed by the bundled command:

```
/cc-grammar-coach:configure install-statusline
```

It either points `statusLine` at the bundled standalone statusline (when none is configured) or backs up your existing script and appends the grammar segment to it; every change is shown before writing, and re-running never appends twice.

## Stable copies

The command first copies `render-grammar.sh` and `grammar-statusline.sh` to stable paths under `~/.claude/cc-grammar-coach/` and wires against those, not the versioned plugin cache. The hook keeps these copies fresh on every prompt, so plugin updates never require re-wiring.

## Manual wiring

If you would rather edit your statusline yourself: Claude Code passes each statusline command a JSON object on stdin that includes `session_id`. Read it, then source the stable renderer copy and call `render_grammar` with that id:

```bash
#!/bin/bash
input=$(cat)

# ... your existing statusline segments ...

# grammar segment:
SID=$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("session_id") or "default")')
if [ -f "$HOME/.claude/cc-grammar-coach/render-grammar.sh" ]; then
    . "$HOME/.claude/cc-grammar-coach/render-grammar.sh"
    render_grammar "$SID"
fi
```

`render_grammar` prints nothing when there is no feedback for the session, and the `-f` guard keeps your statusline safe if the plugin is uninstalled, so the segment is harmless to leave in place permanently.

## State directory (`GRAMMAR_HOME`)

All state lives under one directory, `~/.claude/cc-grammar-coach`, overridable by setting `$GRAMMAR_HOME`. A fresh install creates it lazily; each component makes the subdirectories it writes to. It holds:

| Path                                         | What it is                                                                                                                     |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `status/<session-id>`                        | The current feedback line(s) for one session, read by the statusline. Files older than a day are tidied automatically.         |
| `history.jsonl`                              | Append-only mistake log, one JSON object per non-clean message. The drill's data source.                                       |
| `drills/`                                    | Generated self-contained HTML lessons, one per drill.                                                                          |
| `curriculum.tsv`                             | Learn-mode progress: one `<iso-week>\t<topic-id>` line per week, enforcing one new syllabus topic per week.                    |
| `render-grammar.sh`, `grammar-statusline.sh` | Stable copies of the statusline scripts, refreshed by the hook whenever the plugin updates; the statusline wiring points here. |
