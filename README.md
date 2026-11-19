# opencode-agent-setup

A native OpenCode 2 profile where GPT-6.2 Sol investigates, briefs and reviews, and a local
Qwen3.8-Flash-Next model on Splash implements and validates. Everything — the idea, the profile, the
installer and the results — is in [AGENTS.md](AGENTS.md).

Set up an Apple silicon Mac (Homebrew and Python 3.9+ required):

```sh
python3 install.py
opencode auth login openai
```

```sh
python3 -B -m unittest discover -s tests -p 'test_*.py'
```
