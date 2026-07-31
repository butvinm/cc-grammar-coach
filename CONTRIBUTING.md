# Contributing

## Wire format

The checker emits plain-text lines that the statusline renderer colors and the drill parses. The three markers are Unicode and load-bearing: `→` (U+2192) separates wrong from fix, `✔` (U+2714) marks the praise line, `✨` (U+2728) marks the rephrase line. They must appear verbatim in the prompt (`prompts/checker.txt`), the parsers, and any test fixture; substituting ASCII `->` silently empties the mistake log.

- `✔ <compliment>` - clean message; the compliment must name something in that message (a construction, a tense, an idiom) rather than deliver a stock verdict, and the eval gates the stock-or-reused rate (issue #25). It doubles as the liveness signal, so it must never render blank: when the model returns nothing usable (empty, multi-line, or past the hook's sanity ceiling) the hook writes the literal `✔ Looks good`.
- `[<category>] <wrong> → <fix> (<rule>: <why>)` - one line per grammar error; category slugs and their one-line definitions come from the catalog `config/categories.txt`, filtered by the enabled selection (`$GRAMMAR_HOME/enabled-categories.txt` if the user wrote one, else `config/enabled-categories.txt`); enabled entries are injected into the checker prompt as flaggable categories and disabled ones as explicit silence items (see `docs/mistake-categories.md`). The statusline renderer drops the `[<category>]` tag for display; the drill groups by it.
- `✨ <rephrase>` - one optional natural rephrasing of the whole message; never emitted together with the `✔` line.

## The eval

`eval/` is a maintainer tool; end users never run it. It measures a candidate model's false-positive rate and recall against the checker's narrow spec and catches prompt regressions. The shipped default, `openai/gpt-oss-120b`, was chosen with it: silent on every typo and name/mention case, best recall, ~1.4s median raw latency. When changing the prompt, the model, or the endpoint, vet the change with `eval/run.py` before trusting it; see `eval/README.md` for the harness details and known caveats.
