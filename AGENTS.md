# OpenCode with a cloud orchestrator and local Splash workers

## The idea

A cloud model decides and a local model does the work, in native OpenCode 2: no plugin, no wrapper.

- **Cloud, GPT-6.2 Sol at high effort (`build`):** reads the request and project rules, investigates,
  settles the claims the plan depends on with a small experiment, writes the briefs, reviews the
  diff. Its tokens are the scarce budget, so it stays idle while workers run.
- **Local, Qwen3.8-Flash-Next IQ3_S on Splash:** the `implementer` writes the code, the failing-first
  test and the docs, runs the checks and commits locally; the `validator` re-runs the checks, proves
  the test fails when the change is reverted and checks every changed sentence in the docs.

Workers run one at a time, except that two independent tasks may run at once when at most one of them
builds or uses a simulator; they pass results as brief and report files.

## The profile (`config/`)

`config/opencode.jsonc` becomes `~/.config/opencode/opencode.jsonc`; `config/AGENTS.md` becomes the
global `~/.config/opencode/AGENTS.md`, the orchestration rules every session reads;
`config/skills/github-tickets/SKILL.md` becomes a global skill the orchestrator loads when a request
names or asks it to choose a GitHub issue: it picks from the project board, moves the board Status
(In progress → In review → Done) and comments at each milestone, and never closes an issue or links
it so that a merge closes it. Project rules that limit GitHub changes still win.

| agent | model | job | limits |
|---|---|---|---|
| `build` (primary) | `openai/gpt-6.2-sol#high` | investigate, decide, brief, review | may not call `general` or `explore` |
| `implementer` | `splash/worker#lite-1k` | one briefed change: code, test, docs, local commit | 120 steps; low effort, ≤1,024 thinking tokens per reply; no subagents, no questions |
| `validator` | `splash/worker#lite-512` | independent re-check in one pass; edits only its report | 80 steps; low effort, ≤512 thinking tokens per reply; no subagents, no questions |
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
- OpenCode loads global skills from `skills/<name>/SKILL.md` in its configuration directory.
- Splash's prompt cache keeps a worker step at 5–8 s and about 80 tokens/s from 50k to 220k tokens of
  context, so long sessions cost steps and rework, not per-step speed.
- With Splash's concurrency limit at 4, parallel requests raised combined output from about 110 to 180
  (two) and 270 tokens/s (four), and three 54k-token sessions kept their prompt caches. A cold context
  is still read one at a time (about 24 s per 54k tokens), and two simulator test runs at once killed
  each other, so only one of two parallel workers may build.

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
configuration files and the skill, moving any differing `opencode.json`, `opencode.jsonc`, `AGENTS.md` or
skill file to `backup-<time>/` first and carrying over top-level keys the profile does not define, such as a
local `mcp` block with machine paths (OpenCode 2.3.2 reads only this one global `opencode.jsonc`); then checks that `opencode debug agents` routes every role as configured, that
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
- On a larger change (21 files, checks generated for four platforms) a 40-step validator ran out
  twice before writing its report, and regressions surfaced one validation round at a time: 6.5 h
  wall time. Hence 80 validator steps, report written first, and one-pass validation.
- A poster change on four platforms took 72 min, 53 of them in one implementer: the brief left the
  state design open, so three review rounds supplied it, the worker hit its step limit three times and
  rewrote the new file seven times. Hence the orchestrator designs stateful changes itself (types,
  invariants, edge cases as named tests), splits multi-platform changes into tasks, and briefs
  numbered acceptance criteria; workers edit rather than rewrite and trust the brief's findings.
- A two-issue tvOS Home change took 7.6 h: a showcase brief with five source files but about 1,100 lines of
  UI tests hit the implementer's step limit four times, and the validator reverted files in the task worktree
  and ran two simulator test runs at once. Hence test effort counts toward splitting, a second step-limit
  stop means a smaller new task, revert proofs run in a detached scratch worktree, and cleanup keeps briefs
  and reports.
- A worker once printed a broken tool call as its final text and stopped with nothing committed;
  the orchestrator now resumes any reply without a status line once before investigating.
- A native tvOS search-suggestions change (18 files, about 1,000 lines) took 114 min, 52 of them in
  tests: the full suite ran in both the implementer and the validator, every filtered run rebuilt,
  one implementer spent 33 UI runs (20 min) probing how a system control appears to UI tests, the
  validator built the base twice to prove an old failure, and one hung filtered run cost 10 min.
  Hence one owner per test level (the full suite only in the validator), build once then test
  without building, the orchestrator settling UI queries and known base failures while it
  investigates, test timeouts, and a stop after two identical UI failures.
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
