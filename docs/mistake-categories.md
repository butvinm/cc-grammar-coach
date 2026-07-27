# Categories of mistakes

The taxonomy is split into a **catalog** (every category the checker knows how to define) and a **selection** (the subset a given user has enabled). The checker flags only selected categories; the drill practices whatever got logged.

**Catalog**: `config/categories.txt`, one line per category:

```
slug: definition
```

- `slug` is lowercase-hyphen (`[a-z-]+`), because the hook's fix-line regex in `hooks/grammar-check.sh` accepts nothing else; it is what gets logged to `history.jsonl` and counted by the drill ranking.
- `definition` is one line stating what the category covers, with wrong → fixed examples and, where two categories could collide, a boundary note naming the winner (see the `tense` and `questions` lines). The line is injected verbatim into the checker prompt, so the examples must use the literal `→` arrow the wire format requires.

**Selection**: a flat list of enabled slugs, one per line. The hook reads `$GRAMMAR_HOME/enabled-categories.txt` if the user has one, else the shipped default `config/enabled-categories.txt`. Slugs not in the catalog are ignored; an empty or fully invalid selection falls back down that chain. The default names its slugs explicitly - never "all" - so catalog growth in a plugin update cannot silently widen what gets flagged. Users change their selection by editing the `$GRAMMAR_HOME` file directly, or with:

```
/cc-grammar-coach:configure mistake-categories
```

The hook assembles the checker prompt from both: `{{CATEGORIES}}` becomes the enabled slug list, `{{CATEGORY_DEFINITIONS}}` the enabled definition lines, and `{{DISABLED_CATEGORIES}}` an explicit do-not-flag silence line built from the disabled catalog entries - deselecting a category actively silences it rather than leaving it undefined.

To add a category: add a `slug: definition` line to the catalog, add recall cases for it to `eval/cases.jsonl` (with `"selection": "full"` if it is outside the default selection), and vet with `eval/run.py --repeats 2` or higher before trusting it. Add it to `config/enabled-categories.txt` only if it should be flagged for everyone by default.

## Where the slugs come from

The slugs are adapted from ERRANT (Bryant et al., ACL 2017), the de facto standard error taxonomy in grammatical error correction, with two systematic transforms: ERRANT's operation axis (missing/unnecessary/replacement) is collapsed, because a learner with article trouble has article trouble regardless of the edit operation, and any ERRANT type bundling several separately-teachable rules is split, because the drill ranks weaknesses by category count and a bundled count is meaningless (issue #3). A category here means one teachable grammar rule with its own failure frequency.

The default selection is the author's set, not a completeness claim: which error types are worth flagging is a per-user choice, which is why the selection is configurable (#15). A principled criterion for what belongs in the shipped default is a deliberately open question; until it is decided, the default simply stays the author's selection. The table distinguishes catalog categories in the default selection, catalog categories outside it, and types with no catalog entry (with the current behavior as fact, not a universal justification).

Coverage of ERRANT main types:

| ERRANT type                                           | our slug / decision                                                                                                                                                                                              |
| ----------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| DET                                                   | `articles`                                                                                                                                                                                                       |
| VERB:SVA                                              | `agreement`                                                                                                                                                                                                      |
| VERB:TENSE                                            | `tense`                                                                                                                                                                                                          |
| PREP                                                  | `prepositions`                                                                                                                                                                                                   |
| NOUN:NUM                                              | `plural`                                                                                                                                                                                                         |
| VERB:FORM                                             | split into `verb-after-auxiliary`, `verb-gerund-infinitive`, `verb-participle` - three separately-teachable rules                                                                                                |
| M:VERB, U:VERB (missing/extra verb or auxiliary)      | `verb-missing`                                                                                                                                                                                                   |
| MORPH                                                 | `word-form`                                                                                                                                                                                                      |
| WO, M:VERB:AUX in questions                           | `questions` (in default) covers do-support and subject-auxiliary inversion; `word-order` (in catalog, not in default) covers the rest                                                                            |
| PRON                                                  | `pronouns` - in catalog, not in default                                                                                                                                                                          |
| ADJ:FORM                                              | `comparatives` - in catalog, not in default                                                                                                                                                                      |
| PART                                                  | `particles` - in catalog, not in default                                                                                                                                                                         |
| NOUN:POSS                                             | `possessives` - in catalog, not in default                                                                                                                                                                       |
| PUNCT                                                 | `punctuation` (narrow: run-ons and comma splices) - in catalog, not in default; broader punctuation stays in the static silence list                                                                             |
| SPELL, ORTH, CONTR                                    | no catalog entry: the checker's silence list names typos, capitalization, and contractions explicitly (`prompts/checker.txt` lines 5-11)                                                                         |
| NOUN:INFL, VERB:INFL                                  | no catalog entry: malformed non-words ("catched", "informations") fall under the real-words rule (`prompts/checker.txt` line 3) and read as misspellings                                                         |
| ADJ, ADV, NOUN, VERB, CONJ (word-choice replacements) | no catalog entry: word-choice corrections currently surface only in the ✨ rephrase line                                                                                                                         |
| OTHER                                                 | no escape slug: the checker must pick exactly one defined category, so within-scope errors that fit no definition get force-filed; add a category when logged `rule` texts start disagreeing with their category |

For another target language, swap ERRANT for that language's learner-error scheme (MERLIN/Falko for German, CzeSL for Czech, CGED for Chinese, RULEC-GEC for Russian), fill in the same table, and apply the same two transforms.
