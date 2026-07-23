# Grammar plugin - requirements

Foundation for a ground-up redesign. The existing hook/skill/statusline/eval are reference for which problems are real, not a design to preserve.

## 1. Purpose and scope

A Claude Code plugin that helps a non-native speaker improve their English by working with the English they already type into Claude Code. Two co-equal tools over a shared mistake log:

- **checker** - reviews each English message out of band, can surface feedback.
- **drill** - turns logged mistakes (or the next syllabus topic) into a lesson-plus-quiz web page.

Target is English, fixed in v1. Native language is configurable with **no default** (unset = generic lessons; no nationality ships as a default).

Out of scope: a hand-written grammar engine (a model judges against a narrow spec); scoring naturalness (it lives in the unscored rephrase channel).

**Deferred to v2 - configurable target language.** The FLAG contract is language-neutral, so the checker would generalize cheaply, but nothing else does: the prompt, `categories.txt`, the syllabus, and the eval are all English. Shipping a `target_language` knob in v1 would advertise a capability that does not exist. v2 must, together: parameterize the prompt, ship or accept per-target categories, degrade Learn mode explicitly, and state that non-English is unvalidated.

## 2. Users

Three personas by how much they want to see: **A** sees corrections in flow; **B** wants silent capture only, to feed drills; **C** wants both.

The requirement this forces: **capture and display are independently switchable.** Persona B runs the checker as a logger with display off; the drill still works.

Use cases: see corrections in flow (A/C); silent capture (B/C); drill logged mistakes; learn the next weekly syllabus topic.

## 3. Checker behavioral spec

Up to three outputs per message. Only FLAG is scored.

### 3.1 FLAG (grammar errors, scored)

Flag a fragment only when all hold:

1. one **single** correct fix, not a range;
2. **virtually every** fluent speaker makes the **same** fix;
3. wrong and fixed are both correctly-spelled real words (excludes typos: "a office -> an office" yes, "office -> ofice" never);
4. it is the user's own running prose, not a quote/mention or a code identifier/path/tool name.

Wire format, one line per error (parsed by statusline and drill):

```
[<category>] <wrong> → <fix> (<rule>: <why, short>)
```

**Protocol markers are exactly three, and are Unicode, not ASCII:** `→` (U+2192, separates wrong from fix), `✔` (U+2714, praise/liveness), `✨` (U+2728, rephrase). The prompt instructs the model to emit them, the statusline matches on them, and the eval parses them, so they must appear verbatim in the prompt, the parsers, and any test fixture. This is the one place the project's otherwise-ASCII convention does not apply; substituting `->` silently empties `fixes[]` and starves the drill.

### 3.2 Silence (default)

Stay silent (or offer only a rephrase) on: correct grammar; naturalness/word-choice/clarity/terseness; typos of any kind; code identifiers, tool/product names, paths, anything with a hyphen/underscore/dot/slash/camelCase/backticks; quoted or mentioned fragments; punctuation/casing/contractions/slang; anything fluent speakers would fix differently or dispute. Narrow by design, so ground truth is a rule, not an opinion.

### 3.3 REPHRASE (naturalness, unscored)

One optional `✨` line rewriting the **whole** message more naturally:

- **Restrained**: only when the original reads clearly awkward; bias to silence.
- **Never a fix-reapplication**: must add natural structure, not the fixes re-applied nor a synonym swap. Enforced by the prompt; no mechanical dedup.
- **Preserve** every identifier/path/number/term and each sentence's speech act and meaning.
- Never emitted together with the `✔` praise line.
- **Off-switch**: a toggle disables the channel (the prompt then omits it) - the reliable control, since wording-tuning the rate proved finicky.

Prompt form is **prose**, not a step procedure: a 4-step variant tripled the rephrase-on-clean rate and hurt format compliance on gpt-oss-120b.

### 3.4 PRAISE (liveness, unscored)

On a clean, natural message, one short `✔` compliment. It doubles as the **liveness signal** (proof the checker ran), so it must never render blank: a single static fallback covers a missing or garbled model praise.

### 3.5 Categories

