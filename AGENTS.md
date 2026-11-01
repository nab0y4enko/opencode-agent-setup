# OpenCode Hybrid: cloud plans, local models work

## The idea

Mobile app development (SwiftUI/iOS: UI direction, implementation, bug fixes) with fewer cloud
tokens. The baseline is the Codex CLI flow: GPT-6.1 Sol at medium reasoning plans and reviews, and
GPT-6 Luna subagents implement. This repository replaces the Luna seat with a local model served by
oMLX, inside native OpenCode 2:

- **Cloud (whatever model is selected in the TUI, e.g. Sol medium):** planning, contracts, the final
  check summary, one review of the exact diff.
- **Local (oMLX):** reading, searching, editing, building, testing.

The profile is for real daily work; `install.py` sets up a new Mac with it, and the benchmark
measures what it costs. Reliable orchestration matters more than speed. The goal is a Hybrid session whose cloud share is
small: ≤ 0.35 is the target, ≤ 0.20 the dream. Absolute cloud tokens must fall against the Codex
flow too, so a share bought by local waste does not count.

## The profile (`config/opencode.json`)

Native OpenCode 2 configuration only: no plugin, no controller. `default_agent` is `hybrid`; the
model picker in the TUI chooses the cloud model, and switching it (e.g. to Astra or Opus for a hard
task) changes planning and review.

| agent | model | job | steps | boundary |
|---|---|---|---|---|
| `hybrid` | inherited (cloud) | plans, writes 1–4 contracts with exact symbols or line ranges, up to two repairs per worker, runs the final check, asks a review and after `CHANGES_REQUIRED` one more | 100 | cannot edit; may call only `general`, `explore`, `review` |
| `general` | local | implements one contract and the tests or specs it names, fixes its own build and test failures (up to three check runs), returns a ≤120-word receipt | 200 | unrestricted shell; no subagents; never weakens an assertion |
| `explore` | local | answers precise lookup questions in ≤160 words | 50 | no skills |
| `review` | inherited (cloud) | reviews the exact diff, ends with `VERDICT: PASS|CHANGES_REQUIRED <sha256>` | 30 | unrestricted shell; cannot edit, no skills |
| `title`, `summary`, `compaction` | local | session housekeeping and summary compaction | — | — |

Facts that shape the prompts (source checked on OpenCode 2.2.5):
- An agent's `system` text replaces OpenCode's base prompt and the GPT-tuned provider prompt.
- A subagent's whole final reply is returned to its caller, so short receipts are the main lever on
  cloud tokens.
- The local model can serve 1–4 requests at once; four parallel requests gave about 2.8× the
  throughput of one on the reference Mac.

### Install on a Mac

Prerequisites: OpenCode 2 on `PATH`, oMLX serving the local model, and its API key.

```sh
python3 install.py --key-file <file with the oMLX key>     # later runs reuse the installed omlx.key
python3 install.py --dry-run                               # the redacted change, nothing written
opencode auth login                                        # once per Mac, for the cloud provider
```

