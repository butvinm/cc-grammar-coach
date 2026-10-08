#!/usr/bin/env bash
# The hook behind /cc-grammar-coach:natural, registered for two events and told apart by hook_event_name.
# UserPromptSubmit: remember the user's message in last-prompt/<session-id>, silently. Nothing goes to stdout, because UserPromptSubmit stdout is injected into the conversation.
# UserPromptExpansion of the command: judge the remembered message, or the text passed as the command's argument, and answer by blocking the expansion. A blocked command never expands, never reaches the model, and the block reason is shown to the user without being added to context, so neither the command nor the verdict costs the session anything.
# Verified against Claude Code, not only taken from the docs: a later turn in the same session saw neither the command, its body, nor the verdict, and the transcript stores the block as a system informational entry that is not replayed to the model. UserPromptSubmit does not fire for a command whose expansion was blocked, and for any other command it receives the raw "/..." text, which the remember gates skip.

if [ -n "$CLAUDE_PLUGIN_ROOT" ]; then
  PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
  SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
  PLUGIN_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
fi

GRAMMAR_HOME="${GRAMMAR_HOME:-$HOME/.claude/cc-grammar-coach}"
LAST_DIR="$GRAMMAR_HOME/last-prompt"
COMMAND="cc-grammar-coach:natural"

LLM_BASE_URL="${CLAUDE_PLUGIN_OPTION_LLM_BASE_URL:-}"
LLM_MODEL="${CLAUDE_PLUGIN_OPTION_LLM_MODEL:-openai/gpt-oss-120b}"
LLM_API_KEY="${CLAUDE_PLUGIN_OPTION_LLM_API_KEY:-}"

# One python pass: event, session id and command name on the first three lines, then the text - the prompt for UserPromptSubmit, the command arguments for UserPromptExpansion.
INPUT=$(cat)
{
  IFS= read -r EVENT
  IFS= read -r SID
  IFS= read -r CMD
  TEXT=$(cat)
} < <(printf '%s' "$INPUT" | python3 -c 'import sys, json
d = json.load(sys.stdin)
event = d.get("hook_event_name") or ""
text = d.get("command_args") if event == "UserPromptExpansion" else d.get("prompt")
sys.stdout.write("\n".join([event, d.get("session_id") or "default", d.get("command_name") or "", text or ""]))' 2>/dev/null)
# Same hardening as grammar-check.sh: the session id becomes a path component.
case "$SID" in ''|*/*|*..*) SID=default ;; esac

LAST_FILE="$LAST_DIR/$SID"

TRIMMED="${TEXT#"${TEXT%%[![:space:]]*}"}"
TRIMMED="${TRIMMED%"${TRIMMED##*[![:space:]]}"}"

if [ "$EVENT" = "UserPromptSubmit" ]; then
  # Remember the user's own writing only. Slash commands and injected system text are not, and the gates mirror grammar-check.sh. Length and language are left to the model: an over-long or non-English message still deserves an answer rather than "nothing to check".
  [ -z "$TRIMMED" ] && exit 0
  case "$TRIMMED" in /*|'<'*) exit 0 ;; esac
  case "$TEXT" in *'<task-notification'*|*'<local-command'*|*'<command-name>'*|*'<system-reminder'*|*'<output-file>'*) exit 0 ;; esac
  mkdir -p "$LAST_DIR"
  find "$LAST_DIR" -type f -mtime +1 -delete 2>/dev/null
  # Written through a temp file and renamed, so a check racing this write reads either the old message or the new one, never half of one.
  printf '%s' "$TEXT" > "$LAST_FILE.tmp.$$" && mv -f "$LAST_FILE.tmp.$$" "$LAST_FILE"
  exit 0
fi

# hooks.json already routes only this command here through its matcher; the check keeps the script safe if that wiring ever widens.
[ "$EVENT" = "UserPromptExpansion" ] && [ "$CMD" = "$COMMAND" ] || exit 0

# Prints the block decision and stops. suppressOriginalPrompt keeps the block message from ending with "Original prompt: /cc-grammar-coach:natural ...".
block() {
  REASON="$1" python3 -c 'import os, json
print(json.dumps({
    "decision": "block",
    "reason": os.environ["REASON"],
    "hookSpecificOutput": {"hookEventName": "UserPromptExpansion", "suppressOriginalPrompt": True},
}, ensure_ascii=False))'
  exit 0
}

if [ -n "$TRIMMED" ]; then
  MESSAGE="$TEXT"
else
  [ -s "$LAST_FILE" ] || block "Nothing to check yet: send a message first, or pass the text to check, as in /$COMMAND <text>."
  MESSAGE=$(cat "$LAST_FILE")
fi
{ [ -n "$LLM_BASE_URL" ] && [ -n "$LLM_API_KEY" ]; } || block "The naturalness check needs the plugin's LLM base URL and API key: set them from the /plugin menu."

PAYLOAD=$(MODEL="$LLM_MODEL" SYS_FILE="$PLUGIN_ROOT/prompts/naturalness.txt" USR="$MESSAGE" python3 -c '
import os, json
print(json.dumps({
    "model": os.environ["MODEL"],
    "temperature": 0,
    "messages": [
        {"role": "system", "content": open(os.environ["SYS_FILE"], encoding="utf-8").read()},
        {"role": "user", "content": os.environ["USR"]},
    ],
}))
')
# The user is waiting on this call, unlike the checker's backgrounded one, so it is bounded well inside the hook timeout in hooks.json. The key travels in a curl config on stdin, never in argv, as in grammar-check.sh.
RESP=$(curl -s --max-time 45 "$LLM_BASE_URL/chat/completions" \
  -H "Content-Type: application/json" -d "$PAYLOAD" --config - <<EOF
header = "Authorization: Bearer $LLM_API_KEY"
EOF
)

# The verdict is shown under a quote of the text it judges, so a check that picked up a different message than the user meant is obvious. Markdown emphasis is stripped because the block message is shown as plain text.
VERDICT=$(RESP="$RESP" MESSAGE="$MESSAGE" python3 -c '
import os, json
try:
    text = json.loads(os.environ["RESP"])["choices"][0]["message"]["content"] or ""
except Exception:
    text = ""
text = "\n".join(l.replace("**", "").rstrip() for l in text.strip().split("\n") if l.strip())
if text:
    msg = " ".join(os.environ["MESSAGE"].split())
    if len(msg) > 200:
        msg = msg[:200].rstrip() + "..."
    print("\"%s\"\n\n%s" % (msg, text))
')

[ -n "$VERDICT" ] || block "The naturalness check got no answer from the model; run /$COMMAND again to retry."
block "$VERDICT"
