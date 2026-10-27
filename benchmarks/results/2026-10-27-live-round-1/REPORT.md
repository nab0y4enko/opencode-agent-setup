# Benchmark report `/Users/oleksii.naboichenko/benchmark-runs/mac-a-001`

* protocol `portable-cross-mac-1`, generated 2026-10-27T04:11:19Z, measurement kind `cli`
* machine `oleksii-mac` — macOS-27.0.1-arm64-arm-64bit, python 3.9.6, git git version 2.56.0, codex codex-cli 0.164.0, opencode opencode v2.1.4, RAM 34359738368 bytes
* models `{"codex_cloud": "gpt-6.1-sol", "codex_child": "gpt-6-luna", "opencode_cloud": "openai/gpt-6.1-sol#medium", "local": "omlx/Qwen3.5-9B-OptiQ-4bit", "effort": "medium"}`
* budget `{"wall_clock_seconds_per_arm": 180, "initial": 1, "repair": 1}` per arm (1 initial + 1 repair)
* accepted arms: codex

| arm | client | accepted | cloud | cloud>=lower | local | unknown maint | seconds | tests | exit/timeout | failed gates |
|---|---|---|---|---|---|---|---|---|---|---|
| codex | codex-cli | True | 425757 | 425757 | None | 0 | 62.271 | 12T/0F/0E | 0/False | none |
| opencode | opencode-cli | False | None | 64360 | 68361 | 0 | 190.679 | 0T/0F/0E | 130/True | tests_all_and_pass, check_exit_clean, semantic_verdict_pass, verdict_bound_to_current_digest, routing_expected, usage_complete, within_deadline, within_total_budget, clean_exit |

## Blockers

* **codex**: none
* **opencode**: root Hybrid session ses_e8475be0dffegmze8EjHemGHZR has unfinished assistant records (msg_17b8c1d90001SY7LpUKmY2q9Ds); an incomplete turn is never an accepted arm; Sol reviewer session ses_e8473a88effeAQHmHQ23Pn5naJ has unfinished assistant records (msg_17b8c86d0001jU8uiTZHVM6WnS); an incomplete turn is never an accepted arm; native session ses_e8475be0dffegmze8EjHemGHZR:idle_outcome=missing lacks completion evidence; its counted usage is retained, but a session that never went idle or still awaits an answer cannot pass the arm; native session ses_e8475be0dffegmze8EjHemGHZR:time_idle=None lacks completion evidence; its counted usage is retained, but a session that never went idle or still awaits an answer cannot pass the arm; native session ses_e8473a88effeAQHmHQ23Pn5naJ:idle_outcome=interrupted lacks completion evidence; its counted usage is retained, but a session that never went idle or still awaits an answer cannot pass the arm; recorded routing is not the frozen root/child model and effort; usage is incomplete; the retained total is a lower bound, not a completion; the independent check never ran: arm deadline already expired; the independent check never started; unverified tests never accept an arm; the independent check process exited None; a check that does not exit 0 (including a killed or unstartable check) never accepts; the arm exceeded the frozen 180s budget before finishing; arm exceeded the 179.999996209 s deterministic deadline; retained partial usage is a lower bound; the client exited 130; a nonzero exit is never an accepted arm; no substantive semantic PASS verdict (absent); passing tests alone never accept

## Metrics

```json
{
  "cloud_tokens_per_completed_task": {
    "codex": 425757.0,
    "opencode": null
  },
  "per_arm_completed_tasks": {
    "codex": 1,
    "opencode": 0
  },
  "per_task_note": "each arm carries its own 1 or 0 completed task; a failed arm reports null per-task with its spend retained",
  "undefined_reason": null,
  "failed_attempts_included": true,
  "ratio": {
    "status": "undefined",
    "threshold": 0.3,
    "reason": "defined only when both arms are accepted with complete routing and usage on compatible protocol"
  },
  "runner_authoring_cost": {
    "status": "not_measured",
    "reason": "the runner launches no billing model itself; external authoring cost is reported separately"
  }
}
```

## Caveats

* CLI arms measure CLI clients only; a desktop App session is a separate client label imported by `finish`.
* Token counts are raw model tokens, not quota or price; cross-Mac cache state is an unknown caveat.
* App sessions are labelled codex-app, never a CLI measurement
* unknown maintenance is bounded, never an exact total
* a changed installed native config invalidates every arm; the runner never edits it
* report renders retained evidence only: it launches nothing, deletes nothing and needs no original home, database or config
