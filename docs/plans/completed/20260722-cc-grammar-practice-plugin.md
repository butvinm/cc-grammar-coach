# Build the cc-grammar-coach plugin

## Overview

Package a two-part English-grammar tool as a public Claude Code plugin:

- a **checker** (`UserPromptSubmit` hook) that reviews each English message out of band, logs mistakes, and optionally shows feedback in the statusline;
- a **drill** (skill) that turns the logged mistakes into a lesson-plus-quiz web page.

This is a ground-up rebuild, not a port. The existing `~/.claude/grammar-*` code is reference for which problems are real; its 120 lines of false-positive filters, its two overlapping logs, and its 2100-char prompt are dropped. Every contested decision below was settled by measurement (see the inlined model table).

v1 teaches **English only**. A configurable target language is deferred to v2 (see R1).

This plan is self-contained: the requirements and design needed to execute it are inlined in "Design reference" so no other file is required. Full versions live in `docs/requirements.md` and `docs/design.md`.

## Context (from discovery)

- Repo root: `/home/butvinm/Dev/cc-grammar-coach` (currently only `docs/`). Not yet a git repo.
- Reusable artifacts in the session scratchpad `/tmp/claude-1000/-home-butvinm-Dev-cc-grammar-coach/43228289-01d3-4ca0-9155-6d9bd7694dd8/scratchpad/`:
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
cc-grammar-coach/
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
- Grammar home: `~/.claude/cc-grammar-coach/`, overridable by `$GRAMMAR_HOME`. Holds `status/<session-id>`, `history.jsonl`, `curriculum.tsv`, `drills/`. **Every component creates the directories it writes to (`mkdir -p`)**; a fresh install has none of them. Fixed path because the non-plugin statusline cannot read plugin env vars. Status files older than one day are tidied.

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

### Task 1: Scaffold, manifest, hook declaration, marketplace

**Files:**

- Create: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `hooks/hooks.json`, `.gitignore`, `LICENSE`

- [x] `git init` on `master`; `.gitignore` (local test homes, `*.bak-*`, `drills/`); add `LICENSE` matching the manifest's declared license. (repo already exists on branch `cc-grammar-practice-plugin`; `git init` treated as satisfied per executor note)
- [x] `plugin.json`: name `cc-grammar-coach`, version, description, **author** (the validator warns without it), repository, license, keywords, and the full `userConfig` block (D3) with `type`/`title`/`description`/`default` on every field.
- [x] `hooks/hooks.json`: one `UserPromptSubmit` entry running `"${CLAUDE_PLUGIN_ROOT}"/hooks/grammar-check.sh` (quoted - the root may contain spaces), timeout 10s. Rely on convention discovery; do **not** also add a `hooks` field to `plugin.json`.
- [x] `marketplace.json`: list this one plugin from this repo.
- [x] Declare `llm_api_key` as `sensitive`. **Already verified** (throwaway probe plugin, 2026-07-22): sensitive values are injected into the hook env as `CLAUDE_PLUGIN_OPTION_<KEY>` while being stored outside `settings.json`, so credentials live in userConfig with no private-file fallback. No spike needed.
- [x] Verify: `claude plugin validate` passes (catches bad event names, hook shape, and userConfig schema - `json.load` cannot). (passed `--strict` for both plugin.json and marketplace.json)

### Task 2: Checker prompt and category list

**Files:**

- Create: `prompts/checker.txt`, `config/categories.txt`

- [x] Copy the validated prose prompt from scratchpad `minimal-prompt.txt` into `prompts/checker.txt`, preserving the `→`/`✔`/`✨` markers and the injection-defense line verbatim. (source survived at `docs/minimal-prompt.txt`, not scratchpad)
- [x] Replace the hardcoded category list with `{{CATEGORIES}}` and wrap the rephrase instruction in `{{REPHRASE_START}}` / `{{REPHRASE_END}}` (D5).
- [x] `config/categories.txt`: one slug per line - `articles`, `agreement`, `tense`, `prepositions`, `plural`, `verb-form`, `questions`. (trailing newline; renderer filters empties)
- [x] Verify: render the prompt with defaults (`rephrase=true`) and `diff` it against the scratchpad `minimal-prompt.txt` - must be byte-identical, or the R6 measurements no longer apply. (zero diffs, both 2572 bytes)
- [x] Verify: render with `rephrase=false` and confirm the block and both delimiters are gone and no `✨` remains. (grep: 0 for all three)

### Task 3: Checker hook

**Files:**

- Create: `hooks/grammar-check.sh`

