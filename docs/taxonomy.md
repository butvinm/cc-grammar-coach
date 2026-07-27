# Mistake taxonomy

The category slugs the checker files mistakes under live in `config/categories.txt`, one line per category:

```
slug: definition
```

- `slug` is lowercase-hyphen (`[a-z-]+`), because the hook's fix-line regex in `hooks/grammar-check.sh` accepts nothing else; it is what gets logged to `history.jsonl` and counted by the drill ranking.
- `definition` is one line stating what the category covers, with wrong → fixed examples and, where two categories could collide, a boundary note naming the winner (see the `tense` and `questions` lines). The line is injected verbatim into the checker prompt, so the examples must use the literal `→` arrow the wire format requires.

The hook replaces `{{CATEGORIES}}` in `prompts/checker.txt` with the comma-joined slug list and `{{CATEGORY_DEFINITIONS}}` with the definition lines, so this file is the single source of truth: editing it changes both what the model may output and how it decides.

To add a category: add a `slug: definition` line, add recall cases for it to `eval/cases.jsonl`, and vet with `eval/run.py --repeats 2` or higher before trusting it. If the new category also widens what the checker flags at all, update the scope sentence at `prompts/checker.txt` line 3 too.

## Where the slugs come from

The slugs are adapted from ERRANT (Bryant et al., ACL 2017), the de facto standard error taxonomy in grammatical error correction, with two systematic transforms: ERRANT's operation axis (missing/unnecessary/replacement) is collapsed, because a learner with article trouble has article trouble regardless of the edit operation, and any ERRANT type bundling several separately-teachable rules is split, because the drill ranks weaknesses by category count and a bundled count is meaningless (issue #3). A category here means one teachable grammar rule with its own failure frequency.

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
| WO, M:VERB:AUX in questions                           | `questions` covers only do-support and subject-auxiliary inversion; other word order is not covered yet, see #14                                                                                                 |
| PRON, ADJ:FORM, PART, NOUN:POSS                       | not covered yet, see #14                                                                                                                                                                                         |
| SPELL, ORTH, PUNCT, CONTR                             | excluded deliberately: the checker stays silent on typos, capitalization, and punctuation (`prompts/checker.txt` lines 5-11)                                                                                     |
| NOUN:INFL, VERB:INFL                                  | excluded deliberately: malformed non-words ("catched", "informations") read as misspellings under the real-words rule (`prompts/checker.txt` line 3)                                                             |
| ADJ, ADV, NOUN, VERB, CONJ (word-choice replacements) | excluded deliberately: word choice and naturalness go to the ✨ rephrase line, not to categories                                                                                                                 |
| OTHER                                                 | no escape slug: the checker must pick exactly one defined category, so within-scope errors that fit no definition get force-filed; add a category when logged `rule` texts start disagreeing with their category |

For another target language, swap ERRANT for that language's learner-error scheme (MERLIN/Falko for German, CzeSL for Czech, CGED for Chinese, RULEC-GEC for Russian), fill in the same table, and apply the same two transforms.
