# Benchmark results

Every paid round is listed, failed ones included. "Cloud" is all cloud tokens of an arm (Codex:
Sol + Luna; Hybrid: Sol coordinator + reviewer). Cached input is counted inside cloud tokens and
shown separately in each round's `REPORT.md`. Raw tokens are not prices or quota.

## Mac Studio M5 Max audit (2026-10-28)

Hardware: **Mac Studio, Apple M5 Max, 18 CPU cores, 40 GPU cores, 128 GB unified memory**.
Software: macOS 27.0.1, Xcode 27.1 (27A9275), Codex CLI 0.165.0, OpenCode 2.2.0,
oMLX 0.7.3rc1 (3517). Both cloud roots use GPT-6.1 Sol medium; Codex workers use GPT-6 Luna
medium. The local served alias `qwen-3.8-nf-splash` is `Qwen3.8-Flash-Next-UD-Q4_K_XL`,
served through oMLX's external Splash/GGUF backend, with context 262,144 and output 8,192.
This differs from the M1 Max model and context below; these are separate machine/model measurements.

The updated profile was merged into the installed configuration with verified private backups,
preserving the selected cloud model, other providers/agents, local limits and existing permission
rules. Offline regression tests cover accounting, frozen inputs, evidence seals, process cleanup,
recovery archives and hardware redaction. Frozen fixture solutions remain unchanged in this repository.

| fixture / round | Codex accepted | Codex cloud (Sol / Luna) | Codex s | Hybrid accepted | Hybrid attributed cloud | Hybrid local | unknown maintenance | Hybrid s |
|---|---|---|---|---|---|---|---|---|
| `ttl-python` / 1 | yes | 408,715 (327,394 / 81,321) | 111.662 | **no**: installed shell permission denied the worker check; no review | 15,994 | 49,065 | 965 | 73.356 |

Both Python patches passed all 12 tests in the runner's independent check. Hybrid stopped after the
permission denial, without its own final verification or authoritative review. It is **rejected**;
its low spend is not an accepted saving, and the accepted-arm comparison ratio is undefined.
Hybrid's recorded cloud interval is 15,994–16,959 tokens; the 965 unattributed maintenance tokens
remain separate. Both checkouts were archived, verified and removed, including ignored artifacts.
The redacted [round record](m5max-2026-10-28-ttl-01.json) contains hardware, seat counts, check results
and evidence/archive hashes. Raw run directories and credentials remain outside the repository.

`swiftui-list` has **no completed measurement on this Mac**. Two unpaid preparations were stopped:
the first was superseded by the reviewed profile correction, and the second was stopped while
authorization for the required worker check remains pending. Xcode had not produced a baseline
summary. Neither preparation launched a model arm; neither is a pass or a token comparison.
Their checkouts, partial Xcode logs and build artifacts were archived and verified before removal;
their run-owned simulators were deleted. No installed permission denial was bypassed.

The current runner reports uncertainty intervals and requires their upper bounds to meet token
targets. Historical attributed-only shares below remain recorded as originally published; excluding
maintenance does not, by itself, prove a target under the stricter current calculation.

## SwiftUI simulator fixture (`swiftui-list`, M1 Max profile at `640778a`)

Targets: Hybrid accepted in 3 of 3 final rounds; Hybrid cloud ≤ 50% of Codex cloud; Hybrid cloud
share (Sol ÷ (Sol + local)) ≤ 0.35, stretch ≤ 0.20.

All rounds ran on 2026-10-27 on one Mac (Apple silicon, 32 GB, macOS 27.0.1, Xcode 27.1): Codex CLI
0.164 with GPT-6.1 Sol medium and GPT-6 Luna workers, OpenCode 2.1.4 with GPT-6.1 Sol medium and
`Qwen3.5-9B-OptiQ-4bit` on oMLX.

| round | profile change | Codex accepted | Codex cloud (Sol / Luna) | Codex s | Hybrid accepted | Hybrid Sol | Hybrid local | Hybrid s | share | Hybrid / Codex |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | first profile | yes | 553,995 (407,999 / 145,996) | 115 | yes | 76,401 | 161,713 | 551 | 0.321 | 0.138 |
| 2 | none | yes | 624,671 (452,486 / 172,185) | 115 | **no**: compile error; `check.sh` showed only `TESTS total=0`, so no repair was sent | 76,626 | 78,272 | 281 | 0.495 | 0.123 |
| 3 | `check.sh` lists compiler errors; coordinator quotes requirements, treats build failures as repairs, accepts receipts as written; one-call review | yes | 647,303 (524,454 / 122,849) | 123 | yes | 55,695 | 130,799 | 697 | 0.299 | 0.086 |
| 4 | none | yes | 637,618 (471,426 / 166,192) | 118 | yes | 55,384 | 129,730 | 910 | 0.299 | 0.087 |
| 5 | none | yes | 722,194 (503,408 / 218,786) | 166 | yes | 55,920 | 123,786 | 559 | 0.311 | 0.077 |

**Final rounds 3–5 (profile at commit `640778a`):**
- Accepted 3/3 in both arms.
- Hybrid cloud is a median 0.086 of Codex cloud, about 12× fewer cloud tokens. The cloud share
  has a median of 0.299 (0.299–0.311), so the 0.35 target held every round and the 0.20 stretch
  target never did.
- Hybrid's cloud spend is consistent at 55–56k:
  - the coordinator makes five requests (one `explore` question, one worker contract, its own
    check, one review, and the reply), about 46k;
  - the reviewer makes one request, about 10k;
  - no repair or clarification round trips occurred.
- Local spend is 124–131k:
  - `explore` takes 22–41k and 1.5–7 minutes;
  - the single worker takes 90–102k.
- Hybrid takes 4.5–7× the Codex wall-clock time (559–910 s against 118–166 s).
- The share excludes 6–13k tokens per session that were not attributed to any message. In round
  1 these were traced to local title generation, so the true cloud share is slightly lower.
- What stands between this profile and 0.20: each coordinator request carries the fixed system
  prompt, the tool definitions and the skill catalogue (about 3k). Denying skills to `hybrid`
  would save roughly 15k cloud tokens per task (share about 0.25), but it removes skills from the
  default agent. That is left as the user's choice and was not benchmarked.

## Earlier rounds (older profiles or fixtures; not comparable with the table above)

Their full records are in git history at tag `history/before-cleanup`.

| date | task | Codex / direct cloud | Hybrid cloud | Hybrid local | outcome |
|---|---|---|---|---|---|
| 2026-10-26 | Python TTL fixture, direct Sol vs native Hybrid (old three-arm protocol) | 43,932 (direct Sol, accepted) | 54,967 | 60,876 | Hybrid rejected: verification evidence missing |
| 2026-10-26 | Real Tiviary tvOS task, Codex App Sol+Luna vs native Hybrid (retrospective audit) | 6,171,523 (accepted) | 627,038 | 3,738,469 | Hybrid accepted only after three local repairs and outside corrective guidance: 10% of Codex cloud, not autonomous |
| 2026-10-27 | Python TTL fixture, portable runner, 180 s budget | 425,757 (Sol 274,767 / Luna 150,990, accepted) | ≥ 64,360 | 68,361 | Hybrid hit the deadline before its check and review |
