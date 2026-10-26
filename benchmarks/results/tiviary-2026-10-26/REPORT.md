# Same-task cloud-token report: Codex Sol + Luna versus native OpenCode Sol + Qwen

**Task:** Preserve existing native cards, sizes and styling. Change Categories landing scroll direction to vertical. In a category collection retain horizontally scrolling category selector and change media items below to vertical scrolling. Correct content insets so the complete focused last card clears the fixed glass panel at bottom. Increase mock catalog to 60 items each of live, movies, series with stable unique IDs and valid same-kind memberships.

**Starting commit:** `4f2e5c3aed06d89b3bdd166fbc9fc5268b67d3f7`. Saved task files have identical goal, base, allowed paths and acceptance requirements. No models were run for this retrospective audit.

## Direct answer

| Execution | Cloud tokens | Local tokens | Outcome |
|---|---:|---:|---|
| Codex app: GPT-6.1 Sol medium + GPT-6 Luna medium | **6,171,523** | 0 | Accepted; initial compilation failure, one Luna repair |
| Native OpenCode: GPT-6.1 Sol medium + local Qwen | **627,038** | **3,738,469** | Accepted after three local repairs and external corrective guidance; not autonomous from start |
| Native OpenCode including its preceding failed task execution | **960,534** | **8,969,179** | One eventual accepted completion across both executions/configuration versions |

Native recovery cloud usage / Codex app cloud usage = **627,038 / 6,171,523 = 10.16%**: **89.84% less identified task-execution cloud usage**. Including the prior failed native task execution gives **15.56%**, or **84.44% less**. Both are below a 30% execution-token threshold against this specific **Sol+Luna** baseline. They do not establish autonomous native success or repeatable savings.

The recent tiny TTL-cache round is a separate task. It measured direct Sol (43,932 cloud tokens) against failed native Hybrid (54,967), and did **not** run a Codex Sol+Luna arm. No same-task Sol+Luna comparison exists for that fixture. Never compare its 54,967 tokens with Tiviary's 6,171,523.

## Who used the cloud tokens

| Role | Codex app | Native OpenCode |
|---|---:|---:|
| Sol planning / coordination / semantic review / reporting | 3,013,201 | 627,038 |
| Of native Sol: coordinator | — | 344,100 |
| Of native Sol: separate semantic reviewer | — | 282,938 |
| Luna implementation + repair | 3,158,322 | 0 |
| Qwen implementation + repairs, local only | 0 | 3,738,469 local |
| **Cloud total** | **6,171,523** | **627,038** |

Actual Codex rollout contexts record `gpt-6.1-sol`/medium and one reused `gpt-6-luna`/medium child. Native assistant records show `openai/gpt-6.1-sol#medium` for coordinator/reviewer and `omlx/qwen-3.8-nf-splash` for implementation/repairs. These identities come from recorded execution, not configuration alone.

The observed cloud difference is **5,544,485**. Arithmetically, 3,158,322 corresponds to the Luna cloud work removed from the cloud budget; another 2,386,163 comes from lower Sol usage. This is a decomposition, not proof that local-worker substitution caused the entire difference: orchestration, context, reviews, tests and retries also differ.

## Token accounting, without double counting

| Disjoint cloud category | Codex Sol+Luna | Native Sol+Qwen recovery |
|---|---:|---:|
| Uncached input | 221,623 | 127,321 |
| Cached input | 5,920,640 | 493,696 |
| Non-reasoning output | 18,494 | 5,782 |
| Reasoning output | 10,766 | 239 |
| **Total cloud** | **6,171,523** | **627,038** |

Codex cumulative `input_tokens` already includes cached input; `output_tokens` already includes reasoning. The table subtracts those subsets before displaying them separately. Native OpenCode stores input, cache-read, output and reasoning as disjoint fields. Cache-write is zero here. Codex final cumulative totals were counted once per session and reconciled against final saved usage records. Native session aggregates reconcile with assistant sums with zero maintenance gap in this recovery.

Most of the raw reduction is cached input. Excluding cached input, the comparison is **250,883 versus 133,342**, a **46.85%** reduction, rather than 89.84%. Your raw-token metric includes cache, so the 89.84% figure answers that metric; neither figure measures subscription quota debits or dollar cost.

