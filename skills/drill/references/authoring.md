# Drill data authoring

Shared by the drill and learn skills. Read this before writing the data JSON that `scripts/prepare_drill.py` validates and stores for the dashboard.

Use plain ASCII punctuation in all generated text (straight quotes, hyphens, three dots) - this environment flags em dashes, arrows, and other typographic symbols in written files.

## Question rules

- Mix `choice` and `rewrite` types. Write fresh sentences that exercise the same rule in new contexts (similar register - casual dev chat - but different vocabulary); at most one question per topic may reuse a logged sentence verbatim.
- Make `choice` questions genuinely hard: 3-4 options differing by one word or morpheme, over sentences with 2-3 decision points, so only one option gets every point right. Each distractor must be wrong in exactly one subtle way drawn from the user's error patterns. Prefer testing which form fits (a vs the, in vs into vs to, does...have vs does...has) over whether a form is merely present, and include over-correction traps (an article on an uncountable or a generic plural, a double-marked verb after 'does'). When the right article depends on shared knowledge, set the scene in the prompt ("First message in a thread:").
- Distractors must be wrong in every standard variety of English - skip a tempting distractor if American usage accepts it (e.g. 'already' with past simple).

## Schema

```json
{
  "topics": [
    {
      "id": "articles",
      "label": "Articles",
      "count": 14,
      "lesson": {
        "summary": "English marks singular countable nouns with an article ... (2-4 sentences)",
        "examples": [
          {
            "wrong": "create skill",
            "right": "create a skill",
            "note": "singular countable noun needs an article"
          }
        ]
      }
    }
  ],
  "questions": [
    {
      "topic": "articles",
      "type": "choice",
      "prompt": "Pick the correct sentence:",
      "options": [
        "Let's write test for parser",
        "Let's write a test for the parser"
      ],
      "answer": 1,
      "explain": "Both nouns are singular and countable."
    },
    {
      "topic": "articles",
      "type": "rewrite",
      "prompt": "Fix this sentence: I pushed fix to repo",
      "answers": ["I pushed a fix to the repo", "I pushed the fix to the repo"],
      "explain": "'fix' and 'repo' both need articles."
    }
  ]
}
```

Do not author `kind` or `date`: `prepare_drill.py` stamps `kind` from its `--kind` flag (`drill` or `learn`), which is fixed per skill, and `date` from the clock, and it overwrites anything already there. The file name is built from the same clock, so an authored date could name any file and order the dashboard list wrong.

Every field shown as text above must be a non-empty string, `count` a non-negative integer, and `answer` a 0-based integer index into `options` - the dashboard renders these values directly, so `prepare_drill.py` rejects a JSON `true` where a number belongs and a `null` inside `answers` rather than let the quiz break on them. `topic` must match a topic `id`. `answers` lists every acceptable rewrite; comparison ignores only case, extra spaces, and end punctuation, so enumerate variants yourself - contraction and full forms (We've / We have), and each valid article or tense choice.
