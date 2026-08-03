#!/usr/bin/env python3
"""Maintainer regression harness for the cc-grammar-coach checker hook.

Drives the shipped hooks/grammar-check.sh against eval/cases.jsonl, one case per invocation, with GRAMMAR_HOOK_SYNC=1 so the backgrounded model call is awaited before the hook returns. Each run gets a fresh GRAMMAR_HOME temp dir, so the eval never touches the user's real ~/.claude/cc-grammar-coach state.

Scoring is per class and never pooled:
  - typo-silent        false-positive rate (a misspelling must NOT be flagged)
  - name/mention-silent false-positive rate (identifiers/paths/quoted mentions must stay silent)
  - recall (per grammar category) whether a known error is flagged, and whether it is flagged with the expected category
  - rephrase-dup       every rephrase logged to history.jsonl must differ structurally from the message with the fixes applied; a near-duplicate means the hook-side filter regressed (issue #9), so the ceiling is zero
  - rephrase-recall    an awkward but grammatically correct message must receive a standalone rephrase (issue #21); gated by a floor on the rate of samples carrying one
  - natural-silent     a clean, natural message must receive praise only - no fixes AND no rephrase; scored as a false-positive rate over both signals
  - silent-rephrase    the typo/name silence classes must not acquire rephrases now that the model may rephrase without error lines; their rephrase rate has its own ceiling
  - praise-generic     every ✔ line written in the run must be anchored to its own message (issue #25); a stock verdict or a phrase reused across two different messages is scored generic, and the generic rate has a ceiling
  - praise-unlogged    a displayed compliment must also reach history.jsonl as a praise entry, so the drill can count what the user gets right; deterministic given the model output, so the ceiling is zero

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


# Praise personalization (issue #25): the praise line used to converge on a handful of stock verdicts that carried no information about the message. Two mechanical signals stand in for "personalized", both computed over the ✔ lines the hook wrote into the isolated status files: a compliment equal to one of these stock verdicts (the ones prompts/checker.txt now bans, plus the fallback the hook writes when the model returns nothing usable), and a compliment reused across two different messages - a phrase that fits two messages is by definition not anchored to either.
STOCK_PRAISE = {
    "looks good", "clear and concise", "clean and natural", "clear and natural",
    "clear and correct", "clear and polite", "well phrased", "nicely phrased",
    "good english", "perfect english", "nice message", "no errors",
}


def norm_words(text):
    return re.findall(r"[a-z0-9']+", text.lower())


def norm_praise(text):
    return " ".join(norm_words(text))


# A praise line is a quoted fragment plus a label. The label is the half that can teach: "correct definite article usage" only repeats the bracket tag the error lines already print, while "definite because you named it above" is a rule the user can apply next time. Strip the quotes and a label that is nothing but "correct <category words>" is the degenerate form; matched over the run, it is the metric that says whether the praise explains anything.
PRAISE_QUOTE = re.compile(r'["‘’“”\'](.+?)["‘’“”\']')
CATEGORY_LABEL = re.compile(r"^(correct|proper|good|nice|right)\b[\w\s‑-]*$", re.I)


def praise_label(text):
    return PRAISE_QUOTE.sub("", text).strip(" -.–—").strip()


def is_category_label(text):
    return bool(CATEGORY_LABEL.match(praise_label(text)))


def apply_fixes(message, fixes):
    corrected = message
    for f in fixes:
        wrong = f.get("wrong", "")
        if not wrong:
            continue
        corrected = re.sub(r"(?<!\w)" + re.escape(wrong) + r"(?!\w)", lambda m, _f=f: _f.get("fix", ""), corrected, count=1)
    return corrected


def rephrase_similarity(message, fixes, rephrase):
    return difflib.SequenceMatcher(None, norm_words(apply_fixes(message, fixes)), norm_words(rephrase)).ratio()

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
# Standalone-rephrase floor (issue #21): live sampling of gpt-oss-120b on the three fixture patterns landed 5/6 to 6/6, but each pattern rides on model mood, so the floor starts permissive; raise it once more fixtures accumulate.
MIN_REPHRASE_RECALL = float(os.environ.get("GRAMMAR_EVAL_MIN_REPHRASE_RECALL", "0.5"))
MAX_SILENT_REPHRASE_RATE = float(os.environ.get("GRAMMAR_EVAL_MAX_SILENT_REPHRASE_RATE", "0.25"))
# Generic-praise ceiling (issue #25). Baseline sampling of gpt-oss-120b on the pre-#25 prompt scored ~100% generic (20 live samples drew on six stock verdicts, "Clean and natural." alone taking half of them), so any ceiling below 1.0 separates the old prompt from the new one. It sits at the same 0.25 as the silence ceilings because the residue is the same kind of noise: two unrelated messages can honestly earn the same construction praise ("question inversion"), and that collision costs both samples.
MAX_PRAISE_GENERIC_RATE = float(os.environ.get("GRAMMAR_EVAL_MAX_PRAISE_GENERIC_RATE", "0.25"))
# Category-label ceiling: the share of praise lines whose label only names the category instead of stating the rule. A matched A/B over the same 34 messages put the prompt before the rule-teaching wording at 74% and after it at 26%, so 0.5 separates them with margin on both sides. It is deliberately permissive rather than tight: a three-word imperative may genuinely have no rule worth teaching, and forcing one would invite invention.
MAX_PRAISE_CATEGORY_RATE = float(os.environ.get("GRAMMAR_EVAL_MAX_PRAISE_CATEGORY_RATE", "0.5"))


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

    Returns (flagged, categories, rephrase_count, dup_rephrases, praise, praise_unlogged). flagged is whether the isolated history.jsonl recorded any fix (the authoritative signal for fixes - history is the file the drill learns from); categories is the set of category slugs seen; rephrase_count is how many logged lines carried a rephrase, and dup_rephrases lists the ones that are near-duplicates of the fixes reapplied (must be empty - the hook filters them). praise is the text after the ✔ marker in the isolated status file, or None when the run produced no praise line; it is read from the status file rather than the logged praise entry because the status file is what the user reads, so scoring it covers the display path including the Looks good substitution.

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
        logged_praise = []
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
                    if obj.get("praise"):
                        logged_praise.append(obj["praise"])

        praise = None
        status_path = os.path.join(home, "status", case_id)
        if os.path.exists(status_path):
            for line in open(status_path, encoding="utf-8"):
                if CHECK in line:
                    praise = line[line.find(CHECK) + 1:].strip()
                    break

        # The displayed compliment and the logged one come from the same branch of the hook, so they must agree exactly; a drift means a praised message left no trace for the drill to count, which no other gate can see.
        praise_unlogged = praise is not None and logged_praise[-1:] != [praise]

        categories = {f.get("category", "") for f in fixes}
        return bool(fixes), categories, rephrase_count, dup_rephrases, praise, praise_unlogged
    finally:
        shutil.rmtree(home, ignore_errors=True)


def evaluate(results):
    """Aggregate per-class stats over N repeats per case and decide pass/fail.

    results is a list of per-case dicts: {case, runs, flag_count, exact_count} where flag_count is how many of the `runs` samples flagged, and exact_count is how many flagged with the case's own category (recall cases only); praises holds the ✔ texts the case's samples produced. Rates are means over samples (sum of flags / sum of runs), so they absorb single-sample noise as `runs` grows. Returns (report_lines, ok).
    """
    typo = [r for r in results if r["case"]["class"] == "typo-silent"]
    name = [r for r in results if r["case"]["class"] == "name-silent"]
    recall = [r for r in results if r["case"]["class"] == "recall"]
    natural = [r for r in results if r["case"]["class"] == "natural-silent"]
    reph_recall = [r for r in results if r["case"]["class"] == "rephrase-recall"]

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

    lines.append("NATURAL-SILENT (a clean natural message gets praise only - no fixes, no rephrase)")
    nat_samples = sum(r["runs"] for r in natural)
    nat_noisy = sum(r.get("noisy_count", 0) for r in natural)
    nat_rate = nat_noisy / nat_samples if nat_samples else 0.0
    lines.append("  natural-silent         FP %d/%d samples  (%.0f%%, ceiling %.0f%%)"
                 % (nat_noisy, nat_samples, nat_rate * 100, MAX_SILENT_FP_RATE * 100))
    for r in natural:
        if r.get("noisy_count"):
            lines.append("      FP  %-8s [%d/%d runs] %s"
                         % (r["case"]["id"], r["noisy_count"], r["runs"], r["case"]["message"]))
    if nat_rate > MAX_SILENT_FP_RATE:
        ok = False
        lines.append("      -> FAIL: natural-silent noise rate %.0f%% exceeds ceiling %.0f%%"
                     % (nat_rate * 100, MAX_SILENT_FP_RATE * 100))
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

    rr_samples = sum(r["runs"] for r in reph_recall)
    rr_hits = sum(r.get("rephrase_count", 0) for r in reph_recall)
    rr_rate = rr_hits / rr_samples if rr_samples else 1.0
    lines.append("  rephrase-recall        rephrased %d/%d samples  (%.0f%%, floor %.0f%%)"
                 % (rr_hits, rr_samples, rr_rate * 100, MIN_REPHRASE_RECALL * 100))
    for r in reph_recall:
        missed = r["runs"] - r.get("rephrase_count", 0)
        if missed:
            lines.append("      MISS %-8s [%d/%d runs] %s"
                         % (r["case"]["id"], missed, r["runs"], r["case"]["message"]))
    if rr_rate < MIN_REPHRASE_RECALL:
        ok = False
        lines.append("      -> FAIL: standalone-rephrase recall %.0f%% below floor %.0f%% (awkward but correct messages are being praised)"
                     % (rr_rate * 100, MIN_REPHRASE_RECALL * 100))

    sil = typo + name
    sil_samples = sum(r["runs"] for r in sil)
    sil_reph = sum(r.get("rephrase_count", 0) for r in sil)
    sil_rate = sil_reph / sil_samples if sil_samples else 0.0
    lines.append("  silent-rephrase        %d/%d silence samples carried a rephrase  (%.0f%%, ceiling %.0f%%)"
                 % (sil_reph, sil_samples, sil_rate * 100, MAX_SILENT_REPHRASE_RATE * 100))
    for r in sil:
        if r.get("rephrase_count"):
            lines.append("      REPH %-8s [%d/%d runs] %s"
                         % (r["case"]["id"], r["rephrase_count"], r["runs"], r["case"]["message"]))
    if sil_rate > MAX_SILENT_REPHRASE_RATE:
        ok = False
        lines.append("      -> FAIL: silence-class rephrase rate %.0f%% exceeds ceiling %.0f%% (typo/name messages are being rewritten)"
                     % (sil_rate * 100, MAX_SILENT_REPHRASE_RATE * 100))

    lines.append("")
    lines.append("PRAISE (a %s line must name something in ITS OWN message)" % CHECK)
    # Pooled over every class, not just natural-silent: a typo or name case that stays silent is praised too, and its praise must be as anchored as any other. A case contributes each of its samples, so a stock verdict repeated across repeats is counted once per sample, the same way the other rates count noise.
    praise_samples = [(r["case"]["id"], p) for r in results for p in r.get("praises", [])]
    owners = {}
    for cid, text in praise_samples:
        owners.setdefault(norm_praise(text), set()).add(cid)
    generic = []
    for cid, text in praise_samples:
        key = norm_praise(text)
        if key in STOCK_PRAISE:
            generic.append((cid, text, "stock verdict"))
        elif len(owners[key]) > 1:
            generic.append((cid, text, "reused on %d messages" % len(owners[key])))
    praise_rate = len(generic) / len(praise_samples) if praise_samples else 0.0
    lines.append("  praise-generic         %d/%d praise lines generic  (%.0f%%, ceiling %.0f%%)"
                 % (len(generic), len(praise_samples), praise_rate * 100, MAX_PRAISE_GENERIC_RATE * 100))
    for cid, text, why in generic:
        lines.append("      GEN %-8s %s %s  [%s]" % (cid, CHECK, text, why))
    if praise_rate > MAX_PRAISE_GENERIC_RATE:
        ok = False
        lines.append("      -> FAIL: generic-praise rate %.0f%% exceeds ceiling %.0f%% (the praise line is boilerplate, not feedback about the message)"
                     % (praise_rate * 100, MAX_PRAISE_GENERIC_RATE * 100))

    category_labels = [(cid, text) for cid, text in praise_samples if is_category_label(text)]
    cat_rate = len(category_labels) / len(praise_samples) if praise_samples else 0.0
    lines.append("  praise-category-label  %d/%d labels only name the category  (%.0f%%, ceiling %.0f%%)"
                 % (len(category_labels), len(praise_samples), cat_rate * 100, MAX_PRAISE_CATEGORY_RATE * 100))
    for cid, text in category_labels:
        lines.append("      CAT %-8s %s %s" % (cid, CHECK, text))
    if cat_rate > MAX_PRAISE_CATEGORY_RATE:
        ok = False
        lines.append("      -> FAIL: %.0f%% of praise labels only name the category (the line repeats the bracket tag instead of teaching the rule)"
                     % (cat_rate * 100))

    # Zero-tolerance like rephrase-dup, and for the same reason: given the model output, the hook writes the status file and the log line in one branch, so a displayed compliment missing from history.jsonl is a code regression rather than model noise.
    unlogged = [(r["case"]["id"], r["praise_unlogged"]) for r in results if r.get("praise_unlogged")]
    lines.append("  praise-unlogged        %d praise line(s) displayed but not logged  (ceiling 0)"
                 % sum(n for _cid, n in unlogged))
    for cid, n in unlogged:
        lines.append("      LOST %-8s [%d sample(s)]" % (cid, n))
    if unlogged:
        ok = False
        lines.append("      -> FAIL: a compliment reached the statusline without reaching history.jsonl (the drill cannot count what the user gets right)")

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
    if apply_fixes("I tried your script this morning and is working fine", [{"wrong": "is", "fix": "it is"}]) != "I tried your script this morning and it is working fine":
        print("SELFTEST BROKEN: fix application must substitute whole words, not substrings")
        return 2

    print("SELFTEST: the issue-21 gates (rephrase-recall, natural-silent, silent-rephrase) must each fail on planted results\n")
    fake_21 = [
        {"case": {"id": "st-rr", "class": "rephrase-recall", "message": "awkward but praised"},
         "runs": 1, "flag_count": 0, "exact_count": 0,
         "rephrase_count": 0, "dup_rephrases": [], "noisy_count": 0},
        {"case": {"id": "st-nat", "class": "natural-silent", "message": "clean but rephrased"},
         "runs": 1, "flag_count": 0, "exact_count": 0,
         "rephrase_count": 1, "dup_rephrases": [], "noisy_count": 1},
        {"case": {"id": "st-sil", "class": "typo-silent", "message": "typo message got a rephrase"},
         "runs": 1, "flag_count": 0, "exact_count": 0,
         "rephrase_count": 1, "dup_rephrases": [], "noisy_count": 1},
    ]
    lines_21, ok_21 = evaluate(fake_21)
    print("\n".join(lines_21))
    print()
    if ok_21:
        print("SELFTEST BROKEN: planted issue-21 failures did not trip the gate")
        return 2
    expected = ["standalone-rephrase recall", "natural-silent noise rate", "silence-class rephrase rate"]
    missing = [e for e in expected if not any(e in l for l in lines_21)]
    if missing:
        print("SELFTEST BROKEN: gates did not fire individually: %s" % ", ".join(missing))
        return 2

    print("SELFTEST: the issue-25 praise gate must fail on stock and reused compliments, and pass on anchored ones\n")
    fake_praise = [
        {"case": {"id": "st-p1", "class": "natural-silent", "message": "clean one"},
         "runs": 1, "flag_count": 0, "exact_count": 0, "noisy_count": 0, "praises": ["Clear and concise."]},
        {"case": {"id": "st-p2", "class": "natural-silent", "message": "clean two"},
         "runs": 1, "flag_count": 0, "exact_count": 0, "noisy_count": 0, "praises": ["Question inversion, done right."]},
        {"case": {"id": "st-p3", "class": "natural-silent", "message": "clean three"},
         "runs": 1, "flag_count": 0, "exact_count": 0, "noisy_count": 0, "praises": ["Question inversion, done right."]},
    ]
    praise_lines, praise_ok = evaluate(fake_praise)
    print("\n".join(praise_lines))
    print()
    if praise_ok:
        print("SELFTEST BROKEN: a stock verdict and a compliment reused on two messages did not trip the gate")
        return 2
    if not any("generic-praise rate" in l for l in praise_lines):
        print("SELFTEST BROKEN: the praise gate did not fire on its own line")
        return 2
    anchored = [dict(r, praises=["%s praise %d" % (r["case"]["id"], i)])
                for i, r in enumerate(fake_praise)]
    _, anchored_ok = evaluate(anchored)
    if not anchored_ok:
        print("SELFTEST BROKEN: distinct message-anchored compliments must not trip any gate")
        return 2

    print("SELFTEST: labels that only name the category must fail, rule-teaching labels must pass\n")
    fake_cat = [{"case": {"id": "st-c%d" % i, "class": "natural-silent", "message": "clean %d" % i},
                 "runs": 1, "flag_count": 0, "exact_count": 0, "noisy_count": 0,
                 "praises": ['"fragment %d" - correct definite article usage %d' % (i, i)]}
                for i in range(3)]
    cat_lines, cat_ok = evaluate(fake_cat)
    print("\n".join(cat_lines))
    print()
    if cat_ok or not any("only name the category" in l and "FAIL" in l for l in cat_lines):
        print("SELFTEST BROKEN: category-only labels did not trip the gate")
        return 2
    rules = [dict(r, praises=['"fragment %d" - definite because you named it above %d' % (i, i)])
             for i, r in enumerate(fake_cat)]
    _, rules_ok = evaluate(rules)
    if not rules_ok:
        print("SELFTEST BROKEN: labels stating a rule must not trip any gate")
        return 2

    print("SELFTEST: a compliment shown but never logged must fail on its own\n")
    lost = [dict(anchored[0], praise_unlogged=1)]
    lost_lines, lost_ok = evaluate(lost)
    print("\n".join(lost_lines))
    print()
    if lost_ok or not any("praise-unlogged" in l and "ceiling 0" in l for l in lost_lines):
        print("SELFTEST BROKEN: an unlogged praise line did not trip the gate")
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
        praises = []
        praise_unlogged = 0
        seen = set()
        noisy_count = 0
        for _ in range(repeats):
            flagged, categories, rephrases, dups, praise, unlogged = run_hook(case["message"], case["id"], case.get("selection"))
            if flagged:
                flag_count += 1
            if flagged or rephrases:
                noisy_count += 1
            if want and want in categories:
                exact_count += 1
            rephrase_count += rephrases
            dup_rephrases.extend(dups)
            if praise:
                praises.append(praise)
            if unlogged:
                praise_unlogged += 1
            seen |= categories
        results.append({"case": case, "runs": repeats,
                        "flag_count": flag_count, "exact_count": exact_count,
                        "rephrase_count": rephrase_count, "dup_rephrases": dup_rephrases,
                        "praises": praises, "praise_unlogged": praise_unlogged,
                        "noisy_count": noisy_count})
        mark = "flag" if flag_count else ("reph" if rephrase_count else "silent")
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
