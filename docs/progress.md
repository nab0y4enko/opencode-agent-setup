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