## Attempts, checks and timing

| Measure | Codex app | Native recovery |
|---|---|---|
| Implementation worker sessions | One Luna child, reused | One Qwen child, reused |
| Repairs after initial implementation | 1 | 3; third used external guidance after initial budget exhaustion |
| Cloud usage observations | 41 Sol + 43 Luna distinct completed usage updates | 19 coordinator + 6 reviewer assistant records |
| Local assistant records | 0 | 61 |
| Top-level tool calls | 40 Sol + 41 Luna; exec calls may contain multiple deterministic operations | 127 total across cloud/local tree |
| Recorded duration | 715.946 seconds, approximately 11.93 minutes | 1,996.278 active seconds, approximately 33.27 minutes |
| Final invariant / unit / UI tests | 43 / 3 / 5 | 43 / 4 / 6 |
| Semantic review | Sol parent reviewed source/checks and 15 exported screenshots | Separate inherited Sol reviewer; seven images inspected |

Timing definitions differ: Codex's session span includes integration/archive/reporting; native active time sums initial and recovery executions and excludes some host gaps. Test coverage differs, so this is the same requested change from the same base, not identical validation effort. Native recovery also used lessons from earlier failures and host-guided correction; it is not a blind benchmark.

The preceding failed native execution spent **333,496 cloud + 5,230,710 local tokens**, timed out at approximately 2,400 seconds, and had no accepted completion. Those costs remain charged in the 960,534 campaign execution total above.

## Development, supervision and reporting costs

| Scope | Cloud tokens |
|---|---:|
| Codex Sol+Luna task session tree, including its own checks/review/reporting | 6,171,523 |
| Native recovery task tree only | 627,038 |
| Native recovery plus setup probes and external Codex investigation/supervision/reporting | **at least 9,577,634** |
| Both historical native campaigns, their setup probes and nonoverlapping external host windows | **at least 22,549,058** |

The last total is 960,534 task-execution cloud + 51,692 setup-probe cloud + 12,637,928 earlier external-host cloud + 8,898,904 later external-host cloud. The saved host windows do not overlap (earlier snapshot ends 21:38 UTC; later starts 21:40 UTC). Missing intervals and final replies make this a lower bound. These developmental totals exclude earlier shared/scripted setup and the current repository-reconstruction thread.

The current reconstruction thread had a separately reported **15,394,987 cloud-token lower bound**, including its earlier failed setup and tiny-task benchmark. It is not part of the 627,038 Tiviary execution figure. This audit's growing external cloud usage is separately recorded in `comparison.json`; no new benchmark or local-worker calls were started for it.

**Therefore the historical development campaign did not save cloud tokens overall against running the Codex task once.** The observed execution-only reduction supports the local-worker idea; development overhead and autonomous reliability remain unresolved. Do not hide setup costs inside a claim of ordinary per-task savings, and do not mistake a prototype's one-off development bill for a measured recurring per-task cost.

## Scripted reference, clearly separated

The older scripted OpenCode Sol+Qwen run used **263,216 identified cloud tokens**, **3,875,177 identified local tokens**, and **30,987 unknown-model maintenance tokens**; it was accepted after two local repairs and two cloud reviews. Cloud usage was 4.27% of Codex Sol+Luna, or 95.73% lower. The older headline local total 3,906,164 incorrectly absorbed every unknown maintenance token into local usage; this report keeps them separate. This was the scripted workflow, not the requested daily native experience.

## Conclusion

For this saved Tiviary task, moving implementation from cloud Luna to local Qwen coincided with a large reduction in identified cloud execution tokens: **6.17M to 627K**, or **961K including the preceding failed native execution**. This meets the raw execution-token fraction target against **Codex Sol+Luna**. Native autonomy was not demonstrated, total development cloud costs were higher, and the same comparison has not been performed on the small TTL fixture or another Mac/model.

## Evidence

`comparison.json` contains reconciled calculations, source hashes, model identities, scope and this audit's usage snapshot. `evidence/` contains byte-identical accounting, acceptance, task and host-cost records from the supplied saved evidence. Large raw rollouts remain at their original paths in the copied accounting files. No configuration, model selection or Tiviary source was modified.
