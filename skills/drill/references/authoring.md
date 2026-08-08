# Drill data authoring

Shared by the drill and learn skills. Read this before writing the data JSON that `scripts/prepare_drill.py` stores as a quiz session. `running-a-quiz.md` covers what happens after that.

Use plain ASCII punctuation in all generated text (straight quotes, hyphens, three dots) - this environment flags em dashes, arrows, and other typographic symbols in written files.

## Question rules

- Mix `choice` and `rewrite` types. Write fresh sentences that exercise the same rule in new contexts (similar register - casual dev chat - but different vocabulary); at most one question per topic may reuse a logged sentence verbatim.
- Give each `rewrite` question exactly one construction to fix. Grading is semantic, so an answer that fixes the target rule passes even if it phrases the rest differently - but a sentence with three independent problems has no single verdict and cannot be scored.
- Make `choice` questions genuinely hard: 3-4 options differing by one word or morpheme, over sentences with 2-3 decision points, so only one option gets every point right. Each distractor must be wrong in exactly one subtle way drawn from the user's error patterns. Prefer testing which form fits (a vs the, in vs into vs to, does...have vs does...has) over whether a form is merely present, and include over-correction traps (an article on an uncountable or a generic plural, a double-marked verb after 'does'). When the right article depends on shared knowledge, set the scene in the prompt ("First message in a thread:").
- Distractors must be wrong in every standard variety of English - skip a tempting distractor if American usage accepts it (e.g. 'already' with past simple).

## Explanation text

An `explain` and a lesson `note` say what governs the specific words in that sentence, not what governs English. A law invented to make two or three examples look like a system is the failure mode here: it sounds authoritative, the user has no way to check it, and a wrong rule they do not happen to challenge is one they learn.

Reserve "always" and "never" for exceptionless facts - 'a' before a plural, 'a' before an uncountable noun. Most rules that feel exceptionless are not: 'such a' loses its article under 'no' ("no such file or directory"), 'wait' takes a bare object in "wait your turn", 'need' drops its infinitive as a modal in "you needn't worry". Either qualify the claim with where it holds, or state it about the words at hand and stop.

The category catalog already marks which topics can carry a rule at all. `articles`, `agreement`, `questions`, `verb-after-auxiliary` and `verb-missing` are defined in `config/categories.txt` by a structural condition, so a generalization about them is derivable and safe. `prepositions` and `particles` are defined there by example substitution alone, because no derivation exists - for those, say the item is memorized per verb and give the verb, rather than deriving a law that will be false for the next verb.

## Schema

```json
{
  "date": "2026-07-15",
  "kind": "drill",
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
      "answers": ["I pushed a fix to the repo"],
      "explain": "'fix' and 'repo' both need articles."
    }
  ]
}
```

`kind` is `drill` or `learn` and picks the filename the session is stored under. `topic` must match a topic `id`. `answer` is a 0-based index into `options`, and the options are asked in the order you write them.

`answers` holds reference answers, not an accept-list. The quiz is graded in the session against the rule, so any correct sentence that fixes the tested construction passes and there is nothing to enumerate: one natural answer is enough, and a second only earns its place when it shows a genuinely different way to fix the sentence (an active rewrite next to a passive one), not a spelling of the same one. `answers[0]` is what the user is shown when they get it wrong, so make it the answer you would want them to copy.
