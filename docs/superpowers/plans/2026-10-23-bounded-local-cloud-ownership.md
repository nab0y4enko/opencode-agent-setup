# Bounded local work and cloud fix ownership

Approved direction: the user requested small Qwen tasks, Sol ownership of hard fixes through verified completion, fewer repeated handoffs, testing, a commit and global application without interrupting the running session.

Design: update native role instructions rather than add a scheduler or change models. General gets one independently verifiable objective, normally at most three production files plus associated tests/docs and one focused validation target. These are routing defaults, not permission limits. Complex focus/lifecycle, architectural or repeated failures go directly to Build. Build owns diagnosis, correction, relevant regression checks and acceptance evidence in one session, continuing through informative failures while progress is supported. External blockers, unclear ownership and no-progress loops still stop safely. The coordinator reviews the completed stage and requests only material missing evidence. Existing permissions, step budgets, models, service tiers, endpoints and unrelated settings stay intact.

Alternatives: a lower local step cap would stop work sooner without improving assignment quality; a custom scheduler would add machinery without establishing better routing. Prompt revision fits the approved scope.

Implementation and verification:
- [x] Revise `src/prompts.js`; remove conflicting blanket failure/attempt rules and multi-stage local delegation. Update README and balanced-profile guidance.
- [x] Run existing core and complete test suites; native integration must load revised General/Build/Orchestrator instructions in a disposable directory without model generation. Review example routing cases: small mechanical change, native focus defect, failed but informative cloud test, local budget exhaustion, external blocker.
- [ ] Review the diff; commit verified source/docs. Apply only revised system fields transactionally to the global JSON using existing backup/conflict checks. Validate in a disposable configuration and read-only runtime discovery; never reload, cancel, resume or prompt the running session.
- [ ] Verify unchanged global settings and monitor running-session identity/state read-only. Record checks and rollback journal in local activation evidence. New sessions are the reliable boundary for revised instructions; already-running work is not migrated.

Limits: static/native configuration checks prove instructions are loaded, not better model behavior or quota savings. Do not run a competing Tiviary test job or an inference benchmark against the active local worker.

Semantic review cases (fresh read-only reviewer: no actionable findings; final one-phrase scope clarification checked by the author):

| Situation | Required route/continuation |
|---|---|
| Known one-file mechanical correction | General; one acceptance check, verified commit, cloud acceptance |
| Ambiguous native focus or lifecycle defect | Build directly; validate the diagnosis before choosing the correction |
| Cloud test fails with new useful evidence | Same Build session continues within the fix stage; no dependent-stage advancement |
| Local worker reaches budget or persistent failure | Reconcile once, pass receipts/patch to Build; no repeated local resumes |
| Missing ownership or unavailable external prerequisite | Stop with a concrete blocker and retained evidence; no completion claim |

No model benchmark was run because the existing OpenCode job is using the shared local service. This review and native loading checks establish instruction consistency and effective configuration, not measured behavior or savings.

Verification: focused CLI/core 28/28 passed; full suite with native/local-discovery/plugin checks 155 passed, zero failed, one inference completion test intentionally skipped (156 total; 166.7 seconds). Disposable native preflight loaded all three revised prompts exactly. First full run exposed a CLI wording expectation; explicit assigned-scope wording was restored, then the full suite passed. No model generation benchmark was performed.
