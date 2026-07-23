# Eval harness (maintainer tool)

This is a **maintainer's regression harness**, not part of the installed runtime. End users never run it. It exists to catch checker regressions when the prompt, the model, or the hook changes: it drives the shipped `hooks/grammar-check.sh` against a fixed dataset and scores it per class.

## What it checks

Each case belongs to one class, and the classes are scored separately and **never pooled** into a single number, because a false positive on a typo and a missed grammar error are different failures with different budgets.

- **typo-silent** - the message contains a misspelling. The checker must stay silent: a typo is not a grammar flag (spec rule 3, "wrong and fixed are both correctly-spelled real words"). Scored as a false-positive rate; the ideal is zero, but the gate tolerates a small rate (see below) because the model is nondeterministic.
- **name/mention-silent** - the message contains a code identifier, a path, or a quoted mention. These must stay silent (spec rule 4). Scored as a false-positive rate; the ideal is zero, gated the same way.
- **recall** - the message contains one clear grammar error that a fluent speaker would fix the same way. The checker must flag it. Scored two ways per grammar category: **caught** (flagged with the expected category slug) and **flagged** (flagged at all, any category). The gate uses the aggregate flagged rate against a floor, because category naming is somewhat stochastic while catching the error at all is the real contract.

The dataset (`cases.jsonl`) mixes deterministic synthetic cases with anonymized cases drawn from real traffic (identifiers substituted, prose grammar untouched, labels assigned fresh). No private data.

## How to run

The hook needs a model. Export the LLM settings first, then run:

```sh
# either export the CLAUDE_PLUGIN_OPTION_* names directly, or source a private
# env file that exports LLM_BASE_URL / LLM_API_KEY / LLM_MODEL - run.py maps
# the plain names onto the CLAUDE_PLUGIN_OPTION_* the hook reads:
export LLM_BASE_URL="https://your-endpoint/v1"
export LLM_API_KEY="sk-..."
export LLM_MODEL="openai/gpt-oss-120b"

python3 eval/run.py
```

With no key set, the hook falls back to `claude -p` haiku and the harness tolerates it (slower, lower format compliance - see `docs/requirements.md` section 6).

Prove the non-zero gate path without touching the network:

```sh
python3 eval/run.py --selftest   # feeds fabricated failing results through the real gate; exits 1
```

## Output and exit code

`run.py` prints a per-class summary (silence rates with the offending messages listed, and per-category recall) and ends with `RESULT: PASS` or `RESULT: FAIL`. It **exits non-zero** whenever a gate fails, so CI and the plan's Task 8 can gate on it. Gates:

- silence classes: the per-class false-positive **rate** must not exceed `GRAMMAR_EVAL_MAX_SILENT_FP_RATE` (default `0.25`).
- recall: the aggregate flagged rate must be at least `GRAMMAR_EVAL_MIN_RECALL` (default `0.7`).

Both are environment-overridable for tuning. The silence gate is a rate rather than an absolute zero because the model is nondeterministic (`docs/requirements.md` section 7 measures FP "over several runs") and this harness samples each case once - repeats-per-case is a deferred open question. Consecutive live runs of `gpt-oss-120b` at build time landed the typo-silent class between 20% and 30% FP, straddling the 25% ceiling, so a single run can pass or fail on model noise alone; the ceiling still separates the accepted `gpt-oss-120b` from the rejected `gemini-3.1-flash-lite`, which leaked roughly half its typo cases. Every individual false positive is listed under its class so the maintainer can inspect debatable calls even when the rate stays under the ceiling. The recurring tail on `gpt-oss-120b` is a small set of typo cases the model treats as fixes rather than misspellings - `craete -> create` and `compatrible -> compatible` showed up on every run - plus the odd collocation flag such as `remind about -> remind of`. The prompt is byte-locked to the measured `minimal-prompt.txt`, so this tail is left in place rather than patched.

## Isolation

Every case runs the hook with `GRAMMAR_HOME` pointed at a fresh temp dir (created and removed per case) and `GRAMMAR_HOOK_SYNC=1` so the backgrounded model call is awaited. The eval therefore **never reads or writes the user's real `~/.claude/cc-grammar-coach/history.jsonl`** - otherwise the drill would start teaching the eval dataset. The real state file is byte-identical before and after a full run.
