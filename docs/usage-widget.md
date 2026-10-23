# OpenCode usage dashboard

The sidebar and `/usage` page read OpenCode's own session and assistant-message records. They make no model requests. Cyan identifies cloud usage, green local usage, amber unavailable information or differing review verdicts, and red failures. Colors describe the displayed state, not an efficiency or quality score.

![Usage dashboard](images/usage-details.png)

## Subscription efficiency

The default view leads with local/cloud **output share** and shows percentages beside each raw token category. Each share uses all observed providers in that same category as its denominator. Unknown-provider usage remains in the denominator and appears separately. Empty categories show a dash. Increasing local cache reads cannot inflate local input or output percentages. Turn share counts assistant turns, not completed tasks or quality.

The widget does not read subscription-limit units, so token shares do not show the exact percentage of your plan consumed. Assess local effectiveness using both accepted results and a matched cloud-only baseline. In the saved verified task, local handled 74.7% of input and 89.7% of output; cloud input fell 47.9% and cloud output fell 44.0% compared with Build-only. Both passed the same independent checks; mixed took 122.795 seconds versus 61.802 seconds. This is one bounded task with different cloud reasoning effort and uncontrolled cache/warm state; it is not a general model-quality estimate. See the [matched comparison](cloud-led-comparison.md). Planning and final review stayed on cloud Sol.

Dollar costs and missing-price notices are hidden from the default view. Press `w` for optional accounting and weighted details.

## Raw usage and optional cost

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
| `w` | Toggle optional costs and the secondary weighted heuristic |
| `n` | Select the newest root session |

The weighted heuristic remains available for continuity: input + output + reasoning + cache write + 10% cache read, rounded per message. It is not billing, actual token usage or proof of savings.

The images are captures of native OpenCode TUI output rendered in a terminal emulator. See [capture provenance](images/README.md). The historical benchmark's recorded cloud cost is unavailable; its local operating cost was not measured.