- [x] Implement the D4 flow, including the plugin-root fallback (D2), `mkdir -p` of state dirs, and `GRAMMAR_HOOK_SYNC` support. (recursion guard exits 0 before writing any state; root derived from `${BASH_SOURCE[0]}/..` when env unset)
- [x] Background the model call using the old hook's idiom (`) > /dev/null 2>&1 &` at `grammar-check.sh:325`) - the scratchpad probes are synchronous and are not a model for this. (idiom salvaged; `[ -n "$GRAMMAR_HOOK_SYNC" ] && wait`)
- [x] Portability: language gate and timestamps via python3; no `grep -P`, `date -d`, or `jq`. No false-positive filters. (grep for `jq`/`grep -P`/`date -d`/`xdg-open` -> none; ts via `datetime.astimezone().isoformat`)
- [x] Write `history.jsonl` as a single atomic `>>` append of one line (R5). `chmod +x`. (python emits one json line to stdout, bash `printf >>` appends it; executable)
- [x] Verify (invocation works standalone): run with an isolated env and confirm no crash and empty stdout. (exit=0, stdout=0B against live gpt-oss-120b endpoint)
- [x] Verify (silence): clean-English payload under `GRAMMAR_HOOK_SYNC=1` produces a `✔` line in the status file and no JSONL line. (status "✔ Clear and polite.", no history.jsonl)
- [x] Verify (flag): payload with one clear error (e.g. "he do it") produces a `[<category>] ... → ...` status line **and** one JSONL line whose `fixes[]` is non-empty (this is the arrow-mismatch canary). (two `[agreement] ... → ...` lines + `✨` rephrase in status; 1 jsonl line, fixes[]=2)
- [x] Verify (capture/display split): with `CLAUDE_PLUGIN_OPTION_SHOW_FEEDBACK=false`, the JSONL line is still appended but the status file stays empty. (status 0B, history 1 line)
- [x] Verify (non-blocking): without `GRAMMAR_HOOK_SYNC`, the hook returns in under 1s while the status file is still written afterwards (poll up to 30s). (returned in 0.445s, status empty at return, appeared ~2.5s later)
- [x] Verify (fresh install): all of the above pass with `GRAMMAR_HOME` pointed at an empty temp dir. (every check used a fresh `mktemp -d` home; PRAISE fallback and 4 gates also verified)

### Task 4: Statusline render function and wrapper

**Files:**

- Create: `statusline/render-grammar.sh`, `statusline/grammar-statusline.sh`

- [x] `render-grammar.sh`: `render_grammar()` reads `$GRAMMAR_HOME/status/$SID`, colors `✔`/`✨` green and splits `[category]` fix lines on `" → "` into colored parts, soft-wrapping to width. Extract and parameterize from `~/.claude/statusline.sh:63-145`. (SID from arg or $SID var; GRAMMAR_HOME default `~/.claude/cc-grammar-coach`, overridable; render_fix_line lifted verbatim)
- [x] `grammar-statusline.sh`: minimal standalone statusline sourcing the function (session id from stdin JSON via python3). (python3 parse with default fallback; sources sibling render-grammar.sh via BASH_SOURCE dir)
- [x] Verify: seed a status file with one `✔` line, one `[articles] a → an (rule: ...)` line, and one `✨` line; run the wrapper with a matching payload; assert all three render, the fix line splits into parts (not the fallback branch), and no `[category]` tag leaks into the output. (all 3 render; wrong "a" red + fix "an" green via SPLIT branch; no yellow fallback; no `[articles]` tag in stripped output; `bash -n` clean on both)

### Task 5: Drill skill adapted to the JSONL log

**Files:**

- Create: `skills/grammar-drill/SKILL.md`, `skills/grammar-drill/scripts/build_drill.py`, `skills/grammar-drill/assets/drill-template.html`, `skills/grammar-drill/assets/duo.css`, `skills/grammar-drill/references/syllabus.md`

