# Native patcher test report — 2026-10-22

## Installed

- Homebrew `opencode` 2.1.2.
- `opencode-agent-setup` launcher linked to this workspace.
- No OMO or OpenCode desktop installation.
- No real global agent overrides applied; the wizard is ready for interactive selection.

## Automated and runtime tests

`RUN_NATIVE_TESTS=1 RUN_LOCAL_TESTS=1 npm test`: **24 passed, zero failed or skipped** in the recorded full run. Coverage includes model/variant rejection, native prompt preservation, private credentials, JSONC comments, exact undo, modified-file undo, custom-agent removal, writer locks, malformed config, symlink targets, validation rollback, credential masking, existing custom-role preservation, native runtime loading, effective permission/model/system settings, shadowing rejection, authenticated local provider registration, loopback enforcement before sending credentials, and redirect refusal.

`python3 test/terminal.py`: **3 passed**. Native and authenticated local-provider wizard dry runs showed the General enhancement and saved no configuration; cancellation also saved none.

`npm audit --omit=dev`: zero vulnerabilities at verification time.

## Real local inference

The active local Splash alias was `qwen-3.8-nf-splash` on the existing port 8000. Tests used disposable fixture projects, not Tiviary.

| Run | Result | Elapsed |
|---|---|---|
| Direct General/Qwen worker | Fixed clamp implementation; 3/3 unit tests passed; independent rerun passed | 11.69 s |
| Shipped custom Orchestrator → General, both using Qwen for this test | One foreground child dispatch; no coordinator edit/shell calls; 3/3 tests passed; independent rerun passed | 39.14 s |

The coordinator run used the actual shipped prompt and permission templates. Parent session `ses_e9b4fd8c0ffeZGv6jj2G97Ily7`; General child `ses_e9b4fa358ffe3iHiw3XrSZS1Mp`. Both session records identify `omlx/qwen-3.8-nf-splash`.

An initial local test failed before inference because its inherited PWD pointed to the parent workspace, where the local provider was not configured. The test harness now sets both cwd and PWD explicitly and waits for model registration. Failed fixture assertions were recorded as failures, not passes.

## Limits

- OpenAI authentication is absent, so actual OpenAI coordinator/reviewer inference remains untested. Configured native model routing was tested using available catalog entries without cloud inference.
- This is a functional fixture test, not a macOS UI-test run, throughput benchmark, token-savings estimate, 256K context stress test or shared-concurrency benchmark.
- The native service address observed after installation and at verification was unchanged at `http://127.0.0.1:49374`; oMLX stayed on port 8000. No port setting was edited.
- Foreground execution and retry discipline are prompt policies. Permission records deny coordinator edits/shell, but this run did not deliberately provoke forbidden operations.

Artifacts: `artifacts/test-results.txt`, `artifacts/terminal-results.json`, `artifacts/direct-worker-result.json`, `artifacts/coordinator-delegation-result.json`, `artifacts/live-local-worker.jsonl`, and `artifacts/prompt-changes.diff`.

## Revised policies and commit checkpoints

The expanded templates are in `src/prompts.js`, with native configuration construction in `src/policy.js`. Build remains a primary-capable agent and now also supports subagent dispatch (`mode: all`); Orchestrator explicitly allows Build. Child Build instructions prohibit nested delegation; Build cannot delegate back to itself or Orchestrator.

The revised contract includes structured handoffs, hypothesis-based debugging, evidence-based self-review, explicit completion statuses and one verified commit per completed implementation task/stage. Shared-checkout writers are serialized; concurrent writers require separate worktrees. Any unrelated staged changes or existing user edits to owned files require NEEDS_CONTEXT before editing. These are model instructions, not a runtime Git transaction guard.

Final revision checks: **32/32 automated/native/local-registration tests passed**, zero skipped; **3/3 PTY flows passed**. `scripts/verify-stage-result.py` independently enforces live-test acceptance and exits nonzero for missing commits, wrong routing, failed tests, dirty source state or missing PASS review.

### Real mixed-model stage test

Disposable repository: `/private/var/folders/s4/5c9zv68s2d3dhs64z58w09t80000gn/T/native-stage-check-hgq05wl0/repo`.

- General used `omlx/qwen-3.8-nf-splash` and committed stage 1: `705ffca9a45424323b76df22d1c1a269ce8eb5c2`, changing only `fixture.py`; 3 tests passed.
- Build used `openai/gpt-6.1-sol#high` and committed stage 2: `d4f54b82b637a66d1e859eec79102c5c73220bca`, changing only `fixture.py` and its tests; an inverted-bounds regression failed before the fix, then all 4 tests passed.
- Cloud reviewer used `openai/gpt-6.1-sol#high` and returned PASS after inspecting source/patch/log artifacts. It accurately disclosed that it did not independently verify Git history or rerun tests.
- The external harness independently checked both commits and file scopes, clean source Git status, actual child-session model records, foreground dispatches and a fresh 4-test pass. Its verification passed. Total job time: 156.08 seconds, including local/cloud inference, execution and review. This is not a throughput benchmark.

### Negative staged-user-work test

