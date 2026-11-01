"""Install the Hybrid profile (config/opencode.json) into this Mac's OpenCode configuration.

  python3 install.py [--model <served id>] [--url http://127.0.0.1:8000/v1] [--key-file <path>]
                     [--context N --output N] [--config-dir ~/.config/opencode] [--dry-run]

The profile is merged, never copied over: other providers, other agents, the selected cloud model and
custom permission rules stay. Shell restrictions on hybrid, general and review are dropped (see
AGENTS.md, Permissions). The oMLX key comes from --key-file, $OMLX_API_KEY or the existing omlx.key and
is never printed. Limits come from the served model unless given. The previous file is kept as
opencode.json.bak-<time>, and the result is checked with `opencode debug agents --standalone`.
"""
import argparse
import copy
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / 'benchmarks'))
import permissions as P

PROFILE = REPO_ROOT / 'config' / 'opencode.json'
MODEL_REF = '{file:./local-model.txt}'
LOCAL_MODEL = f'omlx/{MODEL_REF}'
DEFAULT_URL = 'http://127.0.0.1:8000/v1'
MAX_OUTPUT = 32768
SHELL_ROLES = ('hybrid', 'general', 'review')
LOCAL_ROLES = ('general', 'explore', 'compaction')
CLOUD_ROLES = ('hybrid', 'review')
# Rules earlier profile versions installed; a reinstall removes them so they cannot outlive the profile.
LEGACY_RULES = {'general': [{'action': 'skill', 'resource': '*', 'effect': 'deny'}]}
_SECRET = re.compile(r'("[^"]*(?:key|token|secret|password)[^"]*"\s*:\s*)"(?!\{file:)[^"]*"', re.I)


class SetupError(Exception):
    pass


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except ValueError as exc:
        raise SetupError(f'{path} is not strict JSON (JSONC is unsupported): {exc}') from exc


def read_text(path):
    path = Path(path)
    return path.read_text(encoding='utf-8').strip() if path.is_file() else None


