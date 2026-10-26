# Portable native OpenCode config + frozen benchmark

Obsolete repo code was wiped from the working tree (Git history and the archive/recovery
bundle outside the repo still hold it) and replaced with **native OpenCode configuration
only** plus the frozen round-1 benchmark package. There is deliberately **no framework, no
setup CLI, no installed wrapper, no plugin/addon and no controller** here.

```
config/opencode.json            serial single-worker Hybrid profile (portable)
config/parallel-up-to-4.json    optional behavioural overlay, NOT activated or measured
config/local-model.txt          local model id sidecar (example: qwen-3.8-nf-splash)
config/omlx-url.txt             local OpenAI-compatible endpoint sidecar
config/omlx.key.example         placeholder copy -> config/omlx.key (ignored, never committed)
benchmarks/                     frozen fixture, legacy instrumentation, protocol, round-1 results
docs/PLAN.md                    original plan + user scope update
```

## Outcome and honest limits

Measured on one Mac: single-worker Hybrid config, direct and scripted benchmark arms accepted,
**native Hybrid arm failed/rejected** (worker prepended an env assignment and a compound
command to an allowed check, permission denied it, and the coordinator wrongly let that worker
denial block its own authorized final check). See
`benchmarks/results/2026-10-26-round-1/RESULTS.md`. The prompt wording in `config/opencode.json`
that addresses this is an **offline-only, unvalidated correction** — no model was run to
re-measure anything in this package, so nothing here claims a native pass or a token saving.

## Install: merge, do not overwrite

`config/opencode.json` is a **partial** profile. Merge the pieces you want into
`~/.config/opencode/opencode.json` **by hand**, keeping your existing `provider`/`providers`
entries and your own global cloud `model` selection. This file intentionally sets **no**
top-level `model` and **no** `build`/`plan`/`compaction` model overrides, so your chosen cloud
model is inherited; `hybrid` and `review` carry no `model` either (review runs on the
inherited caller model). Do not blind-copy this file over a working global config.

Copy the sidecars next to wherever the config lives — `{file:./x}` references resolve relative
to the **config file's directory**, so they work identically in desktop and CLI without any
shell environment variables:

1. `config/local-model.txt` → the model id your local server actually serves.
2. `config/omlx-url.txt` → e.g. `http://127.0.0.1:8000/v1`.
3. `config/omlx.key.example` → copy to `config/omlx.key` and **replace the entire file
   contents with the single key line** your own local OpenAI-compatible server expects.
   Native `{file:...}` substitution reads the **whole file** (it only trims surrounding
   whitespace), so the key file must be exactly one line and must hold **no comments** — the
   example file is one placeholder line for exactly that reason. `config/omlx.key` is
   git-ignored; never commit a secret, and never commit a real key into a shared example file.

The chosen local model must support tool calls through the OpenAI-compatible endpoint;
confirm the served model id on the other Mac before using this profile.

**Then edit `providers.omlx.models[...].limit`.** `context: 262144` / `output: 8192` are the
numbers **USED in the measured round-1 profile** on one Mac with one model build; they are
**not** discovered universal maxima for the model or for OpenCode. On another Mac you **must**
set context and output to that machine's actual model values — do not assume these numbers
hold elsewhere. They are plain JSON numbers edited directly in `config/opencode.json` (the
`{file:...}` sidecars carry only the model id, endpoint URL and key). `name`/key substitution
is native (`{file:./local-model.txt}`), so editing that sidecar retargets `general`,
`explore`, `title` and `summary` in one place.

Native edit-tool rules deny `*/.config/opencode/*` and `*/.git/*`; they do not provide
filesystem confinement for executable tests. `subagent_depth` stays `1`, and shell access
is deny-by-default plus an explicit allow-list.

## Serial vs optional 4-parallel

Use `config/opencode.json`: **one** general worker at a time — the right default for small,
shared-file or order-dependent work. `config/parallel-up-to-4.json` is an overlay whose
content is the `hybrid` `description`/`system` text **plus `experimental.subagent_depth: 1`**,
so activating it keeps depth at 1 explicitly instead of inheriting some other value. Its
hybrid text permits **at most four concurrently
active general tasks, and only for independent work on disjoint paths/resources**, with
per-child bounded repair, child-session reuse, no recursive delegation, waiting by native
completion notifications (no polling), then coordinator verification of the combined tree and
one inherited-model semantic review of the exact combined digest.

**"4" is prompt guidance, not a scheduler cap.** OpenCode 2.1.4 has no measured
`max_concurrency` key — do not invent one — and `experimental.subagent_depth: 1` must stay 1
(depth 4 would be recursive delegation, not more parallelism). This overlay was **not**
activated or measured on this Mac, so it cannot be described as faster.

## Test fixture

`benchmarks/fixture/` is a disposable RED suite: `python3 -m unittest -v` from that directory
expects **12 tests, 3 failures** (boundary expiry cases). The failure is the point; the fix is
the benchmark task in `benchmarks/results/2026-10-26-round-1/manifest.json`.

## Legacy / instrumentation boundary

`benchmarks/legacy/` and `benchmarks/results/` are historical benchmark-only instrumentation,
**not** daily native commands, and they contain absolute Mac paths for provenance. The archived
launcher is **not** portable unchanged: it hardcodes the models measured here, so per-Mac
adaptation is a *new* version needing a fresh frozen manifest
(see `benchmarks/PROTOCOL.md`). No new runner or controller is provided.

## Native references

* Raw `{file:...}` / `{env:...}` config substitution:
  <https://raw.githubusercontent.com/anomalyco/opencode/v2.1.4/packages/core/src/config/variable.ts>
* `experimental` subagent depth vs (absent) concurrency:
  <https://raw.githubusercontent.com/anomalyco/opencode/v2.1.4/packages/schema/src/config/experimental.ts>

`tool_output` native `max_lines`/`max_bytes` does exist in 2.1.4 but was **not** tested here:
at most a future bounded-output experiment. Measured-profile tuning is deliberately **not**
added now.
