# Native patcher test report — 2026-10-22

Earlier sections record their individual verification runs. The review-fix section at the end gives the latest environment and results.

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

### Historical blockers in the token-measurement revision

The live mixed-model run and the Build-only baseline (`scripts/stage-commit-smoke.py`, then `scripts/build-only-baseline.py`) were **not run** in this revision. At verification time `brew info opencode` reported the formula as not installed, `~/.omlx/settings.json` was absent, nothing answered on port 8000, and the database held no session newer than 11 October; the session IDs quoted earlier in this report are not present in it. The smoke-script integration and the baseline script are therefore syntax-checked and unit-tested at the verifier level only. Until both scripts run on a machine with OpenCode 2.1.2, OpenAI authentication and the local oMLX endpoint, no token-saving number is claimed.

## Live usage plugin (2026-10-22, later revision)

`plugin/agent-usage/` adds an OpenCode 2.1.2 plugin directory with a server entry (`server.js`, Promise API) and a TUI entry (`tui.tsx`). Both import the pure `src/usage-analysis.js`, which was split out of `src/usage.js` so no Node-only module is loaded under Bun; the SQLite loader takes an injected driver for `bun:sqlite`.

API facts were read from the v2.1.2 source tree, not from the published docs, which still describe the older `event`-hook style: a plugin module exports a default definition with an `id` and a `setup(context)` function; local plugins are discovered as files or directories under `plugin/` or `plugins/` in each config root, with `server`/`index` and `tui` entrypoints resolved per directory; session completion is signalled by `session.execution.succeeded|failed|interrupted` events carrying `sessionID`; the TUI context exposes `data.session.list/get/root/family/status`, `data.session.message.list/sync`, `data.on(eventType)`, `ui.router.register`, `ui.slot({append:"sidebar.content"})`, `ui.toast.show({title,message,variant,duration,sessionID})` and `keymap.layer` with slash and palette commands.

Automated: `npm test` now runs **48 passed, 3 skipped**. New tests cover SDK-shaped tree building (Effect DateTime timestamps, subagent dispatch records, prompt text excluded), the agent/model/instance hierarchy, the summary line, the report writer (root only, text/json/latest files, no secrets), the injected-driver path, and `plugin install|status|uninstall` for global and project scopes including refusal to replace or remove a directory the tool did not create. `server.js` parses under Node; `tui.tsx` transforms and bundles its relative imports with esbuild.

### Historical plugin verification limits

During that revision OpenCode was not installed, so none of the following ran: plugin discovery of the symlinked directory, loading `tui.tsx` through OpenCode's runtime JSX support, the `/usage` page and sidebar rendering, the completion toast, `ctx.event.subscribe` in the server half, and `bun:sqlite` reading the live database while OpenCode holds it open. The first run should check the OpenCode log for `loading plugin` lines naming `agent-usage`, then open `/usage` during a delegated session.


## Deep-review corrections — 2026-10-22

This section supersedes earlier environment and verification claims. OpenCode 2.1.2 is installed in this environment; the saved mixed-model session is present and readable. Older absent-runtime reports above describe earlier revisions.

Recovery now supplies restored field descriptors to native validation, preserves concurrent editor bytes on failed or successful validation, and retains the transaction on conflict. Effective permission validation checks overlapping action/resource patterns using OpenCode's wildcard semantics, including `?`, optional command suffixes, path normalization and home expansion. Restored agents inherit global permission layers, portable Plan paths, disabled-state behavior and shallow request header/body merges; decoded property ordering does not affect validation. Inactive models on disabled restored agents do not require availability. Undo runs independently of discovery/version gating and distinguishes disk recovery from native-validated recovery when the executable or API is unavailable. Inherited Markdown and server-expanded environment/file references are reported as unverifiable when the client cannot independently establish the effective source; known literal/source/runtime mismatches remain errors. Plugin install/uninstall dry-runs do not create directories or change links, including project scope. Checkout paths containing spaces, percent signs and hash characters resolve correctly.

Usage is accumulated per message identity (session, agent, model/variant and provider class), with separate compaction records, native errors/retries and per-message pricing. Partly unknown message costs keep aggregate cost unknown. Unknown provider IDs are explicitly unknown. Weighted tokens are rounded per message and conserved across identity, session and class totals; contributing session counts overlap across groups when a session changes identity. The A–D efficiency grade was removed. Routing status is descriptive; possible General-to-Build handoffs do not imply failure or duplicated work.

The saved mixed-model fixture was inspected read-only with the corrected analyzer: four sessions, 31 turns, 59,665 weighted tokens (38,459 cloud and 21,206 local). No matched accepted baseline is available, so this is evidence of observed routing, not token or cost savings. Cloud costs remain unknown without pricing.

