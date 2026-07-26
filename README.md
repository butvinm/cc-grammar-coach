# cc-grammar-coach

An English grammar coach for Claude Code, in two parts:

- a **checker** hook that reviews every English message you send, out of band, logs the mistakes it finds, and shows short feedback in your statusline;
- a **drill** skill that turns those logged mistakes into a personalized lesson-and-quiz web page.

![Grammar feedback in the statusline](docs/img/statusline.png)

## Requirements

- `bash`, `python3`, and `curl` (used by the hook; no `jq` required).
- A grammar model: an OpenAI-compatible chat-completions endpoint (recommended: `openai/gpt-oss-120b`). This is **required** - the checker stays inactive until the base URL, model, and API key are configured.
- Linux or macOS.

## Install

In Claude Code, add this repository as a plugin marketplace, install the plugin, then wire the statusline:

```
/plugin marketplace add butvinm/cc-grammar-coach
/plugin install cc-grammar-coach@cc-grammar-coach
/cc-grammar-coach:install-statusline
```

The last step wires the grammar segment into your statusline (shown, confirmed, and safe to re-run); without it the checker still logs mistakes for the drill but never shows you anything. Details, including manual wiring: [docs/statusline.md](docs/statusline.md).

## Configuration

On install, Claude Code prompts you for these settings; change them later from the `/plugin` menu.

| Field             | Type               | Default               | Meaning                                                                                                                                       |
| ----------------- | ------------------ | --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `native_language` | string             | _(none)_              | Drill uses it to explain English by contrast with your first language; empty means generic lessons. Not read by the checker.                  |
| `rephrase`        | boolean            | `true`                | Allow the checker to append one `✨` natural-rewrite line for clearly awkward messages.                                                       |
| `llm_base_url`    | string             | _(none)_              | OpenAI-compatible endpoint base URL including the version segment, e.g. `https://your-host/v1`; required, the checker is inactive without it. |
| `llm_model`       | string             | `openai/gpt-oss-120b` | Model id sent to the endpoint.                                                                                                                |
| `llm_api_key`     | string (sensitive) | _(none)_              | Bearer key for the endpoint; stored outside `settings.json`.                                                                                  |

## What you'll see

The checker runs on every message automatically; there is nothing to invoke. Per message, the statusline shows one of:

- `✔ Looks good` - clean message, one short compliment.
- `<wrong> → <fix> (<rule>: <why>)` - one line per grammar error.
- `✨ <rewrite>` - optionally, a more natural rewrite of a clearly awkward message (gated by `rephrase`).

It flags only clear-cut grammar errors and stays quiet on word choice, typos, code identifiers, quoted fragments, punctuation, and non-English or very short/long messages. The judge is a model, not a rule engine, so an occasional borderline call slips through - and still feeds the drill, so nothing is lost. Expect feedback a few seconds after you send a message (the call is backgrounded, so it never delays your turn).

## The drill

Ask for a drill in plain language ("give me a grammar drill", "quiz me on my mistakes", "let's learn a new grammar topic"), or invoke the skill explicitly:

```
/cc-grammar-coach:grammar-drill
```

**Drill** mode (default) ranks your recent weak spots from the mistake log and builds a lesson plus quiz per topic, drawn from your own logged mistakes. **Learn** mode teaches the next new topic from the weekly syllabus, one per week. Either way you get a self-contained HTML page that grades your answers in the browser offline, explaining each answer by contrast with your native language when one is configured.

<p align="center">
  <img src="docs/img/quiz-correct.png" width="49%" alt="A choice question answered correctly, with the rule explained">
  <img src="docs/img/quiz-mistake.png" width="49%" alt="A rewrite question answered wrongly, with the fix explained by contrast with the native language">
</p>

## Troubleshooting

No feedback in the statusline? Two usual causes: the display needs the one-time wiring (`/cc-grammar-coach:install-statusline`), and the checker needs LLM credentials (base URL, model, API key in the plugin config). Fresh files under `~/.claude/cc-grammar-coach/status/` mean the checker works and only the display is unwired; no files there mean the hook is not running (is the plugin enabled?). You can also just describe the symptom to Claude and let it walk this chain for you.

## Learn more

- [docs/statusline.md](docs/statusline.md) - wiring details, manual wiring, wire format, state directory layout.
- [docs/requirements.md](docs/requirements.md) - design rationale: the checker's behavioral spec, model measurements, and why a configured endpoint is required (no zero-config fallback).
- [eval/](eval/) - the harness and dataset behind the model choice; vet any alternative endpoint with `eval/run.py` before trusting it.

## License

MIT. See `LICENSE`.