`install.py` merges the profile into `~/.config/opencode/opencode.json` and keeps the previous file
as `opencode.json.bak-<time>`. It keeps other providers, other agents, the selected cloud model and
custom permission rules (before the profile's, so the role boundaries win); it drops any `shell`
restriction on `hybrid`, `general` or `review` (see *Permissions*), a model pinned on `hybrid` or
`review`, and rules earlier profile versions installed. It writes the sidecars `local-model.txt`
(`--model`, else the installed or only served model), `omlx-url.txt` (`--url`, default
`http://127.0.0.1:8000/v1`) and `omlx.key` (mode 600, never printed, never committed). Context is the
served model length and output a quarter of it, at most 32,768, unless `--context`/`--output` say
otherwise. Last it runs `opencode debug agents --standalone` and exits non-zero unless `general` and
`explore` use the local model, `hybrid` and `review` inherit the cloud model, every step limit
matches and the three shell roles may run a wrapped command. Rerun it after changing the profile.

### Maintenance routing and bounded work

OpenCode 2.2.5 summary compaction honors `agents.compaction.model`, falling back to the
session model if resolution fails. The audited installation explicitly pinned that role to Sol;
normal local-worker routing did not override it. This profile pins the supported compaction role
to oMLX. This is a global summary role, including cloud-session summaries; it does not change the
selected cloud model or Hybrid/review routing. Native provider compaction always uses the session
model and bypasses this override. There is no per-worker compaction selector in this version.
Do not change provider compaction settings to work around that boundary; keep contracts/sessions
bounded and report native maintenance spend by its recorded model. Failed compactions may omit
model/effort: accounting must retain unknown attribution rather than invent it.

Sources: [v2.2.5 selection and billing](https://github.com/anomalyco/opencode/blob/v2.2.5/packages/core/src/session/compaction.ts),
[record schema](https://github.com/anomalyco/opencode/blob/v2.2.5/packages/schema/src/session-message.ts),
[model resolution](https://github.com/anomalyco/opencode/blob/v2.2.5/packages/core/src/session/runner/model.ts).
An isolated local-only v2.2.5 probe completed a summary request on oMLX: 753 uncached input,
4,832 cached input, 465 output and 10 reasoning tokens. Raw records stay outside this repository.
The probe used separate configuration/data storage containing only the local provider; it did not
make cloud calls. Recheck routing after upgrades; successful role listing alone is not a request probe.

Contracts are ≤250 words, exploration receipts ≤160 and worker receipts ≤120. Split long work at
explicit, independently testable interfaces rather than extending investigations indefinitely.
One named owner controls each shared build resource. Every build/check invocation counts against
the existing three-run worker limit; retries require diagnosed causes and changes. Preserve the
original command exit code and real compiler diagnostics, and never poll builds waiting for edits.
Critical lifecycle claims need runtime evidence early: actual owning-view scroll callbacks,
held-loader cancellation/obsolete-success fencing, and identity/state preservation. Performance
improvement requires matched baseline conditions. Missing qualification remains a reported gap.

Real-work reviews use one canonical manifest covering tracked and new task content and file modes:

```sh
python3 benchmarks/review_manifest.py --base <recorded-start-commit>  # save outside checkout
# Add --path <task-file> for each explicit task path when unrelated work is present.
```

Give the reviewer that command/base/path list, manifest/digest, all requirements and stable final
check/runtime evidence. Review the whole change and retrieve surrounding context in focused batches.
Compare `--staged` and `--revision HEAD` using the same base/path list with the reviewed
manifest, so index-only hook changes cannot hide behind unchanged working files. Any
content, path, deletion or mode change invalidates approval. The supplementary canonical manifest
in benchmark scope receipts does not replace historical patch digests: frozen fixtures still forbid
new files and retain their original authoritative verdict/acceptance rules. Reports are assembled
from sealed final evidence, not rewritten during implementation.

### Commit, push and recovery ownership

The primary `hybrid` agent owns Git completion; workers and reviewers never commit.
An implementation request authorizes committing and pushing accepted task changes unless the
user or a more specific task contract forbids it. Frozen benchmark contracts retain their own
completion rules. Do not commit every file or worker receipt separately: use coherent,
independently checked and reviewed changes.

1. Record the task branch, upstream and initial staged/unstaged state. Preserve unrelated work.
2. Run the required checks and obtain an independent PASS bound to the exact task changes,
   including new files. Passing tests alone do not approve semantics.
3. Stage explicit task paths, inspect the staged diff and confirm its contents match the reviewed
   snapshot. Exclude unrelated changes and secrets. Changes after review require revalidation
   and a new verdict. Use a clear outcome-focused commit message with the check summary.
   Keep hooks enabled and verify the resulting commit still contains the reviewed content.
4. Push to the task branch without force, then verify the remote branch SHA equals the local
   commit. Do not merge another branch or change remotes to work around a failure.
5. Archive needed files, logs, ignored artifacts and detached histories outside completed task
   worktrees; verify recovery before removing them. Preserve the primary checkout and unrelated
   active work. Confirm no completed task worktrees remain.
6. If checks or review still reject the change, preserve recoverable work and report it as
   incomplete. If push or safe cleanup fails, report the exact remaining action. The final receipt
   includes the commit SHA, verified remote branch, checks, review verdict and cleanup status;
   never report completion with an omitted commit or an unverified push.

### Permissions

The benchmark needs unrestricted shell for `hybrid`, `general` and `review`, as Codex has full
access. The local model wraps commands unasked (`cd … &&`, `2>&1 | tee <log>`, `printf`, `echo`),
and OpenCode checks each pipeline part, so any deny-by-default allowlist rejects the Hybrid arm.
The role boundaries in the table (no edits for `hybrid` and `review`, no subagents for workers) are
part of the measured design and stay.

`prepare` enforces this before any baseline and before any cloud token:
1. It reads the effective rules with `opencode debug agents --standalone` inside the Hybrid
   checkout (so project config counts) and evaluates every command each role runs, wrappers
   included; the last matching rule wins, and `ask` counts as a denial in a non-interactive run.
2. It then has `general` and `review` each run one wrapped command on the local model, in a
   throwaway repository (`<out>/permission-gate/`); no cloud model is called.

A refused rule, a denied probe or a probe that cannot finish blocks the round, with the rule and
the fix in the message (`<out>/permission-gate/permission-gate.json`). On such a blocker, stop and
report it to the user. Never reword profile prompts to fit a restricted allowlist, never route a
command through another tool or shell to evade a denial, and change permissions only with the
user's approval.

## The benchmark (`benchmarks/`)

`benchmarks/run.py` (Python 3.9+ standard library) runs the same frozen task through both flows on
one Mac and accounts for every token:

```sh
python3 -B -m unittest discover -s benchmarks -p 'test_*.py'
python3 benchmarks/run.py run --fixture swiftui-list --out ~/benchmark-runs/swiftui-01 \
  --local-model 'omlx/<served id>' --opencode-bin <opencode CLI>          # prepares; local probe, no cloud call
python3 benchmarks/run.py run --fixture swiftui-list --out ~/benchmark-runs/swiftui-01 \
  --local-model 'omlx/<served id>' --opencode-bin <opencode CLI> --live   # spends tokens
python3 benchmarks/run.py report ~/benchmark-runs/swiftui-01              # offline
python3 benchmarks/run.py compare ~/benchmark-runs/swiftui-0* --out-dir ~/benchmark-runs/summary
```

**Fixtures** (`benchmarks/fixtures/`, registered in `benchmarks/fixtures.py`):
- `swiftui-list`: a small SwiftUI app with 9 unit and 3 UI tests, 5 of them failing at baseline. Its
  frozen `./check.sh <simulator>` prints a compact summary.
- `ttl-python`: a tiny Python bug, 12 tests with 3 failing.

The failing tests are intentional. Never fix a fixture in this repository; solutions belong only in
run directories.

**A round:**
- `prepare` freezes the task, prompts, fixture digests and installed profile, and runs the
  permission gate. It proves the baseline on throwaway simulators (`bench-codex`,
  `bench-opencode`) and deletes them.
- `--live` creates a fresh simulator per arm, then runs the Codex arm (Sol root, up to four Luna
  workers, full access) and then the Hybrid arm, each against its own budget (1,200 s for
  `swiftui-list`).
- The runner's own final check, scope check and digest-bound verdict decide acceptance.
- Checkouts are archived, verified and removed; simulators are deleted.
- An existing `bench-*` simulator is never reused or deleted: delete it yourself.

**Reading `REPORT.md`:**
- *Tokens by seat* shows Sol vs Luna (Codex) and Sol vs local (Hybrid), each split into uncached
  input, cached input, output and reasoning.
- Below it: Hybrid cloud share, Hybrid cloud ÷ Codex cloud, and pass/fail per target.
- Recorded compaction spend is shown separately by request tier, already included in seat totals.
- Absolute cloud counters, cached/uncached input, elapsed time and acceptance remain separate.
  Inflated local cached traffic can lower share without reducing cloud spend.
- `compare` adds medians and accepted counts across rounds.

**Accounting rules that must never be weakened:**
- Codex cumulative usage is counted once per session; cached input and reasoning are subsets.
- OpenCode usage-bearing requests, including compaction/non-assistant records and failed spend,
  are summed once by their recorded model; only unexplained aggregate gaps stay separate maintenance.
- Seats follow the recorded model of each request.
- Failed and timeout spend is kept; unknown usage is never zero.
- Acceptance requires the full suite, the allowed scope, frozen inputs, recorded routing and
  completion, the budget, and an authoritative verdict bound to the exact diff digest.

Results of every paid round: `benchmarks/results/RESULTS.md`.

**Recorded M1 Max result (`swiftui-list`, 2026-10-27, rounds 3–5, profile `640778a`):**
- Both arms were accepted 3/3.
- Hybrid used about 56k cloud tokens against Codex's 637k–722k, a median ratio of 0.086.
- The cloud share was 0.30–0.31, so the 0.35 target held and the 0.20 stretch target did not.
- Hybrid is slower: 9–15 minutes, against about 2 minutes for Codex.
- The main reliability lever was check output a repair can act on: compiler errors, not just
  `TESTS total=0`.
- That profile had 30/40/16/12 steps, an 8,192-token local output limit and workers that ran their
  check once. The current real-work profile has one paired round recorded in `benchmarks/results/RESULTS.md`: both
  arms accepted, absolute cloud tokens lower, but the 0.35 share target missed. One round does not
  establish repeatability. A round still allows each
  worker one repair and one review, because the frozen task prompt and the accounting say so.

## Repository map

```
AGENTS.md                 this document
install.py                installs the profile and sidecars on this Mac and verifies the roles
config/                   the OpenCode profile and sidecar examples
benchmarks/run.py         CLI: prepare, run, finish (Codex App import, ttl-python only), report, compare
benchmarks/accounting.py  usage, routing and verdict accounting (offline)
benchmarks/permissions.py permission gate: effective OpenCode rules and the local probe
benchmarks/hardware.py    privacy-safe hardware facts for reports
benchmarks/fixtures.py    fixture registry
benchmarks/fixtures/      frozen benchmark repositories
benchmarks/test_*.py      offline tests (installer included): fakes and temporary files, no paid calls
benchmarks/results/       RESULTS.md and redacted summaries of final rounds
```

## Rules for agents editing this repository

- Run the full offline suite before every commit; it must stay green. Defects get a regression test
  that fails first.
- Never weaken an accounting, evidence or acceptance check to make a run pass.
- Python standard library only, Python 3.9 compatible; no machine-specific paths in code or tests.
- Keep the profile prompts short and structured: role, inputs, steps, limits, exact reply. The
  profile serves real work; after changing it, rerun `install.py` and record a benchmark round to
  see what it costs.
- No plan, design or scratch documents in the tree; this file is the documentation.
- Published results are redacted: no account identifiers, keys or private skill text. Raw run
  directories stay outside the repository.
