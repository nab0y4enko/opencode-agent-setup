# Matched baseline comparison — 22 October 2026

This is the historical pre-optimization campaign. Its benchmark evidence was archived under `artifacts/before-local-first-20261022-165957` before the local-first rerun. See [the corrected cloud-led comparison](cloud-led-comparison.md) for the current profile. The [all-local experiment](local-first-comparison.md) was withdrawn because planning and review must remain on Sol.

Both approaches produced independently accepted results on the same two-stage clamp task. The accepted Build-only run took 61.507 seconds versus 211.785 seconds for mixed. Build-only first stalled and timed out at five minutes; that attempt is retained. Including it, summed Build attempt time was 361.587 seconds. Actual dollar costs are unavailable.

## Measured results

Execution timing starts immediately before `opencode run` and ends when that process returns. It includes native runtime, inference and tools, and excludes fixture creation and independent verification. Failed-attempt time includes explicit interruption; gaps between attempts are excluded. These are wall-clock measurements, not summed child-session spans.

| Metric | Mixed accepted run | Build accepted retry | Build including failed attempt |
|---|---:|---:|---:|
| Attempt time (seconds) | 211.785 | 61.507 | 361.587 |
| Attempts | 1 | 1 accepted retry | 2 |
| Cloud input tokens | 19,723 | 8,229 | 15,213 |
| Cloud output tokens | 3,548 | 1,029 | 1,549 |
| Cloud reasoning tokens | 210 | 159 | 262 |
| Cloud cache read tokens | 88,192 | 62,976 | 103,040 |
| Cloud cache write tokens | 0 | 0 | 0 |
| Local input tokens | 5,479 | 0 | 0 |
| Local output tokens | 1,000 | 0 | 0 |
| Local reasoning tokens | 688 | 0 | 0 |
| Local cache read tokens | 52,640 | 0 | 0 |
| Local cache write tokens | 0 | 0 | 0 |
| Actual dollar cost | Unknown | Unknown | Unknown |

Totals cover the assistant/compaction counters OpenCode recorded; provider work not reported during the stalled request cannot be measured here. Token categories are reported as stored, without treating their sum or the analyzer’s cache-weighted heuristic as a bill. Cloud cost fields were zero, and the authenticated model catalog supplied `cost: []`; the interrupted message had no cost. These records cannot distinguish unpriced usage from free usage. No invoice data or local energy/hardware measurement was available. The analyzer’s local `$0` is an inference-rate convention, not measured operating cost.

## Task, routes and verification

Each disposable Git repository started with byte-identical `.gitignore`, `fixture.py`, `test_fixture.py` and `unrelated.txt` (SHA-256 hashes retained in the evidence). Stage 1 fixes clamp range behavior without changing the existing three tests and commits only `fixture.py`. Stage 2 adds one inverted-bounds `ValueError` test, demonstrates its failure, implements validation, passes four tests, and commits `fixture.py` plus `test_fixture.py`. Both must preserve patch and test evidence and leave the tracked worktree clean.

- Mixed: Sol medium coordinator → local Qwen General → Sol high Build → Sol high cloud reviewer, all foreground. The coordinator used only read/subagent tools; the reviewer only read.
- Build-only: Sol high Build performs both stages with no child sessions or delegation calls.
- Both accepted runs passed independent replay of each commit, exact passing test counts, committed-patch/artifact equality, regression failure against stage-1 source, and 637 final integer cases covering negative, equal and inverted bounds.
- Native messages confirm the requested agent/model variants, no recorded errors in accepted runs, and successful completion of every measured session. A separate Python SQLite aggregation matched every token category for each session and the aggregate.

Accepted commits:

- Mixed: `7398c9b7f00baae3b5d5588436e841234e19516f`, then `24c6b179d3ff14bac5f6b39c1e66d3882001fb7d`.
- Build: `73e1c4e9f040d3b975631d20cfe2d071ad1931e5`, then `f7f608cf422a2246684b76bb66a2d8c148a83b58`.


## Failed attempt and interpretation

The first Build attempt (`ses_e9aaaa156ffeaDJORPk7u7k0Tc`) completed stage 1 and the expected failing stage-2 test run, then stopped producing tool records. The five-minute harness limit killed the CLI and explicitly interrupted that exact native session; SQLite confirms `interrupted`. No pending permission request was found after cancellation. The available records do not establish why execution stalled. This is a failed, partially completed attempt, not an accepted result. It consumed 6,984 input, 520 output, 103 reasoning and 40,064 cache-read cloud tokens; its captured totals reconcile with SQLite. The retry used a fresh identical fixture and unchanged settings, and completed normally without intervention. Its red-test shell command was identical to the stalled attempt’s command, so a failing unittest exit alone did not reproduce the stall.

On the accepted pair, mixed took 3.44× as long and recorded 2.40× the cloud input tokens; its cloud output, reasoning and cache-read counts were also higher. The coordinator and reviewer added 9,479 cloud input tokens. Mixed additionally used local Qwen. Across all attempts, Build took more time because of the timeout; token category tradeoffs differ, so no dollar-cost ranking follows.

This is one small task and one accepted run per approach, with a Build retry. Mixed includes enhanced role prompts and an extra cloud review; Build-only uses the native Build prompt. Provider caching, warm state and network latency were not controlled or randomized. These measurements compare the shipped approaches on this task and do not isolate the causal effect of delegation or establish general savings.

## Reproduction and evidence

Inference is opt-in through these scripts:

```sh
python3 scripts/stage-commit-smoke.py
python3 scripts/build-only-baseline.py
python3 scripts/compare-baselines.py
```

For this campaign, the exact read-only reconciliation command was:

```sh
python3 scripts/compare-baselines.py --failed-build-attempt artifacts/build-timeout-result.json
```

`compare-baselines.py` makes no inference requests. Failed attempts are included only when explicitly supplied, preventing a later campaign from accidentally counting a stale failure. The measured fixture repositories and both accepted commit chains remain available at the paths recorded in the JSON.

Evidence in the ignored local `artifacts/` directory: `baseline-comparison.json` (complete independent verification, file hashes, raw counters, routes and all attempts), `stage-commit-result.json`, `stage-commit-events.jsonl`, `build-only-result.json`, `build-only-events.jsonl`, `build-timeout-result.json`, `build-timeout-events.jsonl`, `build-timeout-usage.json`, `benchmark-model-pricing.json` and `benchmark-tests.txt`. Earlier artifacts were preserved under `before-comparison-20261022-163358/`.

Verification of the harness changes: 20 focused capture/verifier/reconciliation tests passed. `npm test` completed with 124 passed, zero failed and five opt-in live tests skipped (137.10 seconds). `git diff --check` and Python compilation passed. The paid benchmark runs above were explicit, separate from those default tests.