The baseline harness now enforces acceptance independently, cancels captured native sessions on client timeout, and has no import-time workload. The plugin carries its selected root through route data and displays unknown-provider and both cache token categories. A private OpenCode 2.1.2 TUI test with only the installed symlink verified discovery, TSX rendering and the originating-session page. The production server setup wrote JSON/text/latest reports through Bun SQLite from a synthetic completion event. The fixture database contained zero messages, confirming that check made no generation requests. Natural model-completion event delivery remains unverified; native newest/back interactions are covered by navigation helper regressions rather than visual assertions.

### Test execution incident

A regression that imported the original baseline script exposed its import-time workload before a main-entry guard had been added. It unexpectedly launched two disposable OpenAI Build sessions. Both clients were terminated and both backend sessions were explicitly interrupted; their final assistant records confirm aborted execution. The sessions recorded 25,322 input tokens, 708 visible output tokens, 221 reasoning tokens and 40,192 cache-read tokens in total; recorded dollar cost was unavailable. They are not accepted baseline results. No production configuration or service/port settings were changed. The workload is now behind `if __name__ == "__main__"`; import testing uses a tripwire that forbids subprocess execution.


### Independent review

A fresh reviewer checked the combined diff and focused regressions. Additional findings concerning global permissions, portable Plan paths, disabled agent overrides, request map merging and native reference expansion were corrected and rechecked. No concrete material findings remained in the final review. Natural inference-completion event delivery remains outside the verified plugin coverage.


### Final verification after all corrections

- `RUN_NATIVE_TESTS=1 RUN_LOCAL_TESTS=1 OPENCODE_PLUGIN_TESTS=1 npm test`: **123 passed, zero failed or skipped**, 136.26 seconds. This includes native configuration/undo, shadowed-prompt rejection, authenticated local-provider registration, the private native plugin runtime check, baseline acceptance and cancellation regressions, and all usage/recovery tests.
- `python3 test/terminal.py`: **3/3 passed** (dry-run, cancellation, authenticated local-provider dry-run); no configuration created.
- `python3 -m py_compile scripts/*.py test/terminal.py`: passed.
- `git diff --check`: passed.
- Independent review: no remaining concrete material findings after corrections and targeted rechecks.

Inspectable local evidence: `artifacts/review-fixes-tests.txt`, `artifacts/review-fixes-terminal.json`, `artifacts/review-plugin-runtime.json`. Production configuration was not applied and no commits were staged or pushed. The accidental interrupted runs above are the only new cloud runs in this work; they do not establish a valid matched baseline or known dollar cost.


## Natural completion-event verification — 2026-10-22

This verification supersedes the earlier synthetic-only completion limitation. The genuine OpenCode 2.1.2 server stream and TUI data events were observed in an isolated private runtime with the installed production plugin symlink. No event emitter, fake completion iterable or production setup wrapper was used.

Two defects were reproduced before correction:

1. A successful standalone CLI execution delivered `session.execution.succeeded` but wrote no usage report: the plugin's 750 ms sleep was cancelled by CLI shutdown. Reporting now writes synchronously when the terminal event is received; native execution lifecycle events follow committed records.
2. A separate fast execution within the same session was suppressed by the two-second notification cooldown. The report/sidebar updated but the visible toast retained the previous totals. Session-wide cooldowns were removed from both server and TUI handlers; every terminal execution produces its own checkpoint/notification.

The live local-Qwen regression checks CLI report totals against SQLite before launching the TUI, then completes two TUI requests in the same session and reads the rendered terminal screen to verify both toasts contain fresh totals. The latest successful completion gap was **528 ms**. A further execution was stopped through OpenCode's public native interrupt API; real `session.execution.interrupted` reached both observers and rewrote the report. A private run with an intentionally invalid local API key produced real `session.execution.failed` and a report for that new session. Only the existing loopback oMLX provider was used; no cloud model or production configuration was changed.

Success, failure and interruption are verified on the server. Success and interruption are verified through the TUI's native event listener, with visible success toasts checked against final SQLite tokens. Failure was exercised in the standalone CLI, not visually in the TUI. This is event-delivery and persistence evidence, not a model-quality or savings benchmark.

Reproduce explicitly with `OPENCODE_COMPLETION_TESTS=1 node --test test/plugin-completion.test.js`. The harness is opt-in and its import test forbids subprocess/network work. Credentials exist only in a temporary private file; fixture processes and private server descendants are cleaned up. A small terminal screen reader handles cursor-only toast updates so a repaint is not mistaken for a missing message.

Focused verification after corrections: **4/4 passed**, zero skipped, in 4.95 seconds. Evidence: `artifacts/natural-completion.json`, `artifacts/natural-completion-tui.txt`, `artifacts/natural-completion-focused.txt`. Fresh independent review found no remaining concrete defects in this change.