The first wording permitted an interpretation using a pathspec commit: Qwen committed its docstring change while preserving the unrelated staged diff. That did not satisfy our stricter intended stop rule. The contract was clarified to prohibit this bypass explicitly.

Retest with the clarified General contract: **passed**. Qwen returned NEEDS_CONTEXT; HEAD, the task-owned source file and the user's staged diff all remained unchanged. This is evidence for this tested scenario, not a guarantee that every future model run obeys the prompt.

Artifacts: `artifacts/revision-tests.txt`, `artifacts/revision-terminal.json`, `artifacts/stage-commit-result.json`, `artifacts/stage-verification.json`, `artifacts/staged-conflict-result.json`. Earlier OpenAI-authentication limitations above describe the first installation test and are superseded by this successful authenticated mixed-model test.

No production agent configuration was applied, no port setting changed, and no commits were pushed. The previous final prompt preview is superseded by the revised review artifact.

## Token measurement (2026-10-22, later revision)

`src/usage.js` adds the `usage` command. It reads `session_v2` and `session_message` from OpenCode's SQLite database through Node's built-in `node:sqlite` in read-only mode. Per-turn token counts (input, output, reasoning, cache read/write), agent, model, cost, finish state, compaction markers and subagent dispatch records (child session ID, agent, background flag) all come from OpenCode's stored assistant messages; per-session totals matched the summed turns on real data within the rounding OpenCode itself applies.

Automated: `npm test` now runs **43 passed, 3 skipped** (the skipped tests are the live native/local checks that need `RUN_NATIVE_TESTS`/`RUN_LOCAL_TESTS`). The 14 new tests cover weighting, class/agent/model totals, grade movement, each finding, recorded-versus-priced cost, dispatch deduplication, the SQLite loader against a fixture database with the production schema, credential-free output, and the CLI (`--session`, `--directory`, `--list`, `--json`, `--compare`, missing-session failure). The stage verifier now also fails when the usage report is missing, when General tokens are not local, when all weighted tokens are cloud, or when any dispatch ran in the background.

Real-data check: the report was run read-only against this machine's existing database (169 sessions). A 11 October Build session that dispatched Explore and General children on OpenAI rendered correctly after one fix: OpenCode repeats a background dispatch's tool part in later turns, which first produced 20 dispatch rows for 4 children; records are now deduplicated by child session ID. That session grades D (cloud share 100%, workers on a cloud model, all dispatches background), which is the shape this setup is designed to change.

### Blocked on this machine

The live mixed-model run and the Build-only baseline (`scripts/stage-commit-smoke.py`, then `scripts/build-only-baseline.py`) were **not run** in this revision. At verification time `brew info opencode` reported the formula as not installed, `~/.omlx/settings.json` was absent, nothing answered on port 8000, and the database held no session newer than 11 October; the session IDs quoted earlier in this report are not present in it. The smoke-script integration and the baseline script are therefore syntax-checked and unit-tested at the verifier level only. Until both scripts run on a machine with OpenCode 2.1.2, OpenAI authentication and the local oMLX endpoint, no token-saving number is claimed.

## Live usage plugin (2026-10-22, later revision)

`plugin/agent-usage/` adds an OpenCode 2.1.2 plugin directory with a server entry (`server.js`, Promise API) and a TUI entry (`tui.tsx`). Both import the pure `src/usage-analysis.js`, which was split out of `src/usage.js` so no Node-only module is loaded under Bun; the SQLite loader takes an injected driver for `bun:sqlite`.

API facts were read from the v2.1.2 source tree, not from the published docs, which still describe the older `event`-hook style: a plugin module exports a default definition with an `id` and a `setup(context)` function; local plugins are discovered as files or directories under `plugin/` or `plugins/` in each config root, with `server`/`index` and `tui` entrypoints resolved per directory; session completion is signalled by `session.execution.succeeded|failed|interrupted` events carrying `sessionID`; the TUI context exposes `data.session.list/get/root/family/status`, `data.session.message.list/sync`, `data.on(eventType)`, `ui.router.register`, `ui.slot({append:"sidebar.content"})`, `ui.toast.show({title,message,variant,duration,sessionID})` and `keymap.layer` with slash and palette commands.

Automated: `npm test` now runs **48 passed, 3 skipped**. New tests cover SDK-shaped tree building (Effect DateTime timestamps, subagent dispatch records, prompt text excluded), the agent/model/instance hierarchy, the summary line, the report writer (root only, text/json/latest files, no secrets), the injected-driver path, and `plugin install|status|uninstall` for global and project scopes including refusal to replace or remove a directory the tool did not create. `server.js` parses under Node; `tui.tsx` transforms and bundles its relative imports with esbuild.

### Not verified

OpenCode is not installed on this machine, so none of the following ran: plugin discovery of the symlinked directory, loading `tui.tsx` through OpenCode's runtime JSX support, the `/usage` page and sidebar rendering, the completion toast, `ctx.event.subscribe` in the server half, and `bun:sqlite` reading the live database while OpenCode holds it open. The first run should check the OpenCode log for `loading plugin` lines naming `agent-usage`, then open `/usage` during a delegated session.
