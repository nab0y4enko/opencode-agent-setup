# Minimal native Hybrid implementation plan

**Goal:** apply a small evidence-backed native configuration change and measure one short matched task.
**Architecture:** existing OpenCode roles and selected cloud model; one local Qwen implementer; inherited cloud semantic review. Existing phase launcher and offline accounting only. No new framework or daily-use command.
**Tech stack:** OpenCode 2.1.4, native JSON configuration, Python unittest, git, existing launcher/accounting tools.
**Spec:** original user request and saved investigation; this continuation replaces only the rejected broad *setup* with the narrow budget below. The user scope update at the end of this file **supplements** the constraints, review focus and execution steps below — it does not delete or replace all of those instructions. The exhausted old job stays rejected.

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

Checkboxes below record **whether the step was executed**, not whether the round succeeded.
**Native acceptance FAILED and the measurement target was missed** (known-token ratio 1.2512
against a <=0.30 threshold; native produced 0 accepted completions — see
`benchmarks/results/2026-10-26-round-1/RESULTS.md`). Marking a step complete below must never be
read as native acceptance.

- [x] 1. Local worker prepares config-after.json and removes explicit fixture solution comments. Existing fixture tests remain byte-identical. No benchmark tooling creation. (executed; direct and scripted arms accepted, native arm rejected)
- [x] 2. Same planner reviews complete small patch and verification; explicit digest-bound accept/reject; launcher archives/removes its worktree. (executed; native verdict was `FAIL`/`CHANGES_REQUIRED`)
- [x] 3. Install accepted config atomically after checking original hash. Freeze three clean identical fixture repos, model references, prompt/check hashes and 180-second budgets in evidence outside repos. (executed; external deterministic deadlines covered each whole arm)
- [x] 4. Run direct Sol medium; unchanged scripted phase launcher with the frozen fixture prompts/checks; repaired native Hybrid. Execute sequentially. Deterministic process waiting and accounting; no model status polling. If unchanged scripted workflow cannot run, retain concrete blocker. (executed; native arm FAILED — see RESULTS.md)
- [x] 5. Verify tests, untouched inputs, only allowed source changed, exact reviewed digest and actual routing. Keep failed/timeout arms. No host patch or corrective hint. (executed; identical digest on all three arms is not acceptance, failed arm kept)
- [x] 6. Report per-completed-task cloud/local usage, timings/calls, outcomes, ratios and separate setup/reporting costs. Archive fixture repos and verify content hashes plus recovery bundle before removal. (executed; native per-completed-task usage is undefined at 0 completions; setup/reporting costs excluded)

Evidence: /Users/oleksii.naboichenko/benchmark-evidence/opencode-minimal-native-20261026T231850Z

Delivery split: the **code package** (portable native config, frozen fixture, legacy
instrumentation, protocol and this plan) and the **immutable measured evidence** are separate
deliverables. The raw per-arm records, manifest and accounting remain at the external evidence path above
and are also copied byte-for-byte into `benchmarks/results/2026-10-26-round-1/` after the
small source package was accepted. This deterministic evidence copy preserves the measured
originals without expanding the code-review package.

## User scope update (2026-10-26, after round 1)
- Round 1 outcome stands as recorded: direct accepted, scripted accepted, **native Hybrid
  failed/rejected**; the known-token ratio was 1.2512 against a <=0.30 threshold. The
  native arm is NOT marked passed anywhere, and no second round was run.
- User replaced the previous instruction set: obsolete repo code is wiped from the working
  tree and replaced by portable native OpenCode configuration plus the frozen benchmark
  package. Git history and the verified archive/recovery bundle outside the repo remain the
  recovery path for the removed code.
- Scope for the replacement: native JSON config only (no framework, setup CLI, installed
  wrapper, plugin/addon or controller), no model runs, no recursive delegation, no pushes,
  PRs or remote access, no writes to the installed config directory.
- Portability requirement: another Mac may run a different local model, so model id, endpoint
  and key are `{file:...}` **sidecar** values the user edits, while the numeric
  context/output `limit` values are **edited directly in `config/opencode.json`** (they are
  plain JSON numbers, not sidecars). Either way they are per-machine settings the user sets:
  the numbers used in the measured profile on this Mac are examples of what was used, not
  discovered maxima and not assertions about other hardware.
- This update **supplements** the Constraints, Review focus and Execution sections above;
  those constraints (no model runs by workers, no recursive delegation, retention of every
  meaningful assertion, digest-bound review, failed arms kept) remain in force.
- Parallelism: up to 4 concurrent general workers are optional behavioural guidance for
  genuinely disjoint work only; one worker stays the default and the up-to-4 overlay was
  never activated or measured on this Mac.
- Retained unchanged as historical evidence: the failed native round, the measured
  single-worker config, the frozen manifest and every source record.
