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
