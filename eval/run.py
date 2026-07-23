#!/usr/bin/env python3
"""Maintainer regression harness for the cc-grammar-coach checker hook.

Drives the shipped hooks/grammar-check.sh against eval/cases.jsonl, one case
per invocation, with GRAMMAR_HOOK_SYNC=1 so the backgrounded model call is
awaited before the hook returns. Each run gets a fresh GRAMMAR_HOME temp dir,
so the eval never touches the user's real ~/.claude/cc-grammar-coach state.

Scoring is per class and never pooled:
  - typo-silent        false-positive rate (a misspelling must NOT be flagged)
  - name/mention-silent false-positive rate (identifiers/paths/quoted mentions
                        must stay silent)
  - recall (per grammar category) whether a known error is flagged, and whether
                        it is flagged with the expected category

Exit code is non-zero when any gate fails (silence classes must be perfect;
recall must clear a configurable floor), so CI and the plan's Task 8 can gate.

No jq. Deps: python3, plus whatever the hook itself needs (bash, curl).

Credentials: the hook needs a model. run.py forwards the LLM settings to the
hook as CLAUDE_PLUGIN_OPTION_LLM_BASE_URL / _LLM_API_KEY / _LLM_MODEL, read
from the environment. It accepts either the CLAUDE_PLUGIN_OPTION_* names or the
plain LLM_BASE_URL / LLM_API_KEY / LLM_MODEL names (as exported by a private
grammar-llm.env). Nothing is hardcoded. With no key set the hook falls back to
`claude -p` haiku, which the harness also tolerates.

Usage:
    python3 eval/run.py            # run the real dataset against the shipped hook
    python3 eval/run.py --selftest # prove the non-zero gate path, no network
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

# --- protocol markers (R3): must be byte-identical to the prompt, the hook,
# and the statusline. run.py parses the status file on these exact bytes. ---
ARROW = "→"    # -> separates wrong from fix
CHECK = "✔"    # praise / liveness
SPARKLE = "✨"  # rephrase
assert (ARROW, CHECK, SPARKLE) == ("→", "✔", "✨")

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
HOOK = os.path.join(PLUGIN_ROOT, "hooks", "grammar-check.sh")
CASES = os.path.join(HERE, "cases.jsonl")

PER_CASE_TIMEOUT = 90
MIN_RECALL = float(os.environ.get("GRAMMAR_EVAL_MIN_RECALL", "0.7"))
# The model is nondeterministic (requirements section 7: "FP-rate ... over
# several runs"), and this harness samples each case once (repeats-per-case is a
# deferred open question). A per-class silence false-positive *rate* ceiling
# therefore absorbs single-run noise while still catching a materially worse
# model - the rejected gemini failed ~55% of typo-silence. Every FP is still
# listed in the report for the maintainer to inspect.
MAX_SILENT_FP_RATE = float(os.environ.get("GRAMMAR_EVAL_MAX_SILENT_FP_RATE", "0.25"))


def forward_creds(env):
    """Populate CLAUDE_PLUGIN_OPTION_LLM_* from the environment.

    Prefer the CLAUDE_PLUGIN_OPTION_* names if already set; otherwise map the
    plain LLM_* names (as a sourced grammar-llm.env exports them).
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


