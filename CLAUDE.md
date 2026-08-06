# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Claude Code plugin (`.claude-plugin/plugin.json`), installed from this repo as a marketplace. Nothing is compiled, bundled, or packaged: the repo tree _is_ the artifact, and Claude Code copies it into a versioned plugin cache on install. Runtime is bash + python3 stdlib + curl, no dependencies to install and no virtualenv.

Three pieces share one state directory, `$GRAMMAR_HOME` (default `~/.claude/cc-grammar-coach`):

- `hooks/grammar-check.sh` - a `UserPromptSubmit` hook that sends each English message to an OpenAI-compatible endpoint, appends mistakes to `history.jsonl`, and writes one status file per session.
- `statusline/render-grammar.sh` - reads that status file and prints the coloured segment. Sourced by the user's statusline, not executed by the plugin.
- `skills/drill`, `skills/learn` and `skills/progress` - read `history.jsonl` and teach from it inside the session. Drill and learn author a quiz as JSON and then run it as a conversation; progress reports trends.

`docs/statusline.md` holds the state-directory table; `docs/mistake-categories.md` the taxonomy; `CONTRIBUTING.md` the wire format.

## Commands

There is no build, no linter, and no unit-test suite. `eval/run.py` is the only automated check, and it is a maintainer tool that needs live model credentials - end users never run it.

```
python3 eval/run.py               # one sample per case (fast, noisy)
python3 eval/run.py --repeats 3   # three samples per case, gate on the mean
python3 eval/run.py --selftest    # exercises the gate logic offline; exits 1 by design
```

`run.py` reads `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` from the environment and maps them onto the `CLAUDE_PLUGIN_OPTION_*` names the hook actually reads. Without credentials it exits early rather than measure a hook that checks nothing. Gates and their env overrides are documented in `eval/README.md`; a single run is one noisy sample of a nondeterministic model, so reproduce with `--repeats` before trusting the exit code.

Run the hook once, in isolation, without touching real state - `GRAMMAR_HOOK_SYNC=1` awaits the backgrounded model call that the hook otherwise detaches:

```
printf '{"session_id":"t1","prompt":"we was agree about it"}' | GRAMMAR_HOME=/tmp/gh-test GRAMMAR_HOOK_SYNC=1 CLAUDE_PLUGIN_ROOT=$PWD bash hooks/grammar-check.sh
```

Render the statusline segment offline against a hand-written status file, with no session and no model:

```
GRAMMAR_HOME=/tmp/gh-test COLUMNS=100 bash -c '. statusline/render-grammar.sh; render_grammar <session-id>'
```

Validate and store an authored quiz session (schema and question rules in `skills/drill/references/authoring.md`, the session loop in `skills/drill/references/running-a-quiz.md`):

```
python3 skills/drill/scripts/prepare_drill.py <data.json> [out.json]
```

Record a finished quiz, and print the progress report:

```
python3 skills/drill/scripts/record_result.py <session.json> <topic-id>=<correct>/<total> ...
python3 skills/progress/scripts/summarize_progress.py
```

Syntax-check the shell scripts - the only static check available here:

```
bash -n hooks/grammar-check.sh statusline/render-grammar.sh statusline/grammar-statusline.sh
```

## Architecture

### The wire format is the contract

The checker emits plain text lines; the renderer colours them and the drill parses them. Three Unicode markers are load-bearing and must appear byte-identically in `prompts/checker.txt`, `hooks/grammar-check.sh`, `statusline/render-grammar.sh`, and `eval/run.py`: the arrow separating wrong from fix, the check mark on the praise line, the sparkle on the rephrase line. Substituting ASCII `->` silently empties the mistake log. Full spec in `CONTRIBUTING.md`.

### The hook must stay invisible

`UserPromptSubmit` stdout is injected into the conversation as context, so the hook writes nothing to stdout, ever. The model call runs in a backgrounded subshell so the turn is never delayed; feedback lands in the statusline a few seconds later. Gates before the call (a fresh `skip-next-prompt` token, empty, slash-command, under 15 or over 500 chars, leading `<`, injected system tags, non-Latin ratio) all `exit 0` silently.

### The checker prompt is assembled per invocation

`prompts/checker.txt` is a template, not a prompt. The hook fills `{{CATEGORIES}}`, `{{CATEGORY_DEFINITIONS}}`, and `{{DISABLED_CATEGORIES}}` from the category catalog `config/categories.txt` filtered by the active selection, and strips the `{{REPHRASE_START}}`/`{{REPHRASE_END}}` block when the `rephrase` option is off. Selection resolves in order: `$GRAMMAR_HOME/enabled-categories.txt` (user), then `config/enabled-categories.txt` (shipped default), then the whole catalog. Disabling a category does not merely omit it - it becomes an explicit do-not-flag line in the prompt. Adding a category means a catalog line plus recall cases in `eval/cases.jsonl`; see `docs/mistake-categories.md`.

