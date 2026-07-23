#!/usr/bin/env bash
# Standalone grammar statusline: reads the stdin JSON Claude Code passes to a
# statusLine command, extracts session_id, and prints the grammar feedback
# segment. Wire it in via settings.json statusLine, or source render-grammar.sh
# from an existing statusline to add the segment inline.

input=$(cat)

SID=$(printf '%s' "$input" | python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get("session_id") or "default")
except Exception:
    print("default")')

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=render-grammar.sh
. "$SCRIPT_DIR/render-grammar.sh"

render_grammar "$SID"
