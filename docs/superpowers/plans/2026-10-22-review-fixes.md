# Review fixes implementation plan

> **For agentic workers:** Use superpowers:executing-plans for each assigned bounded fix. Use failing behavioral regression tests before production changes.

**Goal:** Resolve every finding in the deep review and independently check the integrated result.

**Architecture:** Retain the native configuration patcher and shared pure usage analysis. Make recovery conservative, account for usage per message, describe routing without claiming savings, and preserve the originating session in the plugin.

**Tech Stack:** Node ESM, node:test, SQLite, JSONC, Python smoke harnesses, OpenCode 2.1.2.

**Spec:** The review and user's “Fix all, double-check again after” in this conversation.

## Constraints

Preserve user configuration and credentials. No production configuration apply, paid inference, service/port changes, or pushes. Independent workers edit disjoint files and do not stage/commit. Root integrates and runs final verification.

## Review focus

- Concurrent edits during both successful and failed undo validation survive; journal is retained on conflict.
- Restrictive wildcard permissions reject later effective exceptions, including layered configurations.
- Mixed-model/agent sessions and real compaction/error records retain correct totals and costs.
- Recovery works without a supported executable; plugin dry-run creates/removes nothing.
- Plugin navigation keeps its originating root; baseline requires the promised outcome and no delegation.

## Task 1: Recovery and permissions

Files: src/store.js, src/native.js, test/core.test.js, test/native.test.js, new focused safety tests if needed.
- [x] Add and observe failing regressions for undo races, stale restored-field validation, and resource-specific permission exceptions.
- [x] Guard undo writes/rollback/history with reviewed bytes; supply restoration metadata for source/runtime validation, including removals.
- [x] Validate effective restrictions rather than testing wildcard resources as literal paths.
- [x] Run focused tests and the native integration checks without inference.

## Task 2: Usage accounting and interpretation

Files: src/usage.js, src/usage-analysis.js, test/usage.test.js.
- [x] Add and observe failing regressions for mixed identities, partial pricing, compaction-only/error records, and false escalation/efficiency claims.
- [x] Aggregate message-level usage into identity buckets while retaining one summary per session; include compaction and native errors.
- [x] Replace grade with descriptive routing status; mark General-to-Build sequence as a possible handoff, not proven failed work. No counterfactual savings claim.
- [x] Run focused tests; communicate report interface changes to root/plugin worker.

## Task 3: Plugin and baseline

Files: plugin/agent-usage/*, scripts/build-only-baseline.py, new baseline validation module/tests, plugin navigation tests/helper.
- [x] Add and observe failing regression proving originating session survives plugin navigation.
- [x] Pass selected root through route data and test plugin wiring with real runtime where feasible, otherwise explicitly report limits.
- [x] Enforce exact baseline test count, stage commit scopes, clean tree, and no delegation; test negative cases using controlled inputs.
- [x] Align plugin with descriptive routing report; run focused checks and compiler/runtime checks.

## Task 4: CLI integration and documentation (root)

Files: src/cli.js, test/cli.test.js, README.md, docs/test-report.md, docs/progress.md.
- [x] Observe failing regressions for offline/unsupported-version undo and plugin install/uninstall dry-run.
- [x] Run undo before runtime discovery; distinguish journal restoration from available native validation.
- [x] Honor plugin dry-run and update user-facing routing/recovery semantics and stale environment claims.
- [x] Run npm test, enabled native checks, PTY flows, appropriate plugin checks, and independent review. Fix material findings and rerun affected tests.


## Integration rulings and evidence

- Root retained the existing clean feature checkout; workers edit disjoint files without Git index operations. No automatic push or production apply.
- Usage report schema now exposes `routing` and per-message `breakdown` in place of `grade`; General-to-Build sequences are `possibleHandoffs`.
- Undo validates restored disk bytes independently of executable discovery. Missing/unsupported runtime or unverifiable inherited Markdown is explicitly reported as disk recovery without native validation.
- Independent review added coverage for inherited global permissions, native wildcard semantics, portable Plan paths, disabled agent restoration and decoded property ordering.
- Baseline import-side effects were exposed by a test; two accidental cloud fixture sessions were interrupted. Subsequent import tests install a subprocess tripwire before evaluating the module; see test-report.md.
- No valid new live cost/savings baseline has been produced. Runtime plugin verification uses an isolated native TUI and synthetic completion event without generation.

- Final verification: full native/local/plugin suite 123/123 passed with zero skips; PTY 3/3; Python syntax and diff checks passed. Evidence is in artifacts/review-fixes-tests.txt, artifacts/review-fixes-terminal.json, artifacts/review-plugin-runtime.json.
- Independent review completed with no remaining concrete material findings after request and reference-expansion corrections. No implementation changes followed the final test run.
