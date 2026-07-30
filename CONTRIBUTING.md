# Contributing

## Wire format

The checker emits plain-text lines that the statusline renderer colors and the hook parses into `history.jsonl`, which is what the drill and the dashboard read. The three markers are Unicode and load-bearing: `→` (U+2192) separates wrong from fix, `✔` (U+2714) marks the praise line, `✨` (U+2728) marks the rephrase line. They must appear verbatim in the prompt (`prompts/checker.txt`), the parsers, and any test fixture; substituting ASCII `->` silently empties the mistake log.

- `✔ <compliment>` - clean message; doubles as the liveness signal, so it must never render blank.
- `[<category>] <wrong> → <fix> (<rule>: <why>)` - one line per grammar error; category slugs and their one-line definitions come from the catalog `config/categories.txt`, filtered by the enabled selection (`$GRAMMAR_HOME/enabled-categories.txt` if the user wrote one, else `config/enabled-categories.txt`); enabled entries are injected into the checker prompt as flaggable categories and disabled ones as explicit silence items (see `docs/mistake-categories.md`). The statusline renderer drops the `[<category>]` tag for display; the dashboard's progress view groups by it.
- `✨ <rephrase>` - one optional natural rephrasing of the whole message; never emitted together with the `✔` line.

## Dashboard

`dashboard/` is the whole UI: `server.py` (stdlib `http.server`, also the launcher), `index.html`, `duo.css`. `hooks/grammar-check.sh` copies all three into `$GRAMMAR_HOME/dashboard/` on every message when they differ, and that copy - not the versioned plugin-cache path - is what the README, the skills, and the user's bookmark launch, so plugin updates propagate without re-wiring.

The server is a dumb file layer: it reads and appends, and computes nothing per view. All aggregation (bucketing, category ordering, KPI counts) lives in `index.html`, so a new chart needs no new endpoint. Routes:

| Route                    | Returns                                                                                                                       |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| `GET /` , `GET /duo.css` | the two app files from the server's own directory; no other path maps to the filesystem                                       |
| `GET /api/health`        | `{"app": "cc-grammar-coach", "version": ..., "home": "<GRAMMAR_HOME>", "pid": ...}` - the marker the launcher probes          |
| `GET /api/history`       | `history.jsonl` rows as an array; unparsable and non-object lines are skipped                                                 |
| `GET /api/drills`        | newest-first summaries `{file, kind, date, topics: [{label, count}]}` over `drills/*.json`; legacy `drills/*.html` is ignored |
| `GET /api/drills/<file>` | one drill JSON; only a `.json` basename resolves, anything else 404s                                                          |
| `GET /api/results`       | `results.jsonl` rows as an array                                                                                              |
| `POST /api/results`      | appends one validated line; 400 and no write on anything malformed                                                            |

A `results.jsonl` line is `{"ts": "<offset-carrying ISO timestamp>", "drill": "<file name in drills/>", "total": N, "correct": N, "byTopic": {"<topic id>": {"good": N, "total": N}}}`. `ts` carries the local offset like `history.jsonl` does, so a near-midnight attempt buckets on the day it was taken.

Two guards, both because the port is fixed and documented and the log is personal: every request must address the server as `127.0.0.1`/`localhost` (DNS-rebinding guard), and the one write endpoint additionally demands an `application/json` body and a local `Origin` when the browser sends one, so a page on another site cannot post fabricated scores.

Several dashboards can be up at once - `GRAMMAR_DASHBOARD_PORT` exists for exactly that, and the launcher already handles a port held by a dashboard serving a different grammar home. So no stop instruction anywhere in this repo may match on a command line (`pkill -f dashboard/server.py` kills all of them, including servers the user is still using). Stop a dashboard with Ctrl+C in its own terminal, or by the `pid` its `/api/health` reports for the port in question; the launcher's version-skew notice prints that pid itself.

Markup in `index.html` is built two ways and new code picks one on purpose: `el(tag, cls, text)` for anything assembled from data or needing events (the chart, the table), template strings with `esc()` on every interpolation for the fixed panels ported from the old templates (the list card, the lessons, the feedback and result blocks). Prefer `el()` when adding a view - it cannot forget to escape - and if you extend a template-string block, `esc()` every value you interpolate, including numbers.

## Releasing

Bump `version` in `.claude-plugin/plugin.json` and `VERSION` in `dashboard/server.py` in the same commit. The launcher compares the running server's marker against the local copy's constant to tell the user that a server started before the update is still serving the old app; a forgotten bump silently disables that notice.

## The eval

`eval/` is a maintainer tool; end users never run it. It measures a candidate model's false-positive rate and recall against the checker's narrow spec and catches prompt regressions. The shipped default, `openai/gpt-oss-120b`, was chosen with it: silent on every typo and name/mention case, best recall, ~1.4s median raw latency. When changing the prompt, the model, or the endpoint, vet the change with `eval/run.py` before trusting it; see `eval/README.md` for the harness details and known caveats.
