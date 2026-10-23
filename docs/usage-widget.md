# OpenCode usage dashboard

The sidebar and `/usage` page read OpenCode's own session and assistant-message records. They make no model requests. Cyan identifies cloud usage, green local usage, amber unavailable information or differing review verdicts, and red failures. Colors describe the displayed state, not an efficiency or quality score.

![Usage dashboard](images/usage-details.png)

## Raw usage and cost

Cloud and Local show input, output, reasoning, cache-read and cache-write counters separately, plus contributing turns and sessions. Counts accumulate across the root and its descendants. These are native per-turn records; repeated context/cache use is included. The categories are not presented as a single billed total because provider accounting can overlap categories.

Costs use positive per-message amounts recorded by OpenCode when available. A zero or missing cloud amount does not prove free usage. Incomplete coverage shows **Unavailable** and, when present, the known partial amount and number of unpriced turns. Recorded amounts are not invoice verification. Local operating cost is **Not measured**: hardware and electricity are not measured, and the analyzer's zero local API estimate is not shown as a measured dollar cost. Per-model history retains the same cost qualification. The presentation layer also distinguishes complete rate-based estimates from recorded amounts; the installed widget has no billing connection or supplied pricing table, so it cannot invent prices where OpenCode did not record them.

**Elapsed** spans the session start to its final idle/message boundary, or the current time while the family is running. Viewing an old session does not extend it. **Recorded turn span** merges overlapping assistant-message intervals within each provider class. These intervals can include tool and delegated-worker waits. Cloud and local spans can overlap; do not add them or treat them as model compute time or billed duration. Identity spans in the history cover the first through last message for that identity, including gaps.

## Models and review

- **Now** identifies models observed in running sessions. A new run after a model switch waits for its first model record instead of claiming the previous model is running.
- **Selected in UI / Next** is the current model selector, separately labeled; it does not rewrite historical usage and does not prove a model request occurred.
- **Models used** lists observed agent/model/variant identities, most recent first, with raw counters, costs, spans and source sessions. The sidebar shows three identities and indicates when more are available.
- **Configured roles** shows current effective defaults for the viewed location. Explicit UI selections can override them. Open it with `c`.
- **Review** reports a completed, explicit `VERDICT:` marker from a cloud coordinator/primary agent or a separate cloud-reviewer session. Worker self-checks, compaction summaries, quoted/code examples, tool output and unfinished responses cannot supply that verdict. Only the marker and its source IDs are retained; the normalizer drops the surrounding review prose and tool output.
- Independent reviewer activity is shown even without a verdict. Differing coordinator and independent verdicts remain visible. A verdict predating later work or a running continuation is labeled previous. A displayed PASS is the model's report, not independent verification of correctness.

## Controls

| Key | Action |
|---|---|
| `esc` | Return to the originating session |
| `r` | Refresh stored messages |
| `v` | Open the reported review's source session |
| `i` | Open the independent review's source session |
| `c` | Toggle current configured roles |
| `w` | Toggle the secondary weighted heuristic |
| `n` | Select the newest root session |

The weighted heuristic remains available for continuity: input + output + reasoning + cache write + 10% cache read, rounded per message. It is not billing, actual token usage or proof of savings.

The images are captures of native OpenCode TUI output rendered in a terminal emulator. See [capture provenance](images/README.md). The historical benchmark's recorded cloud cost is unavailable; its local operating cost was not measured.
