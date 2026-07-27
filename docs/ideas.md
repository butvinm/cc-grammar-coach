- weekly reminder

- (implemented) "before commiting" and "does he" was both presented as "verb forb" but the are totally different types of mistakes, with different rules and what is more important with separate fequencies. this suggests our taxonomy is wrong. maybe we can use some standard taxonomy? from LanguageTool or some academic approach

- the drill generatio is too long, uses too many custom and ad-hoc actions. can we define a few mandatory steps and scripts for them? like "fetch_last_mistakes.sh", "generate_drill.sh quiz.json" or something like this?

```
❯ /cc-grammar-coach:grammar-drill

● The grammar-drill skill is already loaded via the slash command. Running the drill flow: first, rank recent weak spots from the mistake log.

● Bash(GRAMMAR_HOME="${GRAMMAR_HOME:-$HOME/.claude/cc-grammar-coach}"
      python3 - "$GRAMMAR_HOME/history.jsonl" <<'PY'…)
  ⎿  13 articles
     9  verb-form
     8  prepositions
     … +4 lines (ctrl+o to expand)
  ⎿  Allowed by auto mode classifier

● Bash(GRAMMAR_HOME="${GRAMMAR_HOME:-$HOME/.claude/cc-grammar-coach}"
      python3 - "$GRAMMAR_HOME/history.jsonl" <<'PY'…)
  ⎿  MSG: let's try to create a new sandbox with SANDBOX_SERVICE_PROFILE=full SANDBOX_BRANCH=1.0.4 SANDBOX_LIFETIME=1  while it is creating
     , implement your fix in ~/Dev/adc/adc-package-manager. Let's also treat unathorized as hard error - no need to retry if you have wrong
      credentials
     … +72 lines (ctrl+o to expand)
  ⎿  Allowed by auto mode classifier

  Made 1 scratchpad edit +271 (ctrl+o to expand)

● Bash(python3 "/home/butvinm/Dev/cc-grammar-coach/skills/grammar-drill/scripts/build_drill.py"
      /tmp/claude-1000/-home-butvinm-Dev-cc-grammar-coach/41608f98-cab7-449c-…)
  ⎿  /home/butvinm/.claude/cc-grammar-coach/drills/drill-2026-07-26-0234.html
  ⎿  Allowed by auto mode classifier

● Bash(if command -v open >/dev/null 2>&1; then open "/home/butvinm/.claude/cc-grammar-coach/drills/drill-2026-07-26-0234.html"
      elif command -v xdg-open >/dev/null 2>&…)
  ⎿  (No output)
  ⎿  Allowed by auto mode classifier

● Drill ready: /home/butvinm/.claude/cc-grammar-coach/drills/drill-2026-07-26-0234.html
  Topics: Articles (13 logged mistakes), Verb forms (9), Prepositions (8)
  Questions: 15
```

- UI/UX - list with all mistakes grouped by types with their frequencies, grammar lesson for any selected mistake type, keyboard navigation

- concise statusline mode. user's message repeated verbatim with diff-like mistakes correction:
  Could you provide <red>a</red>strict, logical reasoning why both interactive-review and user-story <red>falls<red><gray>-></gray><green>falls</green> under <green>the</green> "feedback" group?

- the hook should trigger on "User answered Claude's questions" too

- (implemented) in "cc-grammar-coach:grammar-drill" "grammar" is redundant. just "cc-grammar-coach:drill"

- perform deeper analysis of mistakes. is the user making progress? is there any hidden pattern behind his mistakes?

- looks like rephrasing just corrects mistakes (even example from docs/img/statusline.png)

- add a guide how to configure Gemini free

- "/cc-grammar-coach:configure [install-statusline | uninstall-statusline | doctor | ...]"; uninstall-statusline and doctor subcommands are still open

- (implemented) drill and learn are mixed under the same skill, but they are different flows (practice your logged mistakes vs teach the next weekly syllabus topic). consider splitting them
