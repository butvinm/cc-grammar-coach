# Build the cc-grammar-practice plugin

## Overview

Package a two-part English-grammar tool as a public Claude Code plugin:

- a **checker** (`UserPromptSubmit` hook) that reviews each English message out of band, logs mistakes, and optionally shows feedback in the statusline;
- a **drill** (skill) that turns the logged mistakes into a lesson-plus-quiz web page.

This is a ground-up rebuild, not a port. The existing `~/.claude/grammar-*` code is reference for which problems are real; its 120 lines of false-positive filters, its two overlapping logs, and its 2100-char prompt are dropped. Every contested decision below was settled by measurement (see the inlined model table).

v1 teaches **English only**. A configurable target language is deferred to v2 (see R1).

This plan is self-contained: the requirements and design needed to execute it are inlined in "Design reference" so no other file is required. Full versions live in `docs/requirements.md` and `docs/design.md`.

## Context (from discovery)

- Repo root: `/home/butvinm/Dev/cc-grammar-practice` (currently only `docs/`). Not yet a git repo.
- Reusable artifacts in the session scratchpad `/tmp/claude-1000/-home-butvinm-Dev-cc-grammar-practice/43228289-01d3-4ca0-9155-6d9bd7694dd8/scratchpad/`:
  - `minimal-prompt.txt` - the validated v1 prose checker prompt (measured best). **Source of truth for prompt wording.**
  - `probe-hook-api.sh` - reference for the API call, gates, and status write. **Note: it is fully synchronous and is NOT a reference for backgrounding.**
  - `run.py`, `cases.jsonl` - the eval harness and the current (biased, to-be-replaced) case set.
- **The background/detach idiom's only working reference is the old hook**, `/home/butvinm/.claude/hooks/grammar-check.sh:325` (`) > /dev/null 2>&1 &`), plus its `GRAMMAR_HOOK_SYNC` wait at `:330`. Salvage both.
- The statusline grammar block to extract: `/home/butvinm/.claude/statusline.sh:63-145`.

## Development approach

- Shell + prompt + skill project: there are no unit tests. **Per-task verification is a smoke test or an eval run**, listed as explicit checklist items and required before the next task.
- The eval harness (`eval/run.py`) is the checker's test suite; it must pass against the real shipped hook in Task 8.
- Small, focused commits per task. Never `git add .` - stage named files only. Branch `master`.
- Keep this plan in sync: mark `[x]` on completion, add discovered tasks with a plus prefix, blockers with a warning prefix.
- All written files use plain ASCII punctuation **except the three protocol markers** (R3), which must appear verbatim.

---

## Design reference (inlined - the executor needs only this section)

### R1. Scope

Target language is **English, fixed in v1**. Native language is configurable with **no default** (unset = generic lessons; no nationality ships as a default). Correctness is judged by a model against a narrow spec, not a rule engine. Naturalness is never scored.

_Deferred to v2:_ a configurable target language. The FLAG contract is language-neutral so the checker would generalize cheaply, but the prompt, categories, syllabus, and eval are all English. v2 must do these together: parameterize the prompt, supply per-target categories, degrade Learn mode explicitly, and state that non-English is unvalidated.

### R2. Personas -> the one hard requirement

Capture (writing the mistake log) and display (writing the statusline feedback) are **independently toggleable**. Persona B runs capture with display off; the drill still works.

### R3. Checker outputs and the wire format

**Protocol markers are exactly three, and are Unicode, not ASCII:** `→` (U+2192), `✔` (U+2714), `✨` (U+2728). The prompt tells the model to emit them; the statusline matches on them; the eval parses them. They must be byte-identical across prompt, parsers, and fixtures. Substituting `->` silently empties `fixes[]` and starves the drill - this is a known trap, not a style choice.

**FLAG** (grammar errors, the only scored output). Flag a fragment only when all hold: (1) one single correct fix, not a range; (2) virtually every fluent speaker makes the same fix; (3) wrong and fixed are both correctly-spelled real words (excludes typos); (4) it is the user's own running prose, not a quote/mention or a code identifier/path/tool name. One line per error:

```
[<category>] <wrong> → <fix> (<rule>: <why, short>)
```

