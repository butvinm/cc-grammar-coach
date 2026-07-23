# Grammar plugin - implementation design

Status: draft, under active review.
Companion to `requirements.md`; this document turns the settled requirements into a buildable plugin.
Where a decision was measured, `requirements.md` holds the evidence and this document holds the resulting structure.

## 1. Components

Three runtime components plus a maintainer tool:

- **Checker** - a `UserPromptSubmit` hook (bash) that calls the model out of band, captures mistakes to a log, and optionally writes feedback for the statusline.
- **Statusline render** - a shell wrapper plus a sourceable function that renders the checker's feedback. Not installable by the plugin (see section 5); the user wires it in.
- **Drill** - a skill that turns the log into a lesson-plus-quiz web page.
- **Eval** - a maintainer harness plus dataset; in the repo, not part of the installed runtime.

## 2. File tree

```
cc-grammar-coach/                    # repo root, plugin name = cc-grammar-coach
  .claude-plugin/
    plugin.json                         # manifest + userConfig
    marketplace.json                    # for /plugin marketplace add
  hooks/
    hooks.json                          # declares the UserPromptSubmit hook + timeout
    grammar-check.sh                    # the checker (rewritten)
  skills/grammar-drill/
    SKILL.md                            # uses ${user_config.*} and ${CLAUDE_PLUGIN_ROOT}
    scripts/build_drill.py
    assets/{drill-template.html,duo.css}
    references/syllabus.md
  statusline/
    grammar-statusline.sh               # standalone wrapper (user has no statusline)
    render-grammar.sh                   # sourceable render_grammar() (user has one)
  prompts/checker.txt                   # the prose prompt (v1, measured best)
  config/categories.txt                 # default English category taxonomy
  eval/{run.py,cases.jsonl,README.md}
  docs/{requirements.md,design.md}
  README.md
```

## 3. Two roots: static vs mutable

