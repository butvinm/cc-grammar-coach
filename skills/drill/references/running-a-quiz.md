# Running a quiz in the session

Shared by the drill and learn skills. Read this after `prepare_drill.py` has written the session file and printed its path.

The quiz runs here, in the conversation. There is no page and no browser: you ask, the user answers in chat, and you grade. That is the whole point of the format - a grader that understands the rule accepts every correct sentence instead of the ones an author happened to list, and it can answer "wait, why?" the moment the user asks.

## Before the first question

Silence the checker for the duration:

```
touch "$GRAMMAR_HOME/drill-active"
```

The `UserPromptSubmit` hook exits early while that file exists and is under an hour old. Without it, every rewrite answer is reviewed as if it were the user's own writing and logged to `history.jsonl`, which both pollutes the log and feeds the next drill its own questions.

Then print the lesson for the first topic: the `summary`, and the `examples` as `wrong -> right` pairs with their notes. Keep it to what fits on a screen. Print each later topic's lesson when its first question comes up, not all of them upfront.

## The loop

Ask **one question per message** and wait for the answer. Never batch questions, never print the whole quiz, never ask "ready for the next one?" - grade, explain, and go straight into the next question in the same message.

Prefix each question with its position, `Question 3 of 12`, and name the topic. The user cannot scroll a terminal the way they can scroll a page, so the count is the only progress they get.

- `choice` questions: use `AskUserQuestion` with the authored `options` in their authored order. Do not renumber or reorder them - `answer` is an index into that list.
- `rewrite` questions: ask in plain chat and read the next user message as the answer.

## Grading

`choice` is graded on the index. `rewrite` is graded on meaning:

- Correct is any sentence that fixes the construction the question tests and is itself correct English. Accept contractions, synonyms, a different but valid article or tense choice, different word order, and any punctuation or capitalization.
- The authored `answers` are reference answers, not a list of the only accepted strings. Never compare the user's answer to them as text.
- Wrong is when the tested construction is still wrong. If the user fixes the tested rule but introduces an unrelated error, that counts as correct for the score; mention the other error in one clause and move on.
- When the answer is ambiguous or the user hedged, ask what they meant rather than guessing.

## After each answer

One line for the verdict, then the question's `explain` text. On a wrong answer, show a reference answer from `answers` (or the correct option) first. When a native language is configured, say in one clause which habit of that language produced the error.

If the user asks "why?" or pushes back, answer it properly - that is a feature of this format, not an interruption - then resume at the same question number.

## Finishing

When the last question is graded, or when the user stops early, record what was actually asked:

```
python3 "${CLAUDE_PLUGIN_ROOT}/skills/drill/scripts/record_result.py" <session.json> <topic-id>=<correct>/<total> ...
```

Score only the questions that were asked, so an abandoned quiz records an honest partial run rather than a fake perfect one. Then release the checker:

```
rm -f "$GRAMMAR_HOME/drill-active"
```

Do this even when the user stops early, and before your closing message - a drill that ends without clearing the flag leaves the checker mute until the hour is up.
