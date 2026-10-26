# Minimal native Hybrid implementation plan

**Goal:** apply a small evidence-backed native configuration change and measure one short matched task.
**Architecture:** existing OpenCode roles and selected cloud model; one local Qwen implementer; inherited cloud semantic review. Existing phase launcher and offline accounting only. No new framework or daily-use command.
**Tech stack:** OpenCode 2.1.4, native JSON configuration, Python unittest, git, existing launcher/accounting tools.
**Spec:** original user request and saved investigation; this continuation explicitly replaces the rejected broad setup with the narrow budget below. The exhausted old job stays rejected.

## Constraints
- Local only; no push, PR, Tiviary access, model/provider selection change, addons, wrappers or installed controllers.
- One local setup worker: 240 seconds total, one attempt; no recursive delegation. Only shorten three role prompts, add four narrow test-command permissions, and remove fixture solution comments.
- Do not use rejected benchmark.py/verify.py. Reuse only the archived small TTL fixture/tests, generic unchanged run_phase.py and saved native audit logic.
- No extra cloud preparation or cloud implementation sessions. Direct-cloud implementation is allowed solely as the requested baseline arm.
- One initial implementation and at most one repair per arm, 180 seconds total including checks/review. No budget extension or second round.
- Full tests, unchanged test hashes, change scope, exact git-diff SHA, actual request routing and substantive semantic verdict required. Test success alone is insufficient.

## Review focus
- No global/provider/model mutations; Hybrid/review retain model inheritance.
- Shorter prompts must retain no delegation by worker, meaningful checks, failure retention, no permission bypass, and semantic review.
- Fixture has one realistic boundary bug, no explicit solution comment; baseline fails expected boundary tests.
- Matched files/prompts/checks/budgets frozen before direct, scripted, native execution; no solution transfer between arms.
- Account cached input once, reasoning correctly, all failed attempts, descendants and maintenance gaps; unknown usage remains unknown.

## Execution
- [ ] 1. Local worker prepares config-after.json and removes explicit fixture solution comments. Existing fixture tests remain byte-identical. No benchmark tooling creation.
- [ ] 2. Same planner reviews complete small patch and verification; explicit digest-bound accept/reject; launcher archives/removes its worktree.
- [ ] 3. Install accepted config atomically after checking original hash. Freeze three clean identical fixture repos, model references, prompt/check hashes and 180-second budgets in evidence outside repos.
- [ ] 4. Run direct Sol medium; unchanged scripted phase launcher with the frozen fixture prompts/checks; repaired native Hybrid. Execute sequentially. Deterministic process waiting and accounting; no model status polling. If unchanged scripted workflow cannot run, retain concrete blocker.
- [ ] 5. Verify tests, untouched inputs, only allowed source changed, exact reviewed digest and actual routing. Keep failed/timeout arms. No host patch or corrective hint.
- [ ] 6. Report per-completed-task cloud/local usage, timings/calls, outcomes, ratios and separate setup/reporting costs. Archive fixture repos and verify content hashes plus recovery bundle before removal.

Evidence: /Users/oleksii.naboichenko/benchmark-evidence/opencode-minimal-native-20261026T231850Z
