---
name: learn
description: Teach the next new English grammar topic from a weekly syllabus as a lesson and quiz in the session. Invoke when the user asks to learn a new grammar topic, the next topic, or a fresh grammar lesson beyond their logged mistakes.
---

# Learn

Teach the next new topic from the weekly syllabus here in the conversation, as a lesson and a quiz personalized with evidence from the grammar-check hook's mistake log.

The user's native language is `${user_config.native_language}`. When it is set, contrast English rules with the habits that language causes (for example a language with no articles, freer word order, or aspect instead of tense variety). When it is empty, give generic English lessons and do not assume any nationality.

To practice the user's logged mistakes instead of teaching new material, use the `drill` skill.

## Where the data lives

Grammar home defaults to `~/.claude/cc-grammar-coach` and is overridden by `$GRAMMAR_HOME`. Resolve it once:

```
GRAMMAR_HOME="${GRAMMAR_HOME:-$HOME/.claude/cc-grammar-coach}"
```

- `$GRAMMAR_HOME/history.jsonl` - the checker hook's log, one JSON object per reviewed message: `{"ts", "message", "fixes": [{"category", "wrong", "fix", "rule"}], "rephrase"?, "praise"?}`. A clean message is logged with an empty `fixes` list and a `praise` key, so a line is evidence of a mistake only when `fixes[]` has content. Used here only to personalize the lesson.
- `$GRAMMAR_HOME/curriculum.tsv` - one `<iso-week>\t<topic-id>` line per taught topic; may not exist yet.

## Building the lesson

1. Get the ISO week (`date +%G-W%V`) and read `$GRAMMAR_HOME/curriculum.tsv`.

2. If a line for the current week exists, review that week's topic with a fresh quiz - the pace is one new topic per week, enforced here, not by a scheduler. Otherwise take the first topic from `references/syllabus.md` not yet listed in the file and append `<iso-week>\t<topic-id>` (create the file and its parent dir if missing).

3. Personalize: scan `history.jsonl` for the topic's constructions - `fixes[]` on that category, `message` text using or conspicuously avoiding it, and `praise` lines naming it - to see whether the user misuses, avoids, or already handles the construction, and work that evidence into the lesson.

4. Build the drill data. Read `${CLAUDE_PLUGIN_ROOT}/skills/drill/references/authoring.md` for the data schema and question-writing rules, then author:
   - `kind: "learn"`.
   - The single topic gets `count: 0` - nothing has been logged against material the user has not been taught yet - and a 3-5 sentence lesson, since new material needs more setup than remediation, with 6-8 `questions`.
   - Lesson `examples` come from the user's logged sentences when the log has usable evidence for the topic. When it does not, invent examples showing the typical error a speaker of the user's native language makes instead - do not present invented sentences as the user's own.

5. Write the data to a JSON file in the scratchpad, then store the session from the plugin root:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/drill/scripts/prepare_drill.py" <data.json>
   ```

   The script validates the data, writes `$GRAMMAR_HOME/drills/learn-<date>-<HHMM>.json`, and prints the path.

6. Open with one line naming the topic, picking `New topic` or `Review` to match step 2, then run the quiz. Read `${CLAUDE_PLUGIN_ROOT}/skills/drill/references/running-a-quiz.md` and follow it - it covers the checker flag, the one-question-at-a-time loop, semantic grading, and how to record the result.

   ```
   New topic: <label> (<iso-week>)
   <total count> questions.
   ```
