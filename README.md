# Native OpenCode agent setup

OpenCode CLI 2.1.2 was installed with Homebrew. This standalone terminal wizard writes native OpenCode configuration; it does not install OMO or patch OpenCode binaries. Existing ports and server settings are preserved.

Run from your project directory:

```sh
opencode-agent-setup
```

Choose global/project scope, optionally add a custom Orchestrator and cloud reviewer, connect providers, and select each agent's model and supported reasoning variant. Provider setup can be repeated before continuing, so OpenAI and local Qwen can be configured in one wizard. Each agent step explains its role, permissions, and recommendation. You can go back to the previous agent, retain instructions, apply a minimal enhancement, restore the native agent system text, or edit custom text. The final review displays configuration changes and exact agent prompt diffs. Nothing is saved until confirmation. Ctrl-C cancels pending wizard choices; a completed native provider login is a separate persisted action.

OpenAI is recommended for difficult planning, implementation and review. General and Explore use local Qwen when selected. Model IDs and reasoning variants come from the authenticated OpenCode inventory; Codex desktop's model names are not assumed available. OpenAI is not connected on this fresh installation, so a live cloud-coordinator test has not run. Use the wizard's native login option, or `opencode auth login`, to connect it.

For local setup, reuse the existing oMLX key, read an environment variable, or select a private key file. The wizard authenticates discovery against the existing endpoint, then previews a reference to a private credential file. That file is created with mode 0600 only after confirmation; its directory is mode 0700. Native OpenCode validates the reference and authenticates local discovery again. Credentials never appear in generated JSON or terminal diffs. No shared-service restart or port change is needed. Reset/undo preserve credentials, just as they preserve native OpenCode authentication.

The local model discovered during testing was `omlx/qwen-3.8-nf-splash`. Provider setup declares 262144 context and 8192 output tokens; this tool's small functional tests do not establish 256K reliability or a concurrency limit.

## Agents

Build and Plan remain native primary agents; General and Explore remain native subagents. Compaction, Title and Summary are hidden system agents. This release does not expose the documented Scout agent, so the wizard does not fabricate it. Orchestrator and cloud-reviewer are optional custom roles, labelled as such.

The custom coordinator has edit and shell tools denied; it delegates implementation/tests and reviews evidence. The reviewer has read/research access and cannot edit, run shell commands or delegate. General's enhanced profile has a 24-step limit and no nested delegation. Explore's enhanced profile retains its exact native system text and adds concise reporting, with a 12-step limit. Plan's optional enhanced profile denies shell/source edits and can delegate only to Explore. Foreground test dispatch, bounded scopes and concise summaries are prompt policies, not a hard scheduler or global queue.

Native model defaults can be overridden by explicit session/UI model selection. Enhancing an existing custom role is an explicit replacement of its role permissions and text; choosing keep-current preserves them. Hidden-agent prompts are left unchanged.

## Inspect, preview, undo and defaults

```sh
opencode-agent-setup inspect
opencode-agent-setup preview --choices examples/local-workers.json
opencode-agent-setup undo
opencode-agent-setup reset
```

`preview` works offline and does not validate model availability or invoke models. Paths in these examples are relative to this tool's source directory. `apply --choices FILE` checks models against the current inventory before presenting confirmation. `--config /absolute/path/opencode.jsonc` selects a particular target. `--dry-run` previews without saving; `--yes` explicitly authorizes unattended apply/reset/undo.

Undo restores the last tool transaction. If unrelated settings changed later, it preserves them; changes to owned fields cause a conflict instead of overwriting user work. Exact original bytes are restored when the file has not otherwise changed. Newly created configuration files are removed on undo. Repeated identical apply does not create a second transaction.

Reset removes built-in agent overrides from the selected JSON/JSONC file and offers removal of the optional custom roles. It preserves providers, credentials and unrelated settings. Agent Markdown files, other projects, environment overrides and managed settings are reported but never silently deleted. A reset applies to the selected scope; it cannot promise factory defaults across every external configuration source.

Private recovery history and local credential files live under `$XDG_STATE_HOME/opencode-agent-setup` or `~/.local/state/opencode-agent-setup`. A writer lock prevents two cooperating patchers from writing the same target. If a process is killed, inspect its `.agent-setup.lock` before removing it; unfinished transactions can be recovered with undo. Close editors while applying to avoid uncooperative writer races.

The tool supports the examined 2.1.2 schema. Unknown versions are inspection-only. It checks decoded config and effective agent fields, rejecting shadowed prompts and unavailable models. Use fresh OpenCode sessions after prompt/permission changes. Validation is performed for the selected configuration directory; other projects may have higher-priority settings.

## Verification

```sh
npm test
RUN_NATIVE_TESTS=1 RUN_LOCAL_TESTS=1 npm test
python3 test/terminal.py
python3 scripts/live-local-smoke.py
python3 scripts/live-local-smoke.py --coordinator
```

The explicit local smoke scripts use oMLX's current key and endpoint and make local inference requests. They create disposable fixture projects, temporarily store the key in a private file, and delete that key file on exit. They do not run your project's macOS suite. `--coordinator` uses local Qwen for the test coordinator as well as the worker, so it tests native delegation without spending cloud tokens. It is not evidence of authenticated OpenAI routing.

See `docs/test-report.md` for the observed results and limitations. Prompt wording is centralized in `src/policy.js`; `artifacts/all-agent-prompt-changes.diff` shows every optional role enhancement, and `artifacts/prompt-changes.diff` shows the local-worker example. Native baseline text is captured in `data/builtin-2.1.2.json` from the unmodified runtime. OMO was consulted for delegation principles only; no OMO prompt text, package or scheduler is installed.

The launcher is installed using `npm link --ignore-scripts` and points to this source directory. Keep the directory to retain the command. Dependencies are locked in `package-lock.json`; Node 24 was used for verification.

## Stage commits and self-checks

The enhanced profiles now require a verified commit after each completed implementation task or planned stage. Implementers inspect Git state before editing, diagnose the root cause, run required checks and inspect their diff against acceptance criteria before committing. Final reports include STATUS, CHECKS, SELF_CHECK and COMMIT evidence. A failed or blocked required check is not completion, and test-only/read-only work does not need an empty commit.

User work is protected conservatively: any unrelated staged change or existing edit to an owned file requires NEEDS_CONTEXT before editing. Pathspec commits are not an exception. Shared-checkout writers run sequentially; parallel writing requires separate worktrees. No automatic pushes, amends, resets, Git identity changes or repository initialization are permitted without authorization.

Orchestrator can call the enhanced OpenAI Build agent for hard fixes. Build uses `mode: all`, so it remains selectable as a primary agent. A child Build executes the assigned task itself and must not delegate back to the coordinator. The coordinator reviews local-worker evidence and commit checkpoints; risky changes can receive independent cloud review. Detailed exact templates are in `src/prompts.js`.

Explicit live checks (make local/cloud inference requests):

```sh
python3 scripts/stage-commit-smoke.py
python3 scripts/verify-stage-result.py artifacts/stage-commit-result.json
python3 scripts/staged-conflict-smoke.py /absolute/path/to/the/stage-smoke-repo
```

See the revised section of `docs/test-report.md` for mixed-model commits, independent validation and the staged-user-work negative test. Prompt instructions improve discipline but are not hard runtime enforcement; commits provide audit/rollback checkpoints, not proof of correctness.

## Install from this repository

```sh
cd ~/Projects/opencode-agent-setup
npm ci --ignore-scripts
npm link --ignore-scripts
opencode-agent-setup
```

The installed command uses this checkout. The repository remote is configured separately; local commits are not automatically pushed.
