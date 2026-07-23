# cc-grammar-coach

An English grammar coach for Claude Code, in two parts:

- a **checker** hook that reviews every English message you send, out of band, logs the mistakes it finds, and can show short feedback in your statusline;
- a **drill** skill that turns those logged mistakes into a personalized lesson-and-quiz web page.

The checker never blocks your turn and never writes to the conversation: it runs the model call in the background and returns immediately, so the only place you see feedback is the statusline (and only if you opt in). Everything it logs feeds the drill, so even with feedback turned off it keeps building material to practice from.

**v1 teaches English only.** The target language is fixed to English throughout: the prompt, the mistake categories, the syllabus, and the eval are all English-specific. A configurable target language is planned for v2 and is not available yet. Your _native_ language is configurable and only affects how the drill explains things (see below); it never changes what the checker flags.

## Requirements

- `bash`, `python3`, and `curl` (used by the hook; no `jq` required).
- A grammar model. Either an OpenAI-compatible chat-completions endpoint (recommended: `openai/gpt-oss-120b`), or nothing at all, in which case the hook falls back to the local `claude -p` haiku CLI with zero configuration.
- `hunspell` and the `claude` CLI are optional.
- Linux or macOS.

## Install

In Claude Code, add this repository as a plugin marketplace, then install the plugin:

```
/plugin marketplace add butvinm/cc-grammar-coach
/plugin install cc-grammar-coach@cc-grammar-coach
```

`/plugin marketplace add` also accepts a full git URL or a local path to a clone. The `@cc-grammar-coach` suffix names the marketplace; if the plugin name is unambiguous, `/plugin install cc-grammar-coach` works too, and the interactive `/plugin` menu lets you pick it from a list.

### The configuration prompts

On install, Claude Code prompts you for the plugin's settings. Each maps to a `userConfig` field the hook and drill read at runtime:

- **Native language** (`native_language`) - your first language, e.g. `Russian`. The drill uses it to explain English rules by contrast with the habits your language creates (no articles, freer word order, aspect instead of tense, and so on). **No default:** leave it empty for generic, language-neutral lessons that assume no nationality. The checker ignores this field entirely.
- **Suggest rephrasings** (`rephrase`, default **true**) - when on, the checker may add one `✨` line rewriting a clearly awkward message more naturally. Grammar flags appear regardless of this setting; only the extra rewrite is gated by it.
- **Show statusline feedback** (`show_feedback`, default **true**) - when on, the checker writes feedback for the statusline to display. Turn it **off** to keep logging mistakes for the drill while seeing nothing on screen. Capture and display are independent: the drill works either way.
- **LLM base URL** (`llm_base_url`) - the base URL of an OpenAI-compatible endpoint. The hook calls `<base-url>/chat/completions`, so include the version segment, e.g. `https://your-host/v1`. **Leave empty** to fall back to the local `claude -p` (haiku) CLI.
- **LLM model** (`llm_model`, default **`openai/gpt-oss-120b`**) - the model identifier sent to that endpoint.
- **LLM API key** (`llm_api_key`) - the bearer key for the endpoint. Marked **sensitive**: it is stored outside `settings.json` and injected into the hook's environment only. The endpoint path activates only when the base URL, model, and key are all set; otherwise the hook uses the haiku fallback.

You can change any of these later from the `/plugin` menu.

## Statusline wiring (manual, one time)

The plugin **cannot** wire the grammar segment into your statusline for you. A statusline command runs outside the plugin sandbox and does not receive the plugin's environment variables, so it cannot locate the plugin or read its config on its own. Adding the segment is a manual, one-time edit to your own statusline script.

The plugin ships two pieces for this under `statusline/`:

- `render-grammar.sh` - defines `render_grammar`, which reads `$GRAMMAR_HOME/status/<session-id>` and prints the colored feedback segment. Source this from your existing statusline.
- `grammar-statusline.sh` - a complete standalone statusline that parses the session id from stdin and calls `render_grammar` for you. Use it if you do not already have a statusline.

### Add the segment to your own statusline

Claude Code passes each statusline command a JSON object on stdin that includes `session_id`. Read it, then source `render-grammar.sh` and call `render_grammar` with that id:

```bash
#!/bin/bash
input=$(cat)

# ... your existing statusline segments ...

# grammar segment:
SID=$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("session_id") or "default")')
. "$HOME/path/to/cc-grammar-coach/statusline/render-grammar.sh"
render_grammar "$SID"
```

`render_grammar` prints nothing when there is no feedback for the session, so it is safe to leave in place permanently.

