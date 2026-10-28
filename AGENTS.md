# OpenCode Hybrid: cloud plans, local models work

## The idea

Mobile app development (SwiftUI/iOS: UI direction, implementation, bug fixes) with fewer cloud
tokens. The baseline is the Codex CLI flow: GPT-6.1 Sol at medium reasoning plans and reviews, and
GPT-6 Luna subagents implement. This repository replaces the Luna seat with a local model served by
oMLX, inside native OpenCode 2:

- **Cloud (whatever model is selected in the TUI, e.g. Sol medium):** planning, contracts, the final
  check summary, one review of the exact diff.
- **Local (oMLX):** reading, searching, editing, building, testing.

Reliable orchestration matters more than speed. The goal is a Hybrid session whose cloud share is
small: ≤ 0.35 is the target, ≤ 0.20 the dream. Absolute cloud tokens must fall against the Codex
flow too, so a share bought by local waste does not count.

## The profile (`config/opencode.json`)

Native OpenCode 2 configuration only: no plugin, no controller. `default_agent` is `hybrid`; the
model picker in the TUI chooses the cloud model, and switching it (e.g. to Astra or Opus for a hard
task) changes planning and review.

| agent | model | job | boundary |
|---|---|---|---|
| `hybrid` | inherited (cloud) | plans, writes 1–4 contracts, runs the final check, asks one review | cannot edit; may call only `general`, `explore`, `review` |
| `general` | local | implements one contract, runs its check once, returns a ≤120-word receipt | unrestricted shell; no subagents, no skills |
| `explore` | local | answers one lookup question (OpenCode's built-in prompt) | no skills |
| `review` | inherited (cloud) | reviews the exact diff, ends with `VERDICT: PASS|CHANGES_REQUIRED <sha256>` | unrestricted shell; cannot edit, no skills |
| `title`, `summary` | local | session housekeeping | — |

Facts that shape the prompts (OpenCode 2.1.4):
- An agent's `system` text replaces OpenCode's base prompt and the GPT-tuned provider prompt.
- A subagent's whole final reply is returned to its caller, so short receipts are the main lever on
  cloud tokens.
- The local model can serve 1–4 requests at once; four parallel requests gave about 2.8× the
  throughput of one on the reference Mac.

### Install on a Mac

1. Merge `config/opencode.json` into `~/.config/opencode/opencode.json`, preserving existing
   providers, models and the selected cloud model. Do not replace the whole installed
   configuration. Remove any `shell` rule that restricts `hybrid`, `general` or `review` (see
   *Permissions* below); keep every other custom rule.
2. Next to it, place three sidecars:
   - `local-model.txt`: the served model ID;
   - `omlx-url.txt`: e.g. `http://127.0.0.1:8000/v1`;
   - `omlx.key`: one line, the oMLX API key. Never commit it.
3. Set `limit.context` and `limit.output` to that Mac's real local limits. The profile assumes
   32,768 and 8,192.
4. Log in to the cloud provider in OpenCode (`opencode auth login`).
5. Inspect the effective roles with `opencode debug agents --standalone`. Confirm `general` and
   `explore` use the served local model and `hybrid` and `review` inherit the selected cloud model.

### Permissions

The benchmark needs unrestricted shell for `hybrid`, `general` and `review`, as Codex has full
access. The local model wraps commands unasked (`cd … &&`, `2>&1 | tee <log>`, `printf`, `echo`),
and OpenCode checks each pipeline part, so any deny-by-default allowlist rejects the Hybrid arm.
The role boundaries in the table (no edits for `hybrid` and `review`, no subagents or skills for
workers) are part of the measured design and stay.

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
- `compare` adds medians and accepted counts across rounds.

**Accounting rules that must never be weakened:**
- Codex cumulative usage is counted once per session; cached input and reasoning are subsets.
- OpenCode per-message usage is summed once; any session-aggregate gap stays separate maintenance.
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

## Repository map

```
AGENTS.md                 this document
config/                   the OpenCode profile and sidecar examples
benchmarks/run.py         CLI: prepare, run, finish (Codex App import, ttl-python only), report, compare
benchmarks/accounting.py  usage, routing and verdict accounting (offline)
benchmarks/permissions.py permission gate: effective OpenCode rules and the local probe
benchmarks/hardware.py    privacy-safe hardware facts for reports
benchmarks/fixtures.py    fixture registry
benchmarks/fixtures/      frozen benchmark repositories
benchmarks/test_*.py      offline tests: fake clients, temporary databases, no paid calls
benchmarks/results/       RESULTS.md and redacted summaries of final rounds
```

## Rules for agents editing this repository

- Run the full offline suite before every commit; it must stay green. Defects get a regression test
  that fails first.
- Never weaken an accounting, evidence or acceptance check to make a run pass.
- Python standard library only, Python 3.9 compatible; no machine-specific paths in code or tests.
- Keep the profile prompts short and structured: role, inputs, steps, limits, exact reply. Change one
  rule at a time and keep it only if the benchmark shows it helps.
- No plan, design or scratch documents in the tree; this file is the documentation.
- Published results are redacted: no account identifiers, keys or private skill text. Raw run
  directories stay outside the repository.