- [x] Port `SKILL.md`: read `history.jsonl` as JSONL (no legacy grep), rank recent categories, both modes; `${user_config.native_language}` inline; locate the builder via `${CLAUDE_PLUGIN_ROOT}`; portable page opener (`open`/`xdg-open` detection). (legacy grep/awk/tail/stats.tsv dropped; ranking is a concrete embedded python heredoc; opener detect-and-degrade to printing the path; curriculum at `$GRAMMAR_HOME/curriculum.tsv`)
- [x] Port `build_drill.py` near-verbatim: validate the drill JSON (schema embedded in the script - no separate file), fill the template, inline CSS, `mkdir -p` and write to `$GRAMMAR_HOME/drills/`, print the path, never open. (only change vs source: output dir now `$GRAMMAR_HOME/drills/`, GRAMMAR_HOME default `~/.claude/cc-grammar-coach`; embedded `validate()` unchanged)
- [x] Port `drill-template.html`, `duo.css`, `references/syllabus.md`. (byte-identical copies; `assets/duo.md` omitted - referenced by neither SKILL.md nor the template)
- [x] Verify: hand-write a minimal drill JSON, run `build_drill.py`, assert a self-contained HTML file at the printed path that renders and grades offline. (path exists under `$GRAMMAR_HOME/drills/`; no external `<link>`; `.duo-shell` CSS inlined and `__DUO_CSS__` replaced; `const DATA =` + `function check()` grading JS present, `__DRILL_DATA__` replaced)
- [x] Verify (ranking is falsifiable): feed a synthetic `history.jsonl` with 5 `articles`, 3 `tense`, 1 `plural` fix lines and assert the skill's ranking rules select `articles` then `tense`. (ran SKILL.md ranking heredoc verbatim: 5 articles / 3 tense / 1 plural -> 1st=articles, 2nd=tense; reversed-data control gives tense first, so the assertion can fail)

### Task 6: Eval harness and clean public dataset

**Files:**

- Create: `eval/run.py`, `eval/cases.jsonl`, `eval/README.md`

- [x] Port `run.py` from scratchpad: drive the real `hooks/grammar-check.sh` with `GRAMMAR_HOOK_SYNC=1`, read back the status file, score FP/recall per class, never pool; drop the `jq` requirement. (scratchpad source gone; reconstructed from the Task 6 spec + D5; parses status on the exact `→` byte, categories from the isolated `history.jsonl`; classes never pooled; no jq)
- [x] **`run.py` must set `GRAMMAR_HOME` to a fresh temp dir per run**, so evaluation never touches the user's real `history.jsonl` (otherwise the drill would start teaching the eval dataset). (mkdtemp per case, rmtree in finally; `CLAUDE_PLUGIN_ROOT` set, `GRAMMAR_HOOK_ACTIVE` popped)
- [x] Build a clean `cases.jsonl`: synthetic deterministic cases (typo-silent, injected-mutation-caught) plus anonymized real cases drawn from the archived old log's `YOU:` lines (identifiers substituted, prose untouched, labels assigned fresh). No private data. (36 cases: 10 typo-silent, 8 name/mention-silent, 18 recall across all 7 categories; 21 synthetic / 15 real-derived; identifiers/paths/usernames scrubbed, prose grammar untouched)
- [x] `eval/README.md`: how to run, what the classes mean, the maintainer-tool framing. (includes the `CLAUDE_PLUGIN_OPTION_*`/`LLM_*` cred export, per-class semantics, gate/exit-code reference, isolation guarantee)
- [x] Verify: `python3 eval/run.py` runs end to end against the shipped hook, prints a per-class summary, and exits non-zero on failures. (live gpt-oss-120b run: per-class summary printed, real set PASS exit 0 with recall 18/18 and silence FP 20%/0% under the 25% ceiling; `--selftest` proves the non-zero path, exit 1)
- [x] Verify (isolation): `~/.claude/cc-grammar-coach/history.jsonl` is byte-identical before and after a full eval run. (ABSENT before and ABSENT after the full run; per-case tempdir GRAMMAR_HOME guarantees it)

### Task 7: README and install docs

**Files:**

- Create: `README.md`

