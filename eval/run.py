#!/usr/bin/env python3
"""Maintainer regression harness for the cc-grammar-coach checker hook.

Drives the shipped hooks/grammar-check.sh against eval/cases.jsonl, one case per invocation, with GRAMMAR_HOOK_SYNC=1 so the backgrounded model call is awaited before the hook returns. Each run gets a fresh GRAMMAR_HOME temp dir, so the eval never touches the user's real ~/.claude/cc-grammar-coach state.

Scoring is per class and never pooled:
  - typo-silent        false-positive rate (a misspelling must NOT be flagged)
  - name/mention-silent false-positive rate (identifiers/paths/quoted mentions must stay silent)
  - recall (per grammar category) whether a known error is flagged, and whether it is flagged with the expected category
  - rephrase-dup       every rephrase logged to history.jsonl must differ structurally from the message with the fixes applied; a near-duplicate means the hook-side filter regressed (issue #9), so the ceiling is zero

Exit code is non-zero when any gate fails (silence classes must stay under a false-positive-rate ceiling; recall must clear a flagged-any floor and a pooled exact-category floor), so CI and the plan's Task 8 can gate.

The model is nondeterministic, so a single sample of each case is noisy: the exit code of one --repeats 1 run is not by itself authoritative. Reproduce a result before trusting it, or raise --repeats so the gate reads a mean over N independent samples per case (each in its own isolated GRAMMAR_HOME).

No jq. Deps: python3, plus whatever the hook itself needs (bash, curl).

Credentials: the hook needs a model. run.py forwards the LLM settings to the hook as CLAUDE_PLUGIN_OPTION_LLM_BASE_URL / _LLM_API_KEY / _LLM_MODEL, read from the environment. It accepts either the CLAUDE_PLUGIN_OPTION_* names or the plain LLM_BASE_URL / LLM_API_KEY / LLM_MODEL names (as exported by a private grammar-llm.env). Nothing is hardcoded. Credentials are required: the hook has no model fallback and exits early without them, so the harness refuses to run rather than measure a hook that silently checks nothing.

Usage:
    python3 eval/run.py             # run the real dataset against the shipped hook
    python3 eval/run.py --repeats 3 # sample each case 3x and gate on the mean
    python3 eval/run.py --selftest  # prove the non-zero gate path, no network
"""

import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

# --- protocol markers (R3): must be byte-identical to the prompt, the hook, and the statusline. Anchored here so Task 8's cross-file byte-identity grep has a copy in this file even though scoring now reads history.jsonl. ---
ARROW = "→"    # -> separates wrong from fix
CHECK = "✔"    # praise / liveness
SPARKLE = "✨"  # rephrase
assert (ARROW, CHECK, SPARKLE) == ("→", "✔", "✨")

# Rephrase-duplication contract (issue #9): the hook drops a ✨ line whose word sequence is >= DUP_RATIO similar to the message with the reported fixes applied. Threshold and normalization must stay identical to the filter in hooks/grammar-check.sh; the harness recomputes them over history.jsonl to catch a filter regression end to end.
DUP_RATIO = 0.9


def norm_words(text):
    return re.findall(r"[a-z0-9']+", text.lower())


def rephrase_similarity(message, fixes, rephrase):
    corrected = message
    for f in fixes:
        corrected = corrected.replace(f.get("wrong", ""), f.get("fix", ""), 1)
    return difflib.SequenceMatcher(None, norm_words(corrected), norm_words(rephrase)).ratio()

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
HOOK = os.path.join(PLUGIN_ROOT, "hooks", "grammar-check.sh")
CASES = os.path.join(HERE, "cases.jsonl")
CATALOG = os.path.join(PLUGIN_ROOT, "config", "categories.txt")


def catalog_slugs():
    return [l.split(":", 1)[0].strip() for l in open(CATALOG, encoding="utf-8") if l.strip()]

