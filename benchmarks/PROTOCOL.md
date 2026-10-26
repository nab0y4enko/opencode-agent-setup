# Matched-arm benchmark protocol (instrumented experiment, not daily usage)

This describes how the frozen round in `results/2026-10-26-round-1/` was produced and how to
produce a **new** comparable round. It is historical instrumentation. It is not a daily
workflow: day to day you just open OpenCode, select Hybrid, and select your cloud model.
No automation, no polling, no new runner or controller is added by this package.

## Fixed procedure

1. **Three identical fresh LOCAL checkouts outside this repo**, one per arm, from the same
   base commit, each with the same fixture files. No checkout may be reused across arms and
   none may live inside the repo being configured.
2. **Freeze everything before the first arm**: cloud and local model references and reasoning
   variant, the *actual* context/output limits of the model build on that machine, the exact
   check commands (`python3 -m unittest -v`), SHA-256 of every fixture file, of the config,
   of each phase prompt and of the launcher, plus the 180-second total budget per arm
   including checks and review. The 180-second deadline is **external and deterministic and
   covers the whole arm** (implementation, any repair, checks, review and reporting), not each
   phase separately and not a model's own sense of time. The manifest is written before any arm
   runs and never edited.
3. **Arm order is fixed**: direct (single cloud session) → old scripted phases, only if the
   archived launcher still runs **unchanged** → native Hybrid. If the unchanged scripted arm
   cannot run, record the concrete blocker instead of patching it.
4. **One initial implementation and at most one repair per arm.** Budgets are enforced by
   deterministic external deadlines that cover **all** phases (implementation, repair,
   checks, review, reporting), not by asking a model to self-time.
5. **No solution transfer.** No arm may see another arm's diff, verdict, prompt result or
   log; nothing from a finished arm is pasted into a later one.
6. **Record actual routing and actual descendants**: which model really served each request,
   every child session, every failed/aborted attempt, and host intervention. Any post-start
   correction or solution hint invalidates autonomous success for that arm.
7. **Unknown usage stays unknown.** Usage that cannot be attributed is reported as an unknown
   maintenance gap, never smeared into an arm's per-task figure.
8. **Acceptance is full-suite + scope + digest**: whole existing test suite run by the
   party that owns verification, only allowed paths changed, frozen inputs byte-identical,
   no untracked source, and one substantive semantic review bound to the exact
   `git diff --binary HEAD` SHA-256. Passing tests alone never accept; a review of an older
   patch never accept.
9. **Archive and verify before removal.** Checkouts and logs are archived, content hashes and
   the recovery bundle are verified, and only then may the temporary checkouts be removed.
   Failed arms are kept with their evidence; nothing is deleted because it lost.

## The reusable benchmark task

Use `fixture/` (three files; baseline is 12 tests with 3 failing boundary tests) as the **new
frozen local fixture** for a new round, together with the exact task request text copied
verbatim from the round-1 manifest into a `task.txt` that lives **outside** every arm checkout
and outside this repo, so no arm can read it as a file inside its own tree. The round-1 manifest and raw measurement data are retained in
`results/2026-10-26-round-1/` as byte-identical copies of the external evidence. Native per-arm commands, for a new comparison (the original arm-specific working-mode prompts are retained in the frozen evidence):

```sh
# fresh, identical, LOCAL checkout outside this repo, fixture files in place
git init -q && git add -A && git commit -qm baseline
python3 -m unittest -v                      # baseline: 12 tests, 3 failures

# task text: external original manifest task, copied verbatim, same bytes for every arm
#   <external>/task.txt   (never inside an arm checkout)

# arm 1 — direct: one cloud session, no delegation
opencode run --standalone --format json --agent build --model openai/gpt-6.1-sol#medium "$(cat task.txt)"

# arm 3 — native Hybrid: same task text, same machine, same fixture; Hybrid inherits the
# same frozen cloud model as the direct arm; this command does not change the global selection
opencode run --standalone --format json --agent hybrid --model openai/gpt-6.1-sol#medium "$(cat task.txt)"

# arm 2 — old scripted phases only if the archived launcher still runs unchanged; otherwise
# record the concrete blocker
```

Each arm then runs its own frozen check command and semantic review inside the same external
180-second deadline. This package **documents** those commands; it does not run them, ships no
runner that wraps them, and launches no model.

On another Mac this fixture may be replaced by any equivalent small bug with a deterministic
RED suite, provided the checkout is clean/fresh and external to the repo, and the fixture
contains **no exact-solution comments or hints** for the model to read.

## Hard boundaries

* `legacy/` (`run_phase.py`, `account.py`, `audit_native.py`) is **historical**, phase-based
  instrumentation retained for provenance. It **hardcodes the models measured on the original
  Mac** and is **not turnkey or portable unchanged**; adapting it per machine creates a *new*
  version that requires a **fresh frozen manifest** before any of its output may be compared.
  Never present legacy numbers as comparable to a differently configured machine.
* This package adds **no** new runner, framework or controller, and no new test authoring: the
  frozen fixture and its existing tests are the only checks.
* No cloud/local **model or provider selection changes**, no installed-config writes, no
  pushes, PRs or remote access, and no automation that polls model status.
* Totals in `RESULTS.md` include neither setup nor reporting cost; those belong to the parent
  accounting pass, added separately.
* The recorded round produced **2 accepted arms and 1 failed native arm** with a known-token
  ratio of 1.2512 against a 0.30 threshold. Reproducing it may well fail again; that is a
  result, not an error to fix.
