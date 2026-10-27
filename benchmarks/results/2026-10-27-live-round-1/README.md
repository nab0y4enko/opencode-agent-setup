# Live round 1 of the portable runner (2026-10-27, one Mac)

One authorized matched two-arm CLI round, `benchmarks/run.py run --live`, 180 s per arm.

| | Codex CLI (Sol root + Luna worker) | OpenCode Hybrid (Sol root/review + local worker) |
|---|---|---|
| accepted | **yes** | **no** (deadline) |
| cloud tokens | 425,757 exact (root 274,767, worker 150,990) | ≥ 64,360 lower bound (root 40,865, review 23,495) |
| of which cached input | 375,296 | 0 recorded as cache read on root/review |
| local tokens | — | 68,361 (`omlx/Qwen3.5-9B-OptiQ-4bit`) |
| arm seconds | 62.3 (62.7 with final check) | killed at 180 (190.7 with kill and closeout) |
| final check | 12 tests, 0 failures | never ran (deadline expired) |
| verdict | plain `VERDICT: PASS` bound to the diff digest | none: review interrupted |

Both arms produced the same one-line patch (`>` to `>=`). The Hybrid patch was never independently
checked or reviewed within budget, so it is not an accepted task. Per-task cost and the
Hybrid/Codex ratio are **undefined**: the 64,360 figure is a lower bound of a failed arm, not a saving.

Where Hybrid's time went (native records): the local worker took about 42 s before its first token on
an 8.3k-token prompt and finished at about 105 s; the reviewer started at 136 s, spent part of its
budget globbing for `AGENTS.md` outside the fixture, and was interrupted at the deadline.

Environment: codex-cli 0.164.0, OpenCode CLI 2.1.4 (bundled in the OpenCode desktop app), oMLX serving
`Qwen3.5-9B-OptiQ-4bit` with a 32,768-token server context window, Apple Silicon, 32 GB RAM.

This directory is a **summary**. Raw Codex rollouts contain account identifiers and the OpenCode native
records contain private user skill text, so they are not published. Their digests are in
`arms/*/evidence-sha256.json`; the full sealed run (rollouts, native records, logs, verified
tar/bundle archives) is retained outside the repository on the measuring Mac. `report.json` and
`REPORT.md` were regenerated offline from that sealed run after the OpenCode tool-part fix in this
commit; acceptance and totals are unchanged by that regeneration.