PER_CASE_TIMEOUT = 90
MIN_RECALL = float(os.environ.get("GRAMMAR_EVAL_MIN_RECALL", "0.7"))
# The model is nondeterministic (requirements section 7: "FP-rate ... over several runs"), and this harness samples each case once (repeats-per-case is a deferred open question). A per-class silence false-positive *rate* ceiling therefore absorbs single-run noise while still catching a materially worse model - the rejected gemini failed ~55% of typo-silence. Every FP is still listed in the report for the maintainer to inspect.
MAX_SILENT_FP_RATE = float(os.environ.get("GRAMMAR_EVAL_MAX_SILENT_FP_RATE", "0.25"))
# Exact-category recall floor: the fraction of recall samples flagged with their OWN category slug, pooled across all categories. This is the gate against a model that catches every error but files them all under one wrong slug (which would still score 100% on the flagged-any floor below). It is pooled, not per-category, because each category has only 1-3 cases, so a single category can score zero exact hits on one sample by chance and a strict per-category zero-fail would be flaky. The slug definitions in config/categories.txt (issue #3) removed the worst naming overlap (the old catch-all verb-form), but pooling is about per-category sample size, not taxonomy quality, so it stays. Pooling separates a healthy model (~0.9 exact) from mislabel-everything (~0.1) with wide margin; the floor was raised from 0.5 to 0.6 after a --repeats 2 run of gpt-oss-120b on the defined slugs misfiled zero of its 41 flagged samples (exact rate = flagged rate = 93%).
MIN_EXACT_RECALL = float(os.environ.get("GRAMMAR_EVAL_MIN_EXACT_RECALL", "0.6"))


def forward_creds(env):
    """Populate CLAUDE_PLUGIN_OPTION_LLM_* from the environment.

    Prefer the CLAUDE_PLUGIN_OPTION_* names if already set; otherwise map the plain LLM_* names (as a sourced grammar-llm.env exports them).
    """
    pairs = [
        ("CLAUDE_PLUGIN_OPTION_LLM_BASE_URL", "LLM_BASE_URL"),
        ("CLAUDE_PLUGIN_OPTION_LLM_API_KEY", "LLM_API_KEY"),
        ("CLAUDE_PLUGIN_OPTION_LLM_MODEL", "LLM_MODEL"),
    ]
    for opt, plain in pairs:
        if not env.get(opt) and os.environ.get(plain):
            env[opt] = os.environ[plain]


def load_cases(path):
    cases = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as exc:
                sys.exit("cases.jsonl line %d is not valid JSON: %s" % (n, exc))
    return cases


