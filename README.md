# opencode-agent-setup

A native OpenCode 2 profile where the cloud model plans and reviews while a local model (oMLX)
reads, edits, builds and tests. Also a benchmark that measures it against the Codex Sol + Luna flow
on a small SwiftUI app.

Everything — the idea, the profile, installation, the benchmark and its results — is in
[AGENTS.md](AGENTS.md).

```sh
python3 -B -m unittest discover -s benchmarks -p 'test_*.py'
python3 benchmarks/run.py --help
```

## Results by machine

Fixture `swiftui-list` (9 unit and 3 UI tests on an iOS simulator). Both arms run on the same Mac
with GPT-6.1 Sol medium as the cloud model: Codex CLI plans with Sol and implements with GPT-6 Luna
workers; OpenCode Hybrid plans and reviews with Sol and implements with the local model. Figures
are medians over the final rounds on an unchanged profile; every round is in
[RESULTS.md](benchmarks/results/RESULTS.md).

| machine | CPU / GPU | RAM | local model (oMLX) | rounds accepted (Codex / Hybrid) | Codex cloud (Sol + Luna) | Hybrid cloud (Sol) | Hybrid local | cloud share | Hybrid ÷ Codex cloud | time (Codex / Hybrid) |
|---|---|---|---|---|---|---|---|---|---|---|
| MacBook Pro 2021 | Apple M1 Max, 10 CPU cores (8P + 2E), 32 GPU cores | 32 GB | `Qwen3.5-9B-OptiQ-4bit` (7.7 GB), context 32,768, output 8,192 | 3/3 / 3/3 | 647,303 | 55,695 | 129,730 | 0.299 | 0.086 | 123 s / 697 s |

Software for the M1 Max rows: macOS 27.0.1, Xcode 27.1 (iOS 27 simulator), Codex CLI 0.164,
OpenCode 2.1.4, oMLX 0.7.3, profile commit `640778a`, rounds run on 2026-10-27.

Cloud share is Sol ÷ (Sol + local) inside the Hybrid session; the target is ≤ 0.35 (stretch ≤ 0.20).
Hybrid ÷ Codex cloud below 0.5 means the hybrid flow at least halves cloud tokens.

### Adding a machine

1. Install the profile and sidecars as in [AGENTS.md](AGENTS.md), with that machine's real local
   limits, and run the offline suite.
2. Run three or more rounds into separate folders (`swiftui-01`, `swiftui-02`, …), each a
   `run … --fixture swiftui-list` prepare followed by the same command with `--live`, using a
   distinct `--label`.
3. Run `python3 benchmarks/run.py compare <round folders> --out-dir <summary folder>`. Copy the
   medians from its *Rounds* section and each round's `REPORT.md` into a new row above, and add the
   rounds to `RESULTS.md`.
4. Publish no host names, account identifiers or keys.
