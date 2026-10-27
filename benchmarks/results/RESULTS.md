# Benchmark results

Every paid round is listed, failed ones included. "Cloud" is all cloud tokens of an arm (Codex:
Sol + Luna; Hybrid: Sol coordinator + reviewer). Cached input is counted inside cloud tokens and
shown separately in each round's `REPORT.md`. Raw tokens are not prices or quota.

## SwiftUI simulator fixture (`swiftui-list`, current profile)

Targets: Hybrid accepted in 3 of 3 final rounds; Hybrid cloud ≤ 50% of Codex cloud; Hybrid cloud
share (Sol ÷ (Sol + local)) ≤ 0.35, stretch ≤ 0.20.

| round | profile change | Codex accepted | Codex cloud (Sol / Luna) | Hybrid accepted | Hybrid Sol | Hybrid local | share | Hybrid / Codex |
|---|---|---|---|---|---|---|---|---|

## Earlier rounds (older profiles or fixtures; not comparable with the table above)

Their full records are in git history at tag `history/before-cleanup`.

| date | task | Codex / direct cloud | Hybrid cloud | Hybrid local | outcome |
|---|---|---|---|---|---|
| 2026-10-26 | Python TTL fixture, direct Sol vs native Hybrid (old three-arm protocol) | 43,932 (direct Sol, accepted) | 54,967 | 60,876 | Hybrid rejected: verification evidence missing |
| 2026-10-26 | Real Tiviary tvOS task, Codex App Sol+Luna vs native Hybrid (retrospective audit) | 6,171,523 (accepted) | 627,038 | 3,738,469 | Hybrid accepted only after three local repairs and outside corrective guidance: 10% of Codex cloud, not autonomous |
| 2026-10-27 | Python TTL fixture, portable runner, 180 s budget | 425,757 (Sol 274,767 / Luna 150,990, accepted) | ≥ 64,360 | 68,361 | Hybrid hit the deadline before its check and review |
