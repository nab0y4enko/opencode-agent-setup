# Benchmark results

Every paid round is listed, failed ones included. "Cloud" is all cloud tokens of an arm (Codex:
Sol + Luna; Hybrid: Sol coordinator + reviewer). Cached input is counted inside cloud tokens and
shown separately in each round's `REPORT.md`. Raw tokens are not prices or quota.

## Mac Studio M5 Max: current settings, Hybrid only (2026-10-28)

**Accepted: 1/1 Hybrid run** on the current user-updated settings and unchanged benchmark at
`383bd4971b09b52060e16b8a2ac6dc82aba14e01`. The permission gate passed without warnings or
denials. Only Hybrid launched a model arm; Codex was deliberately not attempted.

Hardware: **Mac Studio, Apple M5 Max, 18 CPU cores, 40 GPU cores, 128 GB unified memory**.
Software: macOS 27.0.1, Xcode 27.1 (27A9275), OpenCode 2.2.0 and oMLX 0.7.3rc1 (3517).
Cloud coordinator/reviewer: GPT-6.1 Sol medium. Local model: `qwen-3.8-nf-splash`
(`Qwen3.8-Flash-Next-UD-Q4_K_XL`, oMLX external Splash/GGUF, context 262,144, output 8,192).
The installed profile and benchmark source remained unchanged throughout the run.

| Fixture | Hybrid accepted | Independent final suite | Measured seconds | Attributed cloud | Local | Unattributed maintenance |
|---|---|---|---|---|---|---|
| `swiftui-list` | **yes** | 12/12 passed, zero failed/skipped | 214.520 | 43,069 | 157,188 | 1,029 |

The worker and coordinator also each passed all 12 tests. The authoritative cloud reviewer returned
`PASS` bound to the exact complete-diff digest; the runner independently verified scope, frozen
inputs, config integrity, routing, usage, completion and the 1,200-second budget. No fixture was
changed in this repository.

Cloud tokens are bounded at **43,069–44,098**. Cloud share is **21.40–21.91%**, retaining the
1,029 tokens of unattributed maintenance. This interval is below 35% and above the 20% stretch
threshold. The runner's paired comparison targets remain undefined without Codex: this single
Hybrid run establishes neither a same-round saving against Codex nor a 3/3 reliability result.

The unchanged preparation ran both frozen baselines (12 tests, five intentional failures each) and
two local-only permission probes. Baseline checks took 687.873 and 655.283 seconds because Xcode
waited for simulator diagnostic collection; preparation and probes are outside the measured
Hybrid arm. Its independent final check took 21.264 seconds. No Codex model was called.

All arm checkouts, ignored build/test artifacts and probe repositories were archived, verified and
removed; all run-owned simulators were deleted. Raw evidence remains outside the repository.
The redacted [Hybrid-only record](m5max-2026-10-28-hybrid-only-01.json) includes hardware,
source/config digests, token seats, acceptance gates and verified archive hashes. All 173 offline
regression tests passed before this run.

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
| `ttl-python` / 2 | yes | 299,678 (239,468 / 60,210) | 60.890 | **no**: check allowed, unrelated worker setup/digest commands denied; no review | 9,940 | 116,416 | 918 | 115.199 |
| `ttl-python` / 3 | yes | 281,106 (178,954 / 102,152) | 48.134 | **no**: worker wrapped the check with denied `echo`/`tee` commands; no review | 9,839 | 53,379 | 1,093 | 55.625 |
| `swiftui-list` / 1 | yes | 506,127 (382,852 / 123,275) | 118.045 | **no**: reviewer added denied shell headers/loop; no accepted semantic review | 38,380 | 107,244 | 1,057 | 219.540 |
| `ttl-python` / 4 | yes | 322,445 (262,011 / 60,434) | 61.685 | **no**: worker piped the check through denied `tee`; no review | 9,887 | 61,098 | 974 | 47.569 |
| `swiftui-list` / 2 | **no**: usage limit before its final check | 420,920 (277,706 / 143,214) | 98.404 | **no**: usage limit on the first cloud request | unknown | 0 | unknown | 639.375 |

**Why every Hybrid arm was rejected.** The installed configuration already carried deny-by-default
shell allowlists on `general` and `review` (`shell *` denied, then `cat`, `git diff*`, `shasum`, …
allowed) before this audit. Codex runs with full access, so only Hybrid meets them. The local model
habitually adds `cd … &&`, `2>&1 | tee <log>`, `echo` or `printf` around commands, and each such
wrapper is denied. The M1 Max rounds below recorded no such denial, so these rounds measure the
permission policy, not the profile, and are not comparable with them.

Every Python patch passed all 12 tests in the runner's independent check. All five Hybrid arms are
**rejected**: none reached independent coordinator verification and an authoritative review. Their
low spend is not an accepted saving, and accepted-arm comparison ratios are undefined. Cloud
intervals for Python rounds 1–4 are 15,994–16,959, 9,940–10,858, 9,839–10,932 and 9,887–10,861
tokens; SwiftUI round 1 is 38,380–39,437. Unattributed maintenance stays separate. Every checkout
was archived, verified and removed, including ignored build artifacts. Redacted records:
[ttl 1](m5max-2026-10-28-ttl-01.json), [ttl 2](m5max-2026-10-28-ttl-02.json),
[ttl 3](m5max-2026-10-28-ttl-03.json), [ttl 4](m5max-2026-10-28-ttl-04.json),
[SwiftUI 1](m5max-2026-10-28-swiftui-01.json) and [SwiftUI 2](m5max-2026-10-28-swiftui-02.json).
Raw run directories and credentials remain outside the repository.

Permission and prompt history:
- Before Python round 2 the user authorized two worker allow rules, `./check.sh bench-*` and
  `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest*`; all pre-existing rules were kept.
- Python round 3 tested a worker shell-boundary clarification; it failed.
- Python round 4 tested a stricter worker rule (no `cd`, prefixes, redirects, pipes, chaining or log
  files); the worker still piped the check through `tee`. The rule did not help and is not in the
  repository profile.
- After SwiftUI round 1, the reviewer was told to run only direct `git`, `shasum` and `cat` commands.
  SwiftUI round 2 never reached the reviewer, so the rule is untested and is not in the repository
  profile.
- After the audit the user approved removing every `shell` rule from the installed `general` and
  `review` agents (all other rules kept, private backup retained) and resyncing their prompts to the
  repository profile, so later rounds run under the same open shell policy as the M1 Max rounds.
- Python rounds 2 and 4 overlapped unpaid SwiftUI preparation; their wall-clock values are not
  isolated performance measurements.

SwiftUI round 2 stopped at the ChatGPT subscription usage limit: Codex after its patch and review,
before its own final check (exit 1), and Hybrid on its first cloud request (no usage recorded, so its
cloud spend is unknown, not zero). It is a quota failure, not a measurement of either flow. Its
Hybrid time is almost entirely the runner's final check of an unchanged checkout, which took 637 s;
that round's Codex baseline in preparation took 651 s. Other SwiftUI checks on this Mac took 21–69 s,
so `xcodebuild` UI tests stall intermittently here (testmanagerd/accessibility XPC errors), which
alone can consume most of the 1,200 s Hybrid budget.

Three unpaid SwiftUI preparations preceded the measured runs: the first was superseded by the
reviewed profile correction, the second stopped while check-command authorization was pending,
and the third reproduced the 12-test/five-failure baseline but was superseded by the worker-boundary
correction. Their checkouts and build/test artifacts were archived and verified before removal;
their run-owned simulators were deleted. None launched a model arm or counts as a token comparison.

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