def served_models(url, key, timeout=10):
    """The models oMLX serves, as {id: max_model_len or None}."""
    request = urllib.request.Request(url.rstrip('/') + '/models', headers={'Authorization': f'Bearer {key}'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode('utf-8'))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SetupError(f'cannot list models at {url}: {exc}') from exc
    return {m['id']: m.get('max_model_len') for m in body.get('data') or [] if isinstance(m, dict) and m.get('id')}


def choose_model(requested, previous, served):
    if requested or previous:
        model = requested or previous
        if served and model not in served:
            raise SetupError(f'oMLX does not serve {model!r}; it serves {sorted(served)}')
        return model
    if len(served) == 1:
        return next(iter(served))
    raise SetupError(f'choose the local model with --model; oMLX serves {sorted(served) or "nothing"}')


def choose_limits(context, output, max_model_len, profile_limit):
    """Context is the served length unless given; output is a quarter of it, at most 32,768."""
    context = context or max_model_len or profile_limit['context']
    output = output or min(MAX_OUTPUT, context // 4)
    if output >= context:
        raise SetupError(f'output limit {output} must be below the context limit {context}')
    return {'context': context, 'output': output}


def _keep_rule(agent, rule, profile_rules):
    if rule in profile_rules or rule in LEGACY_RULES.get(agent, []):
        return False
    return not (agent in SHELL_ROLES and rule.get('action') == 'shell' and rule.get('effect') != 'allow')


def merge(installed, profile, model_id, limits):
    """The installed config with the profile applied; everything the profile does not own is kept."""
    out = copy.deepcopy(installed)
    for key in ('$schema', 'default_agent'):
        out[key] = profile[key]
    source = copy.deepcopy(profile['providers']['omlx'])
    entry = dict(source.pop('models')[MODEL_REF], name=model_id, limit=limits)
    current = (out.setdefault('providers', {}).get('omlx') or {})
    models = {k: v for k, v in (current.get('models') or {}).items() if k != MODEL_REF}
    models[model_id] = entry
    out['providers']['omlx'] = dict(current, **source, models=models)
    agents = out.setdefault('agents', {})
    for name, wanted in profile['agents'].items():
        agent = dict(agents.get(name) or {})
        if name in CLOUD_ROLES:
            agent.pop('model', None)
        profile_rules = wanted.get('permissions') or []
        custom = [r for r in agent.pop('permissions', None) or [] if _keep_rule(name, r, profile_rules)]
        agent.update({k: copy.deepcopy(v) for k, v in wanted.items() if k != 'permissions'})
        # Custom rules first, so the profile's role boundaries are the last match and win.
        if custom or profile_rules:
            agent['permissions'] = custom + copy.deepcopy(profile_rules)
        agents[name] = agent
    return out


def check_agents(listing, profile, model_id):
    """Problems in `opencode debug agents --standalone` output; an empty list means installed as intended."""
    if not isinstance(listing, list):
        return ['OpenCode did not list its agents']
    by_id = {a.get('id'): a for a in listing if isinstance(a, dict)}
    problems = []
    for name, wanted in profile['agents'].items():
        agent = by_id.get(name)
        if agent is None:
            problems.append(f'OpenCode lists no {name} agent')
            continue
        model = agent.get('model') or {}
        if name in LOCAL_ROLES and (model.get('providerID'), model.get('id')) != ('omlx', model_id):
            problems.append(f'{name} runs on {model or "the caller model"}, not omlx/{model_id}')
        if name in CLOUD_ROLES and model:
            problems.append(f'{name} pins {model}; it must inherit the selected cloud model')
        if 'steps' in wanted and agent.get('steps') != wanted['steps']:
            problems.append(f'{name} has {agent.get("steps")} steps, the profile sets {wanted["steps"]}')
        if name in SHELL_ROLES:
            rules = agent.get('permissions') or agent.get('permission') or []
            for part in P.command_parts(P.PROBE_COMMAND):
                effect, rule = P.decide(rules, 'shell', part)
                if effect != 'allow':
                    problems.append(f'{name} would {effect} `{part}` (rule {rule}); {P.FIX}')
                    break
    return problems


def effective_agents(binary):
    with tempfile.TemporaryDirectory() as empty:
        proc = subprocess.run([binary, 'debug', 'agents', '--standalone'], cwd=empty, env=dict(os.environ, PWD=empty),
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False)
    if proc.returncode:
        raise SetupError(f'`{binary} debug agents --standalone` failed: {(proc.stderr or proc.stdout).strip()[:300]}')
    try:
        return json.loads(proc.stdout)
    except ValueError as exc:
        raise SetupError(f'`{binary} debug agents --standalone` did not print JSON: {exc}') from exc


def redacted_diff(before, after, path):
    lines = difflib.unified_diff(before.splitlines(), after.splitlines(), str(path), f'{path} (new)', n=1, lineterm='')
    return '\n'.join(_SECRET.sub(r'\1"***"', line) for line in lines)


def write_private(path, text):
    path.write_text(text, encoding='utf-8')
    path.chmod(0o600)


def install(args):
    config_dir = Path(args.config_dir).expanduser()
    target = config_dir / 'opencode.json'
    profile = load_json(PROFILE)
    installed = load_json(target) if target.exists() else {}
    url = args.url or read_text(config_dir / 'omlx-url.txt') or DEFAULT_URL
    key = (read_text(Path(args.key_file).expanduser()) if args.key_file else None) \
        or os.environ.get('OMLX_API_KEY') or read_text(config_dir / 'omlx.key')
    if not key:
        raise SetupError('no oMLX key: pass --key-file, set OMLX_API_KEY, or create omlx.key')
    try:
        served = served_models(url, key)
    except SetupError as exc:
        if not (args.model and args.context):
            raise SetupError(f'{exc}; start oMLX, or pass --model and --context to install offline') from exc
        print(f'warning: {exc}; using the given model and limits', file=sys.stderr)
        served = {}
    model = choose_model(args.model, read_text(config_dir / 'local-model.txt'), served)
    limits = choose_limits(args.context, args.output, served.get(model),
                           profile['providers']['omlx']['models'][MODEL_REF]['limit'])
    merged = merge(installed, profile, model, limits)
    before = json.dumps(installed, indent=2, ensure_ascii=False) + '\n' if installed else ''
    after = json.dumps(merged, indent=2, ensure_ascii=False) + '\n'
    print(f'local model {model} at {url}, context {limits["context"]}, output {limits["output"]}')
    if args.dry_run:
        print(redacted_diff(before, after, target) or 'opencode.json: no change')
        return []
    config_dir.mkdir(parents=True, exist_ok=True)
    if before != after:
        if target.exists():
            backup = target.with_name(f'opencode.json.bak-{time.strftime("%Y%m%d-%H%M%S")}')
            shutil.copy2(target, backup)
            print(f'previous config kept as {backup}')
        target.write_text(after, encoding='utf-8')
        print(f'wrote {target}')
    else:
        print(f'{target} already matches the profile')
    (config_dir / 'local-model.txt').write_text(model + '\n', encoding='utf-8')
    (config_dir / 'omlx-url.txt').write_text(url + '\n', encoding='utf-8')
    write_private(config_dir / 'omlx.key', key + '\n')
    if args.skip_verify:
        return []
    binary = shutil.which(args.opencode_bin)
    if not binary:
        raise SetupError(f'{args.opencode_bin!r} is not on PATH; install OpenCode, then rerun to verify')
    return check_agents(effective_agents(binary), profile, model)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--config-dir', default='~/.config/opencode')
    parser.add_argument('--model', help='served local model ID (default: the installed one, or the only one served)')
    parser.add_argument('--url', help=f'oMLX base URL (default: the installed one, or {DEFAULT_URL})')
    parser.add_argument('--key-file', help='file holding the oMLX API key')
    parser.add_argument('--context', type=int, help='local context limit (default: the served length)')
    parser.add_argument('--output', type=int, help=f'local output limit (default: context/4, at most {MAX_OUTPUT})')
    parser.add_argument('--opencode-bin', default='opencode')
    parser.add_argument('--dry-run', action='store_true', help='print the redacted change and write nothing')
    parser.add_argument('--skip-verify', action='store_true')
    args = parser.parse_args(argv)
    try:
        problems = install(args)
    except SetupError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    for problem in problems:
        print(f'problem: {problem}', file=sys.stderr)
    if problems:
        return 1
    if not args.dry_run:
        print('installed. If this Mac has no cloud login yet, run `opencode auth login`.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
