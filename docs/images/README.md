# Usage widget captures

These images capture the actual OpenCode 2.1.2 TUI displaying the completed cloud-led benchmark session. They are terminal captures, not desktop screenshots: macOS screen-recording access was unavailable (`CGPreflightScreenCaptureAccess()` returned false; `screencapture` could not capture the Terminal window).

The native TUI ran in a 180-column, 48-row PTY with the installed global plugin. Its unmodified ANSI output was interpreted by `@xterm/headless`; Chromium captured the resulting terminal cells using Menlo. The detail image shows the dashboard viewport; the widget image focuses on the sidebar. No interface text, usage figures or layout was invented. The redesigned sidebar shows raw counters, qualified costs, timing, current/previous models and reported review context. Native checks also cover an 80-column terminal and the configured-role / weighted-detail toggles.

- `usage-sidebar.png`: complete session view, including the right sidebar.
- `usage-widget.png`: sidebar detail.
- `usage-details.png`: the `/usage` page.
- `capture-provenance.json`: session and capture parameters, including unchanged message count.

Only `/usage` was submitted. No model request was made. Local operating cost is not measured. Cloud billing was unavailable and remains flagged as unknown. The optional weighted heuristic is secondary to raw counters.