**Silence** (default) on: correct grammar; naturalness/word-choice/clarity; typos of any kind; code identifiers, tool/product names, paths, anything with hyphen/underscore/dot/slash/camelCase/backticks; quoted or mentioned fragments; punctuation/casing/contractions/slang; anything fluent speakers would fix differently.

**REPHRASE** (`✨`, unscored, optional). One line rewriting the whole message more naturally; restrained (only when clearly awkward); never a fix-reapplication; preserves identifiers and each sentence's speech act; never emitted with the `✔` line; the whole channel is omitted from the prompt when `rephrase=false`.

**PRAISE** (`✔`, unscored). On a clean, natural message, one short compliment. It is the liveness signal, so it must never render blank: when the model returns no usable praise (empty, multi-line, or over 50 chars), write the literal fallback `✔ Looks good`.

### R4. Non-functionals

Never write to stdout. Never block the turn (model call backgrounded; the hook returns in well under 1s). Gates: skip empty, slash-command, under 15 or over 500 chars, leading `<` or system-injected tags, and non-English (Latin vs Cyrillic ratio). Portable Linux + macOS (no `grep -P`, `date -d`, `xdg-open`). Deps: `bash`, `python3`, `curl`; no `jq`; `hunspell` and `claude` CLI optional. All state under one namespaced dir.

### R5. Drill and the checker->drill data contract

One append-only JSONL, `history.jsonl`, one line per non-clean message. `ts` is ISO-8601 with offset. Each line is written as a **single atomic `>>` append** (safe under PIPE_BUF), never read-modify-write, because backgrounded jobs from concurrent sessions share the file:

```json
{
  "ts": "2026-07-22T00:54:06+03:00",
  "message": "<raw message>",
  "fixes": [
    {
      "category": "articles",
      "wrong": "create skill",
      "fix": "create a skill",
      "rule": "..."
    }
  ],
  "rephrase": "<or absent>"
}
```

Drill uses it as a cheap index (`fixes[].category` ranks recent weak spots; a line's presence pre-filters mistaken messages) and re-reads `message` as source material for lessons. Two modes: Drill (top 2-3 recent categories, lesson + 4-6 fresh quiz questions from the user's own mistakes) and Learn (next weekly syllabus topic, English-only). Page is self-contained offline HTML, graded in-browser, built by a validating script.

### R6. Model and filter strategy (measured)

| model                 | typo silent | name/mention | recall | bracket format | latency p50/max |
| --------------------- | ----------- | ------------ | ------ | -------------- | --------------- |
| claude -p haiku       | 11/11       | 3/3, 1/1     | 11/13  | ~60%           | 9.8s / 72s      |
| gemini-3.1-flash-lite | 5/11        | 3/3, 1/1     | 10/14  | high           | 1.5s / 13.5s    |
| gpt-5-nano            | 11/11       | 2/3, 0/1     | 10/14  | ~72%           | 9.2s / 45s      |
| gpt-oss-120b          | 11/11       | 3/3, 1/1     | 13/14  | ~96%           | 1.4s / 3.0s     |

No false-positive filters ship. Default model `openai/gpt-oss-120b`; zero-config fallback `claude -p` haiku; custom endpoint opt-in, vetted by the eval.

### D1. File tree

```
cc-grammar-practice/
  .claude-plugin/{plugin.json, marketplace.json}
  hooks/{hooks.json, grammar-check.sh}
  skills/grammar-drill/{SKILL.md, scripts/build_drill.py, assets/{drill-template.html,duo.css}, references/syllabus.md}
  statusline/{grammar-statusline.sh, render-grammar.sh}
  prompts/checker.txt
  config/categories.txt
  eval/{run.py, cases.jsonl, README.md}
  docs/{requirements.md, design.md, plans/}
  README.md
  LICENSE
```

### D2. Two roots

- Plugin root: `${CLAUDE_PLUGIN_ROOT}` when set; **otherwise derived from the script's own location** so the hook is runnable outside Claude Code for testing.
- Grammar home: `~/.claude/cc-grammar-practice/`, overridable by `$GRAMMAR_HOME`. Holds `status/<session-id>`, `history.jsonl`, `curriculum.tsv`, `drills/`. **Every component creates the directories it writes to (`mkdir -p`)**; a fresh install has none of them. Fixed path because the non-plugin statusline cannot read plugin env vars. Status files older than one day are tidied.

