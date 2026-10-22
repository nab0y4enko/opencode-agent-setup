# Usage widget captures

These images capture the actual OpenCode 2.1.2 TUI displaying the completed cloud-led benchmark session. They are terminal captures, not desktop screenshots: macOS screen-recording access was unavailable (`CGPreflightScreenCaptureAccess()` returned false; `screencapture` could not capture the Terminal window).

The native TUI ran in a 180-column, 48-row PTY with the installed global plugin. Its unmodified ANSI output was interpreted by `@xterm/headless`; Chromium captured the resulting terminal cells using Menlo. The detail image and widget image are cropped to their content. No interface text, usage figures or layout was invented. The sidebar capture verified that agent totals remain together at the native sidebar width after separating model labels from totals.

- `usage-sidebar.png`: complete session view, including the right sidebar.
- `usage-widget.png`: sidebar detail.
- `usage-details.png`: the `/usage` page.
- `capture-provenance.json`: session and capture parameters, including unchanged message count.

Only `/usage` was submitted. No model request was made. Recorded local `$0.0000` does not include electricity or hardware costs. Cloud billing was unavailable and remains flagged as unknown.
