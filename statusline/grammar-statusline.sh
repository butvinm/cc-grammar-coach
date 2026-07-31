#!/usr/bin/env bash
# Standalone grammar statusline: reads the stdin JSON Claude Code passes to a statusLine command, extracts session_id, and prints the grammar feedback segment. Wire it in via settings.json statusLine, or source render-grammar.sh from an existing statusline to add the segment inline.
#
# This runs on every statusline render, roughly once every two seconds per open session, so it stays inside bash: no interpreter, no pipeline, no `cat`. session_id is a UUID, so a regex reads it out of the JSON with nothing to unescape, and that keeps python3 off the statusline's dependency list.

IFS= read -r -d '' input

SID_RE='"session_id"[[:space:]]*:[[:space:]]*"([^"]+)"'
if [[ "$input" =~ $SID_RE ]]; then
    SID="${BASH_REMATCH[1]}"
else
    SID=default
fi

SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[[ "$SCRIPT_DIR" == "${BASH_SOURCE[0]}" ]] && SCRIPT_DIR=.
# shellcheck source=render-grammar.sh
. "$SCRIPT_DIR/render-grammar.sh"

render_grammar "$SID"