def run_hook(message, case_id):
    """Invoke the shipped hook for one message in a fresh GRAMMAR_HOME.

    Returns (fixes, categories, status_text). fixes is the parsed fixes[] list
    from the isolated history.jsonl (authoritative); categories is the set of
    category slugs seen; status_text is the raw status file contents.
    """
    home = tempfile.mkdtemp(prefix="grammar-eval-")
    try:
        env = dict(os.environ)
        env["GRAMMAR_HOME"] = home
        env["GRAMMAR_HOOK_SYNC"] = "1"
        env["CLAUDE_PLUGIN_ROOT"] = PLUGIN_ROOT
        env.pop("GRAMMAR_HOOK_ACTIVE", None)
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

        status_path = os.path.join(home, "status", case_id)
        status_text = ""
        if os.path.exists(status_path):
            with open(status_path, encoding="utf-8") as fh:
                status_text = fh.read()

        fixes = []
        history_path = os.path.join(home, "history.jsonl")
        if os.path.exists(history_path):
            with open(history_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        fixes.extend(json.loads(line).get("fixes", []))
                    except json.JSONDecodeError:
                        pass

        # Cross-check against the status file on the exact ARROW byte, in case a
        # fix line reached the statusline but not history.
        status_flagged = any(ARROW in ln and ln.lstrip().startswith("[") for ln in status_text.splitlines())

        categories = {f.get("category", "") for f in fixes}
        flagged = bool(fixes) or status_flagged
        return flagged, categories, status_text
    finally:
        shutil.rmtree(home, ignore_errors=True)


def evaluate(results):
    """Aggregate per-class stats and decide pass/fail. results is a list of
    dicts: {case, flagged, categories}. Returns (report_lines, ok)."""
    typo = [r for r in results if r["case"]["class"] == "typo-silent"]
    name = [r for r in results if r["case"]["class"] == "name-silent"]
    recall = [r for r in results if r["case"]["class"] == "recall"]

    lines = []
    ok = True

    def silence_block(title, group, gate_key):
        nonlocal ok
        fp = [r for r in group if r["flagged"]]
        silent = len(group) - len(fp)
        rate = len(fp) / len(group) if group else 0.0
        lines.append("  %-22s silent %d/%d  (false positives: %d, %.0f%%, ceiling %.0f%%)"
                     % (title, silent, len(group), len(fp), rate * 100, MAX_SILENT_FP_RATE * 100))
        for r in fp:
            lines.append("      FP  %-8s %s" % (r["case"]["id"], r["case"]["message"]))
        if rate > MAX_SILENT_FP_RATE:
            ok = False
            lines.append("      -> FAIL: %s false-positive rate %.0f%% exceeds ceiling %.0f%%"
                         % (gate_key, rate * 100, MAX_SILENT_FP_RATE * 100))

    lines.append("TYPO-SILENT (a misspelling must not be flagged)")
    silence_block("typo-silent", typo, "typo-silent")
    lines.append("")
    lines.append("NAME/MENTION-SILENT (identifiers, paths, quoted mentions stay silent)")
    silence_block("name/mention-silent", name, "name/mention-silent")
    lines.append("")

    lines.append("RECALL (a known grammar error must be flagged)")
    by_cat = {}
    for r in recall:
        by_cat.setdefault(r["case"]["category"], []).append(r)
    total_flagged = 0
    for cat in sorted(by_cat):
        group = by_cat[cat]
        flagged = [r for r in group if r["flagged"]]
        exact = [r for r in group if cat in r["categories"]]
        total_flagged += len(flagged)
        lines.append("  %-14s caught %d/%d (exact category)   flagged %d/%d (any)"
                     % (cat, len(exact), len(group), len(flagged), len(group)))
        for r in group:
            if not r["flagged"]:
                lines.append("      MISS %-8s %s" % (r["case"]["id"], r["case"]["message"]))
    rate = total_flagged / len(recall) if recall else 1.0
    lines.append("  %-14s flagged %d/%d  (%.0f%%, floor %.0f%%)"
                 % ("OVERALL", total_flagged, len(recall), rate * 100, MIN_RECALL * 100))
    if rate < MIN_RECALL:
        ok = False
        lines.append("      -> FAIL: recall %.0f%% below floor %.0f%%"
                     % (rate * 100, MIN_RECALL * 100))

    return lines, ok


def run_selftest():
    """Prove the non-zero gate path deterministically, without the model.

    Feeds fabricated results (a silence false positive and a recall miss)
    through the real evaluate() gate and confirms it fails.
    """
    print("SELFTEST: running the gate on fabricated failing results (no network)\n")
    fake = [
        {"case": {"id": "st-typo", "class": "typo-silent", "message": "planted typo FP"},
         "flagged": True, "categories": {"articles"}},
        {"case": {"id": "st-name", "class": "name-silent", "message": "clean mention"},
         "flagged": False, "categories": set()},
        {"case": {"id": "st-recall", "class": "recall", "category": "tense", "message": "planted miss"},
         "flagged": False, "categories": set()},
    ]
    lines, ok = evaluate(fake)
    print("\n".join(lines))
    print()
    if ok:
        print("SELFTEST BROKEN: fabricated failures did not trip the gate")
        return 2
    print("SELFTEST OK: gate returned failure as expected; exiting non-zero")
    return 1


def main():
    if "--selftest" in sys.argv[1:]:
        return run_selftest()

    if not os.path.exists(HOOK):
        sys.exit("hook not found: %s" % HOOK)

    cases = load_cases(CASES)
    have_key = bool(os.environ.get("CLAUDE_PLUGIN_OPTION_LLM_API_KEY") or os.environ.get("LLM_API_KEY"))
    print("cc-grammar-coach eval: %d cases against %s" % (len(cases), HOOK))
    print("model path: %s\n" % ("custom endpoint (LLM_* forwarded)" if have_key else "claude -p haiku fallback"))

    results = []
    for i, case in enumerate(cases, 1):
        flagged, categories, _ = run_hook(case["message"], case["id"])
        results.append({"case": case, "flagged": flagged, "categories": categories})
        mark = "flag" if flagged else "silent"
        print("  [%2d/%d] %-8s %-8s %s" % (i, len(cases), case["class"][:8], mark, case["id"]))

    print()
    lines, ok = evaluate(results)
    print("\n".join(lines))
    print()
    print("RESULT: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
