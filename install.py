"""Install the Splash orchestrator profile on this Mac.

  python3 install.py [--dry-run] [--skip-brew] [--no-splash] [--wait SECONDS] [--config-dir DIR]

Steps, each skipped when already done:
1. Homebrew: OpenCode 2 (anomalyco/tap/opencode-v2) and Splash (incoai/tap/splash-app, incoai/tap/splash).
2. Splash: selects the worker model named in config/opencode.jsonc, starts the app and waits until the
   model is served (the first start downloads it, about 90 GB).
3. OpenCode: writes config/opencode.jsonc and config/AGENTS.md into ~/.config/opencode. Files that
   differ are first moved to backup-<time>/ there.
4. Checks: `opencode debug agents` routes every role to its configured model, Splash honours the thinking
   cap, and an OpenAI login exists. Signing in (`opencode auth login`) is the one step left to you.

Exit status: 0 when everything is ready, 2 when only manual steps remain, 1 on an error.
"""
import argparse
import json

import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
PROFILE = REPO_ROOT / 'config' / 'opencode.jsonc'
RULES = REPO_ROOT / 'config' / 'AGENTS.md'
INSTALLED_NAMES = {PROFILE: 'opencode.jsonc', RULES: 'AGENTS.md'}
# A plain opencode.json would be merged with the profile, so it is moved aside with the other files.
REPLACED = ('opencode.json', 'opencode.jsonc', 'AGENTS.md')
TAPS = ('anomalyco/tap', 'incoai/tap')
FORMULAE = ('anomalyco/tap/opencode-v2', 'incoai/tap/splash')
CASKS = ('incoai/tap/splash-app',)
SPLASH_APP = 'Splash'
SPLASH_DOMAIN = 'ai.inco.splash'
CLOUD_PROVIDER = 'openai'


class SetupError(Exception):
    pass


def parse_jsonc(text):
    """JSON with // and /* */ comments, the format OpenCode reads."""
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == '\\' else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith('//', i):
            i = text.find('\n', i)
            i = n if i < 0 else i
        elif text.startswith('/*', i):
            end = text.find('*/', i + 2)
            if end < 0:
                raise SetupError('unterminated /* comment')
            i = end + 2
        else:
            out.append(ch)
            i += 1
    try:
        return json.loads(''.join(out))
    except ValueError as exc:
        raise SetupError(f'profile is not valid JSONC: {exc}') from exc


def parse_model_ref(ref):
    """'provider/model#variant' -> (provider, model, variant or None)."""
    match = re.fullmatch(r'([^/#]+)/([^#]+)(?:#(.+))?', ref or '')
    if not match:
        raise SetupError(f'bad model reference: {ref!r}')
    return match.group(1), match.group(2), match.group(3)


def load_profile(path=PROFILE):
    return parse_jsonc(Path(path).read_text(encoding='utf-8'))


def expected_routes(profile):
    """{agent name: (provider, model, variant)} for every agent the profile pins to a model."""
    return {name: parse_model_ref(agent['model'])
            for name, agent in profile.get('agents', {}).items() if agent.get('model')}


def worker_model(profile):
    """(base URL, served model ID) of the local provider the workers use."""
    providers = profile.get('providers', {})
    for provider, model, _ in expected_routes(profile).values():
        if provider in providers:
            settings = providers[provider]
            return settings['settings']['baseURL'].rstrip('/'), settings['models'][model]['modelID']
    raise SetupError('no agent uses a local provider defined in the profile')


def thinking_cap(profile):
    """(served model ID, variant body) of the first local variant that caps thinking."""
    providers = profile.get('providers', {})
    for provider, model, variant in expected_routes(profile).values():
        if provider in providers:
            entry = providers[provider]['models'][model]
            for item in entry.get('variants', []):
                if item['id'] == variant and 'thinking_token_budget' in item['body']:
                    return entry['modelID'], item['body']
    return None


def brew_plan(taps, formulae, casks):
    """The brew commands still needed, given what is installed."""
    plan = [['brew', 'tap', tap] for tap in TAPS if tap not in taps]
    plan += [['brew', 'install', name] for name in FORMULAE if name.rsplit('/', 1)[-1] not in formulae]
    plan += [['brew', 'install', '--cask', name] for name in CASKS if name.rsplit('/', 1)[-1] not in casks]
    return plan


