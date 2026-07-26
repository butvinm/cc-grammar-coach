# Statusline wiring and state reference

The checker shows its feedback through the Claude Code statusline. A statusline command runs outside the plugin sandbox and `statusLine` is a single user setting, so the plugin cannot inject the grammar segment silently; wiring is a one-time step performed by the bundled command:

```
/cc-grammar-coach:install-statusline
```

It picks the right move for your setup, shows you every change before writing it, and is safe to re-run (it detects existing wiring and never appends twice):

- **No statusline configured** - it points `statusLine` in `settings.json` at the bundled standalone statusline, which shows just the grammar segment.
- **Existing statusline script** - it backs your script up and appends the grammar segment at the end, adapted to how your script reads stdin.

## Stable copies

Either way, the command first copies `render-grammar.sh` and `grammar-statusline.sh` to stable paths under `~/.claude/cc-grammar-coach/` and wires against those, not the versioned plugin cache. The hook keeps these copies fresh on every prompt, so plugin updates never require re-wiring.

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

## Wire format

The checker writes plain text lines the statusline colors and the drill parses. The three markers `→`, `✔`, and `✨` are the wire format; they are intentional and load-bearing (see `requirements.md` section 3.1 for the exact contract):

- `✔ <compliment>` - clean message; doubles as the liveness signal, so it never renders blank.
- `[<category>] <wrong> → <fix> (<rule>: <why>)` - one line per grammar error. The renderer drops the `[<category>]` tag for display and colors the parts: wrong fragment red, fix green, reason gray.
- `✨ <rewrite>` - optional natural rewrite of the whole message; never appears together with a `✔` line.

## State directory (`GRAMMAR_HOME`)

All state lives under one directory, `~/.claude/cc-grammar-coach`, overridable by setting `$GRAMMAR_HOME`. A fresh install creates it lazily; each component makes the subdirectories it writes to. It holds:

| Path                                         | What it is                                                                                                                     |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `status/<session-id>`                        | The current feedback line(s) for one session, read by the statusline. Files older than a day are tidied automatically.         |
| `history.jsonl`                              | Append-only mistake log, one JSON object per non-clean message. The drill's data source.                                       |
| `drills/`                                    | Generated self-contained HTML lessons, one per drill.                                                                          |
| `curriculum.tsv`                             | Learn-mode progress: one `<iso-week>\t<topic-id>` line per week, enforcing one new syllabus topic per week.                    |
| `render-grammar.sh`, `grammar-statusline.sh` | Stable copies of the statusline scripts, refreshed by the hook whenever the plugin updates; the statusline wiring points here. |