Point the `.` (source) line at wherever the plugin's files live. The installed copy sits under the versioned plugin cache (`~/.claude/plugins/cache/cc-grammar-coach/cc-grammar-coach/<version>/statusline/render-grammar.sh`); because that path changes when the plugin updates, wiring against a fixed clone of this repo is more durable if you plan to keep the segment long-term. `render-grammar.sh` depends only on `$GRAMMAR_HOME/status/<session-id>`, not on the plugin environment, so either source works.

### Or use the standalone statusline

If you have no statusline yet, point `settings.json` straight at the bundled one:

```json
{
  "statusLine": {
    "type": "command",
    "command": "~/path/to/cc-grammar-coach/statusline/grammar-statusline.sh"
  }
}
```

## Configuration reference

| Field             | Type               | Default               | Meaning                                                                                                                      |
| ----------------- | ------------------ | --------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `native_language` | string             | _(none)_              | Drill uses it to explain English by contrast with your first language; empty means generic lessons. Not read by the checker. |
| `rephrase`        | boolean            | `true`                | Allow the checker to append one `✨` natural-rewrite line for clearly awkward messages.                                      |
| `show_feedback`   | boolean            | `true`                | Write checker feedback for the statusline. Off still logs mistakes for the drill.                                            |
| `llm_base_url`    | string             | _(none)_              | OpenAI-compatible endpoint base URL; empty falls back to `claude -p` haiku.                                                  |
| `llm_model`       | string             | `openai/gpt-oss-120b` | Model id sent to the endpoint.                                                                                               |
| `llm_api_key`     | string (sensitive) | _(none)_              | Bearer key for the endpoint; stored outside `settings.json`.                                                                 |

There is no master on/off toggle: `/plugin disable cc-grammar-coach` turns the whole thing off.

### State directory (`GRAMMAR_HOME`)

All state lives under one directory, `~/.claude/cc-grammar-coach`, overridable by setting `$GRAMMAR_HOME`. A fresh install creates it lazily; each component makes the subdirectories it writes to. It holds:

| Path                  | What it is                                                                                                             |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `status/<session-id>` | The current feedback line(s) for one session, read by the statusline. Files older than a day are tidied automatically. |
| `history.jsonl`       | Append-only mistake log, one JSON object per non-clean message. The drill's data source.                               |
| `drills/`             | Generated self-contained HTML lessons, one per drill.                                                                  |
| `curriculum.tsv`      | Learn-mode progress: one `<iso-week>\t<topic-id>` line per week, enforcing one new syllabus topic per week.            |

## Usage

### The checker

The checker runs on every message automatically once installed; there is nothing to invoke. It is **silent by default** and only reacts in the statusline (when `show_feedback` is on):

- **Clean message** - one short compliment on a `✔` line, e.g. `✔ Looks good`. This is also the liveness signal, so it never renders blank.
- **Grammar error** - one line per error, in the form `[<category>] <wrong> → <fix> (<rule>: <why>)`. Categories are the ones in `config/categories.txt`: `articles`, `agreement`, `tense`, `prepositions`, `plural`, `verb-form`, `questions`.
- **Awkward phrasing** - optionally, when `rephrase` is on, a single `✨` line rewriting the whole message more naturally. It never appears together with a `✔` line.

The three markers `→`, `✔`, and `✨` are the wire format the statusline colors and the drill parses; they are intentional and load-bearing.

The checker stays quiet on things that are not clear-cut grammar errors: correct grammar, word choice and naturalness, typos, code identifiers and paths and tool names, quoted or mentioned fragments, punctuation, casing, and anything fluent speakers would fix differently. It skips very short (under 15 chars) and very long (over 500 chars) messages, slash commands, and non-English text.

### The drill

Ask for a drill in plain language ("give me a grammar drill", "quiz me on my mistakes", "let's learn a new grammar topic"), or invoke the bundled skill explicitly as:

```
/cc-grammar-coach:grammar-drill
```

The skill has two modes. **Drill** (default) ranks your recent weak spots from `history.jsonl` and builds a lesson plus 4-6 quiz questions per topic, drawn from your own logged mistakes. **Learn** teaches the next new topic from the weekly syllabus (English only), at one topic per week. Either way it writes a self-contained HTML page under `drills/` that grades your answers in the browser offline, and gives you the path (opening it automatically where `open` or `xdg-open` is available).

## Model notes

The default model is **`openai/gpt-oss-120b`**, chosen by measurement: it was silent on every typo and name/mention case, had the best recall, and returned in ~1.4s at the median. See `eval/` for the harness and dataset behind that choice.

With **no API key configured**, the hook needs zero setup and falls back to `claude -p` with haiku. That path is slower and less strict about output format, but works offline of any custom endpoint. A **custom OpenAI-compatible endpoint** is opt-in: set the base URL, model, and key, and vet it with `eval/run.py` before trusting it.

## License

MIT. See `LICENSE`.
