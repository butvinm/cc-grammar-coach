#!/usr/bin/env bash
# render_grammar - print the grammar feedback segment for a session.
#
# Sourced, not executed. Reads "$GRAMMAR_HOME/status/$SID" (the file grammar-check.sh writes) and colours each line by the marker it carries so suggestions do not read as errors:
#   ✔ cheer            green   (nothing to fix)
#   ✨ native rephrase  green   (a more native rewrite of the whole message)
#   [category] fix     split per part, see render_fix_line below
# Anything unrecognised falls back to red, so a new line type shows up loudly rather than being silently mis-coloured. Long lines are soft-wrapped to the terminal width on word boundaries so nothing gets truncated.
#
# GRAMMAR_HOME defaults to ~/.claude/cc-grammar-coach and is overridable.

GRAY='\033[90m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
DIM='\033[2m'
RESET='\033[0m'

# Renders one fix line with a colour per part - red for the wrong fragment, green for the correction, gray for the reason, dim for the arrow - so the three can be told apart at a glance instead of reading as one long sentence.
# Wrapping happens here too: only the visible text is measured, and the active colour is re-emitted at the start of each wrapped segment, so escape bytes never corrupt the width calculation.
render_fix_line() {
    awk -v W="$WIDTH" -v WRONG="$1" -v RIGHT="$2" -v WHY="$3" \
        -v CR="$RED" -v CG="$GREEN" -v CGY="$GRAY" -v CD="$DIM" -v CX="$RESET" '
    function add(txt, col,   k, a, m) {
        if (txt == "") return
        m = split(txt, a, " ")
        for (k = 1; k <= m; k++) { n++; word[n] = a[k]; wcol[n] = col }
    }
    BEGIN {
        n = 0
        add(WRONG, CR); add("→", CD); add(RIGHT, CG); add(WHY, CGY)
        out = ""; len = 0; cur = ""
        for (i = 1; i <= n; i++) {
            if (len > 0 && len + 1 + length(word[i]) > W) {
                print out CX; out = ""; len = 0; cur = ""
            }
            if (len > 0) { out = out " "; len++ }
            # Reset before each colour change: the dim used for the arrow and the counter is an *attribute*, not a colour, so without this it stays switched on and washes out every later part of the line.
            if (wcol[i] != cur) { out = out CX wcol[i]; cur = wcol[i] }
            out = out word[i]; len += length(word[i])
        }
        if (len > 0) print out CX
    }'
}

render_grammar() {
    local sid="${1:-$SID}"
    # Defensive: a session id carrying a slash or ".." could read outside status/.
    case "$sid" in ''|*/*|*..*) sid=default ;; esac
    local home="${GRAMMAR_HOME:-$HOME/.claude/cc-grammar-coach}"
    local GRAMMAR_FILE="$home/status/$sid"

    [[ -s "$GRAMMAR_FILE" ]] || return 0

    local WIDTH
    WIDTH=${COLUMNS:-$(tput cols 2>/dev/null)}
    [[ "$WIDTH" =~ ^[0-9]+$ ]] && [ "$WIDTH" -ge 20 ] || WIDTH=120
    # Reserve 4 columns consumed by Claude Code's statusline padding.
    WIDTH=$((WIDTH - 4))

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
                    render_fix_line "$fx_wrong" "$fx_right" "$fx_why" \
                        | while IFS= read -r seg || [[ -n "$seg" ]]; do
                            printf "\n%s" "$seg"
                        done
                    continue
                fi
                LINE_COLOR=$YELLOW; line="$body"
                ;;
            *)         LINE_COLOR=$RED ;;
        esac
        # Word-wrap by character count (UTF-8 aware); a single token longer than WIDTH is emitted as-is rather than hard-split mid-word.
        awk -v W="$WIDTH" '{
            n=split($0,w," "); line="";
            for(i=1;i<=n;i++){
                cand=(line==""?w[i]:line" "w[i]);
                if(length(cand)>W && line!=""){print line; line=w[i]}
                else line=cand
            }
            if(line!="" || NF==0) print line
        }' <<< "$line" | while IFS= read -r seg || [[ -n "$seg" ]]; do
            printf "\n${LINE_COLOR}%s${RESET}" "$seg"
        done
    done < "$GRAMMAR_FILE"
}
