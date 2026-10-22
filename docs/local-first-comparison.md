# Local-first optimization and matched rerun — 22 October 2026

**Withdrawn recommendation:** this all-local experiment does not satisfy the requested architecture. Planning and review must stay on Sol; Qwen is only a bounded worker. Its measurements are historical, not evidence for the recommended mixed profile. See [the corrected cloud-led profile](cloud-led-comparison.md). The old local-first example was replaced by `examples/mixed-workers.json`.

The optimized mixed profile completed the same two-stage clamp task entirely on local Qwen. Both accepted results passed independent verification. Recorded cloud token usage fell to zero from the previous mixed run’s 19,723 input, 3,548 output, 210 reasoning and 88,192 cache-read tokens. Execution took 60.969 seconds, versus 211.785 seconds previously (71.2% less elapsed time). Fresh Build-only completed in 61.639 seconds. This one pair establishes no meaningful speed difference between the two current paths.

## What changed

- Qwen now coordinates as well as implements. Routine planning, discovery, compaction, titles and summaries are recommended local; the reusable `examples/local-first.json` explicitly routes those roles locally. Native hidden-role prompt text remains unchanged.
- One foreground General assignment owns both dependent stages, reuses context and creates a verified commit for each. There is no forced stage-2 cloud handoff or automatic paid reviewer. The measured pipeline had two sessions, one dispatch and 20 assistant turns, versus four sessions, three dispatches and 29 turns previously.
- Orchestrator has an eight-step budget. Local General retains its 24-step budget, ownership checks, regression testing, explicit-path staging and separate commits.
- Cloud Build and review are reserved for evidence-backed escalation and material risks. Both require approval through coordinator permissions; enhanced Build also requires approval before dispatching a paid reviewer. Ordinary local dispatch remains allowed.
- The wizard recommends the local-first coordinator and defaults the optional cloud reviewer to off. Existing choices remain explicitly reviewable; changing recommendations does not silently overwrite saved model selections.

The reusable profile uses `ask` for cloud roles. OpenCode auto-approval modes may approve such requests; this is an interactive approval gate, not a hard dollar cap. The benchmark converts those cloud-role permissions to `deny`, explicitly selects local Qwen for the root and helpers, and rejects any actual cloud or unknown message usage. Native model overrides remain possible when explicitly requested; the coordinator prompt forbids bypassing the cloud gate through another role/model override.

## Recorded measurements

The two new runs were sequential, optimized mixed first, then native Build-only. There was one inference attempt for each and no timeout or retry in this campaign. Timing covers CLI launch through exit, including tools and inference; independent verification and setup are excluded.

| Metric | Optimized mixed | Fresh Build-only |
|---|---:|---:|
| Execution seconds | 60.969 | 61.639 |
| Cloud input tokens | 0 | 5,135 |
| Cloud output tokens | 0 | 1,650 |
| Cloud reasoning tokens | 0 | 105 |
| Cloud cache-read tokens | 0 | 67,072 |
| Cloud cache-write tokens | 0 | 0 |
| Local input tokens | 20,403 | 0 |
| Local output tokens | 4,105 | 0 |
| Local reasoning tokens | 1,457 | 0 |
| Local cache-read tokens | 116,384 | 0 |
| Local cache-write tokens | 0 | 0 |
| Actual dollar cost | Local operating cost unmeasured | Unavailable |

All token categories reconcile exactly against separate Python SQLite aggregation of the native assistant/compaction records, including the complete descendant trees. No cloud messages or unknown routes were recorded for the optimized run. Build’s recorded dollar fields remain zero without pricing; that does not establish free cloud usage. Local inference uses no measured cloud tokens, but electricity and hardware costs were not measured. Token categories and cache-weighted heuristics are not converted into a bill.

## Verification and limitations

Both repositories started with identical SHA-256 hashes for the four tracked fixture files. The verifier independently replayed each commit: three passing tests for stage 1, four for stage 2, exact commit/file scopes and patch artifacts, a failing four-test regression against stage-1 source, and 637 final integer cases including equal, negative and inverted bounds. Both finished with clean tracked worktrees and unchanged unrelated files. Actual per-message agent/model variants matched Qwen for the optimized coordinator/worker and Sol high for native Build. Both native session trees completed successfully.

The local coordinator used read-only `read`/`glob` tools and one subagent call; it did not edit or run shell. Some extra local file discovery remained (13 reads and four globs); the optimization reduces cloud use, handoffs and total turns, rather than proving minimum possible local coordination. Its native eight-step limit bounded the run.

The initial capture treated an omitted `background` option as unknown. OpenCode 2.1.2 defaults it to foreground; completed native metadata confirmed the awaited result. The capture now normalizes that default and detects jobs moved to background, with regression coverage. Saved events were reprocessed without another inference request, retaining the initial capture for audit. The independent tool-scope checker also now accepts the read-only discovery tools permitted by the coordinator’s actual policy, while still rejecting shell/edit. These were harness issues, not failed implementation attempts.

This is the same small functional task and stage evidence contract as before. The old routing test deliberately forced cloud stage 2 and cloud review; those forced calls were removed for the local-first optimization. Mixed uses enhanced prompts and local coordination; Build-only uses its unchanged native prompt. Cache state, provider latency and hardware warm state were not controlled. The result does not establish that Qwen can solve every difficult task or compact long contexts reliably. Cloud escalation remains available when the local evidence shows it is needed.

Accepted commits:

- Optimized: `fea45ea23a06fbb0a1faa6cd88c5409cd6ebb29c`, then `ac5296c115a8184bc335f402691cb3e4ab799912`.
- Build: `effc483a1e7a1cbe1b7ba70952b12076158403db`, then `c586f083ddc626aa41ffb513a53b009e8d4d4dcf`.


## Use and reproduce

Run the setup wizard, configure the existing local oMLX endpoint if needed, choose the suggested local models, enhance the coordinator/workers, and select Orchestrator as the default primary agent. `examples/local-first.json` provides the exact model/role choices used here; its model ID must be available in the target OpenCode configuration. Explicit session/UI model overrides can change routing. To select the configured coordinator directly, use `opencode --agent orchestrator`. Provider credentials are still configured through the existing private-file flow.

Explicit benchmark commands (the Build baseline consumes cloud inference):

```sh
python3 scripts/stage-commit-smoke.py
python3 scripts/build-only-baseline.py
python3 scripts/compare-baselines.py
```

The last command is read-only and starts no inference. Complete evidence: `artifacts/baseline-comparison.json`, `stage-commit-result.json`, `stage-commit-events.jsonl`, `build-only-result.json`, `build-only-events.jsonl`, `local-first-effective-agents.json`, `local-first-initial-capture.json`, `local-first-focused-tests.txt`, `local-first-tests.txt` and `local-first-comparison-summary.json`. The previous campaign, including its Build timeout, is retained under `artifacts/before-local-first-20261022-165957`; it is not included in this fresh pair. The previous results are documented in [the historical comparison](baseline-comparison.md).

Native foreground semantics were checked against [OpenCode v2.1.2 subagent source](https://github.com/anomalyco/opencode/blob/v2.1.2/packages/core/src/tool/plugin/subagent.ts#L188).

Post-change verification: **50 focused checks passed**; `npm test` completed with **129 passed, zero failed, five opt-in live tests skipped** (137.22 seconds). Python/JavaScript syntax checks and `git diff --check` passed. The matched comparison was reverified read-only after the harness fixes; no extra inference runs were needed.
