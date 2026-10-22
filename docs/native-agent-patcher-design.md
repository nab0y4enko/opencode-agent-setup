# Native OpenCode agent configurator — proposed design

Date: 2026-10-22. Status: research and design for user review; implementation has not started.

## Intended outcome

Install OpenCode CLI through Homebrew, then provide a terminal wizard that explains each agent and lets the user choose its model, supported reasoning variant, permissions, and optional prompt changes. Prefer OpenAI for difficult reasoning and review, and the user's local Qwen for exploration and scoped implementation. Show exact changes before saving. Provide a reversible return to native defaults.

No OMO installation, desktop installation, binary patching, new service, or port changes. Previous queue/report infrastructure was removed at the user's request; this tool will not silently recreate it.

## Findings and evidence

- `command -v opencode` returned no executable. Homebrew reports `opencode` 2.1.2 available and not installed. The global configuration and data directories are absent.
- The documentation lists Build and Plan as primary agents; General, Explore and Scout as subagents; Compaction, Title and Summary as hidden system agents.
- There is no built-in Orchestrator in that list. Orchestrator is an agent name/role; `primary`, `subagent`, and `all` are modes. OMO supplied the previous Orchestrator.
- The tagged 2.1.2 core agent plugin defines Build, General, Explore, Compaction, Title and Summary. A separate plugin defines Plan. Scout was not present in those definitions or as a named source file. Treat the docs/runtime difference as an explicit compatibility check, not permission to invent a built-in agent.
- Native 2.1.2 configuration uses `agents`, `system`, `permissions`, `disabled` and structured request/model settings. Older `agent`, `prompt`, `permission`, `disable` settings have a compatibility migration. Prefer the native schema after validating the installed executable.
- The configuration agent loader assigns `agent.system = item.system`. It does not append to an existing agent system string. Explore's original restrictions must survive an enhanced prompt. Other harness instructions and Plan reminders are separate layers and must not be advertised as fully visible in a single agent prompt diff.
- Native delegation supports a fresh child session when no session ID is supplied, foreground completion by default, and optional background execution with completion notification. A child's explicit override wins over its configured agent model, which wins over inheritance. A UI model selection can also change the active session independently of persisted agent defaults.
- Plan denies ordinary file edits but its default shell access is not a complete read-only sandbox. Permission previews must explain this limitation.
- A read-only request to `http://127.0.0.1:8000/v1/models` returned HTTP 401. Local model IDs and availability are not yet authenticated or verified. Historical model names are hints, not validated choices.

Sources:

- https://opencode.ai/docs/agents/#built-in
- https://opencode.ai/docs/config/
- https://opencode.ai/docs/models/
- https://formulae.brew.sh/formula/opencode
- https://github.com/anomalyco/opencode/blob/v2.1.2/packages/core/src/plugin/agent.ts
- https://github.com/anomalyco/opencode/blob/v2.1.2/packages/core/src/plugin/plan.ts
- https://github.com/anomalyco/opencode/blob/v2.1.2/packages/core/src/config/plugin/agent.ts
- https://github.com/anomalyco/opencode/blob/v2.1.2/packages/schema/src/config/agent.ts
- https://github.com/anomalyco/opencode/blob/v2.1.2/packages/schema/src/config/model.ts
- https://github.com/anomalyco/opencode/blob/v2.1.2/packages/core/src/tool/plugin/subagent.ts
- https://github.com/alvinunreal/oh-my-opencode-slim/blob/master/src/agents/orchestrator.ts (reference only)

## Alternatives

1. **Native configuration wizard — recommended.** A standalone CLI maintains supported overrides and optional custom agents. No runtime orchestration extension. Easier inspection, upgrades and reset; cannot turn prompt preferences into a hard scheduler or global queue.
2. **Runtime plugin.** Could enforce dispatch policies and add telemetry, but increases maintenance and recreates part of the extension infrastructure the user removed. Not needed for this request.
3. **Patch installed source or binary.** Fragile across Homebrew upgrades and difficult to restore correctly. Reject.

## Agent policy

The wizard starts with an Orchestration explanation, rather than pretending Orchestrator is built in. Offer two explicit profiles:

- **Native roles:** Build remains the primary implementation agent, with optional delegation guidance. No custom coordinator.
- **Delegation coordinator — recommended for this user's goal:** add an optional `orchestrator` primary agent. Keep Build available for direct difficult implementation; use existing Explore and General for Qwen workers. Add an optional `cloud-reviewer` subagent for difficult delegated reasoning and escalation.

Suggested assignments are policy categories, not hard-coded unverified model IDs:

