# Round 1 results — 2026-10-26 (historical, one Mac, not portable, not a success story)

Figures below are the recorded totals from `comparison.json`; every per-arm source record in
`direct/`, `scripted/` and `native/` is preserved byte-identical, including the rejected
native arm. Nothing here was re-measured or recomputed for this package.

Frozen round: `manifest.json` (frozen 2026-10-26T23:21:01Z, OpenCode v2.1.4, 180 s total per
arm, 1 initial + at most 1 repair, `check` = `python3 -m unittest -v`, allowed changed path
`ttl_cache.py`, threshold: native cloud tokens / direct cloud tokens <= 0.30 for accepted
tasks). The manifest and every raw per-arm record live in the external evidence directory
cited at the end of this file, not in this code package; the fixture and measured-config
hashes recorded here verify against that external manifest.

## Outcome

| Arm | Accepted | Autonomous | Cloud total (identified tokens) | Uncached input | Cache read | Cache write | Output | Reasoning | Local total | Wall s | Assistant calls | Tool calls |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direct (cloud) | **accepted** | yes | **43,932** | 9,549 | 33,408 | 0 | 863 | 112 | 0 | 53.568 | 6 | 9 |
| scripted (cloud+local phases) | **accepted** | yes | **50,155** | 17,287 | 32,000 | 0 | 857 | 11 | 80,589 (18,451 in / 59,072 cache / 2,009 out / 1,057 reasoning) | 97.865 | 17 | 29 |
| native (Hybrid) | **FAILED — rejected** | no | **54,967** | 15,739 | 37,504 | 0 | 1,629 | 95 | 60,876 (7,461 in / 51,136 cache / 1,536 out / 743 reasoning) | 105.917 | 16 | 19 |

All three arms produced the same complete-diff digest
`9ef8713f1f528d27ebabf895a8f6925ba0100647c1020471c404b43b9070797f` (only `ttl_cache.py`
changed, frozen inputs unchanged, no untracked source). Digest equality is **not**
acceptance: the native patch was rejected for missing required verification evidence.

## Cloud tokens per completed task

* direct: `43932` cloud tokens / 1 accepted completion.
* scripted: `50155` cloud tokens / 1 accepted completion (plus 80,589 local tokens).
* native: **undefined — 0 completions.** `cloud_tokens_per_completed_task` is `null` in the
  record; the 54,967 cloud tokens and 60,876 local tokens are spent without acceptance.
  Known-token ratio native/direct is `54967 / 43932 = 1.2512` against the `<= 0.30`
  threshold. **No savings, no efficiency claim, and no 30% success claim follows from this
  round.**

## Maintenance gaps (attached to an arm, excluded from its per-arm total)

Gaps are recorded sessions that **do belong to a named arm and session lineage** — they are
not orphaned or unassigned — but whose usage fell outside that arm's frozen per-arm tally and
whose **model tier could not be determined**, so they are excluded from the per-arm totals and
from the known-token ratio: direct 801 (1 session attached to the direct arm, cloud
`gpt-6.1-sol`/medium, succeeded); scripted 3,295 (811 + 824 + 823 + 837 over 2 local + 2 cloud
sessions attached to the scripted arm, succeeded); native 964 (964 + 0 + 0, attached to the
native arm, succeeded). Attribution to an arm is known; **the model tier of these sessions
stays unknown usage**, and no ratio in this file silently absorbs them.

## Why the native arm failed (preserved, not narrated away)

1. The `general` worker ran `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v > <log> 2>&1;
   echo "EXIT_CODE=$?"` instead of the allowed bare command; native permission returned
   `permission.rejected: shell`, so no test log was ever created (`native/tools.json`,
   `native/execution.json`).
2. The Hybrid coordinator treated that worker-specific denial as blocking **its own**
   separately authorized final check and never ran the full suite itself.
3. The `review` subagent correctly returned `CHANGES_REQUIRED`; verdict markers in
   `native/result.json` are hybrid `FAIL` and review `CHANGES_REQUIRED`, and the reviewer's
   later read of the non-existent log errored because the check never ran.
4. The parent/offline test suite passes. That does **not** override the native failure and
   cannot confer autonomous acceptance on the rejected arm.

The command-handling wording added to `config/opencode.json` addresses exactly (1) and (2).
It is an **offline-only, unvalidated correction**: nothing in this package re-ran a model.

## Measurement limitations

* **Self-review vs separate review.** The direct arm's `PASS` verdict came from the same
  cloud `build` session that implemented the change (self-review), while the native arm used
  a separate `review` subagent on the inherited cloud model. The arms are not
  review-equivalent; the direct baseline is the more permissive of the two.
* **Launcher unchanged, prompts adapted.** `run_phase.py` is byte-identical across arms
  (`85f9251a33648765df8ac6c8bdd96b3584e04745d6c657b3ebd7e6039338ea21`), but the frozen
  fixture prompts were adapted for this round (explicit solution comments removed from the
  fixture). Re-running with older prompts is a different measurement.
* **Setup/reporting costs are not in the table.** Per-arm figures exclude worker setup and
  report generation; they are placeholders pending the final parent accounting, which will
  be added separately. Do not invent numbers here.
* Historical artifacts here contain absolute Mac paths for provenance only. Portable
  configuration (`config/`) must not contain any.
* One Mac, one local model build, one round, no second round. Nothing here establishes a
  general cost or speed claim.

## Separate setup/reporting accounting

See `accounting.json` for the retained job rows, incomplete usage and exact rollout snapshot.

- Current continuation planner/setup/supervision/reporting cloud lower bound: **10,441,864** tokens.
- Identified cloud tokens across the three benchmark arms: **149,054**.
- Current all-in cloud lower bound: **10,590,918**.
- Known local setup/delivery lower bound: **626,012**; one timed-out delivery has missing usage. Benchmark local: **141,465**.
- Earlier rejected broad setup: separately recorded cloud lower bound **3,541,291**, local usage unavailable.

These figures include failed/rejected setup work. They grow through final reporting; cached input and reasoning subsets are counted once. They are raw usage, not subscription quota. Native remains **failed**, and neither the corrective portable profile nor optional parallel profile was live validated.

Whole-thread all-in cloud lower bound (earlier failure and diagnosis included once): **15,394,987**. This contains the separately listed earlier snapshot; do not add it again.