def run_hook(message, case_id, selection=None):
    """Invoke the shipped hook once for one message in a fresh GRAMMAR_HOME.

    Returns (flagged, categories, rephrase_count, dup_rephrases). flagged is whether the isolated history.jsonl recorded any fix (the authoritative signal - the status file is a display subset of the same match, so it adds nothing); categories is the set of category slugs seen; rephrase_count is how many logged lines carried a rephrase, and dup_rephrases lists the ones that are near-duplicates of the fixes reapplied (must be empty - the hook filters them).

    selection="full" enables the whole catalog by writing enabled-categories.txt into the isolated GRAMMAR_HOME, so recall cases for categories outside the default selection can be scored; without it the hook runs on the shipped default selection, which is what the silence gates are calibrated for.
    """
    home = tempfile.mkdtemp(prefix="grammar-eval-")
    try:
        if selection == "full":
            with open(os.path.join(home, "enabled-categories.txt"), "w", encoding="utf-8") as fh:
                fh.write("\n".join(catalog_slugs()) + "\n")
        env = dict(os.environ)
        env["GRAMMAR_HOME"] = home
        env["GRAMMAR_HOOK_SYNC"] = "1"
        env["CLAUDE_PLUGIN_ROOT"] = PLUGIN_ROOT
        forward_creds(env)

        payload = json.dumps({"session_id": case_id, "prompt": message})
        subprocess.run(
            ["bash", HOOK],
            input=payload,
            capture_output=True,
            text=True,
            env=env,
            timeout=PER_CASE_TIMEOUT,
        )

        fixes = []
        rephrase_count = 0
        dup_rephrases = []
        history_path = os.path.join(home, "history.jsonl")
        if os.path.exists(history_path):
            with open(history_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    line_fixes = obj.get("fixes", [])
                    fixes.extend(line_fixes)
                    rephrase = obj.get("rephrase")
                    if rephrase:
                        rephrase_count += 1
                        if rephrase_similarity(obj.get("message", ""), line_fixes, rephrase) >= DUP_RATIO:
                            dup_rephrases.append(rephrase)

        categories = {f.get("category", "") for f in fixes}
        return bool(fixes), categories, rephrase_count, dup_rephrases
    finally:
        shutil.rmtree(home, ignore_errors=True)


def evaluate(results):
    """Aggregate per-class stats over N repeats per case and decide pass/fail.

    results is a list of per-case dicts: {case, runs, flag_count, exact_count} where flag_count is how many of the `runs` samples flagged, and exact_count is how many flagged with the case's own category (recall cases only). Rates are means over samples (sum of flags / sum of runs), so they absorb single-sample noise as `runs` grows. Returns (report_lines, ok).
    """
    typo = [r for r in results if r["case"]["class"] == "typo-silent"]
    name = [r for r in results if r["case"]["class"] == "name-silent"]
    recall = [r for r in results if r["case"]["class"] == "recall"]

    lines = []
    ok = True

    def silence_block(title, group):
        nonlocal ok
        samples = sum(r["runs"] for r in group)
        fp_samples = sum(r["flag_count"] for r in group)
        rate = fp_samples / samples if samples else 0.0
        lines.append("  %-22s FP %d/%d samples  (%.0f%%, ceiling %.0f%%)"
                     % (title, fp_samples, samples, rate * 100, MAX_SILENT_FP_RATE * 100))
        for r in group:
            if r["flag_count"]:
                lines.append("      FP  %-8s [%d/%d runs] %s"
                             % (r["case"]["id"], r["flag_count"], r["runs"], r["case"]["message"]))
        if rate > MAX_SILENT_FP_RATE:
            ok = False
            lines.append("      -> FAIL: %s false-positive rate %.0f%% exceeds ceiling %.0f%%"
                         % (title, rate * 100, MAX_SILENT_FP_RATE * 100))

    lines.append("TYPO-SILENT (a misspelling must not be flagged)")
    silence_block("typo-silent", typo)
    lines.append("")
    lines.append("NAME/MENTION-SILENT (identifiers, paths, quoted mentions stay silent)")
    silence_block("name/mention-silent", name)
    lines.append("")

    lines.append("RECALL (a known grammar error must be flagged, with its category)")
    by_cat = {}
    for r in recall:
        by_cat.setdefault(r["case"]["category"], []).append(r)
    total_flagged = 0
    total_exact = 0
    total_samples = 0
    for cat in sorted(by_cat):
        group = by_cat[cat]
        samples = sum(r["runs"] for r in group)
        flagged = sum(r["flag_count"] for r in group)
        exact = sum(r["exact_count"] for r in group)
        total_flagged += flagged
        total_exact += exact
        total_samples += samples
        lines.append("  %-14s caught %d/%d (exact category)   flagged %d/%d (any)"
                     % (cat, exact, samples, flagged, samples))
        for r in group:
            if r["flag_count"] == 0:
                lines.append("      MISS %-8s %s" % (r["case"]["id"], r["case"]["message"]))
    flag_rate = total_flagged / total_samples if total_samples else 1.0
    exact_rate = total_exact / total_samples if total_samples else 1.0
    lines.append("  %-14s flagged %d/%d (%.0f%%, floor %.0f%%)   exact %d/%d (%.0f%%, floor %.0f%%)"
                 % ("OVERALL", total_flagged, total_samples, flag_rate * 100, MIN_RECALL * 100,
                    total_exact, total_samples, exact_rate * 100, MIN_EXACT_RECALL * 100))
    if flag_rate < MIN_RECALL:
        ok = False
        lines.append("      -> FAIL: flagged recall %.0f%% below floor %.0f%%"
                     % (flag_rate * 100, MIN_RECALL * 100))
    # Exact-category gate (T2): a model that files every error under one slug still clears the flagged-any floor, so pool exact-category recall and floor it. Pooled (not per-category) because single-category naming is stochastic.
    if exact_rate < MIN_EXACT_RECALL:
        ok = False
        lines.append("      -> FAIL: exact-category recall %.0f%% below floor %.0f%% (errors flagged under the wrong category)"
                     % (exact_rate * 100, MIN_EXACT_RECALL * 100))

    lines.append("")
    lines.append("REPHRASE (a logged %s line must not be just the fixes reapplied)" % SPARKLE)
    total_rephrases = sum(r.get("rephrase_count", 0) for r in results)
    dups = [(r["case"]["id"], d) for r in results for d in r.get("dup_rephrases", [])]
    lines.append("  rephrase-dup           %d duplicate(s) among %d logged rephrase(s)  (ceiling 0)"
                 % (len(dups), total_rephrases))
    for cid, dup in dups:
        lines.append("      DUP %-8s %s %s" % (cid, SPARKLE, dup))
    # Zero-tolerance, unlike the rate-based silence gates: the hook filter is deterministic given the logged fixes, so any duplicate that reaches history.jsonl is a code regression, not model noise.
    if dups:
        ok = False
        lines.append("      -> FAIL: a rephrase that only repeats the corrections escaped the hook filter")

    return lines, ok


def run_selftest():
    """Prove the non-zero gate path deterministically, without the model.

    Feeds fabricated results (a silence false positive and a recall miss) through the real evaluate() gate and confirms it fails.
    """
    print("SELFTEST: running the gate on fabricated failing results (no network)\n")
    fake = [
        {"case": {"id": "st-typo", "class": "typo-silent", "message": "planted typo FP"},
         "runs": 1, "flag_count": 1, "exact_count": 0},
        {"case": {"id": "st-name", "class": "name-silent", "message": "clean mention"},
         "runs": 1, "flag_count": 0, "exact_count": 0},
        {"case": {"id": "st-recall", "class": "recall", "category": "tense", "message": "planted miss"},
         "runs": 1, "flag_count": 0, "exact_count": 0},
    ]
    lines, ok = evaluate(fake)
    print("\n".join(lines))
    print()
    if ok:
        print("SELFTEST BROKEN: fabricated failures did not trip the gate")
        return 2

    print("SELFTEST: rephrase-dup gate alone must also fail, with every other class healthy\n")
    fake_dup = [
        {"case": {"id": "st-reph", "class": "recall", "category": "tense", "message": "planted dup"},
         "runs": 1, "flag_count": 1, "exact_count": 1,
         "rephrase_count": 1, "dup_rephrases": ["planted duplicate rephrase"]},
    ]
    dup_lines, dup_ok = evaluate(fake_dup)
    print("\n".join(dup_lines))
    print()
    if dup_ok:
        print("SELFTEST BROKEN: a planted duplicate rephrase did not trip the gate")
        return 2
    if rephrase_similarity("yesterday I fix bug", [{"wrong": "fix", "fix": "fixed"}], "Yesterday I fixed bug.") < DUP_RATIO:
        print("SELFTEST BROKEN: a fixes-reapplied rephrase scored below DUP_RATIO")
        return 2
    if rephrase_similarity("yesterday I fix bug", [{"wrong": "fix", "fix": "fixed"}], "The bug got fixed yesterday, finally.") >= DUP_RATIO:
        print("SELFTEST BROKEN: a restructured rephrase scored above DUP_RATIO")
        return 2
    print("SELFTEST OK: gate returned failure as expected; exiting non-zero")
    return 1


def parse_repeats(argv):
    repeats = 1
    if "--repeats" in argv:
        i = argv.index("--repeats")
        try:
            repeats = int(argv[i + 1])
        except (IndexError, ValueError):
            sys.exit("--repeats needs a positive integer, e.g. --repeats 3")
        if repeats < 1:
            sys.exit("--repeats must be >= 1")
    return repeats


def main():
    if "--selftest" in sys.argv[1:]:
        return run_selftest()

    if not os.path.exists(HOOK):
        sys.exit("hook not found: %s" % HOOK)

    repeats = parse_repeats(sys.argv[1:])
    cases = load_cases(CASES)
    have_key = bool(os.environ.get("CLAUDE_PLUGIN_OPTION_LLM_API_KEY") or os.environ.get("LLM_API_KEY"))
    have_url = bool(os.environ.get("CLAUDE_PLUGIN_OPTION_LLM_BASE_URL") or os.environ.get("LLM_BASE_URL"))
    if not (have_key and have_url):
        sys.exit("LLM credentials required: export LLM_BASE_URL and LLM_API_KEY (or the CLAUDE_PLUGIN_OPTION_* names) - the hook has no model fallback and exits early without them")
    print("cc-grammar-coach eval: %d cases x %d repeat(s) against %s" % (len(cases), repeats, HOOK))
    if repeats == 1:
        print("note: single sample per case - the model is nondeterministic; reproduce before trusting the exit code")
    print()

    results = []
    for i, case in enumerate(cases, 1):
        want = case.get("category")
        flag_count = 0
        exact_count = 0
        rephrase_count = 0
        dup_rephrases = []
        seen = set()
        for _ in range(repeats):
            flagged, categories, rephrases, dups = run_hook(case["message"], case["id"], case.get("selection"))
            if flagged:
                flag_count += 1
            if want and want in categories:
                exact_count += 1
            rephrase_count += rephrases
            dup_rephrases.extend(dups)
            seen |= categories
        results.append({"case": case, "runs": repeats,
                        "flag_count": flag_count, "exact_count": exact_count,
                        "rephrase_count": rephrase_count, "dup_rephrases": dup_rephrases})
        mark = "flag" if flag_count else "silent"
        suffix = "  (%d/%d flagged)" % (flag_count, repeats) if repeats > 1 else ""
        print("  [%2d/%d] %-8s %-8s %s%s" % (i, len(cases), case["class"][:8], mark, case["id"], suffix))

    print()
    lines, ok = evaluate(results)
    print("\n".join(lines))
    print()
    print("RESULT: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
