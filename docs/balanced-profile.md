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

Orchestrator is the default primary agent, cannot edit or run shell, and can dispatch local General/Explore as well as cloud Build/reviewer. General retains its no-delegation and 24-step limits. Planning and final review remain on Sol. Related implementation stages reuse one local worker context, with separate verified commits.

Astra remains an exceptional, explicitly selected cloud escalation; it is not an automatic default. To request it deliberately, select the available Astra model for a difficult cloud Build session. Luna has not replaced any planner/reviewer role; it remains a candidate requiring representative quality evaluation.

Start a fresh OpenCode session to use the default. Explicit session/UI model selections and project overrides can still change effective routing. Activation was verified for global scope and this repository; unrelated project-specific overrides were not enumerated. The native request configuration was checked read-only; no new paid benchmark or provider billing measurement was made.

The previous matched benchmark remains documented in [cloud-led comparison](cloud-led-comparison.md). Its explicit Plan role used high effort; the active balanced profile now uses medium for that role. Orchestrator and actual implementation/review routing from that benchmark are unchanged.

Activation evidence: `artifacts/balanced-global-activation.json`, `balanced-global-activation.log` and the redacted `balanced-global-preview.diff`. The setup transaction journal supports reversal with:

```sh
opencode-agent-setup undo
```

Undo preserves credential files, as documented by the existing credential/recovery policy.

The statistics plugin is now installed globally at `~/.config/opencode/plugins/agent-usage`, linked to this checkout. Fresh native checks revalidated all configured model variants, Standard service tier, disabled warming and the installed link. Open `/usage` in a fresh OpenCode instance; [actual terminal captures](images/README.md) show the completed benchmark without another model request. The durable [benchmark receipt](benchmarks/2026-10-22-cloud-led.json) contains the verified measurements.
