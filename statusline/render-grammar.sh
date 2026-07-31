#!/usr/bin/env bash
# render_grammar - print the grammar feedback segment for a session.
#
# Sourced, not executed. Reads "$GRAMMAR_HOME/status/$SID" (the file grammar-check.sh writes) and colours each line by the marker it carries so suggestions do not read as errors:
#   ✔ cheer            green   (nothing to fix)
#   ✨ native rephrase  green   (a more native rewrite of the whole message)
#   [category] fix     split per part, see render_fix_line below
# Anything unrecognised falls back to red, so a new line type shows up loudly rather than being silently mis-coloured. Long lines are soft-wrapped to the terminal width on word boundaries so nothing gets truncated.
#
# The statusline re-renders every couple of seconds while the status file only changes once per prompt, so wrapping is done with bash builtins and parameter expansion alone: no subprocess and no pipeline, hence no fork per rendered line.
#
# GRAMMAR_HOME defaults to ~/.claude/cc-grammar-coach and is overridable.

GRAY=$'\033[90m'
GREEN=$'\033[32m'
YELLOW=$'\033[33m'
RED=$'\033[31m'
DIM=$'\033[2m'
RESET=$'\033[0m'

# Splits text on spaces and appends each word, tagged with the colour it is to be printed in, to the pending-word list that _grammar_flush_words wraps.
_grammar_push_words() {
    local col="$1" rest="$2" word
    while [[ -n "$rest" ]]; do
        word="${rest%% *}"
        if [[ "$word" == "$rest" ]]; then rest=""; else rest="${rest#* }"; fi
        [[ -n "$word" ]] || continue
        _GRAMMAR_WORDS+=("$word")
        _GRAMMAR_COLORS+=("$col")
    done
}

# Prints the pending words as one statusline row per wrapped segment, each preceded by a newline, then empties the list.
# Only the visible text is measured, and the active colour is re-emitted at the start of each segment, so escape bytes never corrupt the width calculation. A single word longer than WIDTH is emitted as-is rather than hard-split mid-word.
_grammar_flush_words() {
    local i out="" len=0 cur="" word col
    for ((i = 0; i < ${#_GRAMMAR_WORDS[@]}; i++)); do
        word="${_GRAMMAR_WORDS[i]}"
        col="${_GRAMMAR_COLORS[i]}"
        if [[ $len -gt 0 && $((len + 1 + ${#word})) -gt $WIDTH ]]; then
            printf '\n%s' "$out$RESET"
            out=""; len=0; cur=""
        fi
        if [[ $len -gt 0 ]]; then out+=" "; len=$((len + 1)); fi
        # Reset before each colour change: the dim used for the arrow is an *attribute*, not a colour, so without this it stays switched on and washes out every later part of the line.
        if [[ "$col" != "$cur" ]]; then out+="$RESET$col"; cur="$col"; fi
        out+="$word"
        len=$((len + ${#word}))
    done
    if [[ $len -gt 0 ]]; then printf '\n%s' "$out$RESET"; fi
    _GRAMMAR_WORDS=()
    _GRAMMAR_COLORS=()
    return 0
}

# Renders one fix line with a colour per part - red for the wrong fragment, green for the correction, gray for the reason, dim for the arrow - so the three can be told apart at a glance instead of reading as one long sentence.
render_fix_line() {
    _grammar_push_words "$RED" "$1"
    _grammar_push_words "$DIM" "→"
    _grammar_push_words "$GREEN" "$2"
    _grammar_push_words "$GRAY" "$3"
    _grammar_flush_words
}

render_grammar() {
    local sid="${1:-$SID}"
    # Defensive: a session id carrying a slash or ".." could read outside status/.
    case "$sid" in ''|*/*|*..*) sid=default ;; esac
    local home="${GRAMMAR_HOME:-$HOME/.claude/cc-grammar-coach}"
    local GRAMMAR_FILE="$home/status/$sid"

    [[ -s "$GRAMMAR_FILE" ]] || return 0

    # Claude Code exports COLUMNS to the statusline process and keeps it in step with the pane across resizes (measured over 47 consecutive renders: 162, 176, 180, 395), so the constant applies only to a statusline invoked without it.
    # `tput cols` was measuring nothing: no descriptor there is a terminal, so ncurses answered out of COLUMNS itself, and without COLUMNS it would answer with the terminfo default of 80.
    local WIDTH=${COLUMNS:-120}
    [[ "$WIDTH" =~ ^[0-9]+$ ]] && [ "$WIDTH" -ge 20 ] || WIDTH=120
    # Reserve 4 columns consumed by Claude Code's statusline padding.
    WIDTH=$((WIDTH - 4))

    local _GRAMMAR_WORDS=() _GRAMMAR_COLORS=()
    local line LINE_COLOR body fx_wrong fx_rest fx_why fx_right
    while IFS= read -r line || [[ -n "$line" ]]; do
        case "$line" in
            '✔'*)      LINE_COLOR=$GREEN ;;
            '✨'*)      LINE_COLOR=$GREEN ;;
            '['*'] '*)
                # Split "wrong → right (why)" into its parts and render each in its own colour.
                # A tagged line that does not carry the arrow is not a fix line we understand, so it falls through to the flat yellow rendering below.
                body="${line#*] }"
                if [[ "$body" == *" → "* ]]; then
                    fx_wrong="${body%% → *}"
                    fx_rest="${body#* → }"
                    fx_why=""
                    [[ "$fx_rest" == *"("* ]] && { fx_why="(${fx_rest##*(}"; fx_rest="${fx_rest%(*}"; }
                    fx_right="${fx_rest%"${fx_rest##*[![:space:]]}"}"
                    render_fix_line "$fx_wrong" "$fx_right" "$fx_why"
                    continue
                fi
                LINE_COLOR=$YELLOW; line="$body"
                ;;
            *)         LINE_COLOR=$RED ;;
        esac
        # Word-wrap by character count (UTF-8 aware); a single token longer than WIDTH is emitted as-is rather than hard-split mid-word.
        _grammar_push_words "$LINE_COLOR" "$line"
        _grammar_flush_words
    done < "$GRAMMAR_FILE"
}