### D3. Config (all via userConfig in plugin.json)

Fields, each needing `type`/`title`/`description` and a `default` where applicable: `native_language` (string, no default), `rephrase` (boolean, default true), `show_feedback` (boolean, default true), `llm_base_url` (string), `llm_model` (string, default `openai/gpt-oss-120b`), `llm_api_key` (string, sensitive). The hook reads `CLAUDE_PLUGIN_OPTION_<KEY>`; the drill reads `${user_config.native_language}` inline in SKILL.md; the statusline reads no config. No master enable toggle (`/plugin disable` covers it). No `target_language` in v1 (R1).

### D4. Hook flow (~90 lines)

1. Recursion guard `GRAMMAR_HOOK_ACTIVE` set -> exit.
2. Resolve plugin root (env or script location) and `$GRAMMAR_HOME`; `mkdir -p` the state dirs; read `CLAUDE_PLUGIN_OPTION_*`.
3. python3 parse stdin JSON (prompt, session_id). Clear `status/<sid>`; tidy status files older than a day.
4. Gates (R4); language ratio via python3.
5. Background subshell, empty stdout: render the prompt (D5); call the API (curl + python3) or `claude -p` haiku fallback; light sanitation (strip `**`/backticks, blank lines), no filters; capture (single atomic append to `history.jsonl` if any fix or rephrase); display (write `status/<sid>` only if `show_feedback=true`, with the `✔ Looks good` fallback).
6. `GRAMMAR_HOOK_SYNC=1` makes the hook `wait` for its background subshell instead of returning immediately. Tests and the eval set it; normal operation never does.

### D5. Prompt rendering contract

`prompts/checker.txt` is the measured prompt with exactly two substitution points:

- `{{CATEGORIES}}` - replaced by the comma-joined contents of `config/categories.txt`.
- A rephrase block delimited by the literal lines `{{REPHRASE_START}}` and `{{REPHRASE_END}}` - kept (delimiters stripped) when `rephrase=true`, and the whole block removed when `rephrase=false`.

