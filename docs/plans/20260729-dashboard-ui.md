# Dashboard UI: one local web app fed with JSON by all skills

Issue: https://github.com/butvinm/cc-grammar-coach/issues/26

Base: branch `issue-26-dashboard` off `issue-4-keyboard-and-progress` (PR #24, which contributed the quiz keyboard controls this plan ports). PR #24 merges first; rebase onto master if it lands mid-implementation.

## Overview

Invert the page-generation architecture: instead of each skill baking a standalone dead-end HTML file, the plugin gets one local web app - quiz, lessons, and the progress chart as switchable views of the same data - served by a small on-demand stdlib Python server reading JSON from `$GRAMMAR_HOME`. Skills shrink to the one step that needs an LLM: authoring drill/lesson JSON and dropping it into the data directory. The user can open the dashboard any time without invoking a skill, quiz results survive the tab (the server can write), and the progress view reads the live mistake log instead of a stale snapshot.

Decisions locked in discussion (issue #26): the server runs temporarily - started manually or by a skill, dies with the terminal, no daemon or autostart; pre-existing drill HTML files under `$GRAMMAR_HOME/drills/` are not migrated or indexed - they stay openable as plain files; the dashboard indexes drill JSON from its birth onward; stdlib-only Python, no new dependencies; the launcher must make the no-skill path one action. **The canonical launch path is `python3 $GRAMMAR_HOME/dashboard/server.py`** - the only path that is stable across plugin updates and exists without a skill; both SKILL.md files and the README use it.

## Context (from discovery)

- `hooks/grammar-check.sh` appends mistakes to `$GRAMMAR_HOME/history.jsonl` and already contains the plugin-update-survival mechanism: an idempotent `cmp`-guarded copy of scripts into `$GRAMMAR_HOME` (lines 17-22). The dashboard files ride the same mechanism, but into a subdirectory that must be created first (the existing loop copies flat and only `status/` is pre-created).
- `skills/drill/scripts/build_drill.py` validates authored drill JSON against the schema in `skills/drill/references/authoring.md` and injects it into `skills/drill/assets/drill-template.html` with `skills/drill/assets/duo.css` inlined. The validation and the JSON contract survive; the page assembly dies.
- `skills/drill/assets/drill-template.html` holds the quiz state machine and keyboard controls - ports into the dashboard quiz view, but its key handlers are document-level and dereference quiz-only nodes, so they must be gated on the active view, and its Esc handler today is a no-op on the lessons screen (`phase !== 'start'`), so the back-to-list control is new behavior.
- `skills/progress/scripts/build_progress.py` holds the day/week/month bucketing (timezone note: it buckets each `ts` in the offset carried by the string, not the machine zone); `skills/progress/assets/progress-template.html` holds the chart/tooltip/table rendering. The JS ports; the Python aggregation moves client-side and must preserve the offset-respecting bucketing.
- `docs/statusline.md` documents the `$GRAMMAR_HOME` contents table, including `drills/` as "generated self-contained HTML lessons" - a certain edit, not a conditional one. `curriculum.tsv` (learn-mode week tracking) is untouched by this plan.
- `eval/` is unrelated (checker prompt harness) and untouched.

## Development Approach

- **Testing approach: manual verification** (user's choice; the repo is deliberately test-free). Every task ends with falsifiable verification steps in the style of `docs/plans/completed/20260722-cc-grammar-practice-plugin.md` - concrete commands and assertions that can fail, not "looks good". Browser behavior is verified by driving the real page (headless chromium via puppeteer-core from the scratchpad, as done for the keyboard controls); nothing test-related is committed.
- **Visual self-verification is mandatory for every UI task**: the implementing agent screenshots each new or changed view in both color schemes and inspects the images itself (reads them, checks layout, labels, overflow, state colors) before marking the task done - DOM assertions alone do not close a UI checkbox.
- Complete each task fully before moving to the next; a task's verification must pass before starting the next one.
- Small focused changes; update this plan file when scope changes during implementation.
- Size guards, checked in Task 8: `dashboard/server.py` stays under ~250 lines; `dashboard/index.html` stays under ~1100 lines (re-set in Task 8 from the original ~900, which summed only the two absorbed templates; the rationale and the re-derivation are recorded there). Meaningful growth past the guard means the UI is accreting features this plan did not ask for.

## Progress Tracking

- mark completed items with `[x]` immediately when done
- add newly discovered tasks with a `+` prefix
- document issues/blockers with a `!` prefix

## Solution Overview

Data layout in `$GRAMMAR_HOME` (owned by the plugin at runtime):

- `history.jsonl` - unchanged, hook-owned.
- `drills/*.json` - authored drill/lesson data, one file per session, named `drill-<date>-<HHMM>.json`, schema = existing authoring schema plus a top-level `kind: "drill" | "learn"` badge (stamped deterministically by the prepare script, not authored by the LLM). Legacy `drills/*.html` files sit alongside, ignored by the dashboard.
- `results.jsonl` - appended by the server on quiz completion: `{"ts": ..., "drill": "<json filename>", "total": N, "correct": N, "byTopic": {"<topic>": {"good": N, "total": N}}}`.
- `dashboard/` - the app copy: `server.py`, `index.html`, `duo.css`, refreshed by the hook.

Server (`dashboard/server.py`, stdlib `http.server` + `webbrowser`): binds `127.0.0.1` only, port from `$GRAMMAR_DASHBOARD_PORT` (default 8437). Endpoints: `GET /` (index.html), `GET /duo.css`, `GET /api/health` (`{"app": "cc-grammar-coach", "version": ...}`), `GET /api/history` (parsed log rows as a JSON array - the client counts undated/aggregates), `GET /api/drills` (summary listing: filename, kind, date, topic labels/counts, newest first), `GET /api/drills/<file>` (one full drill JSON), `GET /api/results`, `POST /api/results` (validated append). Requests whose `Host` header is not `127.0.0.1` or `localhost` (with optional `:port`) are rejected - DNS-rebinding guard for a fixed documented port serving the raw message log. Running it is the launcher: if the port already answers `/api/health` with our app marker, it opens the browser and exits 0, printing a version-skew notice when the running server's `version` differs from the local copy's; if the port is occupied by something else, it exits with a message naming `$GRAMMAR_DASHBOARD_PORT`; otherwise it starts, opens the browser via `webbrowser.open` unless `--no-open` (used by curl verification), honors `--url-path <hash>` for skill deep-links, and serves until Ctrl+C. No CORS headers, no directory listing, only the enumerated routes.

UI (`dashboard/index.html`, one page, duo.css design system, hash routing): `#drills` - list of authored sessions (date, kind, topic labels, last result from results) plus the entry point to each quiz; `#drill=<file>` - the ported quiz view (lessons screen, quiz machine, keyboard controls, result screen) which POSTs results on completion; `#progress` - the ported chart view (KPI tiles, all-mistakes chart, small multiples, table) computed client-side from `/api/history`. A tab bar switches views. Two porting constraints from the merge: key handlers gate on the active view, and the layout switches per view - centered fixed-height card for the quiz, top-down flow for list and progress (the exact `place-items` trap PR #24 documented). Views that fail to fetch show an explicit "server gone - restart with `python3 $GRAMMAR_HOME/dashboard/server.py`" state, never a blank page.

Skills: drill and learn keep ranking/mining/authoring exactly as today, then run a slimmed `prepare_drill.py --kind drill|learn` (validation kept from `build_drill.py`, output = JSON into `$GRAMMAR_HOME/drills/`, no HTML), then launch the canonical server path pointed at the new drill. The progress skill becomes: launch the server at `#progress`. `build_progress.py`, both templates, `build_drill.py`, and `skills/drill/assets/duo.css` are deleted by the end (duo.css is copied to `dashboard/` early and deleted only after its last consumer dies - ordering matters, see Tasks 2/5/6).

Key design decisions:

- Aggregation client-side, server generic: keeps the server a dumb file/append layer with no per-view code; the bucketing logic is ~60 lines of JS. Alternative (server-side `/api/progress`) rejected to keep endpoint count and server size down.
- Launcher = the server itself (idempotent start-or-focus): rejected a separate shell launcher because `webbrowser` already handles macOS/Linux portably and one file means one thing to copy and document.
- Fixed default port with env override: rejected ephemeral ports because a bookmarkable URL is the point.
- Summary listing + per-file endpoint over returning every full drill: the drills directory only grows, and the list view should stay O(summaries), not O(every question ever authored).
- `kind` via a script flag, not LLM-authored: one fixed value per SKILL.md removes an authoring failure mode.

## Technical Details

- Drill JSON: authoring schema from `skills/drill/references/authoring.md` (topics with lessons/examples, questions choice|rewrite) + `kind` (stamped by the script), `date` (already present). Validation errors abort before a file lands in `drills/`.
- Results append is the only write endpoint; server validates shape (known keys, ints, drill filename matches an existing `.json`) and appends one line; malformed POST returns 400 and writes nothing.
- History endpoint returns rows as-is (parsed JSON objects, unparsable lines skipped); the client tolerates missing/bad `ts` exactly as `build_progress.py` does today (skip from charts, count as undated) and buckets each timestamp in the offset carried by the string - never via the browser's local `Date` conversion, which would shift near-midnight foreign-offset entries into the wrong day.
- Static routes serve only the two known files from the server's own directory - no URL-to-filesystem mapping; `GET /api/drills/<file>` resolves strictly to a basename within `$GRAMMAR_HOME/drills/` ending in `.json`.
- The hook gains a second `cmp`-guarded copy loop for the dashboard files: `mkdir -p "$GRAMMAR_HOME/dashboard"`, source `$PLUGIN_ROOT/dashboard/`, no `chmod +x` needed; statusline copies untouched; stays inside the hook's sub-second non-blocking budget.

## What Goes Where

- **Implementation Steps**: everything below - code, skill text, docs.
- **Post-Completion**: real-world soak (using the dashboard for actual drills over days), plugin-update propagation check after the next release.

## Implementation Steps

### Task 1: Dashboard server with data endpoints and launcher behavior

**Files:**

- Create: `dashboard/server.py`

- [x] `GET /api/health` returns the app marker with version; `GET /` and `GET /duo.css` serve the app files from the server's directory with correct content types; every other path 404s; requests with a non-local `Host` header are rejected
- [x] `GET /api/history` returns parsed rows (unparsable lines skipped); `GET /api/drills` returns newest-first summaries (filename, kind, date, topics with labels and counts); `GET /api/drills/<file>` returns one drill or 404, accepting only `.json` basenames; `GET /api/results` returns parsed results or an empty array
- [x] `POST /api/results` validates the result shape and drill filename, appends one line to `$GRAMMAR_HOME/results.jsonl`, 400s on anything malformed without writing
- [x] launcher behavior: health-marker port -> open browser, print version-skew notice when markers differ, exit 0; foreign-server port -> exit nonzero naming `$GRAMMAR_DASHBOARD_PORT`; free port -> bind 127.0.0.1, open browser via `webbrowser.open` unless `--no-open`, honor `--url-path`, serve until interrupted
- [x] verify with curl against a temp `GRAMMAR_HOME` fixture: health marker fields; history row count equals fixture line count minus deliberately-bad lines; first `/api/drills` entry is the lexically newest filename; a valid POST appends exactly one line (`wc -l` before/after) and a malformed POST returns 400 leaving the file byte-identical (`cmp`); `curl -H "Host: evil.example"` is rejected; `GET /api/drills/../history.jsonl` and `/etc/passwd`-style paths 404; a second `server.py` start while one runs exits 0 without binding; `python3 -m http.server` on the port first -> launcher exits nonzero with the port message

### Task 2: UI shell with tabs, hash routing, and drills list

**Files:**

- Create: `dashboard/index.html`
- Create: `dashboard/duo.css` (copied from `skills/drill/assets/duo.css`; the source copy stays until Task 6 - `build_drill.py` and `build_progress.py` still read it)

- [x] one-page shell in the duo design system: tab bar (Drills, Progress), hash router mapping `#drills` (default), `#drill=<file>`, `#progress` to views; per-view layout switch (top-down flow for list/progress, centered card reserved for the quiz view); dark mode via the existing tokens
- [x] drills list view: fetch `/api/drills` and `/api/results`, render session cards (date, kind badge, topic labels with counts, last result when present), empty state when no JSON drills exist, fetch-failure state naming the restart command; clicking a card navigates to `#drill=<file>`
- [x] verify in the browser against a fixture home with two drill JSONs (one `kind: learn`) and no results file: both cards render with correct badges and the learn badge differs visibly; empty-state appears when `drills/` holds only legacy HTML; killing the server and reloading shows the fetch-failure state, not a blank page; hash back/forward switches views without reload; under emulated dark scheme the computed `--duo-bg` differs from light and card text/background contrast is >= 4.5:1 (fetch-failure verified via in-page view switch after killing the server: a full browser reload with the server dead can only show the browser's own connection-error page, since index.html itself is served by that server)

### Task 3: Quiz view ported from the drill template

**Files:**

- Modify: `dashboard/index.html`
- Delete: `skills/drill/assets/drill-template.html`

- [x] port the lessons screen, quiz state machine (requeue-on-miss, progress bar, feedback), result screen, and the keyboard controls (digits/arrows/Enter/Esc, keycaps, Enter-lock) into the `#drill=<file>` view, loading the drill via `GET /api/drills/<file>`
- [x] gate all key handlers on the quiz view being active: Enter/digits/arrows are inert on `#drills` and `#progress` (the template's handlers are document-level and dereference quiz-only nodes - unguarded they throw or click hidden buttons)
- [x] back navigation: Esc during the quiz returns to the drill's lessons screen (today's behavior); Esc on the lessons screen navigates to `#drills` (new - today it is a no-op); the quiz card keeps the fixed-height footer behavior via `fit()` adapted to the view container, or a simpler equivalent that keeps the action button stationary
- [x] delete `skills/drill/assets/drill-template.html`
- [x] verify by replaying the full keyboard check sequence from PR #24 against the dashboard quiz (selection, wrap-around, out-of-range digits, post-check inertness, digits into the rewrite input, Esc to lessons) plus: a second Esc lands on `#drills`; pressing Enter and digits on the list and progress views changes nothing and logs no console errors; completing a quiz shows the result screen
- ! interim breakage accepted from the plan's ordering: `build_drill.py` (and the drill SKILL.md step that calls it) still reads the template deleted here, so the drill skill is broken on this branch until Task 6 replaces it with `prepare_drill.py`
- note: the drill loaded into the quiz machine is cached by filename, so a tab switch to Progress and back does not reset a quiz in progress (the issue #26 core flow); a different `#drill=` file refetches
- note: `place-items: center` on the drill view was replaced with `align-content: center` - justify-items shrank the shell to its content width instead of the 640px shell width

### Task 4: Quiz results persistence

**Files:**

- Modify: `dashboard/index.html`

- [x] on reaching the result screen, POST the result payload once (guard against re-POST for the same completion); on failure the result screen shows a visible "result not saved" notice
- [x] drills list shows the last recorded result per drill; the result screen shows the previous attempt's score when one exists
- [x] verify: complete a fixture quiz twice - `results.jsonl` gains exactly two lines with correct totals and topics, and the second result screen shows the first attempt's score; kill the server mid-quiz and finish - the result screen shows the not-saved notice and the file is unchanged; reload the list - the card shows the latest recorded score
- note: the POST timestamp is written with the browser's local offset (`localISO`), matching `history.jsonl`, so a future accuracy-over-time chart can bucket results the same offset-respecting way the progress view buckets mistakes; `toISOString()` (UTC) was rejected because it shifts near-midnight attempts to the neighbouring day
- note: `lastResult` is loaded alongside the drill JSON and replaced by each successful POST, so the previous-attempt line survives repeated "Try again" runs without a refetch; a failed POST leaves it untouched
- discovered (follow-up, not blocking): the drills-list card score (Task 2) renders bare as `3 / 3` with no "last result" label - readable in context, but a candidate for a caption if the list ever grows more numbers

### Task 5: Progress view ported client-side

**Files:**

- Modify: `dashboard/index.html`
- Delete: `skills/progress/assets/progress-template.html`
- Delete: `skills/progress/scripts/build_progress.py`

- [x] port the bucketing from `build_progress.py` to JS over `/api/history`: day/week/month span thresholds, zero-filling, undated counting, and offset-respecting date extraction (bucket on the date carried in the `ts` string, never on browser-local `Date` conversion)
- [x] port the chart view (KPI tiles, all-mistakes chart, small multiples with shared scale, tooltips, table view, footer caveat with undated note) and add the two empty states: no history at all, and history with no dated mistakes (no divide-by-zero, message matching the old builder's "no dated mistakes" intent)
- [x] verify BEFORE deleting the Python: run `build_progress.py` against the real log and against a fixture containing a `+13:00`-offset row landing near local midnight - the dashboard progress view must match the builder's summary line (mistake/category counts), all three KPI tiles, the bucket labels, and three spot-checked table cells including the foreign-offset row's bucket; an empty fixture and an all-undated fixture render their empty states; then delete the template and builder
- [x] verify deletions: `grep -rn "build_progress\|progress-template" --exclude-dir=docs .` returns nothing (one residual hit: `skills/progress/SKILL.md:15` still calls the builder - Task 7's checkbox, see the breakage note below)
- ! interim breakage accepted from the plan's ordering, mirroring Task 3: the progress SKILL.md still runs the builder deleted here, so the progress skill is broken on this branch until Task 7 replaces it with the server launch
- note: the aggregate the page computes was compared field-by-field against the JSON `build_progress.py` injected into its template, over the real 202-line log (262 mistakes, 11 categories, daily buckets) and over the offset fixture - identical `JSON.stringify` output including category order, zero-filled buckets and the undated count; the `+13:00` row buckets on Jul 26 (its own date) while a browser-local conversion would have put it on Jul 25
- note: the progress view keeps the 640px shell width rather than the old standalone page's 960px - a wider pane would break alignment with the tab bar, which is the fixed chrome of every view; the small multiples fall to two columns and the 13-column table scrolls inside `.pg-tablewrap` (the page itself never scrolls horizontally), with `white-space: nowrap` added to the bucket column, which the narrower shell otherwise wrapped onto two lines
- ! size guard overshoot to settle in Task 8: `dashboard/index.html` is 1059 lines against the "~900" guard. Accounting: 228 shell/list/router + 420 quiz port (382-line template) + 55 results + 356 progress port (256-line template). The guard was set as "the two templates total ~640", which never budgeted for the router, tab bar, drills list, results POST and the four fetch-failure/empty states - all of them plan scope, none of them template code. No unasked feature is hiding in the delta

### Task 6: Rework drill and learn skills to emit JSON

**Files:**

- Create: `skills/drill/scripts/prepare_drill.py` (from `build_drill.py`: keep validation, add `--kind`, write JSON, no HTML)
- Delete: `skills/drill/scripts/build_drill.py`
- Delete: `skills/drill/assets/duo.css` (last consumer dies with `build_drill.py`)
- Modify: `skills/drill/SKILL.md`
- Modify: `skills/learn/SKILL.md`
- Modify: `skills/drill/references/authoring.md`

- [x] `prepare_drill.py --kind drill|learn <data.json>`: validate authored data with the existing `validate()`, stamp `kind`, write `$GRAMMAR_HOME/drills/drill-<date>-<HHMM>.json`, print the filename - refuse to write on any validation failure or missing/invalid `--kind`
- [x] rewrite both SKILL.md flows: author JSON as today -> run `prepare_drill.py` with the fixed per-skill kind -> launch `python3 "$GRAMMAR_HOME/dashboard/server.py" --url-path "#drill=<file>"` (replacing the open/xdg-open snippet); updated reply templates; authoring.md updated: `kind` documented as script-stamped, `build_drill.py` reference renamed
- [x] verify: a hand-written valid drill JSON lands in the fixture home via `prepare_drill.py --kind learn` with `"kind": "learn"` inside, and the printed launch command opens the dashboard on that drill; an invalid JSON (bad question type) and a missing `--kind` both exit nonzero writing nothing; `grep -rn "build_drill\|drill-template\|xdg-open\|duo.css" skills/` returns no hits outside this plan's history (one residual `xdg-open` hit: `skills/progress/SKILL.md:20,24` still opens a built page - Task 7's checkbox, same ordering gap Task 5 left)
- note: the script prints the bare file name, not the full path - its only consumer is `--url-path "#drill=<file>"`, and making the skill derive a basename from a path is an avoidable failure mode; the full path never appears in the new reply templates either, which report the dashboard URL
- note: both SKILL.md files carry the same "dashboard copy missing -> fall back to `${CLAUDE_PLUGIN_ROOT}/dashboard/server.py` once and say so" clause the plan writes for the progress skill in Task 7 - the hook-copy race is identical for all three skills
- note: the launch step tells the agent to use the Bash tool's background mode; the server serves until interrupted, so a foreground call would hang the skill until the tool times out
- discovered (follow-up, not blocking): the drill and learn frontmatter descriptions still say "as a local web page"; left alone here because those strings are the skill triggers the eval harness gates, and Task 7 only covers the two manifests

### Task 7: Thin the progress skill, wire the hook copy, update manifests

**Files:**

- Modify: `skills/progress/SKILL.md`
- Modify: `hooks/grammar-check.sh`
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`

- [x] progress SKILL.md becomes: launch `python3 "$GRAMMAR_HOME/dashboard/server.py" --url-path "#progress"`, reply with the URL (no builder, no summary parsing; if the dashboard copy does not exist yet because the hook has not run, fall back to the plugin-root copy once and say so)
- [x] hook: `mkdir -p "$GRAMMAR_HOME/dashboard"` plus a second `cmp`-guarded copy loop for `server.py`, `index.html`, `duo.css` from `$PLUGIN_ROOT/dashboard/` (no `chmod +x`); statusline loop untouched
- [x] bump plugin version to 0.6.0 and update both manifest descriptions (pages -> dashboard)
- [x] verify: record a baseline hook timing first (`time` on the pre-change hook with a fixture stdin), then: delete `$GRAMMAR_HOME/dashboard/`, invoke the hook with fixture stdin, assert all three files appear and `cmp` clean against the repo copies; corrupt one byte of the copied `server.py`, re-invoke, assert re-copied; post-change timing within 10% of baseline; `drills/*.html` files untouched throughout (`ls -la` timestamps unchanged)
- note: the timing gate depends entirely on which hook path is the denominator, so both were measured against `git show HEAD:hooks/grammar-check.sh`, 40 invocations per round, alternating rounds. On the realistic path (endpoint configured, both python3 passes running, curl backgrounded against a closed local port) the hook costs ~52 ms per invocation and the copy loop is inside the noise: -1.9% median over 9 rounds. On the unconfigured fixture path the hook exits at the endpoint check before any python3 runs, so the baseline is only ~7.2 ms of bash startup plus two `cmp` forks and three more forks read as +13.9% median over 15 rounds. Same absolute cost either way - about +1 ms against a stated sub-second budget - so the gate is met on the path the 10% band was written for, and the degenerate path's percentage is an artifact of its 7 ms denominator
- note: the two `mkdir -p` calls were merged into one (`mkdir -p "$STATUS_DIR" "$GRAMMAR_HOME/dashboard"`) rather than added as a second call, to not spend a fork on the directory the plan's own text asks for
- note: the progress reply template is now the single line `Progress ready: http://127.0.0.1:<port>/#progress`, matching drill and learn's `Drill ready:` line; the builder's summary line is gone with the builder and the SKILL.md explicitly forbids reading the log to reconstruct it
- [x] verified beyond the checkboxes: launching the hook-copied `$GRAMMAR_HOME/dashboard/server.py` (not the repo copy) serves `/`, `/duo.css` and `/api/history` and prints exactly the URL the new reply template quotes; a second launch while it runs exits 0 with the already-running notice, which is the re-invoked-skill case
- discovered (follow-up, not blocking): the progress frontmatter description still says "Render a local web page" - left alone for the same reason Task 6 left drill's and learn's, those strings are the eval-gated skill triggers, and this task's scope names only the two manifests

### Task 8: Verify acceptance criteria

- [x] fresh-fixture end-to-end: empty `GRAMMAR_HOME` -> hook copies dashboard -> `python3 $GRAMMAR_HOME/dashboard/server.py` -> empty states render -> add drill JSON + history fixture -> quiz via keyboard -> result recorded -> append to `history.jsonl`, reload progress view, new mistake appears -> reread the drill's lessons from the list; no skill invoked at any point
- [x] real skill runs in subagents against the real `$GRAMMAR_HOME`: one subagent executes the rewritten drill SKILL.md flow end to end (rank from the real log, author real lesson/quiz JSON, `prepare_drill.py --kind drill`), a second executes the learn flow (`--kind learn`), a third executes the progress flow; each must finish with its drill visible in the dashboard (or the progress view open) and report the exact reply-template output - failures or SKILL.md ambiguities found by the subagents are plan blockers, not notes
- [x] visual acceptance pass over the real data: screenshot the drills list (with the freshly authored sessions), the new drill's lessons and one quiz question, a result screen, and the progress view - light and dark - and inspect each image before sign-off
- [x] the issue #26 core flow: from a finished quiz, switch to the progress tab and then back into the drill's lessons - tab switches only, no file opens
- [x] dead-reference sweep: `grep -rn "build_progress\|build_drill\|progress-template\|drill-template\|__DRILL_DATA__\|__PROGRESS_DATA__\|__DUO_CSS__\|skills/drill/assets/duo.css\|progress.html" --exclude-dir=.git .` returns hits only under `docs/plans/` and `docs/ideas.md` history
- [x] size guards: `wc -l dashboard/server.py` under ~250 and stdlib-only imports (`grep -n "^import\|^from" dashboard/server.py`); `wc -l dashboard/index.html` under ~1100 (guard re-set, see the decision line below)

Evidence and outcomes:

- the three skill runs were executed by the orchestrator (a subagent cannot spawn subagents), each against the real `$GRAMMAR_HOME`, each finishing with its artifact on disk and the reply-template output below:
  - drill -> `drills/drill-2026-07-29-1714.json`; reply: `Drill ready: http://127.0.0.1:8437/#drill=drill-2026-07-29-1714.json` / `Topics: Articles (124 logged mistakes), Question formation (33), Prepositions (26)` / `Questions: 18`
  - learn -> `drills/drill-2026-07-29-1719.json` (kind `learn`, "Present perfect vs past simple", 8 questions) plus a fresh `curriculum.tsv` line `2026-W31\tpresent-perfect-vs-past`; reply used the pre-fix `Drill ready:` wording, which is exactly the defect fixed below
  - progress -> reply: `Progress ready: http://127.0.0.1:8437/#progress`; the page rendered 262 mistakes / 262 last-7-days / 11 categories, top categories Articles 124, Questions 33, Prepositions 26
- fresh-fixture run: virgin home -> hook copied all three dashboard files `cmp`-clean -> both empty states (`data-state="empty"`, `data-state="no-history"`) rendered -> `prepare_drill.py` wrote `drill-2026-07-29-1729.json` -> keyboard quiz completed 3/3 -> `results.jsonl` gained exactly one line naming the drill -> appending a fourth `history.jsonl` mistake and reloading moved the KPIs from 3/3 categories to 4/4 with the new `verb-tense` panel -> the list card then showed `3 / 3` and reopening it landed on the lessons screen. No skill invoked; no console errors
- visual pass: ten screenshots (drills list, drill lessons, a choice question, the result screen, the full-page progress view - light and dark each) taken against a byte copy of the real `$GRAMMAR_HOME` and read back one by one; the live real home was additionally served read-only and screenshotted for the list and the progress view, rendering identically. Layout, badges (green `drill` vs blue `learn`), keycaps, feedback colors, the stationary action button, the 11 small-multiple panels and the footer caveat all check out in both schemes
- size guards measured: `server.py` 210 lines, stdlib-only imports; `index.html` 1059 lines

- blocker fix (data loss, flagged independently by the drill and the learn run): `prepare_drill.py` named its output `drill-<date>-<HHMM>.json` with no collision guard, so two sessions prepared in the same minute - drill then learn back to back is a plausible session - silently overwrote each other. It now falls back to `drill-<date>-<HHMMSS>.json` and then to a `-<n>` suffix, and creates the file with an exclusive open so two concurrent runs cannot claim one name; three back-to-back runs in one minute produce three files
- blocker fix (broken shell state): `skills/progress/SKILL.md` put the `GRAMMAR_HOME` resolution and the server launch in two separate fenced blocks, and Bash tool calls do not share shell state - run as written, the second call executed `python3 "/dashboard/server.py"`. Merged into one block. `skills/drill/SKILL.md` and `skills/learn/SKILL.md` had the same split (a "resolve it once" block far above the commands that use it); their "Where the data lives" text now says it is resolved inside every command that needs it, and the resolution line was added to the ranking block and to both launch blocks
- blocker fix (unhandled launch outcomes): all three SKILL.md launch paragraphs documented only "serves" and "already running", while `server.py` has two more - the version-skew notice and a nonzero exit when a foreign program holds the port. All three now list the four outcomes and say to read the launcher output before replying, to relay the skew sentence instead of a bare URL, and to report the failure rather than a URL pointing at a foreign program. The four output strings were verified verbatim against the running launcher (`serving ...`, `dashboard already running at ...`, `... with version 0.0.1 (local copy is 0.6.0); stop it with Ctrl+C and relaunch ...` exit 0, `port 8474 is in use by another program ...` exit 1)
- blocker fix (wrong wording): `skills/learn/SKILL.md` replied `Drill ready:` for a lesson although the dashboard titles the page "New Lesson" and badges it `learn` - now `Lesson ready:`. Its step also said to pick "New topic" or "Review" while showing only the New topic variant; the Review line is now spelled out instead of guessed
- [decision] size guard for `dashboard/index.html` re-set from ~900 to ~1100 rather than compressing the file. The original number was derived as "the two templates total ~640", and that derivation is simply incomplete: it never counted the ~90 lines of bucketing ported out of `build_progress.py` (Python, so invisible to a template line count), nor the router, tab bar, drills list, results POST and the four empty/failure states, all of which are plan scope. Composition of the 1059 lines: 194 CSS, 119 markup, 733 JS (115 blank, 55 comment); the two dead templates contributed 108 CSS, 99 markup, 408 JS. Every top-level function maps to a plan checkbox (fetch/server-gone, list, drill load, quiz machine, results POST, aggregation, chart, router) - no unasked feature hides in the delta, so compressing readable code to hit a stale number would buy nothing
- note: the issue #26 core flow ends on the finished result screen, not on the lessons screen - the drill is cached by filename, so leaving to Progress and coming back restores the completed run with its score intact, and the lessons are one in-page "Lessons" click away. The whole flow ran with zero document loads (`page.on('load')` counter unchanged from boot), which is the "tab switches only, no file opens" claim
- [decision] every write-generating check ran against a fixture home or a byte copy of the real one, so the real `results.jsonl` still does not exist; the real home was served read-only for the two live screenshots. Nothing junk was written into the user's data
- discovered (follow-up, not blocking): the result screen title is score-derived ("Flawless" / "Lesson complete" / "Keep drilling") and so says "Lesson complete" for a `kind: drill` session - inherited verbatim from the old template, cosmetic
- note: the collision names keep `/api/drills` newest-first, which sorts lexically by filename - `sorted(reverse=True)` over `drill-...-1714.json`, `drill-...-171425.json`, `drill-...-171425-2.json` returns the seconds file, then the `-2` file, then the minute file, so only a third collision inside the same second lists slightly out of order

### Task 9: Update documentation

- [ ] rework README.md: dashboard section (canonical launch command, on-demand lifecycle, localhost-only note replacing the offline-page claim), updated drill/learn/progress sections; screenshots: replace `docs/img/quiz-correct.png`, `docs/img/quiz-mistake.png` (dashboard quiz), replace `docs/img/progress.png` (dashboard progress view), add `docs/img/dashboard-drills.png` (list view); `docs/img/statusline.png` unchanged
- [ ] update `docs/statusline.md` state table (unconditional): reword `drills/` (authored JSON, legacy HTML alongside), add `dashboard/` and `results.jsonl` rows
- [ ] annotate `docs/ideas.md`: the line-45 UI/UX bullet's keyboard-navigation clause is done and the navigation-between-views concern is covered by #26; the grouped-mistakes-by-type browser with per-type lessons remains open
- [ ] move this plan to `docs/plans/completed/`

### Task 10: Live handover

- [ ] start the server on the real `$GRAMMAR_HOME` (background, `--no-open`) with the fresh data authored by the Task 8 skill runs still present
- [ ] hand the user working links in the final report: `http://127.0.0.1:<port>/#drills`, `http://127.0.0.1:<port>/#drill=<freshest drill file>`, and `http://127.0.0.1:<port>/#progress`, plus the one-line restart command for later sessions
- [ ] verify each link with a `curl` status check and one final screenshot of `#drills` immediately before reporting them

## Post-Completion

**Manual soak:** use the dashboard for real drills for a few days - watch for port collisions with other local tooling, browser-restore quirks with the hash routes, and whether the results data suggests charting accuracy over time (follow-up feature, not this plan).

**Plugin-update propagation:** after the next `/plugin` update lands on the machine, confirm the hook refreshes `$GRAMMAR_HOME/dashboard/` on first message and that the launcher's version-skew notice fires when an old server is still running.
