# Portable benchmark runner: unfinished

This is **not a runnable release**. The primary checkout has no `benchmarks/run.py`.
`UNACCEPTED-candidate.patch` preserves local-authored work for inspection and recovery only.
It has not passed complete semantic review and is not approved for use.

The final local candidate passed 29 offline tests, including both fake CLI arms and offline
report regeneration. Delivery failed: 136,809 source/doc bytes exceed the native 131,072-byte
complete-review ceiling. The package is incomplete and its verified fingerprint is unavailable.
Requested new negative regressions for missing model/reasoning/completion evidence were not
added (the suite stayed at 29 tests). Tests passing does not qualify this candidate.

The final job finished within its budget; three earlier jobs timed out. All five candidates
were rejected; no further repair round was launched. `status.json` records verified archive,
Git bundle and recovery-ref receipts. Only the primary checkout remains; independent disposable
smoke-test checkouts were also archived and removed. Full evidence: `/Users/oleksii.naboichenko/benchmark-evidence/portable-benchmark-build-20261027T000349Z`.

Remaining work: reduce source below the complete-review ceiling without weakening behavioral
checks; add the missing regressions; complete verification and semantic review; then run a
frozen matched real benchmark. Actual Codex App imports and automated CLI measurements must
remain distinct. The optional up-to-four worker profile remains unqualified.

## Outcomes and costs

- New completed benchmark tasks: **0**; per-completed-task cost and savings are undefined.
- Live paid benchmark arms during this build: **0**. Fake tests are not measured model runs.
- Planner-session raw cloud lower bound: **43,915,750** tokens at the saved
  in-turn snapshot. This includes earlier investigation/configuration/reporting in this same
  session, not an isolated runner-build measurement; it grows until the session ends.
- Known local authoring lower bound: **5,348,329** input+output tokens; **3** timed-out jobs
  have unavailable usage, not zero. Per-job durations/counts are in `local-authoring-costs.json`.
- Cached input is included in input; reasoning is included in output. Neither is added twice.
  Raw tokens are not measured subscription quota debits. All-in cloud is at least the session
  snapshot; unobserved external usage is unavailable. No amortized saving is claimed.

No installed config/model/provider changes, pushes, PRs, Tiviary edits, or cloud implementation
subagents were made during this build. Historical reports/native profiles remain unchanged.
