# Grammar plugin - implementation design

Status: draft, under active review.
Companion to `requirements.md`; this document turns the settled requirements into a buildable plugin.
Where a decision was measured, `requirements.md` holds the evidence and this document holds the resulting structure.

## 1. Components

Three runtime components plus a maintainer tool:

- **Checker** - a `UserPromptSubmit` hook (bash) that calls the model out of band, captures mistakes to a log, and writes feedback for the statusline.
- **Statusline render** - a shell wrapper plus a sourceable function that renders the checker's feedback. Not injectable by the plugin silently (see section 6); wired by the `/cc-grammar-coach:install-statusline` command.
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
  commands/
    install-statusline.md               # one-time statusline wiring, agent-performed
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
| `llm_base_url`    | string                              | env            | not needed                              |
| `llm_model`       | string, default openai/gpt-oss-120b | env            | not needed                              |
| `llm_api_key`     | string, sensitive                   | env (verified) | not needed                              |

- The **hook** reads `CLAUDE_PLUGIN_OPTION_<KEY>` environment variables (documented for hook processes).
- The **drill** reads `${user_config.KEY}` inline substitution in `SKILL.md`; Claude sees the values in context and writes the native-language contrast itself, so no value is passed to a subprocess. `${CLAUDE_PLUGIN_ROOT}` substitutes the same way to locate bundled scripts and assets.
- The **statusline** reads no config; it only reads the fixed `status/<session-id>` path.
- **Verified empirically** (throwaway probe plugin, 2026-07-22): `sensitive` userConfig values _are_ injected into the hook env as `CLAUDE_PLUGIN_OPTION_<KEY>`, even though they are stored outside `settings.json` (which holds non-sensitive options only). Credentials therefore live in userConfig like everything else; no private-file fallback is needed. `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PLUGIN_DATA` are also set for hook processes.

### Toggles

Only one: `rephrase` - the naturalness-channel off-switch (section 3.3 of requirements).

There is no `show_feedback` display toggle. It shipped in 0.1.0 and was removed: a config flag titled "Show statusline feedback" promised something the plugin cannot deliver alone (display also needs the statusline wiring), so enabling it and seeing nothing was the plugin's first real-use failure. Display is now controlled by exactly one thing - whether the statusline is wired (the install-statusline command) - and the hook always writes status files; the capture-vs-display split survives as "wired or not" instead of a flag. Persona B (capture only, no display) simply does not run the command.

There is no master enable toggle either: `/plugin disable cc-grammar-coach` removes the hook, which is the same thing.

## 5. Checker hook flow (rewritten, ~90 lines vs 332)

1. Resolve `$GRAMMAR_HOME`; refresh the stable statusline-script copies (section 6); read settings from `CLAUDE_PLUGIN_OPTION_*` env vars.
2. Credentials gate: exit unless the base URL and API key are both set. There is no zero-config model fallback - the earlier `claude -p` haiku path was removed because its ~60% format compliance (requirements section 6) silently dropped fixes and lost history; a checker that visibly requires configuration beats one that silently half-works. This also killed the `GRAMMAR_HOOK_ACTIVE` recursion guard, whose only purpose was to stop the `claude -p` call from re-firing this hook.
3. Parse stdin JSON with python3 (prompt, session_id). Clear `status/<sid>`; tidy status files older than a day.
4. Gates (portable): empty, slash-command, under 15 or over 500 chars, leading `<` or system-injected tags, and the language ratio. The language gate moves to python3 counting Latin vs Cyrillic, which removes `grep -P`.
5. Background block, empty stdout:
   a. Build the prompt: `${CLAUDE_PLUGIN_ROOT}/prompts/checker.txt`, with the category list, native and target language, and the rephrase step included only when `rephrase=on`.
   b. Call the model: curl plus python3 for JSON against the configured endpoint.
   c. Light sanitation only: strip `**` and backticks, drop blank lines. No filters.
   d. Capture: if the result carries any fix or rephrase, append one JSONL line to `history.jsonl`.
   e. Display: always write `status/<sid>`, with the praise-liveness fallback on the clean case. Whether anything shows is decided solely by the statusline wiring (section 6).
6. Timestamps also move to python3, removing `date -d`. The only remaining platform branch is the drill's page opener (`open` vs `xdg-open`), detected at use.

Categories: `config/categories.txt` ships the English list in the plugin root and the hook reads only that. The grammar-home override is dropped with the target knob (v2 concern). Membership stays deferred (requirements section 3.5).

## 6. Statusline

- `statusline/render-grammar.sh` defines `render_grammar()`: it reads `$GRAMMAR_HOME/status/$SID` and prints the feedback, colored by marker (`✔`/`✨` green, `[category]` fix split into parts and colored), soft-wrapped to terminal width. This is the current statusline's grammar block, lifted out and parameterized by `$GRAMMAR_HOME`.
- `statusline/grammar-statusline.sh` is a minimal standalone statusline that sources the function and calls it, for users who have none.
- A plugin cannot set `statusLine` silently, so wiring is a one-time explicit step - but performed by the agent, not by hand: `/cc-grammar-coach:install-statusline` (last line of the README install block) points `statusLine.command` at the standalone script when none is configured, or appends the `render_grammar` snippet to an existing statusline script (backup, idempotent, verified end to end with a test status file). Manual wiring stays documented in the README as the advanced path.
- The wiring references stable copies of both scripts in `$GRAMMAR_HOME`, not the versioned plugin cache path (which changes every release); the hook refreshes those copies on every prompt via `cmp`, so plugin updates propagate to the statusline without re-wiring.
- The statusline needs no config and no plugin env; it only needs the fixed status path.

## 7. Drill

- `SKILL.md` reads `${user_config.native_language}` inline, and `$GRAMMAR_HOME/history.jsonl` as JSONL (trivial parse, no legacy-format handling, no grep over prose). It ranks recent categories, writes the drill JSON, and runs `${CLAUDE_PLUGIN_ROOT}/skills/grammar-drill/scripts/build_drill.py`.
- `build_drill.py` is reused almost unchanged: validate the drill JSON against a schema, fill the template, inline the CSS, write to `$GRAMMAR_HOME/drills/`, print the path. The page opener is detected (`open`/`xdg-open`).
- Dropped from the current skill: the human-log grep, the pre-2026 legacy-format handling, and any use of a stats file for ranking.
- Learn mode tracks the weekly topic in `$GRAMMAR_HOME/curriculum.tsv`; English-only (requirements section 5.3).

## 8. Packaging

- `plugin.json`: `name` cc-grammar-coach, plus version, description, author, homepage, repository, license, keywords, the `userConfig` block (section 4), and the hooks pointer.
- `hooks/hooks.json`: one `UserPromptSubmit` entry running `${CLAUDE_PLUGIN_ROOT}/hooks/grammar-check.sh` with a short timeout. The hook backgrounds the model call and returns immediately with empty stdout, so its synchronous part is fast and a ~10s timeout is ample.
- `.claude-plugin/marketplace.json`: lists this one plugin from this repo, so `/plugin marketplace add <owner>/cc-grammar-coach` then `/plugin install` works, followed by the interactive userConfig prompts and the `/cc-grammar-coach:install-statusline` wiring step.

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