Labels for grouping, not scored. They live in a configurable `categories.txt` the prompt reads (keeps the model's slugs consistent for drill grouping) and are target-specific. The statusline colors any `[slug]` generically; the drill groups by whatever slugs appear. Exact English membership is deferred to the dataset stage.

## 4. Non-functional requirements

- Never write to stdout (no context pollution).
- Never delay the turn (the model call runs in the background).
- Capture and display independently toggleable.
- Gates: skip empty, slash-command, too-short, too-long, system-injected, and non-English messages.
- Platforms: Linux + macOS (portable substitutes for `grep -P`, `date -d`, `xdg-open`).
- Dependencies: `bash`, `python3`, `curl`; no `jq`. `hunspell` and the `claude` CLI optional.
- All state under one namespaced directory (clean install and uninstall).

## 5. The drill

A skill (Claude runs it), co-equal with the checker, consuming its log. Two modes: Drill (practice logged mistakes) and Learn (next syllabus topic).

### 5.1 Data contract (checker to drill)

One append-only JSONL, the single source of truth, one line per non-clean message:

```json
{
  "ts": "...",
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

Every field is already computed for the statusline, so logging is free. The drill uses it as a cheap **index** (`fixes[].category` ranks weak spots; a line's presence pre-filters mistaken messages) and re-reads `message` as **source material** for lessons. Release anonymization touches identifiers in `message` only, so grammar labels stay invariant.

### 5.2 Drill mode

Rank categories by **recent** mistakes (about a week; widen if too few), take the top 2-3, skip deliberate checker-test messages. Per topic: a short lesson with 2-4 examples from the user's own mistakes, and 4-6 fresh quiz questions. Render and open the page.

### 5.3 Learn mode

Teach the next unstarted topic from a curated English syllabus, one per week, tracked in a curriculum file; review the current week's topic if already set. Personalize from the log (misuse or, just as telling, avoidance). **English-only**; other targets get Drill mode only.

### 5.4 The page

Self-contained offline HTML written to the state dir, graded in-browser, mixing choice and rewrite questions (rewrite accepts enumerated variants, ignoring case, spacing, end punctuation). A builder script validates the drill JSON against a schema and fills the template; it never opens the page itself. Generated text is plain ASCII.

### 5.5 Personalization

With a native language set, lessons contrast the English rule with that language's habits (Russian: no articles, freer word order, aspect over tense). Unset: generic, no contrast.

### 5.6 Guardrails

Too few usable fixes (about five): say the log is too small, do not fabricate. Never present invented example sentences as the user's own.

## 6. Model and filter strategy

Measured: minimal prompt, zero filters, 49 local cases, one run each, four models.

| model                 | typo silent | name/mention | recall | bracket format | latency p50/max |
| --------------------- | ----------- | ------------ | ------ | -------------- | --------------- |
| claude -p haiku       | 11/11       | 3/3, 1/1     | 11/13  | ~60%           | 9.8s / 72s      |
| gemini-3.1-flash-lite | 5/11        | 3/3, 1/1     | 10/14  | high           | 1.5s / 13.5s    |
| gpt-5-nano            | 11/11       | 2/3, 0/1     | 10/14  | ~72%           | 9.2s / 45s      |
| gpt-oss-120b          | 11/11       | 3/3, 1/1     | 13/14  | ~96%           | 1.4s / 3.0s     |

- **No false-positive filters ship.** Every strong model passes the typo/name/mention classes unaided; only gemini needed the filters, and it is rejected (it also invents wrong corrections).
- **Default model: `gpt-oss-120b`** (no filters, best recall, ~96% format, flat low latency, cheap).
- **Zero-config fallback: `claude -p` haiku** (no key, reliable content, but ~10s and ~60% format).
- **Custom endpoint is opt-in**, vetted by the eval (`gpt-oss-120b` tested-good, `gemini-3.1-flash-lite` tested-bad).
- Format compliance is model-dependent, not inherent; tolerating the occasional bare line is enough.

Numbers are preliminary (biased dataset, single run) and get re-confirmed on the clean dataset.

The table is raw model latency. Build-time measurement of the shipped hook end-to-end (four real English messages, `gpt-oss-120b` via a remote proxy) gave a wall-clock of ~2-4s, median ~3s: the raw p50 of 1.4s plus python subprocess spawns and network round-trip to the remote endpoint. The call is backgrounded, so this never blocks the turn.

## 7. Evaluation

A **maintainer tool** (decides filters and model, catches prompt regressions); end users never run it.

- **Dataset** (public, in-repo, the main eval): anonymized real traffic (identifiers substituted, prose untouched, so labels stay invariant; raw kept local) plus synthetic deterministic cases (typo-silent, injected-mutation-caught).
- **Sampling**: gated turns from real transcripts, uniform, so mostly silence (the honest FP denominator); a separate enriched set for recall. Never pooled.
- **Labeling**: a strong model proposes flag-or-silence against the narrow spec; unassignable cases are excluded ("exclude the middle"); the maintainer confirms. Known risks: single-labeler and same-vendor blind spots.
- **Metrics**: FP-rate (primary) and recall, separated, each over several runs (the model is nondeterministic), model pinned.
- English only.

## 8. Packaging

Claude Code plugin plus `marketplace.json` (`/plugin marketplace add` then `/plugin install`). Hook, skill, and `${CLAUDE_PLUGIN_ROOT}` paths install cleanly. **The statusline cannot be plugin-installed** (`statusLine` is a single user setting): ship a render function plus a standalone wrapper, with one manual wiring step at install. The README states plainly that v1 teaches English only.

## 9. Open questions

- Silence-gate thresholds (length bounds, language ratio).
- Eval sub-details: repeats-per-case, dataset size, enriched-set source.
- State file layout under the namespaced directory.
- Category membership (from data).
- Marker encoding: keep Unicode (`✨`/`✔`/`->`) or move to ASCII sentinels. Optional cleanup - the bracket format is ~96% reliable on `gpt-oss-120b`.
