# Runnable cross-Mac benchmark plan

Goal: let the user run the SAME frozen task on different Macs and compare Codex Sol+Luna cloud tokens against native OpenCode Sol+local-worker cloud tokens. Historical reports are not executable benchmarks.

Implementation is benchmark-only instrumentation, not an installed controller/addon or daily workflow wrapper. No global config/provider/model selection changes. No paid model runs during authoring.

- [x] Implement a Python-stdlib CLI under benchmarks: `run --live` for automatic native CLI arms; `prepare` plus `finish --codex-thread ID --live` for actual Codex desktop session import; `report` offline; `compare` offline.
- [x] Freeze fresh external output path, identical clean fixture copies, task/prompts/hashes/cloud Sol medium/Luna medium/local-model reference, 180-second per-arm budget, one initial plus at most one repair, exact tests and scope before launch. Refuse existing run/output reuse. Record hardware, software versions and config hashes without copying secrets.
- [x] Codex CLI arm uses session-scoped native config defaults for Luna workers and concurrent-worker cap1; no global changes. App import uses real recorded root+descendant sessions and cannot be labelled CLI. Desktop import has a retrospective duration gate, not a claimed automated timeout.
- [x] OpenCode arm uses installed native Hybrid and selected matching cloud model through invocation flags, not replacement native role definitions. Validate configured local general model and actual recorded routing. No status model polling or host corrective hints. All native permissions remain in force.
- [x] Count each Codex session final cumulative input+output once; cache/reasoning are subsets. Count OpenCode disjoint fields per assistant once; retain unknown maintenance/model usage. Capture root and descendants including failures and ongoing/pending records. Missing coverage is never zero or an accepted total.
- [x] Acceptance requires full unchanged tests, only ttl_cache.py changed, no untracked source, current complete git-diff digest, correct substantive root/cloud-reviewer verdict, expected actual worker routing and observed repair budget. No tests-only acceptance. Reports retain all failure/timeout cost; ratio target is Hybrid CLOUD / Codex Sol+Luna CLOUD <=0.30 for completed tasks.
- [x] Preserve run evidence outside disposable repos; verify file hashes and Git recovery bundles before cleanup. Do not delete user paths; safe resume/import only from own frozen manifest. Keep historical evidence unchanged.
- [x] Add meaningful offline unittest coverage with fake CLI/log/database fixtures: known token math, descendants, routing mismatch, missing usage, false verdict/test-only failure, scope drift, deadlines, evidence preservation, fresh-output refusal, cross-Mac compatibility and the complete mock two-arm run. No real auth/model calls in tests.
- [x] Document exact commands for a new Mac, local model/config prerequisites, CLI-vs-App distinction, manual desktop timing caveat, report files and cross-Mac comparison. Implementation was split into accounting, runner, portability and test-packaging stages. Retain recovery archives, review the complete changes, verify the offline suite, commit and push the task branch, and remove task worktrees.

Validated delivery: 99 offline tests pass (46 accounting, 46 runner, 7 portability).
The test suite uses fake clients; no live model comparison or token-saving claim was made.
Local Worker was removed from Codex at the user's request before final packaging; the parent
reviewed and integrated the archived candidate and completed test packaging directly.
