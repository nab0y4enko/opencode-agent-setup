# Native agent patcher implementation plan

Approved design: native-agent-patcher-design.md. Execution: inline, as explicitly requested.

1. Install Homebrew CLI, inspect version/help and native config/agent output.
2. Implement tested discovery, policy templates and exact unified diffs using native configuration; retain built-in prompts.
3. Implement transactional JSONC writes, conflict detection, backup, undo and reset; test failure and preservation cases.
4. Implement interactive model/variant/prompt selection, optional custom roles and final confirmation; expose inspect and preview commands.
5. Run automated and isolated native integration tests, install the launcher, and document live authentication blockers.

Constraints: no OMO, desktop, ports, daemon or queue changes. No unrequested inference or invented available model IDs.

Review focus: JSONC preservation; reset after user edits; native permissions; model availability and inheritance; prompt replacement semantics.
