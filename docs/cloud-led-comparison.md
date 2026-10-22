# Cloud-led mixed profile and verified comparison — 22 October 2026

Sol owns planning, coordination and final correctness review. Qwen is a bounded execution worker. The earlier all-local recommendation was withdrawn because moving planning and review to Qwen violates that quality boundary. Cloud models remain available.

## Current routing and overhead reduction

- Sol medium Orchestrator plans the task, gives one complete assignment to local General, then reviews the actual patches and test evidence in the same cloud session. Worker self-checks remain implementation evidence, not final approval.
- Sol high Plan handles explicit planning mode; Sol high Build handles difficult implementation or an evidence-backed local blocker; the independent Sol high reviewer is available when a separate review seat is warranted. Cloud dispatch permissions remain allowed; the benchmark has no blanket deny or added per-call approval gate.
- Qwen handles General implementation/tests, Explore/Scout discovery and mechanical title generation. Substantive summaries and compaction stay on Sol medium to preserve reasoning context. Native hidden-role prompts remain unchanged.
- Related dependent stages reuse one local worker context, with a separate verified commit per stage. The cloud coordinator checks their evidence once. No forced cloud stage-2 implementation or automatic extra reviewer is needed on this small task. The coordinator has an eight-step budget and General retains 24 steps.

The exact choices are in `examples/mixed-workers.json`. Wizard recommendations were corrected to match; saved user choices are not silently overwritten. To use the mixed profile, configure the local provider through the existing private-key flow, select the suggested cloud/local role models, enhance the coordinator/workers, and make Orchestrator the default or start `opencode --agent orchestrator`. Explicit session/model selections can override configured defaults.

## Fresh measurements

The corrected mixed run and native Build-only run started from byte-identical tracked fixtures and ran sequentially, one inference attempt each. Both use the same functional acceptance criteria and per-stage evidence. Timing covers CLI launch through exit, including tools and inference, excluding setup and independent verification.

| Metric | Cloud-led mixed | Fresh Build-only |
|---|---:|---:|
| Execution seconds | 122.795 | 61.802 |
| Cloud sessions / turns | 1 / 3 | 1 / 14 |
| Local sessions / turns | 1 / 19 | 0 / 0 |
| Cloud input tokens | 6,493 | 12,455 |
| Cloud output tokens | 756 | 1,349 |
| Cloud reasoning tokens | 0 | 83 |
| Cloud cache-read tokens | 6,400 | 73,088 |
| Cloud cache-write tokens | 0 | 0 |
| Local input tokens | 19,218 | 0 |
| Local output tokens | 6,588 | 0 |
| Local reasoning tokens | 3,273 | 0 |
| Local cache-read tokens | 280,960 | 0 |
| Local cache-write tokens | 0 | 0 |
| Actual dollar cost | Unavailable | Unavailable |

The corrected mixed run recorded **47.9% fewer cloud input tokens** than fresh Build-only, with fewer cloud output and cache-read tokens too. It took **1.99× as long**. Cloud planning/review remained in place. Compared with the original mixed pipeline, cloud input fell from 19,723 to 6,493 (67.1% less); cloud sessions fell from three to one, and cloud assistant turns from 20 to three. Original elapsed time was 211.785 seconds.

These are native recorded assistant/compaction counters, independently reconciled against SQLite for each session and the complete tree. Recorded cloud cost fields were zero without pricing, which does not establish free usage. No invoice data or local hardware/electricity measurement was available. Cache-weighted totals are heuristics, not a bill; no dollar saving is claimed.

## Independent verification

Both results passed:

- Exact starting SHA-256 hashes for `.gitignore`, `fixture.py`, `test_fixture.py` and `unrelated.txt`.
- Two separate commits with exact scopes: stage 1 changes only `fixture.py`; stage 2 changes `fixture.py` and `test_fixture.py`.
- Independent replay: three passing tests at stage 1, four at stage 2; saved patches match committed diffs; red test evidence is present.
- The four-test regression fails against stage-1 source because `ValueError` is not raised, then passes with stage-2 source.
- Four final tests plus 637 independent integer cases covering negative, equal and inverted bounds; clean tracked worktrees and unchanged excluded files.
- Actual model attribution: Sol medium cloud coordinator, one foreground local Qwen worker, no extra delegated reviewer or cloud implementation child. Sol read the evidence and returned `VERDICT: PASS`; the worker did not own that judgment. Native sessions completed successfully and token categories match SQLite exactly.

Accepted commits:

- Mixed: `a37a3e4b4cd166ce5cd16388e665a61549145a44`, then `216dc56ab2f7b137b1894d3344bf3ac2d721b6f7`.
- Build: `fa98e6268899ddc93e1cbc9b30600d02e046538d`, then `39d55220a4a6e74152240ae4b6710c9bfa64940e`.


This is one small task, not a general capability or pricing benchmark. The mixed coordinator uses medium effort with enhanced role instructions, while native Build uses high effort. Provider caching, network latency and warm state were not controlled. Repository regression checks ran during part of the measurement window; this is another reason not to generalize timing. Local execution can take longer; moving judgment back to Qwen would invalidate this comparison’s role requirement.

## Evidence and reproduction

```sh
python3 scripts/stage-commit-smoke.py
python3 scripts/build-only-baseline.py
python3 scripts/compare-baselines.py
```

The first two commands make the configured local/cloud inference requests; the last only independently checks saved results. Evidence is in the ignored local `artifacts/` directory: `baseline-comparison.json`, `cloud-led-comparison-summary.json`, `stage-commit-result.json`, `stage-commit-events.jsonl`, `build-only-result.json`, `build-only-events.jsonl`, `cloud-led-mixed-verification.json`, `cloud-led-effective-agents.json`, `cloud-led-focused-tests.txt` and `cloud-led-tests.txt`. The all-local campaign is archived under `artifacts/before-cloud-led-20261022-182541`; the original mixed/Build campaign, including the old Build timeout, is under `artifacts/before-local-first-20261022-165957`. Neither historical campaign is counted as a fresh attempt here.

Final repository verification: **53 focused checks passed**; `npm test` — **132 passed, zero failed, five opt-in live checks skipped**, 135.34 seconds. Python/JavaScript syntax checks and `git diff --check` passed.

A sanitized, tracked [machine-readable receipt](benchmarks/2026-10-22-cloud-led.json) preserves these measurements and independent verification. After global activation, the Build harness was updated to isolate its configuration and use a private server; a no-inference native check confirmed it retains the native Build prompt/mode and excludes global custom agents. This protects future comparisons and does not change the measurements above.