### Model output is not trusted

The hook re-parses the model's lines with an optional-brackets regex, validates the category against the catalog, and re-emits matched lines in canonical bracketed form. It then drops a rephrase that merely repeats the corrections: fixes are applied to the message on word boundaries and the word-sequence similarity compared against `0.9`. That threshold and its normalization exist twice, in `hooks/grammar-check.sh` and as `DUP_RATIO` in `eval/run.py` - changing one without the other breaks the gate silently.

### Statusline propagation, and why editing `statusline/` looks like a no-op

A statusline command runs outside the plugin sandbox and `statusLine` is a single user setting, so the plugin cannot inject its segment. The hook therefore copies both statusline scripts into `$GRAMMAR_HOME` on every prompt (when they differ), and the wiring installed by `/cc-grammar-coach:configure install-statusline` points at those stable copies rather than the versioned cache path, so plugin updates propagate without re-wiring.

Consequence when developing: editing `statusline/*.sh` in a checkout changes nothing live. The hook copies from the _installed plugin root_ (see `installPath` in `~/.claude/plugins/installed_plugins.json`), and will overwrite any hand-edited stable copy on the next prompt. To test a change against a live session, update the file in the installed plugin root too; otherwise use the offline render command above.

### The statusline path is fork-free on purpose

The segment re-renders roughly every two seconds per open session while the status file changes only once per prompt, so `statusline/render-grammar.sh` and `statusline/grammar-statusline.sh` use bash builtins and parameter expansion only - no pipeline, no subshell, no interpreter, no `tput`, and `python3` is deliberately not a dependency on this path (PR #32). Wrapping is a hand-rolled word packer for that reason. Do not reintroduce a subprocess per line here.

Claude Code exports `COLUMNS` to the statusline process and keeps it in step with the pane on resize, so the `120` fallback in `render_grammar` is unreachable under Claude Code and exists only for other callers.

### Skills read state, the hook writes it

`skills/drill` ranks `fixes[].category` over a recency window (7 days, widened to the last 200 lines when thin) rather than lifetime totals, so topics the user stopped getting flagged on stop being drilled. `skills/learn` walks `skills/learn/references/syllabus.md` and enforces one new topic per ISO week through `$GRAMMAR_HOME/curriculum.tsv`. Both author JSON, hand it to `prepare_drill.py` for validation and storage under `$GRAMMAR_HOME/drills/`, and then run the quiz themselves.

### The quiz runs in the session, and that is what buys the grading

There is no page and no server (issue #31, after the dashboard of #26 was built and abandoned in PR #30). The old static page graded a rewrite by string-comparing it against a hand-authored accept-list under a case/whitespace/end-punctuation normalization, so a correct sentence failed over a comma and the authoring rules had to demand every variant be enumerated. Grading in the session is the entire reason the format changed: the model checks the tested construction, so `answers[]` is a reference answer rather than an accept-list, and "wait, why?" gets an answer mid-quiz.

Two consequences the code carries. A written quiz answer reaches the checker as an ordinary prompt and would be logged as the user's own writing, then re-ranked into the next drill, so the skill drops `$GRAMMAR_HOME/skip-next-prompt` in the same message it asks a `rewrite` question and `hooks/grammar-check.sh` consumes it on the next prompt. It is a one-shot token and not a "drill in progress" lease because a drill is not one sitting - a real one ran across thirteen hours interleaved with ordinary work, and a lease covering that would have silenced a day of genuine feedback. `choice` questions need no token at all: an `AskUserQuestion` answer never reaches the hook (issue #11). `record_result.py` sums the per-topic scores instead of taking a total, so a quiz stopped partway records an honest partial run.

`skills/progress` reads `history.jsonl` and `results.jsonl` and prints tables through `summarize_progress.py`; the skill interprets them and is told not to invent a target, streak or grade.

### The eval never pools classes

Silence classes (typo, name/mention, natural) are scored as false-positive rates against a ceiling; recall against a floor, twice (flagged-at-all, and flagged under the right slug); rephrase duplication has zero tolerance. A false positive on a typo and a missed error are different failures with different budgets, so a single aggregate number is meaningless. Each case runs the hook in a fresh temp `GRAMMAR_HOME`, so a full run leaves the user's real `history.jsonl` byte-identical.

## Conventions

- No `jq` anywhere - JSON is parsed with `python3` stdlib in the hook and with bash pattern matching on the statusline path.
- Portable to Linux and macOS: no `grep -P`, no `date -d`, no unconditional `xdg-open`.
- Comments explain _why_, at the density of the surrounding file; the shell scripts carry long rationale comments and new code there is expected to match.
- Prose lines are never wrapped at a column - break at a sentence or clause boundary or not at all.
- `version` in `.claude-plugin/plugin.json` has only ever been bumped on commits that changed the user-facing surface (commands, skills, required configuration); most merged PRs leave it alone.
