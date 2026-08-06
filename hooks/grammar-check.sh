#!/usr/bin/env bash
# UserPromptSubmit checker. Reviews each English message out of band, logs mistakes to history.jsonl, and writes statusline feedback.
# Writes nothing to stdout and never blocks the turn: the model call is backgrounded and the hook returns immediately (unless GRAMMAR_HOOK_SYNC).

if [ -n "$CLAUDE_PLUGIN_ROOT" ]; then
  PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
  SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
  PLUGIN_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
fi

GRAMMAR_HOME="${GRAMMAR_HOME:-$HOME/.claude/cc-grammar-coach}"
STATUS_DIR="$GRAMMAR_HOME/status"
HISTORY_FILE="$GRAMMAR_HOME/history.jsonl"
mkdir -p "$STATUS_DIR"

# Keep stable copies of the statusline scripts in GRAMMAR_HOME. The statusline runs outside the plugin sandbox and the versioned plugin-cache path changes on every update, so the wiring installed by /cc-grammar-coach:configure install-statusline points here instead and plugin updates propagate without re-wiring.
for _f in render-grammar.sh grammar-statusline.sh; do
  if ! cmp -s "$PLUGIN_ROOT/statusline/$_f" "$GRAMMAR_HOME/$_f" 2>/dev/null; then
    cp "$PLUGIN_ROOT/statusline/$_f" "$GRAMMAR_HOME/$_f" && chmod +x "$GRAMMAR_HOME/$_f"
  fi
done

MIN_CHARS=15
MAX_CHARS=500

REPHRASE="${CLAUDE_PLUGIN_OPTION_REPHRASE:-true}"
LLM_BASE_URL="${CLAUDE_PLUGIN_OPTION_LLM_BASE_URL:-}"
LLM_MODEL="${CLAUDE_PLUGIN_OPTION_LLM_MODEL:-openai/gpt-oss-120b}"
LLM_API_KEY="${CLAUDE_PLUGIN_OPTION_LLM_API_KEY:-}"

# The checker needs a configured endpoint; without credentials there is nothing to call, so stop after the statusline-copy refresh above.
{ [ -n "$LLM_BASE_URL" ] && [ -n "$LLM_API_KEY" ]; } || exit 0

