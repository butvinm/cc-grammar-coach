#!/usr/bin/env bash
# UserPromptSubmit checker. Reviews each English message out of band, logs mistakes to history.jsonl, and optionally writes statusline feedback.
# Writes nothing to stdout and never blocks the turn: the model call is backgrounded and the hook returns immediately (unless GRAMMAR_HOOK_SYNC).

[ -n "$GRAMMAR_HOOK_ACTIVE" ] && exit 0

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

MIN_CHARS=15
MAX_CHARS=500

REPHRASE="${CLAUDE_PLUGIN_OPTION_REPHRASE:-true}"
SHOW_FEEDBACK="${CLAUDE_PLUGIN_OPTION_SHOW_FEEDBACK:-true}"
LLM_BASE_URL="${CLAUDE_PLUGIN_OPTION_LLM_BASE_URL:-}"
LLM_MODEL="${CLAUDE_PLUGIN_OPTION_LLM_MODEL:-openai/gpt-oss-120b}"
LLM_API_KEY="${CLAUDE_PLUGIN_OPTION_LLM_API_KEY:-}"

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

export GRAMMAR_HOOK_ACTIVE=1
(
  PROMPT_SYS=$(PLUGIN_ROOT="$PLUGIN_ROOT" REPHRASE="$REPHRASE" python3 -c '
import os
root = os.environ["PLUGIN_ROOT"]
keep = os.environ.get("REPHRASE", "true") != "false"
tmpl = open(os.path.join(root, "prompts", "checker.txt"), encoding="utf-8").read()
cats = [l.strip() for l in open(os.path.join(root, "config", "categories.txt"), encoding="utf-8") if l.strip()]
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
sys.stdout.write("\n".join(out).replace("{{CATEGORIES}}", ", ".join(cats)))
')

  FEEDBACK=""
  if [ -n "$LLM_API_KEY" ] && [ -n "$LLM_BASE_URL" ]; then
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
  fi

  if [ -z "$FEEDBACK" ]; then
    FEEDBACK=$(printf 'Text: %s' "$PROMPT" | claude -p --model claude-haiku-4-5-20251001 "$PROMPT_SYS" 2>/dev/null)
  fi

  JLINE=$(FB="$FEEDBACK" MSG="$PROMPT" SHOW="$SHOW_FEEDBACK" STATUS="$STATUS_FILE" python3 -c '
import os, sys, re, json, datetime

fb = os.environ.get("FB", "")
msg = os.environ.get("MSG", "")
show = os.environ.get("SHOW", "true") != "false"
status_path = os.environ["STATUS"]

lines = []
for l in fb.split("\n"):
    l = l.replace("**", "").replace("`", "").rstrip()
    if l.strip():
        lines.append(l)
if not lines:
    sys.exit(0)

fix_re = re.compile(r"^\[([a-z-]+)\]\s+(.+?)\s+→\s+(.+?)\s+\((.+)\)\s*$")
fixes, fix_lines, rephrase, praise = [], [], None, None
for l in lines:
    m = fix_re.match(l)
    if m:
        fixes.append({"category": m.group(1), "wrong": m.group(2), "fix": m.group(3), "rule": m.group(4)})
        fix_lines.append(l)
    elif l.lstrip().startswith("✨"):
        rephrase = l.lstrip()[1:].strip()
    elif "✔" in l:
        praise = l

has_content = bool(fix_lines) or rephrase is not None

if has_content:
    obj = {
        "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "message": msg,
        "fixes": fixes,
    }
    if rephrase:
        obj["rephrase"] = rephrase
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))

if show:
    if has_content:
        parts = list(fix_lines)
        if rephrase:
            parts.append("✨ " + rephrase)
        open(status_path, "w", encoding="utf-8").write("\n".join(parts))
    else:
        compliment = praise[praise.find("✔") + 1:].strip() if praise else ""
        if not compliment or len(compliment) > 50 or len(lines) > 1:
            compliment = "Looks good"
        open(status_path, "w", encoding="utf-8").write("✔ " + compliment)
')
  [ -n "$JLINE" ] && printf '%s\n' "$JLINE" >> "$HISTORY_FILE"
) > /dev/null 2>&1 &

[ -n "$GRAMMAR_HOOK_SYNC" ] && wait
exit 0
