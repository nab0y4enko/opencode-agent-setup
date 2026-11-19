# OpenCode with a cloud orchestrator and local Splash workers

## The idea

A cloud model decides and a local model does the work, in native OpenCode 2: no plugin, no wrapper.

- **Cloud, GPT-6.2 Sol at high effort (`build`):** reads the request and project rules, investigates,
  settles the claims the plan depends on with a small experiment, writes the briefs, reviews the
  diff. Its tokens are the scarce budget, so it stays idle while workers run.
- **Local, Qwen3.8-Flash-Next IQ3_S on Splash:** the `implementer` writes the code, the failing-first
  test and the docs, runs the checks and commits locally; the `validator` re-runs the checks, proves
  the test fails when the change is reverted and checks every changed sentence in the docs.

Workers run one at a time (they share one model and its prompt cache) and pass results as brief and
report files.

## The profile (`config/`)

`config/opencode.jsonc` becomes `~/.config/opencode/opencode.jsonc`; `config/AGENTS.md` becomes the
global `~/.config/opencode/AGENTS.md`, the orchestration rules every session reads.

| agent | model | job | limits |
|---|---|---|---|
| `build` (primary) | `openai/gpt-6.2-sol#high` | investigate, decide, brief, review | may not call `general` or `explore` |
| `implementer` | `splash/worker#lite-1k` | one briefed change: code, test, docs, local commit | 120 steps; low effort, ≤1,024 thinking tokens per reply; no subagents, no questions |
| `validator` | `splash/worker#lite-512` | independent re-check; edits nothing | 40 steps; low effort, ≤512 thinking tokens per reply; no subagents, no questions |
| `title` | chosen by OpenCode (`gpt-6-luna`) | names sessions | — |

Other settings: `websearch.provider: random` (otherwise web search asks a question and cancels an
unattended run) and `tool_output` capped at 400 lines / 30,000 bytes (long build logs slow every later
local turn).

Facts the profile depends on (checked on OpenCode 2.3.2 and Splash 1.7.0):
- Subagents run in the background; the orchestrator gets a message when one finishes. Without the
  "end your turn while a worker runs" rule it keeps probing and polling, which doubled cloud tokens.
- Splash reads `thinking_token_budget` per request and closes thinking at the cap; OpenCode passes a
  variant's `body` through unchanged. oMLX names the same field `thinking_budget`.
- Role agents with `subagent` permissions fix the number of workers; rules in `AGENTS.md` alone did not.

## Install on a Mac

Prerequisites: an Apple silicon Mac (128 GB for this model), Homebrew and Python 3.9+.

```sh
python3 install.py --dry-run     # what would change; nothing written
python3 install.py               # brew packages, Splash model, configuration, checks
opencode auth login openai       # once per Mac; the installer reports when it is still missing
```

`install.py` installs `anomalyco/tap/opencode-v2`, `incoai/tap/splash` and the `incoai/tap/splash-app`
cask when missing; selects the worker model in Splash (`defaults write ai.inco.splash model …`),
starts it and waits until the model is served (the first start downloads about 90 GB); writes the two
configuration files, moving any differing `opencode.json`, `opencode.jsonc` or `AGENTS.md` to
`backup-<time>/` first; then checks that `opencode debug agents` routes every role as configured, that
Splash honours the thinking cap, and that an OpenAI login exists. Exit 0 means ready, 2 means only
manual steps remain (they are listed), 1 an error. Rerun it after changing `config/`.

## Results

One task, run unattended many times: on a tvOS SwiftUI app, analyse how the accent color is set and
switch it to the native system pink, following the project's rules (failing-first test, rule test
plans, docs). The right result keeps the asset-catalog mechanism with a single `systemPinkColor`
reference and a test over Light/Dark × normal/increased contrast. M5 Max, 128 GB.

| setup | runs | time | quality | cloud tokens written |
|---|---|---|---|---|
| any number of generic workers, orchestrator at xhigh | 2 | 40 min | 7.5–9 | — |
| three role agents (investigator, implementer, validator) | 2 | 43 min | 8 | 8k |
| orchestrator investigates, two role agents | 4 | 28–34 min | 5–9.5 | 15–18k |
| + thinking caps | 2 | 21–26 min | 9–9.5 | 17–38k |
| + "stay idle while workers run" (this profile, Q4_K_XL) | 2 | 22–25 min | 9.5 | 10–12k |
| this profile on IQ3_S | 4 | 20–26 min (avg 23.7) | 8.5–9.5 | 9–13k |
| this profile on oMLX 0.8.0, oQ3h-mtp | 2 | 30–38 min | 5–9 | 10–23k |

What moved the numbers:
- Local generation dominates time; fewer local tokens is the main speed lever. Capping thinking cut
  local tokens by up to 40% with no quality loss.
- A local investigator was slow; the cloud orchestrator investigating directly halved that phase,
  but needs the rule "test the existing mechanism before replacing it" or it skips the experiment.
- oMLX was about 30% slower per token than Splash here, and its memory guard rejected long prompts
  while Xcode was building, so Splash stays.

## Rules for agents editing this repository

- Run `python3 -B -m unittest discover -s tests -p 'test_*.py'` before every commit; it must stay
  green. Defects get a regression test that fails first.
- Python standard library only, Python 3.9 compatible; no machine-specific paths in code, tests or
  `config/`.
- Keep prompts short and structured. After changing `config/`, rerun `install.py` and repeat a real
  task to see what it costs.
- No plan, design or scratch documents in the tree; this file is the documentation.
- Published results are redacted: no project names, host names, account identifiers or keys.