# --- parse stdin (one python pass: session_id on line 1, then the raw prompt) ---
INPUT=$(cat)
{
  IFS= read -r SID
  PROMPT=$(cat)
} < <(printf '%s' "$INPUT" | python3 -c 'import sys, json
d = json.load(sys.stdin)
sys.stdout.write((d.get("session_id") or "default") + "\n" + (d.get("prompt") or ""))' 2>/dev/null)
# Harden the session id before it becomes a path component: a value carrying a slash or ".." could escape status/. Real ids are Claude Code UUIDs; anything else falls back to "default".
case "$SID" in ''|*/*|*..*) SID=default ;; esac

STATUS_FILE="$STATUS_DIR/$SID"
: > "$STATUS_FILE"
find "$STATUS_DIR" -type f -mtime +1 -delete 2>/dev/null

# A drill in progress silences the checker. Quiz answers are exercise sentences aimed at a rule the user is being taught, not organic writing, and logging them would both distort history.jsonl and feed the drill its own output - skills/drill ranks topics over the same fixes[] it would be writing. The flag is created and removed by the drill and learn skills; the staleness cap is what keeps a session abandoned mid-quiz from muting the checker forever, and 60 minutes is well past any drill and well short of a day of unchecked writing.
DRILL_FLAG="$GRAMMAR_HOME/drill-active"
if [ -e "$DRILL_FLAG" ]; then
  if [ -n "$(find "$DRILL_FLAG" -mmin -60 2>/dev/null)" ]; then
    exit 0
  fi
  rm -f "$DRILL_FLAG"
fi

[ -z "$PROMPT" ] && exit 0
case "$PROMPT" in /*) exit 0 ;; esac
[ "${#PROMPT}" -lt "$MIN_CHARS" ] && exit 0
[ "${#PROMPT}" -gt "$MAX_CHARS" ] && exit 0
case "$PROMPT" in
  '<'*) exit 0 ;;
  *'<task-notification'*|*'<local-command'*|*'<command-name>'*|*'<system-reminder'*|*'<output-file>'*) exit 0 ;;
esac
LANG_OK=$(printf '%s' "$PROMPT" | python3 -c '
import sys
t = sys.stdin.read()
lat = sum(1 for c in t if ("a" <= c <= "z") or ("A" <= c <= "Z"))
cyr = sum(1 for c in t if "Ѐ" <= c <= "ӿ")
print("ok" if lat > 0 and cyr <= lat else "skip")
' 2>/dev/null)
[ "$LANG_OK" != "ok" ] && exit 0

(
  PROMPT_SYS=$(PLUGIN_ROOT="$PLUGIN_ROOT" GRAMMAR_HOME="$GRAMMAR_HOME" REPHRASE="$REPHRASE" python3 -c '
import os
root = os.environ["PLUGIN_ROOT"]
home = os.environ["GRAMMAR_HOME"]
keep = os.environ.get("REPHRASE", "true") != "false"
tmpl = open(os.path.join(root, "prompts", "checker.txt"), encoding="utf-8").read()
catalog = [l.strip() for l in open(os.path.join(root, "config", "categories.txt"), encoding="utf-8") if l.strip()]

def slug(entry):
    return entry.split(":", 1)[0].strip()

def load_selection(path):
    try:
        names = {l.strip() for l in open(path, encoding="utf-8") if l.strip()}
    except OSError:
        return None
    picked = [e for e in catalog if slug(e) in names]
    return picked or None

enabled = (load_selection(os.path.join(home, "enabled-categories.txt"))
           or load_selection(os.path.join(root, "config", "enabled-categories.txt"))
           or catalog)
enabled_slugs = {slug(e) for e in enabled}
disabled = [e for e in catalog if slug(e) not in enabled_slugs]

def gloss(entry):
    return entry.split(":", 1)[1].strip().split(" - \"", 1)[0]

dis_line = ""
if disabled:
    dis_line = "- disabled error categories for this user - do not flag these even when you are sure: " + "; ".join(
        "%s (%s)" % (slug(e), gloss(e)) for e in disabled)

out, in_block = [], False
for line in tmpl.split("\n"):
    if line.strip() == "{{REPHRASE_START}}":
        in_block = True
        continue
    if line.strip() == "{{REPHRASE_END}}":
        in_block = False
        continue
    if in_block and not keep:
        continue
    out.append(line)
import sys
sys.stdout.write("\n".join(out)
    .replace("\n{{DISABLED_CATEGORIES}}", "\n" + dis_line if dis_line else "")
    .replace("{{CATEGORIES}}", ", ".join(slug(e) for e in enabled))
    .replace("{{CATEGORY_DEFINITIONS}}", "\n".join("  - " + e for e in enabled)))
')

  PAYLOAD=$(MODEL="$LLM_MODEL" SYS="$PROMPT_SYS" USR="$PROMPT" python3 -c '
import os, json
print(json.dumps({
    "model": os.environ["MODEL"],
    "temperature": 0,
    "messages": [
        {"role": "system", "content": os.environ["SYS"]},
        {"role": "user", "content": os.environ["USR"]},
    ],
}))
')
  # The Authorization header carries the key via a curl config read from stdin (the shell writes the here-doc straight to curl), so the secret never lands in any process argv where `ps` could read it.
  RESP=$(curl -s --max-time 60 "$LLM_BASE_URL/chat/completions" \
    -H "Content-Type: application/json" -d "$PAYLOAD" --config - <<EOF
header = "Authorization: Bearer $LLM_API_KEY"
EOF
)
  FEEDBACK=$(printf '%s' "$RESP" | python3 -c '
import sys, json
try:
    sys.stdout.write(json.load(sys.stdin)["choices"][0]["message"]["content"] or "")
except Exception:
    pass
' 2>/dev/null)

  JLINE=$(FB="$FEEDBACK" MSG="$PROMPT" STATUS="$STATUS_FILE" PLUGIN_ROOT="$PLUGIN_ROOT" python3 -c '
import os, sys, re, json, datetime, difflib

fb = os.environ.get("FB", "")
msg = os.environ.get("MSG", "")
status_path = os.environ["STATUS"]

slugs = set()
try:
    for cl in open(os.path.join(os.environ["PLUGIN_ROOT"], "config", "categories.txt"), encoding="utf-8"):
        if cl.strip():
            slugs.add(cl.split(":", 1)[0].strip())
except (KeyError, OSError):
    pass

lines = []
for l in fb.split("\n"):
    l = l.replace("**", "").replace("`", "").rstrip()
    if l.strip():
        lines.append(l)
if not lines:
    sys.exit(0)

# The model sometimes drops the square brackets around the category ("tense fix → fixed (...)"), so the brackets are optional and the category is validated against the catalog instead; matched lines are re-emitted in the canonical bracketed form the statusline renderer parses.
fix_re = re.compile(r"^\[?([a-z-]+)\]?\s+(.+?)\s+→\s+(.+?)\s+\((.+)\)\s*$")
fixes, fix_lines, rephrase, praise = [], [], None, None
for l in lines:
    m = fix_re.match(l)
    if m and (m.group(1) in slugs if slugs else l.startswith("[")):
        fixes.append({"category": m.group(1), "wrong": m.group(2), "fix": m.group(3), "rule": m.group(4)})
        fix_lines.append("[%s] %s → %s (%s)" % (m.group(1), m.group(2), m.group(3), m.group(4)))
    elif l.lstrip().startswith("✨"):
        rephrase = l.lstrip()[1:].strip()
    elif "✔" in l:
        praise = l

# Drop a ✨ line that only repeats the corrections: apply the reported fixes to the message and compare word sequences, ignoring case and punctuation. Fixes substitute on word boundaries, not raw substrings - a reported wrong of "is" must hit the standalone word, never the tail of "this". The 0.9 similarity ceiling (not exact match) also catches rephrases where the model folded in a small fix it never reported; a genuine rewrite changes order or vocabulary and lands far below it. Threshold and normalization are mirrored in eval/run.py - keep them in sync.
if rephrase is not None:
    corrected = msg
    for f in fixes:
        corrected = re.sub(r"(?<!\w)" + re.escape(f["wrong"]) + r"(?!\w)", lambda m, _f=f: _f["fix"], corrected, count=1)
    a = re.findall(r"[a-z0-9\x27]+", corrected.lower())
    b = re.findall(r"[a-z0-9\x27]+", rephrase.lower())
    if difflib.SequenceMatcher(None, a, b).ratio() >= 0.9:
        rephrase = None

has_content = bool(fix_lines) or rephrase is not None

# Every reviewed message is logged, clean ones included: a praise entry carries an empty fixes list and a praise key, so what the user got right accumulates the same way mistakes do. Readers that only want mistakes must test fixes[] for content instead of treating every line as a mistake.
obj = {
    "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    "message": msg,
    "fixes": fixes,
}

if has_content:
    if rephrase:
        obj["rephrase"] = rephrase
    parts = list(fix_lines)
    if rephrase:
        parts.append("✨ " + rephrase)
    open(status_path, "w", encoding="utf-8").write("\n".join(parts))
else:
    compliment = praise[praise.find("✔") + 1:].strip() if praise else ""
    # The prompt asks for at most 70 characters, but the ceiling here is a sanity guard against a paragraph, not the target: a message-anchored compliment that overshoots by a few words is still worth more than the generic fallback, and the statusline soft-wraps it.
    if not compliment or len(compliment) > 120 or len(lines) > 1:
        compliment = "Looks good"
    # The fallback is logged as it was displayed rather than dropped: a run where the model returned no usable compliment is data about the checker, and the entry still counts as one clean message.
    obj["praise"] = compliment
    open(status_path, "w", encoding="utf-8").write("✔ " + compliment)

sys.stdout.write(json.dumps(obj, ensure_ascii=False))
')
  [ -n "$JLINE" ] && printf '%s\n' "$JLINE" >> "$HISTORY_FILE"
) > /dev/null 2>&1 &

[ -n "$GRAMMAR_HOOK_SYNC" ] && wait
exit 0
