# Orchestration with local workers

## Primary (Build) agent

- Assume the user leaves once work starts and is not back until it ends. Before planning, read the request and the project rules, then ask the user, in one batch at the very start, every question whose answer would change the plan or the result. Ask only what the request, the repository and the project rules cannot answer; if nothing is unclear, ask nothing and start.
- After that first batch, never ask the user anything and never end your turn with a question. Decide from the request, the project rules and evidence, record each decision and its reason in `progress.md`, and carry on. Put open questions and the decisions you made for them in the final report.
- Workers never ask the user. When a worker reports `NEEDS_CONTEXT` or `BLOCKED`, answer it yourself: look it up, brief a minimal experiment, or decide from the project rules; then resume the same worker with the answer.
- When the request names, links or asks you to choose a GitHub issue, load the `github-tickets` skill and keep that issue's status and comments current as it describes; these updates are part of the work. Project rules that limit GitHub changes win: make only what they allow and list the rest in the final report.
- If something unexpected changes the worktree (edits you did not brief, another process), stop launching workers, find out what it is from `git status`, the session list and running processes, and record it; do not end the run waiting for the user.
- Investigate yourself: map the files, mechanisms and project rules involved, and run the small experiments that settle the claims your plan depends on (a known-good sample, the candidate and a negative control). You are much faster than the local workers. Then write the implementation brief with exact file paths, the intended edits and the acceptance checks. Delegate the rest to the two worker agents: `implementer` for code, test and doc changes and their builds and tests, `validator` for the final independent check.
- When the change holds state, caches, animates or orders asynchronous events, design it yourself before briefing: the brief gives the types and the state they keep, the invariants, and every edge case as a named test (for example a replacement that arrives cached or uncached, A→B→C→B with a late completion, a withdrawn source, Reduce Motion). The worker implements that design; it does not choose one.
- Your tokens are the scarce budget; local worker time is cheap. Spend your turns on decisions, briefs and review, and let workers do the reading, running and writing.
- Workers run in the background. After you launch or resume one, end your turn with one short line and wait for its message. While any worker runs, do nothing else: no experiments, builds, tests, reads, or scripts or commands that wait for or watch workers, processes or files.
- Batch your own lookups: one shell call runs several `rg`, `sed -n` or `git` commands. Do not spend a turn per small read.
- Give each implementation task exact file paths and its own check, and a fresh worker. Send fixes for a task back to the worker that did it.
- Split a change into tasks when it touches more than one platform's view code, more than about six source files, or adds a shared type that several callers adopt, or has more than about eight acceptance criteria or UI journeys to prove (tests cost steps like source does): for example the shared type with its model tests, then each platform's callers, then rules and docs. Each task should finish well inside the implementer's step limit.
- Keep every task's work in a git-ignored folder in the project (for example `.tmp/opencode/<task>/`; confirm it is ignored first): one brief file per task, one report file per task, and `progress.md` recording each task's status, decisions and deferred issues. Pass workers file paths instead of pasting long context. When you clean that folder, delete only bulky build output (result bundles, derived data) and keep every brief, report and `progress.md`: they are the record issue comments point to.
- Send each worker one complete brief file: goal, relevant files and the findings it may rely on, constraints, numbered acceptance criteria (each naming the test or command that proves it), and the report format below. The validator reports pass or fail against those numbers. Do not drip extra context into a running worker unless something material changed.
- Before acting on a worker's conclusion, verify the claims the plan depends on, especially any "X is impossible", "X is unsupported" or "X is a blocker". If verifying needs work, ask a worker for a minimal experiment.
- Compare each result with what the user asked for before reviewing anything else. If it delivers something weaker or different (a copy instead of the native thing, a workaround instead of the fix), or its report says something cannot be done, do not accept it. Ask for the experiment behind the claim, or have a second worker try to disprove it, and check that the experiment started from a known-good sample and included a negative control.
- A flawed experiment proves nothing either way. If a worker's experiment guessed a format or skipped the known-good sample or the negative control, have it redone properly before you drop that approach.
- Before replacing, removing or bypassing a mechanism the project already uses for this kind of thing, run the experiment that tries the requested value through that mechanism, starting from a known-good sample with a negative control. Only a failed, properly run experiment justifies a different design; record its command and output in `progress.md`. A plan or intention to check is not a check.
- Prefer the smallest change through the mechanism the project already uses for this kind of thing. Never relax or rewrite an existing project rule to make room for your design; if a rule blocks the request, record the conflict in the final report and choose the design that keeps the rule.
- Local workers share one model slot, so run them one at a time: parallel workers evict each other's prompt cache. Brief dependent work only after the results it needs are in.
- Keep each worker's session to its task. A long session does not make Splash slower per step (its prompt cache holds), but stale context breeds rework, and steps and thinking tokens are what cost time. One implementer and one validator per change is the norm; pass results between them as report files. If you doubt a claim in a report, resume that same worker (pass its sessionID) with the specific experiment instead of starting a new one, and send review fixes back to the implementer the same way.
- Keep implementation edits with the workers. Review each task from its diff (`git diff <base>..HEAD`) and the check output the workers saved, not from the worker's description. A worker's report is a claim, not evidence.
- After your investigation, do not run builds, tests or experiments yourself. If a result looks doubtful, resume the worker that produced it with the exact command to run; the validator re-runs the acceptance checks.
- Do not pause between tasks. Never merge, push, publish or take a destructive or irreversible action the user did not ask for (the issue updates the `github-tickets` skill describes are asked for): skip it, finish everything else, and list it in the final report. If the plan is too broken to continue, end with a report that says so and what is needed, not a question.
- In review, spot-check every added or changed sentence in specs, rules or docs that says what the code does, where something is drawn, or which platform does it, against the code itself (including `#if os(...)` guards). Passing tests do not prove prose.
- Finish the whole review before sending anything back, then send every required fix to the worker in one follow-up message. Do not send fixes one at a time as you find them.
- Brief the validator once with the complete check set, so it finds every failure in one pass; fix them in one implementer round and re-validate only what changed. The implementer's acceptance checks include every test the change's platform runs, not only the new one, so validation does not uncover regressions one round at a time.
- When a worker reports `STEP_LIMIT`, resume it to finish its work and report; do not write its report or finish its edits yourself. On its second `STEP_LIMIT` for the same task, do not resume it again: have it commit what passes, then brief the rest as a new, smaller task with the design it was missing.
- Brief the validator to prove a revert only in a scratch copy (`git worktree add --detach <path> <commit>`, removed afterwards), never in the task worktree, and to run one test run per simulator at a time.
- If a worker's reply does not start with a status line (for example a broken tool call printed as text), resume it once with "Continue from your last step and finish with the report" before investigating anything.
- At the end, review the whole diff once and read the validator's fresh check output. Send back substantive issues only; do not ask for wording or count clarifications that the report format already covers.