| Agent | Classification | Suggested model policy | Prompt policy |
|---|---|---|---|
| Orchestrator | Optional custom primary | Available OpenAI coding model; medium effort initially, high for complex planning | Minimal coordination contract; no direct source edits or shell execution |
| Build | Built-in primary | Available strong OpenAI coding model; high for hard implementation | Native by default; optional bounded delegation guidance |
| Plan | Built-in primary | Available strong OpenAI coding model; high for complex planning | Preserve planning restrictions; delegate read-only research only |
| General | Built-in subagent | Authenticated local Qwen | Scoped fixes and test execution, concise evidence, no recursive delegation |
| Explore | Built-in subagent | Authenticated local Qwen | Preserve read-only rules; targeted searches and concise cited findings |
| Scout | Documented subagent, runtime availability to verify | Local Qwen for bounded docs/source research | Configure only if present; preserve its actual permissions |
| Compaction | Hidden built-in | Preserve native selection initially | Preserve original prompt; long-context fidelity needs a separate evaluation |
| Title | Hidden built-in | Optional local Qwen | Keep the exact native title contract |
| Summary | Hidden built-in | Optional local Qwen | Keep the exact native summary contract |
| Cloud reviewer | Optional custom subagent | Available strong OpenAI model, high effort | Read-only analysis/review; bounded escalation evidence |

The wizard must explain that reasoning variants differ by model/provider. Only offer variants discovered for that model. Do not promise model IDs seen in Codex desktop are available through OpenCode authentication.

## Wizard interaction

Working command name: `opencode-agent-setup`. Use a terminal list/select interface with back, skip, cancel and final review. Normal operation needs no model calls.

1. Check executable/version and load the matching supported schema and built-in catalog. Unknown versions or unrecognized schemas permit inspection only until validated.
2. Select global or project scope; default global for this user's setup. Show target paths and effective configuration sources, including environment and project overrides. Mask credentials.
3. Explain primary/subagent modes and choose the orchestration profile. Selecting a custom coordinator is an explicit addition and an explicit default-agent choice.
4. Discover available providers/models and optionally connect credentials through native OpenCode authentication. Keep secrets out of generated config, previews and logs. Never read Codex credentials as a substitute.
5. Configure the local endpoint without changing its address/port. Discover the actual Qwen model; distinguish advertised context limits from proven reliable context. Offer 256K context/8K output only as an explicit advertised configuration, not a new benchmark result.
6. Visit agents in the table's order. Each step shows origin, role, mode, native permissions, inherited/current model, suggested model and reason. The user can keep native, use suggestion, choose another available model, or enter an explicit ID marked unverified until checked.
7. Prompt options per agent: keep native; apply a reviewed minimal enhancement; edit custom text; restore native. Show the original agent system text and full proposed text as a unified diff, with a separate permission/model diff. Where no agent-specific system text exists, label the addition accurately. Do not claim to display all dynamic harness instructions.
8. Show a combined review: changed files, exact configuration fields, added/removed sentences, model/variant choices, default agent, custom agents and permission effects. Apply only after explicit confirmation in the tool.
9. Save atomically with an advisory writer lock and a manifest of owned fields/files. Validate through OpenCode, report activation/new-session requirements, and roll back the transaction if validation fails. Recommend a fresh session for behavioral changes.
10. Offer an explicit smoke-test action with model names and expected cloud usage disclosed. Never start paid inference simply to render a preview.

## Proposed prompt text for review

These are additions/contracts to refine during implementation, not changes already applied.

Coordinator:

> Plan the work and delegate bounded exploration, scoped implementation and test execution to the configured workers. Give each worker an objective, owned paths, acceptance criteria and required validation. Start a fresh worker session for each independent assignment. Review the diff and relevant evidence without repeating completed exploration. Use the cloud reviewer for ambiguous requirements, architectural decisions, security-sensitive changes or a worker failure that requires deeper reasoning. For test-only work, dispatch one foreground worker and give one final review; do not request intermediate status or launch duplicate tests. Do not edit source files or execute shell commands directly.

General/Qwen worker:

> Work only within the assigned scope. Make the smallest correct change, follow project instructions and run the assigned checks. Run tests to terminal completion within this foreground assignment; retain exit status, test counts and artifact paths. Do not spawn detached test jobs or declare success from a successful build alone. Return a concise summary containing changes, validation evidence and unresolved issues. If blocked, return the concrete blocker and useful evidence; do not repeatedly retry unchanged failures or delegate recursively.

Explore/Qwen worker, appended to a preserved native read-only contract:

> Search only as broadly as the assigned question requires. Return the answer, relevant file paths and line references, and remaining uncertainty. Avoid dumping files or lengthy search transcripts. Do not implement fixes.