Final combined verification: `RUN_NATIVE_TESTS=1 RUN_LOCAL_TESTS=1 OPENCODE_PLUGIN_TESTS=1 OPENCODE_COMPLETION_TESTS=1 npm test` — **127 passed, zero failures or skips**, 136.31 seconds. The strengthened natural smoke then passed **4/4**, including the explicit 528 ms follow-up gap and the CLI-before-TUI SQLite comparison. Python compilation and `git diff --check` passed. Full output: `artifacts/natural-completion-tests.txt`.


## Matched baseline execution — 2026-10-22

The mixed-model and Build-only scripts have now both run on the same two-stage fixture and passed independent acceptance. This supersedes earlier statements that no accepted matched baseline exists. See [the full comparison](baseline-comparison.md) for token categories, timings, exact commit SHAs and method limits. Mixed completed in 211.785 seconds; the accepted Build retry completed in 61.507 seconds. The first Build attempt timed out and was explicitly interrupted at five minutes; it remains in the evidence and total effort. Summed Build attempt time was 361.587 seconds. Raw tokens reconcile independently with SQLite; actual dollar costs remain unavailable. Both results passed three/four-test commit replay, red regression validation, matching patch evidence, 637 additional integer cases and scope/route checks.

Post-benchmark repository check: `npm test` — **124 passed, zero failed, five opt-in live checks skipped**, 137.10 seconds; focused baseline tests — **20 passed**.


## Local-first optimization and fresh comparison — 2026-10-22

The optimized coordinator and single worker ran on local Qwen and completed the same two-stage task in **60.969 seconds with zero recorded cloud tokens**. Fresh native Build-only completed in **61.639 seconds**, recording 5,135 cloud input, 1,650 output, 105 reasoning and 67,072 cache-read tokens. Both passed independent commit replay, effective red regression checks, four final tests, 637 additional integer cases, exact scope/model checks and direct SQLite token reconciliation. There was one inference run per approach; no new timeout or retry. The prior 211.785-second mixed pipeline and its old Build timeout remain archived. See [the full local-first comparison](local-first-comparison.md) for costs, limits, guard behavior and evidence.

Post-change verification: **50 focused checks passed**; `npm test` completed with **129 passed, zero failed, five opt-in live tests skipped** (137.22 seconds). Python/JavaScript syntax checks and `git diff --check` passed. The matched comparison was reverified read-only after the harness fixes; no extra inference runs were needed.


## Corrected role policy — 2026-10-22

The all-local recommendation above was withdrawn: it does not satisfy the requested quality boundary. Sol owns planning, coordination and final review; Qwen performs bounded execution only. `examples/mixed-workers.json` assigns Orchestrator/Plan/Review plus substantive context synthesis to cloud models, and General/Explore/Title to local Qwen. Cloud Build/review remain callable. Routine work is planned and reviewed in one cloud session with one local assignment, retaining the overhead reduction without replacing cloud judgment. See [the corrected comparison](cloud-led-comparison.md).

Corrected fresh pair passed all independent checks: Sol-led/Qwen-worker mixed **122.795s**, native Build **61.802s**. Mixed cloud counters: input **6,493**, output **756**, reasoning **0**, cache read **6,400**; Build: input **12,455**, output **1,349**, reasoning **83**, cache read **73,088**. Mixed used 47.9% fewer recorded cloud input tokens and took 1.99× as long, with Sol retaining planning and final review. Both committed stages, regression replay, 637 extra cases and direct SQLite reconciliation passed. Actual dollars remain unavailable.

Final repository verification: **53 focused checks passed**; `npm test` — **132 passed, zero failed, five opt-in live checks skipped**, 135.34 seconds. Python/JavaScript syntax checks and `git diff --check` passed.

## Final save, application and capture verification — 2026-10-22

Fresh `npm test`: **133 passed, zero failed, five opt-in checks skipped**, 134.89 seconds. Those opt-in checks were exercised separately: native runtime/local-provider/plugin checks **4/4 passed**; natural completion checks **4/4 passed**, including real success, failure, interruption and a **531 ms** follow-up completion gap. The native plugin rendering check passed again after the sidebar wrapping fix. No cloud inference was used during this save/commit/capture task.

The balanced global configuration and plugin installation were rechecked against native effective agents: all selected model variants, Standard service tier, disabled warming and the plugin symlink matched. A private, no-inference native runtime confirmed future Build baselines cannot inherit enhanced global instructions or custom roles. Matched benchmark replay and SQLite reconciliation passed again; no benchmark generation was repeated. Python compilation, plugin JavaScript syntax and `git diff --check` passed.

Actual PTY captures of the completed benchmark show the compact widget and `/usage` detail page. Separating model labels from totals keeps `7,889` together at the native sidebar width. Opening the panel did not change the database message count. macOS desktop capture was unavailable; [image provenance](images/README.md) documents the real terminal-output capture and rendering. Sanitized measurements, active settings, completion evidence and verification records are saved under `docs/benchmarks/`. Private credentials and raw session logs were not added to Git.
