# Native OpenCode profile and portable benchmark

This repository provides a native single-worker Hybrid profile and a Python standard-library
benchmark CLI. The benchmark runs the same frozen TTL-cache task through Codex (cloud planner
and one cloud worker) and OpenCode Hybrid (cloud coordinator/reviewer and one local worker).

## Start on another Mac

Install Python 3.9 or newer, Git, Codex CLI and OpenCode CLI. Authenticate both clients and configure your
local model server. No Local Worker plugin or Python packages are needed to **run** this benchmark.
The native database reader targets OpenCode's `session_v2` / `session_message` schema; unsupported
schemas produce a blocked result, not invented usage. The config reader requires strict JSON.

Clone this branch, or copy the checkout, then run from its root:

```sh
git clone --branch native-patcher https://github.com/nab0y4enko/opencode-agent-setup.git
cd opencode-agent-setup
python3 -B -m unittest discover -s benchmarks -p 'test_*.py' -v
python3 benchmarks/run.py --help
```

The tests use fake clients and temporary databases. They make no paid model calls.

Configure the native profile as described below. Replace `YOUR_SERVED_MODEL_ID` with the actual
model served on this Mac. Choose a new output directory **outside the checkout**:

```sh
python3 benchmarks/run.py run \
  --out "$HOME/benchmark-runs/mac-a-001" \
  --label mac-a \
  --local-model 'omlx/YOUR_SERVED_MODEL_ID'
```

Without `--live`, this prepares identical fixture repositories, freezes the inputs and prints
preflight blockers and planned commands. Resolve blockers before continuing. To execute that
prepared run, repeat the same command with `--live`; options that differ from the prepared run
are refused before anything launches:

```sh
python3 benchmarks/run.py run \
  --out "$HOME/benchmark-runs/mac-a-001" \
  --label mac-a \
  --local-model 'omlx/YOUR_SERVED_MODEL_ID' \
  --live
```

**Live runs consume model usage.** They default to a 180-second budget per arm, one initial
worker assignment and at most one repair. The default cloud model is `gpt-6.1-sol`, the Codex
worker is `gpt-6-luna`, and reasoning is medium. Both arms must use the same cloud model.
The CLI overrides apply to the benchmark invocation; the runner does not write global settings.
A started run cannot be restarted for free: use a fresh output directory for another attempt.

Per-Mac paths are explicit options if the defaults differ:

```text
--codex-bin          codex
--opencode-bin       opencode   (the OpenCode desktop app bundles one at
                                /Applications/OpenCode.app/Contents/Resources/opencode-cli)
--codex-home         ~/.codex
--opencode-config    ~/.config/opencode/opencode.json
--opencode-db        ~/.local/share/opencode/opencode.db
--codex-cloud-model  gpt-6.1-sol
--opencode-cloud-model openai/gpt-6.1-sol#medium
--child-model        gpt-6-luna
--timeout           180
```

`--opencode-config` must identify the installed profile OpenCode actually uses; it is inspected
and fingerprinted, not installed or merged by the benchmark. Keep the cloud models and task
settings identical across Macs. Hardware and local-model differences are recorded separately.

## Read and compare results

```sh
python3 benchmarks/run.py report "$HOME/benchmark-runs/mac-a-001"
python3 benchmarks/run.py compare \
  "$HOME/benchmark-runs/mac-a-001" \
  "$HOME/benchmark-runs/mac-b-001" \
  --out-dir "$HOME/benchmark-runs/comparison-001"
```

Copy each **whole output directory** between Macs, including `arms/`, `archives/`, and manifests.
Reports and comparisons use retained evidence and launch no models. `REPORT.md` and `report.json`
show acceptance, failed gates, usage and timing; `COMPARISON.md` and `comparison.json` compare
compatible rounds. Anything still running in an arm's own process group after the client exits is
terminated before the final check. Execution closeout archives and verifies owned fixture repositories
before removing them. Reports do not delete repositories; archive receipts remain in the output directory.

Passing tests alone does not accept an arm. Acceptance also requires the frozen fixture and scope,
recorded routing/completion, budget, and an authoritative semantic verdict matching the exact diff.
Codex cumulative input/output is counted once per session; cached input, cache-write input and
reasoning are subsets. The Codex worker's own recorded turns must fit one assignment plus one repair,
whichever root tool dispatched them.
OpenCode's disjoint assistant-message counters are summed once, with unexplained maintenance kept
separate. Failed/timeout spend remains visible. Missing usage is unknown, never zero. Savings and
per-completed-task figures are undefined when the required evidence or completed tasks are missing.
Raw tokens are not subscription quota debits or prices; cache differences limit cross-Mac comparisons.

## Optional Codex desktop import

Use `prepare` with the same options as `run`. Follow the generated `DESKTOP.md` and paste the exact
`prompts/codex-app.txt` into a new desktop chat in the prepared Codex fixture repository. Then:

```sh
python3 benchmarks/run.py finish "$HOME/benchmark-runs/mac-a-app-001" \
  --codex-thread YOUR_ROOT_THREAD_ID --live
```

This imports the actual root and descendants, verifies the result, and launches Hybrid only after
an accepted import. Desktop runs are labelled separately from CLI runs. Their session budget is
checked retrospectively; the runner cannot terminate a desktop session. Final verification time
is included in the arm's elapsed-time check. Do not transfer solutions or evidence between arms.

## Install the native profile

Merge `config/opencode.json` into your installed OpenCode JSON **without replacing your existing
providers or global model selection**. The profile leaves Hybrid/review on the caller's cloud model
and assigns `general`, `explore`, `title`, and `summary` to the configured local provider.

Place the sidecars next to the installed JSON:

- `local-model.txt`: the actual served local model ID.
- `omlx-url.txt`: the local OpenAI-compatible endpoint, for example `http://127.0.0.1:8000/v1`.
- Copy `omlx.key.example` to `omlx.key` and replace its entire content with the single key line.
  Keep this secret out of Git. Do not add comments to a substituted key file.

Edit the local model's context/output limits to match that Mac's actual model build. The supplied
262144/8192 values are examples from an earlier measured profile, not discovered universal limits.
The local model must support tool calls. Native permission denials remain in force.

`config/parallel-up-to-4.json` is an optional, unqualified overlay; the benchmark uses one worker.
Its “four” is prompt guidance, not a verified scheduler limit.

## Historical evidence

`benchmarks/fixture/` intentionally starts with 12 tests and three failing expiry-boundary cases.
Do not fix that baseline in this repository. `benchmarks/results/`, `benchmarks/legacy/`, and
`benchmarks/development/` preserve earlier runs and rejected candidates. They are not fresh results
from this runner. The old protocol in `benchmarks/PROTOCOL.md` documents those historical rounds.
Offline runner tests establish software behavior; they do not establish a live benchmark victory
or a measured token saving.