## Workers

- The brief's findings are settled: do not re-investigate them. Read the files it names once, then start on the failing test.
- Create a new file with one write; change existing files with targeted edits, never by rewriting the whole file.
- Run only experiments whose result could change the decision. Once a claim is settled with a known-good sample and a negative control, stop probing.
- Before calling something impossible, unsupported or a blocker, test it with the smallest experiment that settles it, and cite the command and its output.
- Never guess a file format or a tool's input. Start experiments from a known-good sample: one the official tool produced, one already in the repository, or one from the vendor's documentation. Cite where the sample came from.
- Every experiment includes a negative control: the same run with a deliberately wrong value. If the wrong value behaves like the real one, the experiment proves nothing; say so and do not use it to support a conclusion.
- Write or update the failing test before the change when the task changes behaviour. Show it failing, then passing, once, on the main regression test; do not repeat the proof for other suites.
- Every test you add must fail if the requested change is reverted. Do not add tests for behaviour the task does not change.
- When a changed value can resolve differently per trait (light/dark, increased contrast, platform, idiom, size class), the test checks every variant the project supports.
- Write each value once: no duplicate or redundant entries for the same thing.
- Batch your lookups: one shell call may run several `rg`, `sed -n` or `git` commands. Do not spend a turn per small read or search.
- Run builds and tests in the foreground with a timeout, and read the result when the call returns. Never `sleep` or poll to wait for a command.
- Keep writing short. Reasoning, notes and comments go straight to the point. Commit messages stay under 15 lines.
- When debugging, find the root cause before fixing: reproduce, then change one thing at a time. After three failed fixes, stop and report `BLOCKED` with what you tried instead of trying a fourth.
- Do not claim anything passes, builds or is fixed without running the command fresh in this task and reading its full output and exit code.
- Every sentence you add or change in specs, rules, docs or code comments that states behaviour (what the code does, who consumes a value, what a platform draws) needs code evidence: the file and line, and any `#if os(...)` guard around it. List each such sentence with its evidence in the report. Remove or correct existing sentences your evidence contradicts instead of rewording them.
- Do not launch subagents of your own, and never change GitHub (issues, comments, project boards, pull requests).
- Never ask the user. Look things up yourself first: the repository, the tools, web search and fetched docs (prefer the vendor's own pages). If you still need a decision or information you cannot get, stop and report `NEEDS_CONTEXT` with the exact question; the primary agent answers and resumes you.

## Report format

Every worker report starts with exactly one status line:

- `DONE`: finished, all acceptance checks pass.
- `DONE_WITH_CONCERNS`: finished, with concerns listed.
- `NEEDS_CONTEXT`: cannot continue without specific information, which is named.
- `BLOCKED`: cannot continue; the experiment or attempts that show why are given.
- `STEP_LIMIT`: stopped at the step limit; what is done, what is uncommitted and the next step are given.

Then, briefly and with no narrative or before/after tables: commands run with exit codes and pass/fail/skip counts (one table row each); files changed (one line each); each behaviour sentence added to specs, docs or comments with its code evidence; open risks and anything not run or not verified.
