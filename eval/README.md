# Eval harness (maintainer tool)

This is a **maintainer's regression harness**, not part of the installed runtime. End users never run it. It exists to catch checker regressions when the prompt, the model, or the hook changes: it drives the shipped `hooks/grammar-check.sh` against a fixed dataset and scores it per class.

## What it checks

Each case belongs to one class, and the classes are scored separately and **never pooled** into a single number, because a false positive on a typo and a missed grammar error are different failures with different budgets.

- **typo-silent** - the message contains a misspelling. The checker must stay silent: a typo is not a grammar flag (spec rule 3, "wrong and fixed are both correctly-spelled real words"). Scored as a false-positive rate; the ideal is zero, but the gate tolerates a small rate (see below) because the model is nondeterministic.
- **name/mention-silent** - the message contains a code identifier, a path, or a quoted mention. These must stay silent (spec rule 4). Scored as a false-positive rate; the ideal is zero, gated the same way.
- **recall** - the message contains one clear grammar error that a fluent speaker would fix the same way. The checker must flag it. Scored two ways per grammar category: **caught** (flagged with the expected category slug) and **flagged** (flagged at all, any category). The gate uses the aggregate flagged rate against a floor, because category naming is somewhat stochastic while catching the error at all is the real contract.
- **rephrase-dup** - not a case class but a property checked across every run: a rephrase logged to `history.jsonl` must differ structurally from the message with its fixes applied. The hook drops near-duplicates itself (word-sequence similarity >= `0.9` after lowercasing and stripping punctuation, mirrored as `DUP_RATIO` in `run.py`), so any duplicate reaching the log is a code regression (issue #9), not model noise - the ceiling is zero and the gate is hard.
- **rephrase-recall** - the message is grammatically correct but built on constructions no native would use (translated idioms, impersonal openers, nominalization chains). The checker must offer a standalone `✨` rephrase instead of praise (issue #21). Gated by a floor on the rate of samples carrying a rephrase.
- **natural-silent** - the message is clean, natural English. The checker must answer with praise only: a fix or a rephrase on these cases is a false positive. Scored as a rate over both signals against the same ceiling as the other silence classes.
- **silent-rephrase** - not a case class but a guard over the typo/name silence classes: now that the model may rephrase without error lines, those messages must not start acquiring rephrases (a rephrase silently rewriting a misspelling is the failure mode). Their rephrase rate has its own ceiling.

The dataset (`cases.jsonl`) mixes deterministic synthetic cases with anonymized cases drawn from real traffic (identifiers substituted, prose grammar untouched, labels assigned fresh). No private data.

Cases carrying `"selection": "full"` run with the entire catalog enabled (the harness writes `enabled-categories.txt` into the isolated `GRAMMAR_HOME`), so recall is gated for every catalog category a user can enable, not just the shipped default selection. All other cases run on the default selection - that is the configuration the silence/FP gates are calibrated for; a user's custom selection changes the false-positive surface and carries no CI guarantee.

## How to run

The hook needs a model. Export the LLM settings first, then run:

```sh
# either export the CLAUDE_PLUGIN_OPTION_* names directly, or source a private
# env file that exports LLM_BASE_URL / LLM_API_KEY / LLM_MODEL - run.py maps
# the plain names onto the CLAUDE_PLUGIN_OPTION_* the hook reads:
export LLM_BASE_URL="https://your-endpoint/v1"
export LLM_API_KEY="sk-..."
export LLM_MODEL="openai/gpt-oss-120b"

python3 eval/run.py               # one sample per case (fast, noisy)
python3 eval/run.py --repeats 3   # three samples per case, gate on the mean
```

Credentials are required: the hook has no model fallback (the old `claude -p` haiku path was dropped for its ~60% format compliance), so `run.py` exits early when they are missing instead of measuring a hook that silently checks nothing.

Prove the non-zero gate path without touching the network:

```sh
python3 eval/run.py --selftest   # feeds fabricated failing results through the real gate; exits 1
```

## Output and exit code

`run.py` prints a per-class summary (silence rates with the offending messages listed, and per-category recall) and ends with `RESULT: PASS` or `RESULT: FAIL`. It **exits non-zero** whenever a gate fails, so CI and the plan's Task 8 can gate on it. Gates:

- silence classes: the per-class false-positive **rate** (flagged samples / total samples) must not exceed `GRAMMAR_EVAL_MAX_SILENT_FP_RATE` (default `0.25`).
- recall floor (flagged-any): the aggregate flagged rate must be at least `GRAMMAR_EVAL_MIN_RECALL` (default `0.7`).
- rephrase duplicates: zero tolerance - one near-duplicate rephrase in any logged line fails the run (see **rephrase-dup** above).
- rephrase recall floor: the rate of `rephrase-recall` samples carrying a standalone rephrase must be at least `GRAMMAR_EVAL_MIN_REPHRASE_RECALL` (default `0.5`; live sampling of `gpt-oss-120b` landed 5/6-6/6 on the fixture patterns, but the floor starts permissive until more fixtures accumulate).
- natural-silent ceiling: fixes-or-rephrase rate on `natural-silent` cases must not exceed `GRAMMAR_EVAL_MAX_SILENT_FP_RATE` (shared with the other silence classes).
- silent-rephrase ceiling: the rephrase rate over typo/name silence samples must not exceed `GRAMMAR_EVAL_MAX_SILENT_REPHRASE_RATE` (default `0.25`).
- recall floor (exact category): the pooled fraction of errors flagged under their **own** category slug must be at least `GRAMMAR_EVAL_MIN_EXACT_RECALL` (default `0.6`, raised from `0.5` after a `--repeats 2` run on the defined slugs misfiled zero of 41 flagged samples). A model that catches every error but files them all under one wrong category would still clear the flagged-any floor; this floor catches that. It is pooled across categories rather than gated per category because each category has only 1-3 cases, so one category can score zero exact hits on a single sample by chance - pooling separates a healthy model (~0.9 exact) from mislabel-everything (~0.1) without failing on naming noise. The per-slug definitions in `config/categories.txt` (issue #3) removed the worst overlap (the old catch-all `verb-form`); per-category exact counts are still printed so a genuinely weak category is visible.

**Reproduce before trusting the exit code.** The model is nondeterministic, so one `--repeats 1` run is a single noisy sample of each case. Pass `--repeats N` to sample each case N times (each in its own isolated `GRAMMAR_HOME`) and gate on the mean rate across samples; a higher N is what makes the exit code stable enough to gate CI on. The floor and ceiling are environment-overridable for tuning. The silence gate is a rate rather than an absolute zero because the model is nondeterministic, so the false-positive rate is only meaningful over several runs. Consecutive single-sample live runs of `gpt-oss-120b` at build time landed the typo-silent class between 20% and 30% FP, straddling the 25% ceiling, so a single run can pass or fail on model noise alone; the ceiling still separates the accepted `gpt-oss-120b` from the rejected `gemini-3.1-flash-lite`, which leaked roughly half its typo cases. Every individual false positive is listed under its class so the maintainer can inspect debatable calls even when the rate stays under the ceiling. The recurring tail on `gpt-oss-120b` is a small set of typo cases the model treats as fixes rather than misspellings - `craete -> create` and `compatrible -> compatible` showed up on every run - plus the odd collocation flag such as `remind about -> remind of`. The prompt is byte-locked to the shipped `prompts/checker.txt`, so this tail is left in place rather than patched.

## Isolation

Every case runs the hook with `GRAMMAR_HOME` pointed at a fresh temp dir (created and removed per case) and `GRAMMAR_HOOK_SYNC=1` so the backgrounded model call is awaited. The eval therefore **never reads or writes the user's real `~/.claude/cc-grammar-coach/history.jsonl`** - otherwise the drill would start teaching the eval dataset. The real state file is byte-identical before and after a full run.
