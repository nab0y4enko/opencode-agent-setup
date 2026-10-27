# opencode-agent-setup

A native OpenCode 2 profile where the cloud model plans and reviews while a local model (oMLX)
reads, edits, builds and tests. Also a benchmark that measures it against the Codex Sol + Luna flow
on a small SwiftUI app.

Everything — the idea, the profile, installation, the benchmark and its results — is in
[AGENTS.md](AGENTS.md).

```sh
python3 -B -m unittest discover -s benchmarks -p 'test_*.py'
python3 benchmarks/run.py --help
```