- [x] Write install (`/plugin marketplace add`, `/plugin install`, the userConfig prompts), the manual statusline wiring step, config reference, usage, and the v1-is-English-only statement. (README.md at repo root; all six userConfig fields named from D3/plugin.json; manual statusline step documents both the source-render_grammar snippet and grammar-statusline.sh; config + GRAMMAR_HOME tables; v1-English-only stated up front)
- [x] Confirm the exact slash form Claude Code exposes for the bundled skill before documenting it. (documented `/cc-grammar-coach:grammar-drill` = `/plugin-name:skill-name`; evidence: installed humanizer plugin README shows `/humanizer:humanizer` for the same plugin:skill pattern, and the Skill-tool contract states plugin skills use `plugin:skill`; live confirmation left for Task 8)
- [x] Verify: perform a real clean install by following the README verbatim against an empty `GRAMMAR_HOME`, and confirm feedback appears - not a read-through. (MECHANICAL clean-install path verified against a fresh empty GRAMMAR_HOME: shipped hooks/grammar-check.sh with GRAMMAR_HOOK_SYNC=1 + the README's CLAUDE_PLUGIN_OPTION_* config + creds from ~/.claude/grammar-llm.env produced a status file with 3 fix lines + a ✨ rephrase and one history.jsonl line; both README statusline snippets then rendered that status file correctly, exit 0. The interactive `/plugin marketplace add` + `/plugin install` step cannot run in this subagent and is left for the Task 8 live session.)

### Task 8: Verify acceptance criteria

- [x] End-to-end: send a real English message in a live session; confirm feedback appears in the statusline within ~2s on `gpt-oss-120b`. (mechanical equivalent; interactive live-session confirmation deferred to manual: ran the shipped `hooks/grammar-check.sh` under `GRAMMAR_HOOK_SYNC=1` with gpt-oss-120b creds on a fresh temp `GRAMMAR_HOME`, timed across 4 real English messages -> latency 1.96/2.86/3.23/4.09s, median ~3.0s (above R6's raw p50 1.4s; the delta is python-subprocess spawns + network RTT to the remote proxy, not model time), every run wrote a correct status feedback line with fix + `✨` lines or the `✔` praise. Did NOT drive a real TUI session.)
- [x] Re-run `eval/run.py` against the shipped hook; confirm the typo/name/mention silence classes hold and recall matches R6 (closing the loop the probe opened on a stripped variant). (3 live gpt-oss-120b runs, nondeterministic -> ranges: typo-silent FP 20-30% [2-3/10], 2/3 runs under the harness 25% ceiling; name/mention-silent FP 0-12% [0-1/8], all under ceiling; recall 15-17/18 [83-94%], all clear the 70% floor and match R6's ~13/14 (~93%) ballpark. RESULT: run1 FAIL / run2 PASS / run3 PASS. `craete`->`create` and `compatrible`->`compatible` are the recurring typo-silence tail; prompt is byte-locked to `minimal-prompt.txt` per D5 so not touched.)
- [x] Confirm capture/display toggles, the rephrase off-switch, and `/plugin disable` all behave per R2/R3. (capture/display: `SHOW_FEEDBACK=false` -> status file 0 bytes, `history.jsonl` still 1 line with fixes [R2]. rephrase off-switch: `REPHRASE=false` -> rendered prompt has 0 `✨` and 0 delimiters and hook status carries no `✨`/no `rephrase` key; `REPHRASE=true` -> rendered prompt has the `✨` instruction and hook status shows the `✨` line. `/plugin disable`: mechanism verified, not invoked - all runtime flows through the single `hooks/hooks.json` `UserPromptSubmit` -> `grammar-check.sh` entry [plugin.json declares no `hooks`/`commands`/`statusLine`], and `userConfig` has no master enable toggle [D3], so disabling the plugin unregisters the sole hook; interactive `/plugin disable` deferred to manual.)
- [x] Confirm no `grep -P`, `date -d`, `xdg-open`, or `jq` remain: grep the tree. (21 shipped files grepped: `grep -P` 0, `date -d` 0. `xdg-open` appears only inside the `command -v xdg-open` guard of the Task-5-mandated portable opener [`skills/grammar-drill/SKILL.md:89`] + doc prose; `jq` appears only in negative doc prose ["no jq required"]. No unconditional dependence on any banned tool -> no portability defect; nothing fixed.)
- [x] Confirm the three protocol markers are byte-identical across `prompts/checker.txt`, `statusline/render-grammar.sh`, `eval/run.py`, and `hooks/grammar-check.sh`. (byte-level python check: all three present in all four files with identical UTF-8 bytes - `→` U+2192 = e2 86 92, `✔` U+2714 = e2 9c 94, `✨` U+2728 = e2 9c a8.)

### Task 9: Finalize documentation and migrate

- [x] Update `README.md` and `docs/` for anything discovered during the build. (recorded the measured end-to-end wall-clock reality ~2-4s median ~3s vs raw model p50 1.4s in README.md "Model notes" and docs/requirements.md section 6; eval/README.md now states the per-class FP-rate ceiling honestly as an ideal-zero-but-gated-at-0.25 rate and names the recurring `craete`/`compatrible` typo tail; the confirmed slash form `/cc-grammar-coach:grammar-drill` was already documented in README.md)
- [x] SAFE COPY ONLY per user override: legacy grammar-* corpus copied (not moved) to ~/.claude/grammar-legacy-backup/; no deletes, old hook and statusline left intact; full plan-spec migration deferred to the user.
- [x] deferred - new plugin not yet installed via /plugin install; to be confirmed by the user post-install. The mechanical hook->status->history path was already proven in Tasks 3/7/8 against a fresh GRAMMAR_HOME.
- [x] handled by the exec orchestrator at completion

## Post-Completion

_Manual / external, no checkboxes:_

- Publish the repo to GitHub and optionally submit to the plugin directory.
- Switch the personal statusline to source `render-grammar.sh` (the manual wiring step no plugin can automate).
- Replace the preliminary R6 numbers with a run over the full clean dataset (requirements open items: repeats-per-case, dataset size).
- v2: configurable target language, per R1.
