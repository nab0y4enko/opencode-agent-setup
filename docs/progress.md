# Implementation progress

Design approved; implementation authorized directly in user message.
Ruling: execute inline without an extra approval handoff because the user explicitly requested installation, implementation and tests after approving the design.
Ruling: keep this dedicated non-Git workspace rather than create an unrelated checkout. Use Node ESM JavaScript with JSDoc and Node's test runner to avoid a build requirement; JSONC and terminal libraries remain dependencies.

Completed: Homebrew CLI installation; runtime baseline and schema discovery; policy/model choices; transactional JSONC storage and undo/reset; interactive wizard; launcher installation.
Review findings fixed with regression tests: empty custom role after undo, undo-preview race, effective prompt shadowing, credential masking, existing role preservation, local model inventory/auth validation, and loopback validation before credential access/request with redirect refusal.
Ruling: use a referenced private key file after explicit wizard confirmation for local provider credentials, because the already-running shared service does not inherit newly exported shell variables. No service restart or port reconfiguration required.
Verified: 24/24 automated/native/local-registration tests; 3/3 real PTY flows; npm audit zero vulnerabilities. Real Splash worker: 3/3 tests in 11.69 seconds. Shipped Orchestrator+General templates: one foreground dispatch, no coordinator edit/shell calls, 3/3 tests in 39.14 seconds; both agents local Qwen for this test.
Limitation: OpenAI inference integration awaits native OpenAI authentication. No global agent selections were applied; the user runs the wizard to review/select models and exact prompt changes.

## Revision: stage checkpoints and stronger agent contracts

User authorized prompt revision, callable Build escalation and isolated tests; production apply remains pending review.
Stage 1 self-check: preserved native Explore instructions; Build mode all plus explicit Orchestrator allow; prevent Build/Orchestrator recursion; bounded General has no nested dispatch. Implementers inspect Git state, verify and self-review before explicit-path stage commits; blocked validation is not completion, unrelated staged/user edits require context, no pushes/amends/reset/identity changes.
Stage 1 validation: RUN_NATIVE_TESTS=1 RUN_LOCAL_TESTS=1 npm test -> 26 passed; python3 test/terminal.py -> 3 passed. No port settings changed.
Stage 2 review corrections: serialize shared-index writers or use separate worktrees; permit resolving BLOCKED through escalation while forbidding dependent-stage advancement. Strengthen staged-user-work stop rule after a real negative test showed the earlier wording permitted a pathspec commit.
Stage 2 tests: 32/32 full automated/native/local checks, 3/3 PTY flows; real mixed Sol/Qwen pipeline produced two separate stage commits, 4/4 independent tests and cloud PASS; external verifier checked actual model routing/commit scopes. Updated negative test returned NEEDS_CONTEXT with HEAD/source/index unchanged. No production apply or port changes.

Canonical working repository: /Users/oleksii.naboichenko/Projects/opencode-agent-setup. Imported the original three commits into its native-patcher branch while preserving the preconfigured origin. Relinked the installed command to this checkout; npm ci/audit clean, 32/32 automated/native/local checks and 3/3 PTY flows passed from the new location. No push, production apply or port change.

## Revision: token measurement

Added the read-only `usage` command (session tree, per-class/agent/model token totals, dispatches, escalations, findings, grade, comparison) built on OpenCode's session database; wired it into the stage smoke test and verifier; added a Build-only baseline script. 43/43 automated tests pass, 3 live tests skipped. Live mixed-versus-baseline comparison is blocked here: OpenCode and oMLX are not installed on this machine at the time of this revision. Nothing committed or applied to production configuration.

## Revision: live usage plugin

Added `plugin/agent-usage/` (TUI page `/usage` with agents -> models -> instances and live tokens, sidebar block, completion toast; server half writes the end-of-session report) and `opencode-agent-setup plugin install|status|uninstall`. Pure analysis split into `src/usage-analysis.js`. 48/48 automated tests pass; runtime behaviour inside OpenCode is unverified on this machine (OpenCode not installed).


## Revision: deep-review fixes and independent double-check

Resolved recovery races and restored-field validation; effective wildcard permissions and configuration inheritance; message-level usage attribution, compaction, errors and partial pricing; misleading efficiency grades and assumed failed escalations; plugin root selection, dry-runs and encoded checkout paths; and strict baseline acceptance/import/timeout safety. Added source-compatible handling for disabled overrides, request maps and server-expanded references. Rechecked in a fresh independent review with no concrete material findings remaining.