No language placeholder in v1 (the prompt never named a specific native language; that is the drill's job). **Rendering with defaults must produce a file byte-identical to the measured `minimal-prompt.txt`**, otherwise the R6 measurements no longer describe the shipped artifact.

---

## Implementation Steps

### Task 1: Scaffold, manifest, hook declaration, marketplace, sensitive-config spike

**Files:**

- Create: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `hooks/hooks.json`, `.gitignore`, `LICENSE`

- [ ] `git init` on `master`; `.gitignore` (local test homes, `*.bak-*`, `drills/`); add `LICENSE` matching the manifest's declared license.
- [ ] `plugin.json`: name `cc-grammar-practice`, version, description, author, repository, license, keywords, and the full `userConfig` block (D3) with `type`/`title`/`description`/`default` on every field.
- [ ] `hooks/hooks.json`: one `UserPromptSubmit` entry running `"${CLAUDE_PLUGIN_ROOT}"/hooks/grammar-check.sh` (quoted - the root may contain spaces), timeout 10s. Rely on convention discovery; do **not** also add a `hooks` field to `plugin.json`.
- [ ] `marketplace.json`: list this one plugin from this repo.
- [ ] **Spike:** declare `llm_api_key` as `sensitive`, install the plugin locally with a stub hook that echoes `CLAUDE_PLUGIN_OPTION_LLM_API_KEY`, and confirm the value arrives. If it does not, record the decision to keep credentials (only) in a private file and adjust D3 before Task 3.
- [ ] Verify: `claude plugin validate` passes (catches bad event names, hook shape, and userConfig schema - `json.load` cannot).

### Task 2: Checker prompt and category list

**Files:**

- Create: `prompts/checker.txt`, `config/categories.txt`

- [ ] Copy the validated prose prompt from scratchpad `minimal-prompt.txt` into `prompts/checker.txt`, preserving the `→`/`✔`/`✨` markers and the injection-defense line verbatim.
- [ ] Replace the hardcoded category list with `{{CATEGORIES}}` and wrap the rephrase instruction in `{{REPHRASE_START}}` / `{{REPHRASE_END}}` (D5).
- [ ] `config/categories.txt`: one slug per line - `articles`, `agreement`, `tense`, `prepositions`, `plural`, `verb-form`, `questions`.
- [ ] Verify: render the prompt with defaults (`rephrase=true`) and `diff` it against the scratchpad `minimal-prompt.txt` - must be byte-identical, or the R6 measurements no longer apply.
- [ ] Verify: render with `rephrase=false` and confirm the block and both delimiters are gone and no `✨` remains.

### Task 3: Checker hook

**Files:**

- Create: `hooks/grammar-check.sh`

- [ ] Implement the D4 flow, including the plugin-root fallback (D2), `mkdir -p` of state dirs, and `GRAMMAR_HOOK_SYNC` support.
- [ ] Background the model call using the old hook's idiom (`) > /dev/null 2>&1 &` at `grammar-check.sh:325`) - the scratchpad probes are synchronous and are not a model for this.
- [ ] Portability: language gate and timestamps via python3; no `grep -P`, `date -d`, or `jq`. No false-positive filters.
- [ ] Write `history.jsonl` as a single atomic `>>` append of one line (R5). `chmod +x`.
- [ ] Verify (invocation works standalone): run with an isolated env and confirm no crash and empty stdout:
      `GRAMMAR_HOME=$(mktemp -d) GRAMMAR_HOOK_SYNC=1 CLAUDE_PLUGIN_OPTION_LLM_BASE_URL=... CLAUDE_PLUGIN_OPTION_LLM_API_KEY=... CLAUDE_PLUGIN_OPTION_LLM_MODEL=openai/gpt-oss-120b ./hooks/grammar-check.sh < payload.json`
- [ ] Verify (silence): clean-English payload under `GRAMMAR_HOOK_SYNC=1` produces a `✔` line in the status file and no JSONL line.
- [ ] Verify (flag): payload with one clear error (e.g. "he do it") produces a `[<category>] ... → ...` status line **and** one JSONL line whose `fixes[]` is non-empty (this is the arrow-mismatch canary).
- [ ] Verify (capture/display split): with `CLAUDE_PLUGIN_OPTION_SHOW_FEEDBACK=false`, the JSONL line is still appended but the status file stays empty.
- [ ] Verify (non-blocking): without `GRAMMAR_HOOK_SYNC`, the hook returns in under 1s while the status file is still written afterwards (poll up to 30s).
- [ ] Verify (fresh install): all of the above pass with `GRAMMAR_HOME` pointed at an empty temp dir.

### Task 4: Statusline render function and wrapper

**Files:**

- Create: `statusline/render-grammar.sh`, `statusline/grammar-statusline.sh`

- [ ] `render-grammar.sh`: `render_grammar()` reads `$GRAMMAR_HOME/status/$SID`, colors `✔`/`✨` green and splits `[category]` fix lines on `" → "` into colored parts, soft-wrapping to width. Extract and parameterize from `~/.claude/statusline.sh:63-145`.
- [ ] `grammar-statusline.sh`: minimal standalone statusline sourcing the function (session id from stdin JSON via python3).
- [ ] Verify: seed a status file with one `✔` line, one `[articles] a → an (rule: ...)` line, and one `✨` line; run the wrapper with a matching payload; assert all three render, the fix line splits into parts (not the fallback branch), and no `[category]` tag leaks into the output.

### Task 5: Drill skill adapted to the JSONL log

**Files:**

- Create: `skills/grammar-drill/SKILL.md`, `skills/grammar-drill/scripts/build_drill.py`, `skills/grammar-drill/assets/drill-template.html`, `skills/grammar-drill/assets/duo.css`, `skills/grammar-drill/references/syllabus.md`

- [ ] Port `SKILL.md`: read `history.jsonl` as JSONL (no legacy grep), rank recent categories, both modes; `${user_config.native_language}` inline; locate the builder via `${CLAUDE_PLUGIN_ROOT}`; portable page opener (`open`/`xdg-open` detection).
- [ ] Port `build_drill.py` near-verbatim: validate the drill JSON (schema embedded in the script - no separate file), fill the template, inline CSS, `mkdir -p` and write to `$GRAMMAR_HOME/drills/`, print the path, never open.
- [ ] Port `drill-template.html`, `duo.css`, `references/syllabus.md`.
- [ ] Verify: hand-write a minimal drill JSON, run `build_drill.py`, assert a self-contained HTML file at the printed path that renders and grades offline.
- [ ] Verify (ranking is falsifiable): feed a synthetic `history.jsonl` with 5 `articles`, 3 `tense`, 1 `plural` fix lines and assert the skill's ranking rules select `articles` then `tense`.

### Task 6: Eval harness and clean public dataset

**Files:**

- Create: `eval/run.py`, `eval/cases.jsonl`, `eval/README.md`

- [ ] Port `run.py` from scratchpad: drive the real `hooks/grammar-check.sh` with `GRAMMAR_HOOK_SYNC=1`, read back the status file, score FP/recall per class, never pool; drop the `jq` requirement.
- [ ] **`run.py` must set `GRAMMAR_HOME` to a fresh temp dir per run**, so evaluation never touches the user's real `history.jsonl` (otherwise the drill would start teaching the eval dataset).
- [ ] Build a clean `cases.jsonl`: synthetic deterministic cases (typo-silent, injected-mutation-caught) plus anonymized real cases drawn from the archived old log's `YOU:` lines (identifiers substituted, prose untouched, labels assigned fresh). No private data.
- [ ] `eval/README.md`: how to run, what the classes mean, the maintainer-tool framing.
- [ ] Verify: `python3 eval/run.py` runs end to end against the shipped hook, prints a per-class summary, and exits non-zero on failures.
- [ ] Verify (isolation): `~/.claude/cc-grammar-practice/history.jsonl` is byte-identical before and after a full eval run.

### Task 7: README and install docs

**Files:**

- Create: `README.md`

- [ ] Write install (`/plugin marketplace add`, `/plugin install`, the userConfig prompts), the manual statusline wiring step, config reference, usage, and the v1-is-English-only statement.
- [ ] Confirm the exact slash form Claude Code exposes for the bundled skill before documenting it.
- [ ] Verify: perform a real clean install by following the README verbatim against an empty `GRAMMAR_HOME`, and confirm feedback appears - not a read-through.

### Task 8: Verify acceptance criteria

- [ ] End-to-end: send a real English message in a live session; confirm feedback appears in the statusline within ~2s on `gpt-oss-120b`.
- [ ] Re-run `eval/run.py` against the shipped hook; confirm the typo/name/mention silence classes hold and recall matches R6 (closing the loop the probe opened on a stripped variant).
- [ ] Confirm capture/display toggles, the rephrase off-switch, and `/plugin disable` all behave per R2/R3.
- [ ] Confirm no `grep -P`, `date -d`, `xdg-open`, or `jq` remain: grep the tree.
- [ ] Confirm the three protocol markers are byte-identical across `prompts/checker.txt`, `statusline/render-grammar.sh`, `eval/run.py`, and `hooks/grammar-check.sh`.

### Task 9: Finalize documentation and migrate

- [ ] Update `README.md` and `docs/` for anything discovered during the build.
- [ ] Migration: point the install at `~/.claude/cc-grammar-practice/`; **archive** `~/.claude/grammar-feedback.log` and `grammar-trace.jsonl` outside the state dir (message corpus for the eval; never imported into `history.jsonl`); delete `grammar-stats.tsv`, `grammar-ignore.txt`, `grammar-llm.env`; remove the old hook and the grammar block from the personal statusline.
- [ ] Verify (post-migration): send a message and confirm the new install writes a status line and appends to the new `history.jsonl`, and that the archived log is untouched.
- [ ] Move this plan to `docs/plans/completed/`.

## Post-Completion

_Manual / external, no checkboxes:_

- Publish the repo to GitHub and optionally submit to the plugin directory.
- Switch the personal statusline to source `render-grammar.sh` (the manual wiring step no plugin can automate).
- Replace the preliminary R6 numbers with a run over the full clean dataset (requirements open items: repeats-per-case, dataset size).
- v2: configurable target language, per R1.