- **Plugin root** (`${CLAUDE_PLUGIN_ROOT}`, read-only): all code and static assets - hook, prompt, categories, skill, statusline scripts, eval.
- **Grammar home** (writable state): `~/.claude/cc-grammar-coach/`, overridable via `$GRAMMAR_HOME`.
  Holds `status/<session-id>` (ephemeral feedback), `history.jsonl` (the drill's source), `curriculum.tsv`, and `drills/`.

Grammar home is a **fixed path**, not `${CLAUDE_PLUGIN_DATA}`, because the statusline is not a plugin component and cannot see plugin env vars.
All three components resolve the same fixed path with no plugin-env dependency; uninstall is removing one directory.

## 4. Configuration

All user configuration lives in the plugin's `userConfig` (declared in `plugin.json`); there is no hand-rolled config file.
Each component reads it by its own idiomatic channel:

| setting           | type                                | read by hook   | read by drill                           |
| ----------------- | ----------------------------------- | -------------- | --------------------------------------- |
| `native_language` | string, no default                  | env            | inline `${user_config.native_language}` |
| `rephrase`        | boolean, default true               | env            | not needed                              |
| `show_feedback`   | boolean, default true               | env            | not needed                              |
| `llm_base_url`    | string                              | env            | not needed                              |
| `llm_model`       | string, default openai/gpt-oss-120b | env            | not needed                              |
| `llm_api_key`     | string, sensitive                   | env (verified) | not needed                              |

- The **hook** reads `CLAUDE_PLUGIN_OPTION_<KEY>` environment variables (documented for hook processes).
- The **drill** reads `${user_config.KEY}` inline substitution in `SKILL.md`; Claude sees the values in context and writes the native-language contrast itself, so no value is passed to a subprocess. `${CLAUDE_PLUGIN_ROOT}` substitutes the same way to locate bundled scripts and assets.
- The **statusline** reads no config; it only reads the fixed `status/<session-id>` path.
- **Verified empirically** (throwaway probe plugin, 2026-07-22): `sensitive` userConfig values _are_ injected into the hook env as `CLAUDE_PLUGIN_OPTION_<KEY>`, even though they are stored outside `settings.json` (which holds non-sensitive options only). Credentials therefore live in userConfig like everything else; no private-file fallback is needed. `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PLUGIN_DATA` are also set for hook processes.

### Toggles

Only two, both semantically distinct:

- `show_feedback` - the capture-vs-display split (Persona B runs capture with display off).
- `rephrase` - the naturalness-channel off-switch (section 3.3 of requirements).

There is no master enable toggle: `/plugin disable cc-grammar-coach` removes the hook, which is the same thing.

## 5. Checker hook flow (rewritten, ~90 lines vs 332)

1. Recursion guard: `GRAMMAR_HOOK_ACTIVE` set -> exit (the `claude -p` fallback would otherwise re-fire this hook).
2. Resolve `$GRAMMAR_HOME`; read settings from `CLAUDE_PLUGIN_OPTION_*` env vars.
3. Parse stdin JSON with python3 (prompt, session_id). Clear `status/<sid>`; tidy status files older than a day.
4. Gates (portable): empty, slash-command, under 15 or over 500 chars, leading `<` or system-injected tags, and the language ratio. The language gate moves to python3 counting Latin vs Cyrillic, which removes `grep -P`.
5. Background block, empty stdout:
   a. Build the prompt: `${CLAUDE_PLUGIN_ROOT}/prompts/checker.txt`, with the category list, native and target language, and the rephrase step included only when `rephrase=on`.
   b. Call the model: API path (curl plus python3 for JSON) when credentials are present, else `claude -p` haiku under the recursion guard.
   c. Light sanitation only: strip `**` and backticks, drop blank lines. No filters.
   d. Capture: if the result carries any fix or rephrase, append one JSONL line to `history.jsonl`.
   e. Display: only when `show_feedback=on`, write `status/<sid>`, with the praise-liveness fallback on the clean case.
6. Timestamps also move to python3, removing `date -d`. The only remaining platform branch is the drill's page opener (`open` vs `xdg-open`), detected at use.

Categories: `config/categories.txt` ships the English list in the plugin root and the hook reads only that. The grammar-home override is dropped with the target knob (v2 concern). Membership stays deferred (requirements section 3.5).

## 6. Statusline

- `statusline/render-grammar.sh` defines `render_grammar()`: it reads `$GRAMMAR_HOME/status/$SID` and prints the feedback, colored by marker (`✔`/`✨` green, `[category]` fix split into parts and colored), soft-wrapped to terminal width. This is the current statusline's grammar block, lifted out and parameterized by `$GRAMMAR_HOME`.
- `statusline/grammar-statusline.sh` is a minimal standalone statusline that sources the function and calls it, for users who have none.
- Install is the one unavoidable manual step (a plugin cannot set `statusLine`): either point `statusLine.command` at `grammar-statusline.sh`, or source `render-grammar.sh` in an existing statusline and call `render_grammar`. Documented in the README.
- The statusline needs no config and no plugin env; it only needs the fixed status path.

## 7. Drill

- `SKILL.md` reads `${user_config.native_language}` inline, and `$GRAMMAR_HOME/history.jsonl` as JSONL (trivial parse, no legacy-format handling, no grep over prose). It ranks recent categories, writes the drill JSON, and runs `${CLAUDE_PLUGIN_ROOT}/skills/grammar-drill/scripts/build_drill.py`.
- `build_drill.py` is reused almost unchanged: validate the drill JSON against a schema, fill the template, inline the CSS, write to `$GRAMMAR_HOME/drills/`, print the path. The page opener is detected (`open`/`xdg-open`).
- Dropped from the current skill: the human-log grep, the pre-2026 legacy-format handling, and any use of a stats file for ranking.
- Learn mode tracks the weekly topic in `$GRAMMAR_HOME/curriculum.tsv`; English-only (requirements section 5.3).

## 8. Packaging

- `plugin.json`: `name` cc-grammar-coach, plus version, description, author, homepage, repository, license, keywords, the `userConfig` block (section 4), and the hooks pointer.
- `hooks/hooks.json`: one `UserPromptSubmit` entry running `${CLAUDE_PLUGIN_ROOT}/hooks/grammar-check.sh` with a short timeout. The hook backgrounds the model call and returns immediately with empty stdout, so its synchronous part is fast and a ~10s timeout is ample.
- `.claude-plugin/marketplace.json`: lists this one plugin from this repo, so `/plugin marketplace add <owner>/cc-grammar-coach` then `/plugin install` works, followed by the interactive userConfig prompts and the one manual statusline step.

## 9. Reuse vs rewrite, and migration

Reuse/rewrite map:

- `grammar-check.sh`: **rewrite** (minimal, no filters, portable, config-driven). Salvage the recursion guard, the gates, the background pattern, and the status write.
- statusline grammar block: **extract** into `render-grammar.sh`, parameterized by `$GRAMMAR_HOME`.
- `grammar-drill` skill and `build_drill.py`: **reuse and adapt** (JSONL log, inline config, plugin paths, portable opener; drop legacy parsing).
- `eval/run.py`: **reuse and adapt** to the new hook and dataset, and drop its jq requirement.
- the prompt: **new** (prose v1 from the probe).
- **dropped entirely**: the 120 lines of python filters, `grammar-trace.jsonl`, `grammar-stats.tsv`, `grammar-ignore.txt`, the human `grammar-feedback.log` format, and `grammar-llm.env` (replaced by userConfig).

Migration (maintainer's machine only; new users start empty):

- State moves from flat `~/.claude/grammar-*` files to `~/.claude/cc-grammar-coach/`.
- The old `grammar-feedback.log` is **archived outside the state dir, never imported.** Its fix lines are unreliable (produced by the rejected prompt and model, which mislabels typos and invents wrong corrections), so it must not feed the drill: `history.jsonl` starts empty and the new checker refills it. But its `YOU:` lines are the maintainer's genuine traffic and the only existing source for the eval's anonymized real cases, where labels are assigned from scratch and the old bad labels never matter. Archive, do not delete.
- The old flat files (`grammar-stats.tsv`, `grammar-ignore.txt`, `grammar-trace.jsonl`, `grammar-llm.env`) are removed; their roles are gone (no filters, no stats ranking) or moved (credentials to userConfig).
- `curriculum.tsv` may be copied over if its topic history is still wanted; it is low-risk since it holds only week-to-topic mappings, not model output.
