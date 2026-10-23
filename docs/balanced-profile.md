# Active balanced OpenCode profile — 22 October 2026

The balanced profile is activated globally in `/Users/oleksii.naboichenko/.config/opencode/opencode.json`. OpenCode 2.1.2 native validation passed before application in a disposable configuration and after the transactional global write. Effective agents were checked again globally and from this repository. No model generation was needed for activation validation.

| Role | Model | Reasoning / purpose |
|---|---|---|
| Orchestrator | GPT-6.1 Sol | Medium; planning, coordination and routine final review |
| Plan | GPT-6.1 Sol | Medium; explicit planning mode |
| Build | GPT-6.1 Sol | High; difficult implementation / local blocker escalation |
| Independent reviewer | GPT-6.1 Sol | High; separate review when warranted |
| Compaction / summary | GPT-6.1 Sol | Medium; preserve substantive context |
| General | Local Qwen | Bounded implementation and tests |
| Explore / title | Local Qwen | Bounded discovery / mechanical labels |

Every configured OpenAI role explicitly requests `service_tier: "default"` (Standard) and uses the ordinary model ID, not a Fast model ID. Background warming is disabled. Existing service ports were preserved; oMLX was discovered and authenticated at its existing endpoint. Its key is referenced through a private credential file (0600, with a 0700 parent directory); the global JSON does not contain the key itself.

Orchestrator is the default primary agent, cannot edit or run shell, and can dispatch local General/Explore as well as cloud Build/reviewer. General retains its no-delegation and 24-step limits. Planning and final review remain on Sol. General receives one small objective, normally at most three production files plus associated tests/docs and one focused validation target. These are prompt sizing defaults, not runtime permission limits. Hard focus/lifecycle/concurrency, architectural and cross-component fixes go directly to Sol Build. Local blockers escalate once; Build retains the coherent fix stage through evidence-backed corrections and required validation. The coordinator reviews completed stages rather than imposing a handoff after each red check. Verified stage commits and genuine-blocker stops remain required.

Astra remains an exceptional, explicitly selected cloud escalation; it is not an automatic default. To request it deliberately, select the available Astra model for a difficult cloud Build session. Luna has not replaced any planner/reviewer role; it remains a candidate requiring representative quality evaluation.

Start a fresh OpenCode session to use the default. Explicit session/UI model selections and project overrides can still change effective routing. Activation was verified for global scope and this repository; unrelated project-specific overrides were not enumerated. The native request configuration was checked read-only; no new paid benchmark or provider billing measurement was made.

The previous matched benchmark remains documented in [cloud-led comparison](cloud-led-comparison.md). Its explicit Plan role used high effort; the active balanced profile now uses medium for that role. Orchestrator and actual implementation/review routing from that benchmark are unchanged.

Activation evidence: `artifacts/balanced-global-activation.json`, `balanced-global-activation.log` and the redacted `balanced-global-preview.diff`. The setup transaction journal supports reversal with:

```sh
opencode-agent-setup undo
```

Undo preserves credential files, as documented by the existing credential/recovery policy.

The statistics plugin is now installed globally at `~/.config/opencode/plugins/agent-usage`, linked to this checkout. Fresh native checks revalidated all configured model variants, Standard service tier, disabled warming and the installed link. Open `/usage` in a fresh OpenCode instance; [actual terminal captures](images/README.md) show the completed benchmark without another model request. The durable [benchmark receipt](benchmarks/2026-10-22-cloud-led.json) contains the verified measurements.

## Routing revision — 23 October 2026

The revision removes the earlier multi-stage local assignment recommendation and the blanket stop after a failed check. Qwen retains its 24-step budget and cannot plan or judge final correctness. Sol Build continues within its authorized stage while distinct hypotheses produce progress; it still stops for external blockers, ownership conflicts, material scope decisions, exhausted execution budget or repeated attempts without progress. Continuations reuse the owning session and existing receipts. Model assignments, step budgets, permissions and service settings are preserved.

Global application writes only the Orchestrator, General and Build system fields using the transaction journal. No reload, restart, cancellation or prompt is sent to an existing session. Start a fresh session for a reliable boundary for the revised instructions; the running session is not migrated. Native configuration loading tests do not establish model behavior or subscription savings. Local activation evidence is retained under `artifacts/bounded-routing-activation.json`.

This routing revision was applied globally after commit `bc4a743`. Verification passed 155 tests with zero failures; one inference-based completion test was intentionally skipped to avoid competing with the running job. Native loading verified the exact three revised system fields and preservation of every other global/effective agent setting. The same active root dispatch and child shell command were observed before and after application.