Cloud reviewer:

> Review the assigned question or diff and worker evidence. Inspect relevant artifacts and identify actionable correctness, design or security issues. Return findings with file references and a recommendation. Do not modify files or repeat the worker's entire investigation.

Borrow principles such as explicit ownership, dependency-aware dispatch and artifact verification from OMO, not its scheduler-specific tool names, wake loops, multiplexer hooks or full prompt. Write original minimal text; document attribution/license requirements if actual source text is reused.

Permissions enforce coordinator edit/shell denial and worker delegation denial. Foreground dispatch, concise responses and escalation thresholds remain prompt policy; do not market them as guaranteed runtime enforcement. Strict cross-session concurrency requires server-side support or a separate queue, outside this patcher's initial scope.

## Reset and rollback

Provide two separately labelled actions:

- **Undo this tool's changes:** restore prior values of owned fields and remove owned custom agents/prompt files. Preserve unrelated settings, credentials and later user edits. Compare stored applied values with current values and show conflicts before touching them.
- **Reset agent overrides to native defaults:** preview and remove user overrides for built-in agents in the selected writable scope, plus selected tool-owned custom roles/default-agent changes. Native implementation then supplies defaults for the installed release. Warn when project, environment or managed settings will still override the result. Never delete all OpenCode settings or authentication as an agent reset.

Keep timestamped pre-change backups outside OpenCode's auto-discovered agent directories, with restrictive permissions. JSONC comments and unrelated keys must survive edits. Existing prompt files are never overwritten without recording their original bytes. Repeated apply/reset must be idempotent. Concurrent modification or unsupported ownership conflicts abort safely rather than overwriting user work.

## Proposed implementation sequence

1. Install the CLI using `brew install opencode`; verify version, help, native agent inventory and effective config in an isolated empty test directory. Keep the installed defaults untouched at this stage.
2. Establish a small TypeScript/Node CLI project with a terminal prompt library and a JSONC editing library; separate version/catalog discovery, policy/prompt templates, configuration transactions and the wizard. Confirm available runtime before selecting exact dependency versions.
3. Implement read-only inspect and preview first, including discovery errors, model availability, inheritance and docs/runtime discrepancies.
4. Implement per-agent choices and reviewed prompt templates, then transactional apply, validation and conflict-aware undo/reset.
5. Exercise the full wizard through a pseudo-terminal with isolated HOME/XDG paths. Only after dry-run acceptance, offer application to the user's real configuration.
6. Run real local exploration and a small fixture fix with assertions, then a foreground test assignment. Inspect actual child model IDs and completion evidence. If OpenAI authentication is available, verify coordinator-to-Qwen and cloud escalation. Otherwise label those live checks blocked, not passed.

## Test and acceptance matrix

- Installed native agent inventory matches the patcher's displayed built-ins; absent Scout is not fabricated.
- Model selection distinguishes available, disconnected and unknown IDs. Unavailable Qwen cannot silently fall back to paid cloud. Unsupported reasoning variants fail before apply.
- Preview includes every changed model, permission and prompt line; keep-native changes no system text. Explore's read-only contract and hidden-agent output contracts survive enhancement.
- Cancellation at every step changes no OpenCode configuration. CLI EOF/non-interactive execution fails clearly or uses an explicit dry-run mode.
- JSON and JSONC with comments/trailing commas, missing config, unrelated settings, multiple config sources, paths with spaces, malformed config, symlinks and unreadable files have defined outcomes. Refuse ambiguous targets rather than silently replacing them.
- Atomic failure/interrupt simulation leaves the original configuration recoverable. Concurrent apply or user modification is detected. Backups do not expose credentials.
- Reapply produces no duplicate instructions. Undo restores original bytes when no intervening edits exist. Reset preserves credentials/unrelated config and reports higher-priority overrides.
- Native configuration validation succeeds. Coordinator source-edit/shell attempts and worker nested-delegation attempts are denied in a disposable test fixture; distinguish prompt expectations from permission enforcement.
- Live worker completes a deterministic code fix and tests; report actual model, elapsed time and tokens if exposed. A deliberately failing test returns failure; a build with zero tests is not a pass. A long foreground test does not generate coordinator monitoring requests in the observed trace.
- Produce a test report listing automated results, live results, skipped/blocked checks and artifacts. No throughput, reliability or savings claim without a measured run.

## Review decisions

Recommended profile: optional custom Orchestrator + preserved native Build/Plan + Qwen General/Explore + optional cloud reviewer. Keep hidden prompts native and start with conservative model choices for compaction. This needs design approval before implementation; exact model IDs are chosen from the user's authenticated inventory in the wizard.