def plan_files(config_dir, sources=None):
    """(files to move to the backup, files to write) for the OpenCode configuration directory."""
    sources = sources or INSTALLED_NAMES
    config_dir = Path(config_dir)
    wanted = {name: Path(src).read_bytes() for src, name in sources.items()}
    move, write = [], []
    for name in REPLACED:
        target = config_dir / name
        if target.exists() and target.read_bytes() != wanted.get(name):
            move.append(target)
    for name, data in wanted.items():
        target = config_dir / name
        if not target.exists() or target.read_bytes() != data or target in move:
            write.append((target, data))
    return move, write


def apply_files(config_dir, move, write, stamp):
    if move:
        backup = Path(config_dir) / f'backup-{stamp}'
        backup.mkdir(parents=True, exist_ok=True)
        for path in move:
            shutil.move(str(path), str(backup / path.name))
    Path(config_dir).mkdir(parents=True, exist_ok=True)
    for path, data in write:
        path.write_bytes(data)


def route_problems(listing, routes):
    """Mismatches between `opencode debug agents` output and the profile's routes."""
    by_name = {}
    for agent in listing:
        by_name[agent.get('name', '').lower()] = agent
    problems = []
    for name, (provider, model, variant) in sorted(routes.items()):
        agent = by_name.get(name.lower())
        if agent is None:
            problems.append(f'{name}: missing from opencode debug agents')
            continue
        got = agent.get('model') or {}
        actual = (got.get('providerID'), got.get('id'), got.get('variant'))
        if actual != (provider, model, variant):
            problems.append(f'{name}: routed to {actual}, expected {(provider, model, variant)}')
    return problems


def has_login(auth_listing, provider=CLOUD_PROVIDER):
    """True when `opencode auth list` shows a stored credential for the provider."""
    for line in auth_listing.splitlines():
        words = line.split()
        if words and words[0].lower() == provider and 'stored' in (w.lower() for w in words[1:]):
            return True
    return False


def run(cmd, dry_run=False, check=True, **kwargs):
    print('  $ ' + ' '.join(cmd))
    if dry_run:
        return subprocess.CompletedProcess(cmd, 0, '', '')
    proc = subprocess.run(cmd, text=True, capture_output=True, **kwargs)
    if check and proc.returncode != 0:
        raise SetupError(f'{cmd[0]} failed ({proc.returncode}): {(proc.stderr or proc.stdout).strip()[-400:]}')
    return proc


def output(cmd):
    return subprocess.run(cmd, text=True, capture_output=True, check=False).stdout


def served_models(base_url, timeout=5):
    try:
        with urllib.request.urlopen(base_url + '/models', timeout=timeout) as resp:
            return [m['id'] for m in json.load(resp).get('data', [])]
    except (urllib.error.URLError, OSError, ValueError):
        return None