Final combined native/local/plugin suite: 123 passed, no failures/skips. PTY flows: 3/3 passed. Private native symlink plugin test rendered the originating session and wrote reports from a synthetic completion event with zero messages. Natural completion delivery remains unverified. The initial baseline import test accidentally launched two cloud fixture runs; both were interrupted, and a subprocess tripwire plus guarded entry point now protects imports. Full details and evidence paths are in test-report.md. No production apply, staging or push.


## Revision: natural completion delivery

Verified real OpenCode lifecycle events with local Qwen in isolated private runtimes. Fixed missing standalone CLI reports by removing the delayed write; fixed stale rapid follow-up toasts by removing per-session cooldowns. Natural server success/failure/interruption now produce reports; TUI success/interruption events were observed and both rapid success toasts matched persisted totals (528 ms gap). Added opt-in live regression plus import/cleanup/screen-reader safeguards. See the latest test-report section and natural-completion artifacts for coverage and final suite results.

Final native/local/synthetic/natural suite: 127/127 passed, zero skips/failures. Strengthened natural-focused suite: 4/4; independent scoped review clear. Full output: artifacts/natural-completion-tests.txt.

- Ran the matched two-stage mixed/Build benchmark and independently verified both accepted outcomes against Git, test replay and native SQLite counters. Retained the first Build timeout and its usage; see `docs/baseline-comparison.md`. Added comparable execution timing, safe mixed-harness imports and a read-only comparison script with explicit failed-attempt inclusion.

- Optimized mixed to local Qwen coordination plus one context-preserving local worker; removed forced cloud stage/review calls, gated paid escalation and added the local-first example. Fresh same-task verification passed on both paths: local-first 60.969s/zero cloud counters, native Build 61.639s. Fixed omitted-foreground capture and permitted read-only tool verification without repeating inference. See `docs/local-first-comparison.md`.

- Corrected the overbroad local routing: Sol owns planning, coordination and final review; Qwen only executes bounded work. Cloud roles remain callable. Kept one context-preserving local assignment and review in the existing cloud session to reduce duplicated context. Withdrew the all-local recommendation and replaced its example with `examples/mixed-workers.json`.

- Reverified the corrected cloud-led profile against a fresh Build baseline: mixed 122.795s / 6,493 cloud input, Build 61.802s / 12,455 cloud input. Sol performed planning/review in one cloud session; Qwen performed the implementation stages. Both independent acceptance checks passed.

- Activated the user-approved balanced profile globally with transactional native validation: Orchestrator/Plan/Summary/Compaction Sol medium, Build/reviewer Sol high, local Qwen workers, explicit Standard request tier and warming off. Effective settings verified globally and in this repository; credentials remain in a private file. See `docs/balanced-profile.md`.

## Saved and globally applied — 22 October 2026

The balanced cloud-led profile is active globally: Sol medium plans and reviews; local Qwen performs bounded implementation and exploration; Sol high remains available for difficult implementation and independent review. OpenAI roles explicitly use Standard service tier and warming is disabled. The usage plugin is installed globally as a link to this checkout. Fresh native discovery verified every selected model/variant and the plugin link.

Saved the sanitized matched benchmark receipt and actual terminal captures under `docs/benchmarks/` and `docs/images/`. Capturing the completed session added no messages or inference. Desktop screenshot access was unavailable; image provenance documents the native PTY capture and terminal rendering.

Future Build baselines isolate global configuration and use a private server to preserve native instructions and permissions after profile activation. A regression test and a no-inference native API check verified the isolation. Raw runtime logs and private credentials remain outside the committed evidence.


## Raw usage and review dashboard — 22 October 2026

Implemented the approved sidebar/dashboard design with raw counters, qualified costs, elapsed/recorded timing, actual model history, current selection, configurable-role visibility, and review source navigation. The global plugin link serves this checkout; fresh OpenCode instances load the redesign. All 154 final checks passed with native/local/plugin/completion coverage, alongside 44 focused checks and independent SQLite verification of the captured benchmark. No cloud generation was used. See `docs/usage-widget.md` and the saved terminal captures.
