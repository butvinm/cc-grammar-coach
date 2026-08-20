# Running a quiz in the session

Shared by the drill and learn skills. Read this after `prepare_drill.py` has written the session file and printed its path.

The quiz runs here, in the conversation. There is no page and no browser: you ask, the user answers in chat, and you grade. That is the whole point of the format - a grader that understands the rule accepts every correct sentence instead of the ones an author happened to list, and it can answer "wait, why?" the moment the user asks.

## Before the first question

Print the lesson for the first topic: the `summary`, and the `examples` as `wrong -> right` pairs with their notes. Keep it to what fits on a screen. Print each later topic's lesson when its first question comes up, not all of them upfront.

A drill is not one sitting. The user may answer three questions, go back to work, and pick the rest up hours later - that is normal use, not abandonment. Nothing here holds state between questions, so a quiz can be resumed from its session file at any time.

## The loop

Ask **one question per message** and wait for the answer. Never batch questions, never print the whole quiz, never ask "ready for the next one?" - grade, explain, and go straight into the next question in the same message.

Prefix each question with its position, `Question 3 of 12`, and name the topic. The user cannot scroll a terminal the way they can scroll a page, so the count is the only progress they get.

- `choice` questions: use `AskUserQuestion` with the authored `options` in their authored order. Do not renumber or reorder them - `answer` is an index into that list. Each option's `label` is the authored sentence verbatim, and its `description` is the empty string - the schema requires the field, so it can be emptied but not dropped. Never summarize an option into the word or morpheme that makes it differ, in either field: that names the decision point before the user has read the sentence, and finding it is the question. Nothing else is needed: an `AskUserQuestion` answer never reaches the checker hook.
- `rewrite` questions: the answer arrives as an ordinary message, so the checker would review it as the user's own writing. Drop a one-shot token in the same message you ask the question, and only for a `rewrite`:

  ```
  touch "$GRAMMAR_HOME/skip-next-prompt"
  ```

  The hook consumes it on the next prompt and skips exactly that one message. It clears itself, so there is nothing to undo if the user answers something else or never answers at all - at worst one unrelated message goes unchecked, and a token older than 30 minutes is discarded without firing. Never set it ahead of a batch of questions and never leave it set between them: the user writes real English between quiz answers and wants that checked.

## Grading

`choice` is graded on the index. `rewrite` is graded on meaning:

- Correct is any sentence that fixes the construction the question tests and is itself correct English. Accept contractions, synonyms, a different but valid article or tense choice, different word order, and any punctuation or capitalization.
- The authored `answers` are reference answers, not a list of the only accepted strings. Never compare the user's answer to them as text.
- Wrong is when the tested construction is still wrong. If the user fixes the tested rule but introduces an unrelated error, that counts as correct for the score; mention the other error in one clause and move on.
- When the answer is ambiguous or the user hedged, ask what they meant rather than guessing.

## After each answer

One line for the verdict, then the question's `explain` text. On a wrong answer, show a reference answer from `answers` (or the correct option) first. When a native language is configured, say in one clause which habit of that language produced the error.

The explanation is the authored `explain`. Anything added on top of it must be about the words in that sentence: a rule generalized at grading time has had neither an authoring pass nor the sanity check of being written down next to the question it explains, and the pull to state one is strongest right after a wrong answer, when a bare correction feels too thin. `authoring.md` covers which topics can carry a general rule and which are memorized per word - the same limits apply here.

If the user asks "why?" or pushes back, answer it properly - that is a feature of this format, not an interruption - then resume at the same question number.

## Finishing

When the last question is graded, or when the user stops early, record what was actually asked:

```
python3 "${CLAUDE_PLUGIN_ROOT}/skills/drill/scripts/record_result.py" <session.json> <topic-id>=<correct>/<total> ...
```

Score only the questions that were asked, so a quiz stopped partway records an honest partial run rather than a fake perfect one. There is nothing else to clean up: the one-shot token is consumed by the hook, not released here.