def chat(base_url, body, timeout=300):
    request = urllib.request.Request(base_url + '/chat/completions', json.dumps(body).encode(),
                                     {'content-type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.load(resp)


def step_brew(args):
    print('1. Homebrew packages')
    if args.skip_brew:
        print('  skipped (--skip-brew)')
        return
    if not shutil.which('brew'):
        raise SetupError('Homebrew is required: https://brew.sh')
    taps = output(['brew', 'tap']).split()
    formulae = output(['brew', 'list', '--formula', '-1']).split()
    casks = output(['brew', 'list', '--cask', '-1']).split()
    plan = brew_plan(taps, formulae, casks)
    if not plan:
        print('  OpenCode 2 and Splash are installed')
    for cmd in plan:
        run(cmd, args.dry_run)


def step_splash(args, profile):
    print('2. Splash and the worker model')
    base_url, model_id = worker_model(profile)
    if args.no_splash:
        print('  skipped (--no-splash)')
        return True
    served = served_models(base_url)
    if served is not None and model_id in served:
        print(f'  serving {model_id}')
        return True
    selected = output(['defaults', 'read', SPLASH_DOMAIN, 'model']).strip()
    if selected != model_id:
        run(['defaults', 'write', SPLASH_DOMAIN, 'model', '-string', model_id], args.dry_run)
    if served is not None:
        print(f'  Splash serves {served}; restarting it with {model_id}')
        run(['osascript', '-e', f'quit app "{SPLASH_APP}"'], args.dry_run, check=False)
        if not args.dry_run:
            time.sleep(5)
    run(['open', '-a', SPLASH_APP], args.dry_run)
    if args.dry_run:
        return True
    print(f'  waiting up to {args.wait} s for {model_id} (the first start downloads it)')
    deadline = time.monotonic() + args.wait
    while time.monotonic() < deadline:
        served = served_models(base_url)
        if served is not None and model_id in served:
            print(f'  serving {model_id}')
            return True
        time.sleep(15)
    print(f'  NOT READY: Splash does not serve {model_id} yet. Open Splash, let the download finish, '
          f'then rerun this installer.')
    return False


def step_config(args):
    print(f'3. OpenCode configuration in {args.config_dir}')
    move, write = plan_files(args.config_dir)
    if not move and not write:
        print('  up to date')
        return
    stamp = time.strftime('%Y%m%d-%H%M%S')
    for path in move:
        print(f'  back up {path.name} -> backup-{stamp}/')
    for path, _ in write:
        print(f'  write {path.name}')
    if not args.dry_run:
        apply_files(args.config_dir, move, write, stamp)


def step_checks(args, profile, splash_ready):
    print('4. Checks')
    if args.dry_run:
        print('  skipped (--dry-run)')
        return []
    if not shutil.which('opencode'):
        raise SetupError('opencode is not on PATH')
    if Path(args.config_dir).expanduser() != DEFAULT_CONFIG_DIR:
        print('  skipped: OpenCode reads ~/.config/opencode, not --config-dir')
        return []
    proc = subprocess.run(['opencode', 'debug', 'agents'], text=True, capture_output=True, check=False)
    try:
        listing = json.loads(proc.stdout)
    except ValueError as exc:
        raise SetupError(f'opencode debug agents did not print JSON: {(proc.stderr or proc.stdout)[-400:]}') from exc
    problems = route_problems(listing, expected_routes(profile))
    if problems:
        raise SetupError('agent routing does not match the profile: ' + '; '.join(problems))
    for name, ref in sorted(expected_routes(profile).items()):
        print(f'  {name}: {ref[0]}/{ref[1]}#{ref[2]}')
    remaining = []
    cap = thinking_cap(profile)
    if splash_ready and cap:
        base_url, _ = worker_model(profile)
        model_id, body = cap
        budget = body['thinking_token_budget']
        reply = chat(base_url, dict(body, model=model_id, max_tokens=budget + 1500, messages=[{
            'role': 'user', 'content': 'How many prime numbers are between 100 and 200? Think, then answer.'}]))
        used = ((reply.get('usage') or {}).get('completion_tokens_details') or {}).get('reasoning_tokens')
        if used is None or used > budget + 8:
            raise SetupError(f'Splash ignored the thinking cap: {used} reasoning tokens for a budget of {budget}')
        print(f'  thinking cap holds: {used} of {budget} tokens')
    elif not splash_ready:
        remaining.append('Let Splash finish downloading the worker model, then rerun python3 install.py')
    if has_login(output(['opencode', 'auth', 'list'])):
        print(f'  {CLOUD_PROVIDER} login found')
    else:
        remaining.append(f'Sign in to the cloud model: opencode auth login {CLOUD_PROVIDER}')
    return remaining


DEFAULT_CONFIG_DIR = Path.home() / '.config' / 'opencode'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--dry-run', action='store_true', help='print what would change; change nothing')
    parser.add_argument('--skip-brew', action='store_true', help='do not install or check Homebrew packages')
    parser.add_argument('--no-splash', action='store_true', help='do not configure or start Splash')
    parser.add_argument('--wait', type=int, default=3600, help='seconds to wait for the worker model (default 3600)')
    parser.add_argument('--config-dir', type=Path, default=DEFAULT_CONFIG_DIR, help='OpenCode configuration directory')
    args = parser.parse_args(argv)
    try:
        if platform.system() != 'Darwin' or platform.machine() != 'arm64':
            raise SetupError('this profile needs an Apple silicon Mac')
        profile = load_profile()
        step_brew(args)
        splash_ready = step_splash(args, profile)
        step_config(args)
        remaining = step_checks(args, profile, splash_ready)
    except SetupError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    if remaining:
        print('\nAlmost done. Remaining:')
        for item in remaining:
            print(f'  - {item}')
        return 2
    print('\nReady. Start with: opencode')
    return 0


if __name__ == '__main__':
    sys.exit(main())
