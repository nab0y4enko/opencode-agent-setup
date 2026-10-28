"""Portable two-arm cross-Mac benchmark CLI (Python stdlib; authoring makes no model call).

Commands (every path and model choice is an explicit per-machine argument):
  prepare --out OUT --local-model omlx/<id> [--label mac-a] [--codex-bin ... --opencode-bin ...
          --codex-home ~/.codex --opencode-db ~/.local/share/opencode/opencode.db
          --opencode-config ~/.config/opencode/opencode.json --timeout 180]
  run     same arguments as prepare, plus --live to launch the Codex Sol+Luna arm and the native
          OpenCode Hybrid arm; without --live nothing launches and only a dry-run plan is written.
  finish  OUT --codex-thread <root thread id> --live imports a real Codex DESKTOP APP session
          (labelled codex-app, never a CLI measurement), then launches the Hybrid arm.
  report  OUT regenerates report.json/REPORT.md offline from retained evidence; launches nothing.
  compare OUT [OUT ...] offline; refuses frozen-field mismatches between Macs.
"""
import argparse
import datetime
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tarfile
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import accounting as A
import fixtures as FX
import hardware
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURE = 'ttl-python'
DEFAULT_CLOUD_CODEX = 'gpt-6.1-sol'
DEFAULT_CLOUD_OPENCODE = 'openai/gpt-6.1-sol#medium'
DEFAULT_CHILD_MODEL = 'gpt-6-luna'
DEFAULT_EFFORT = 'medium'
CLIENT_EFFORTS = ('minimal', 'low', 'medium', 'high')
SUPPORTED_EFFORTS = ('medium',)
MAX_WORKERS = 4
PERMISSION_BYPASS_FLAGS = ('--yolo', '--dangerously-bypass-approvals-and-sandbox', '--no-sandbox',
                           '--full-auto', '--auto-approve', '--auto', '--allow-all',
                           '--disable-permissions', '--permission-mode')
GLOBAL_CONFIG_FLAGS = ('--global', '-g', '--config', '--edit-config', '--write-config',
                       '--update-config', '--install', '--set-profile', '--profile')
TASK = FX.TTL_TASK
CODEX_ADDENDUM = '\n\nCLIENT: Codex CLI baseline (orchestrated instrumented run, not daily usage).\nAuthorized benchmark exception to the local-worker defaults above, for this run only:\n* The root session on the assigned cloud Sol model at {effort} effort plans and reviews and must not implement code itself.\n* Delegate all implementation to 1-4 workers on the configured subagent model {child_model} at {effort} effort; run workers in parallel only on disjoint files, and give each worker at most ONE repair using real failure evidence.\n* The worker must not switch models, delegate further, commit, push, create worktrees or launch model commands.\n* The root runs the required check itself, then emits the VERDICT line itself from the root session after substantive review of the complete diff digest.\n'
OPENCODE_ADDENDUM = '\n\nCLIENT: installed native OpenCode Hybrid (instrumented run, not a new controller).\n* Use the installed native roles unchanged: the Hybrid coordinator runs on the cloud model passed with --model, `general` is the configured local worker, `review` runs on the inherited caller model.\n* Do not override any role model, change config or providers, or install anything; all installed native permission denials stay in force.\n* Delegate all implementation to 1-4 `general` worker sessions, in parallel only on disjoint files; each worker gets at most ONE repair.\n* The coordinator verifies independently and obtains exactly ONE review from the `review` subagent bound to the exact complete-diff digest; the review emits the VERDICT line.\n'

def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

def git(repo, *args):
    proc = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise A.PreflightBlocker(f"git {' '.join(args)} failed: {proc.stderr.strip()[:300]}")
    return proc.stdout.strip()

def tool_version(binary):
    """Version text for machine info: an absent or unrunnable tool is 'unavailable', never a crash.

    Machine information is collected during preparation on every Mac, where either client may simply
    not be installed.  A missing executable is reported as 'unavailable' here; preflight is what turns
    an absent binary into a readable launch blocker before anything is launched.
    """
    if not binary:
        return 'unavailable'
    resolved = str(Path(binary).expanduser())
    if not (os.path.isfile(resolved) or shutil.which(resolved)):
        return 'unavailable'
    try:
        proc = subprocess.run([resolved, '--version'], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return 'unavailable'
    text = (proc.stdout or proc.stderr).strip().splitlines()
    return text[0][:120] if proc.returncode == 0 and text else 'unavailable'

def permission_blockers(argv):
    """A benchmark arm may never bypass installed native permissions or edit global config."""
    flags = [str(arg) for arg in (argv or []) if str(arg).startswith('-')]
    bypassed = [flag for flag in flags if flag in PERMISSION_BYPASS_FLAGS]
    global_edits = [flag for flag in flags if flag in GLOBAL_CONFIG_FLAGS]
    blockers = []
    if bypassed:
        blockers.append(f'launch argv bypasses installed native permission(s) with {bypassed}; every '
                        'installed denial stays in force for a benchmark arm')
    if global_edits:
        blockers.append(f'launch argv edits installed/global configuration with {global_edits}; only '
                        'session-scoped overrides are allowed for an arm')
    return blockers

def config_integrity(manifest):
    """Re-read the frozen native config digest: a config edited mid-run invalidates every arm."""
    record = manifest.get('native_config') or {}
    (path, frozen) = (record.get('path'), record.get('raw_sha256'))
    current = None
    if path and frozen:
        try:
            current = A.sha256_file(Path(path))
        except OSError:
            return {'status': 'missing', 'path': path, 'frozen_sha256': frozen, 'current_sha256': None, 'changed': True, 'source': 'live'}
        resolved_changed = False
        if 'snapshot' in record:
            try:
                resolved_changed = A.config_snapshot(Path(path), os.environ)['snapshot'] != record['snapshot']
            except (A.PreflightBlocker, OSError):
                resolved_changed = True
        changed = current != frozen or resolved_changed
        return {'status': 'changed' if changed else 'unchanged', 'path': path, 'frozen_sha256': frozen,
                'current_sha256': current, 'changed': changed, 'resolved_snapshot_changed': resolved_changed, 'source': 'live'}
    return {'status': 'unavailable', 'path': path, 'frozen_sha256': frozen, 'current_sha256': None, 'changed': None, 'source': 'live'}

def report_config_integrity(manifest):
    """Offline report: the installed-config verdict comes ONLY from the retained execution closeout.

    A report never re-reads the live installed config.  The original file may be edited or deleted
    long after the run finished, and that later edit must not rewrite measured history.  A config
    edited WHILE the arms were measured is still refused, because the closeout receipt captured at
    execution time already recorded the differing digest.  With no closeout receipt at all the
    configuration window is unverifiable, so acceptance can never be claimed.
    """
    frozen = manifest.get('native_config') or {}
    retained = manifest.get('config_integrity_final')
    if not isinstance(retained, dict) or not retained:
        return {'status': 'unrecorded', 'path': frozen.get('path'), 'frozen_sha256': frozen.get('raw_sha256'),
                'current_sha256': None, 'changed': None, 'verified': False, 'live_probe': False,
                'source': 'retained at execution closeout'}
    merged = dict(retained)
    merged.update({'source': 'retained at execution closeout', 'changed': bool(retained.get('changed')),
                   'verified': retained.get('status') == 'unchanged', 'live_probe': False})
    return merged

def machine_info(bins):
    pages = os.sysconf('SC_PHYS_PAGES') if hasattr(os, 'sysconf') else 0
    size = os.sysconf('SC_PAGE_SIZE') if hasattr(os, 'sysconf') else 0
    return {'label': None, 'platform': platform.platform(), 'system': platform.system(), 'machine': platform.machine(), 'macos': platform.mac_ver()[0] or None, 'python': platform.python_version(), 'physical_memory_bytes': int(pages) * int(size) if pages and size else None, 'cpu_count': os.cpu_count(), 'hardware': hardware.mac_hardware() if platform.system() == 'Darwin' else {'status': 'unavailable'}, 'git': tool_version('git'), 'codex': tool_version(bins.get('codex')), 'opencode': tool_version(bins.get('opencode'))}

def resolve_out(raw, *, fresh):
    path = Path(raw).expanduser().resolve()
    if path == REPO_ROOT or REPO_ROOT in path.parents:
        raise A.PreflightBlocker(f'output path must live OUTSIDE the repository: {path}')
    if fresh:
        if path.exists():
            raise A.PreflightBlocker(f'output path already exists; a run needs a fresh directory and never reuses one: {path}')
    elif not (path / 'manifest.json').exists():
        raise A.PreflightBlocker(f'{path} is not a prepared run (no manifest.json)')
    return path

def load_manifest(out):
    return json.loads((out / 'manifest.json').read_text(encoding='utf-8'))

def save_manifest(out, manifest):
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')

def fixture_of(manifest):
    """The fixture a manifest was prepared with; manifests from before the registry are the Python one."""
    try:
        return FX.get(manifest.get('fixture') or DEFAULT_FIXTURE)
    except KeyError as exc:
        raise A.PreflightBlocker(str(exc)) from exc

def fixture_hashes(fixture):
    return {name: A.sha256_file(fixture.dir / name) for name in fixture.files()}

def make_checkout(repo, fixture):
    repo.mkdir(parents=True)
    for name in fixture.files():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fixture.dir / name, repo / name)
    git(repo, 'init', '-q')
    exclude = repo / '.git' / 'info' / 'exclude'
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text(''.join(f'{pattern}\n' for pattern in ['__pycache__/', '*.pyc'] + fixture.excluded), encoding='utf-8')
    # The baseline commit is the runner's own: no user hook or signing setup may alter or block it.
    isolated = ('-c', 'user.name=benchmark', '-c', 'user.email=benchmark@local', '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false')
    git(repo, *isolated, 'add', '-A')
    git(repo, *isolated, 'commit', '-qm', 'frozen fixture baseline')
    return git(repo, 'rev-parse', 'HEAD')

def simulator_line(fixture, arm):
    simulator = fixture.simulator(arm)
    return f'\nSimulator for this run: {simulator} (use exactly: ./check.sh {simulator}).\n' if simulator else ''

def build_prompts(child_model=DEFAULT_CHILD_MODEL, effort=DEFAULT_EFFORT, fixture=None):
    """The frozen prompt must name the models this round actually launches, never a default."""
    fixture = fixture or FX.get(DEFAULT_FIXTURE)
    codex = fixture.task + CODEX_ADDENDUM.format(child_model=child_model, effort=effort) + simulator_line(fixture, 'codex')
    return {'codex': codex, 'opencode': fixture.task + OPENCODE_ADDENDUM + simulator_line(fixture, 'opencode'),
            'codex-app': codex.replace('CLIENT: Codex CLI baseline', 'CLIENT: Codex desktop App import')}

def frozen_fields(manifest):
    """Canonical cross-machine frozen contract: task, prompts, fixture, budget, cloud models.

    Per-machine state (checkout paths, binaries, local model, database/home locations, machine
    label, completed arms) is deliberately excluded, so an accidental edit to a frozen field is
    detectable while the intended per-Mac differences stay allowed.
    """
    models = manifest.get('models') or {}
    arms = manifest.get('arms') or {}
    fields = {'protocol': manifest.get('protocol'), 'task_sha256': A.sha256_bytes(str(manifest.get('task') or '').encode('utf-8')),
            'fixture_sha256': manifest.get('fixture_sha256'), 'frozen_files': manifest.get('frozen_files'),
            'allowed_changed': manifest.get('allowed_changed'), 'expected_tests': manifest.get('expected_tests'),
            'check': manifest.get('check'), 'budget': manifest.get('budget'), 'permission_policy': manifest.get('permission_policy'),
            'cloud_models': {key: models.get(key) for key in ('codex_cloud', 'codex_child', 'opencode_cloud', 'effort')},
            'prompts': {name: (record or {}).get('prompt_sha256') for (name, record) in sorted(arms.items())}}
    if manifest.get('fixture'):
        # Only manifests that name a fixture seal it, so earlier sealed manifests keep their digest.
        fields['fixture'] = manifest['fixture']
    return fields

def frozen_fields_sha256(manifest):
    return A.sha256_bytes(json.dumps(frozen_fields(manifest), sort_keys=True, separators=(',', ':')).encode('utf-8'))

def frozen_manifest_blockers(manifest):
    stored = manifest.get('frozen_fields_sha256')
    current = frozen_fields_sha256(manifest)
    if not stored:
        return ['the frozen contract of this run was never digest-bound; acceptance cannot be recomputed from an unsealed manifest']
    if stored != current:
        return [f'the frozen manifest contract changed after prepare (sealed {stored[:12]} != current {current[:12]}): an edited task, prompt, fixture, budget, cloud model or check is a different round, never a re-measurement']
    return []

def model_blockers(manifest):
    """An unmatched cloud model or an unverifiable effort is refused before anything launches or bills.

    Both arms must run the SAME bare cloud model (the Codex root model and the provider-stripped Hybrid
    coordinator model), and the Hybrid model string must pin the effort explicitly.  Only
    SUPPORTED_EFFORTS is verifiable here: native accounting reads the reasoning variant out of the
    recorded sessions and knows exactly one value, so a different effort could never be verified and is
    refused instead of being measured against the wrong expectation.
    """
    models = manifest.get('models') or {}
    effort = models.get('effort')
    blockers = []
    if effort not in SUPPORTED_EFFORTS:
        blockers.append(f'reasoning effort {effort!r} is not the supported {list(SUPPORTED_EFFORTS)} effort; native accounting '
                        f'verifies only {"/".join(SUPPORTED_EFFORTS)} routing (the clients would accept {list(CLIENT_EFFORTS)}), '
                        'so an unverifiable effort is refused before launch instead of being billed unverified')
    cloud = str(models.get('codex_cloud') or '')
    if not cloud or '/' in cloud:
        blockers.append(f'--codex-cloud-model {cloud!r} must be a bare cloud model id without a provider prefix; a local or routed id is never the cloud baseline')
    routed_model = str(models.get('opencode_cloud') or '')
    (provider, sep, rest) = routed_model.partition('/')
    (model, hash_sep, routed_effort) = rest.partition('#')
    if not sep or not provider or not model:
        blockers.append(f'--opencode-cloud-model {routed_model!r} must be provider/model or provider/model#effort; an unmatched cloud model is refused before launch')
    elif routed_effort and routed_effort != effort:
        blockers.append(f'--opencode-cloud-model {routed_model!r} pins effort {routed_effort!r} while the frozen effort is {effort!r}; a mismatched effort is refused before launch')
    elif not hash_sep or not routed_effort:
        blockers.append(f'--opencode-cloud-model {routed_model!r} names no explicit #effort; the Hybrid coordinator effort must be '
                        f'pinned in the model string and equal the frozen {effort!r} effort, never inferred from a default')
    elif cloud and model != cloud:
        blockers.append(f'the two arms must run the same cloud model: the Codex root is {cloud!r} while the Hybrid coordinator is '
                        f'{model!r}; one round measures one cloud model on both sides, so a cross-model round is refused pre-launch')
    elif provider == str(models.get('local') or '').split('/', 1)[0]:
        blockers.append(f'the Hybrid coordinator model {routed_model!r} resolves to the local provider {provider!r}; the cloud side of the ratio cannot be measured on the local worker')
    child = str(models.get('codex_child') or '')
    if not child:
        blockers.append('--child-model is required so the frozen prompt and the recorded routing name the same worker model')
    elif child == cloud:
        blockers.append(f'--child-model {child!r} equals the cloud root model; the frozen arm shape needs a distinct delegated worker model')
    return blockers

def budget_blockers(seconds):
    """A nonpositive frozen per-arm wall clock is refused before any checkout, launch or model call."""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds <= 0:
        return [f'--timeout {seconds!r} must be a positive number of seconds; a nonpositive frozen budget leaves a launched arm '
                'with no real deadline to be killed at, so the round is refused before preparation or launch']
    return []

def symlinked_components(path, root):
    """Symlinked path components at or below the run tree, checked lexically (nothing is followed)."""
    (target, base) = (os.path.abspath(str(path)), os.path.abspath(str(root)))
    if target != base and not target.startswith(base + os.sep):
        return [(target, 'outside the run output tree')]
    offenders = []
    current = base
    for part in ([] if target == base else os.path.relpath(target, base).split(os.sep)):
        current = os.path.join(current, part)
        if os.path.islink(current):
            offenders.append((current, os.readlink(current)))
    return offenders

DESKTOP_STEPS = "Codex desktop App import (manual, real App session — never labelled CLI):\n1. In the Codex App open the ALREADY PREPARED project folder listed below as its own project.\n   Do not copy any other arm's diff, log or verdict into it (no solution transfer).\n2. Select the cloud Sol model with medium reasoning; delegated workers must be Luna medium.\n3. Paste exactly the frozen prompt in prompts/codex-app.txt (same task bytes as the CLI arms)\n   and let the App session finish on its own.  The frozen budget is checked RETROSPECTIVELY from\n   the recorded session window; this tool cannot kill a desktop App session.\n4. Then run:  python3 benchmarks/run.py finish OUT --codex-thread <root thread id> --live\n   which imports the real root + descendant rollouts, verifies routing/digest/verdict/time, and\n   then launches the native OpenCode Hybrid arm on the identical fixture.\n"

def simctl(*args):
    """Run `xcrun simctl`; a failure is a preflight blocker, never a silent no-op."""
    proc = subprocess.run(['xcrun', 'simctl', *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise A.PreflightBlocker(f"xcrun simctl {' '.join(args)} failed: {(proc.stderr or proc.stdout).strip()[:300]}")
    return proc.stdout

def simulator_devices():
    devices = json.loads(simctl('list', 'devices', '-j') or '{}').get('devices') or {}
    return [dict(device, runtime=runtime) for (runtime, entries) in devices.items() for device in entries]

def newest_iphone():
    """The newest available iOS runtime and an iPhone device type it supports."""
    runtimes = [r for r in json.loads(simctl('list', 'runtimes', '-j')).get('runtimes', []) if r.get('platform') == 'iOS' and r.get('isAvailable')]
    if not runtimes:
        raise A.PreflightBlocker('no available iOS simulator runtime; install one in Xcode before running a simulator fixture')
    runtime = max(runtimes, key=lambda r: [int(part) for part in str(r.get('version', '0')).split('.') if part.isdigit()])
    phones = [d for d in runtime.get('supportedDeviceTypes') or [] if d.get('productFamily') == 'iPhone']
    if not phones:
        raise A.PreflightBlocker(f"iOS runtime {runtime.get('identifier')} supports no iPhone device type")
    return runtime['identifier'], phones[0]['identifier']

def simulator_create(name):
    """Create the run's own simulator; an existing device with the name is someone else's and is refused."""
    if any(device.get('name') == name for device in simulator_devices()):
        raise A.PreflightBlocker(f'a simulator named {name!r} already exists; it may belong to another run or to you, so it is never reused or deleted. Delete it yourself or finish that run first')
    (runtime, device_type) = newest_iphone()
    udid = simctl('create', name, device_type, runtime).strip()
    return {'name': name, 'udid': udid, 'runtime': runtime, 'device_type': device_type, 'created_utc': now()}

def simulator_delete(record):
    """Delete only the device whose UDID this run recorded and whose name still matches."""
    receipt = {'name': record.get('name'), 'udid': record.get('udid')}
    try:
        match = [d for d in simulator_devices() if d.get('udid') == record.get('udid')]
        if not match:
            return dict(receipt, status='already_absent')
        if match[0].get('name') != record.get('name'):
            return dict(receipt, status='blocked_name_mismatch', found=match[0].get('name'))
        if match[0].get('state') == 'Booted':
            simctl('shutdown', record['udid'])
        simctl('delete', record['udid'])
    except A.PreflightBlocker as exc:
        return dict(receipt, status='blocked_simctl_failed', blocker=str(exc))
    return dict(receipt, status='deleted')

def release_simulators(out, manifest):
    receipts = []
    retained = {}
    for arm, record in (manifest.get('simulators') or {}).items():
        receipt = simulator_delete(record)
        receipts.append(receipt)
        if receipt.get('status') not in ('deleted', 'already_absent'):
            retained[arm] = record
    manifest['simulators'] = retained
    if receipts:
        path = out / 'simulator-cleanup.json'
        try:
            earlier = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
        except (OSError, ValueError):
            earlier = []
        path.write_text(json.dumps(earlier + receipts, indent=2), encoding='utf-8')
    return receipts

def create_owned_simulator(out, manifest, arm, name):
    """Defer Ctrl-C until the new device's ownership is durable, including in native children."""
    if not hasattr(signal, 'pthread_sigmask'):
        raise A.PreflightBlocker('creating a run-owned simulator requires POSIX signal masking')
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT})
    try:
        record = simulator_create(name)
        manifest.setdefault('simulators', {})[arm] = record
        save_manifest(out, manifest)
        return record
    finally:
        # Restoring the caller's mask delivers a pending SIGINT only after the saved
        # UDID lets the caller's interruption handler delete exactly its own device.
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)

def start_arm_simulator(out, manifest, arm):
    """Create and boot the arm's simulator before its clock starts, so boot time is equal and untimed."""
    fixture = fixture_of(manifest)
    if not fixture.needs_simulator:
        return None
    record = create_owned_simulator(out, manifest, arm, fixture.simulator(arm))
    simctl('boot', record['udid'])
    simctl('bootstatus', record['udid'], '-b')
    record['booted_utc'] = now()
    save_manifest(out, manifest)
    return record

def baseline_blockers(fixture, baseline):
    expected = (fixture.expected_tests, fixture.expected_baseline_failures)
    seen = (baseline.get('tests_run'), (baseline.get('failures') or 0) + (baseline.get('errors') or 0))
    if seen != expected:
        return [f'the frozen baseline check reported {seen[0]} tests with {seen[1]} failures instead of the expected {expected[0]} tests with {expected[1]} failures; this Mac cannot reproduce the frozen starting point ({baseline.get("log")})']
    return []

def cmd_prepare(args):
    try:
        fixture = FX.get(args.fixture)
    except KeyError as exc:
        raise A.PreflightBlocker(str(exc)) from exc
    budget = fixture.default_budget if args.timeout is None else args.timeout
    for blocker in budget_blockers(budget):
        print(f'BLOCKER: {blocker}', file=sys.stderr)
        return 2
    out = resolve_out(args.out, fresh=True)
    for blocker in model_blockers({'models': {'codex_cloud': args.codex_cloud_model, 'codex_child': args.child_model, 'opencode_cloud': args.opencode_cloud_model, 'local': args.local_model, 'effort': args.effort}}):
        print(f'BLOCKER: {blocker}', file=sys.stderr)
        return 2
    bins = {'codex': args.codex_bin, 'opencode': args.opencode_bin}
    snapshot = A.config_snapshot(Path(args.opencode_config).expanduser(), os.environ)
    (profile_blockers, profile_observed) = A.validate_native_profile(snapshot, args.local_model)
    prompts = build_prompts(args.child_model, args.effort, fixture)
    (out / 'prompts').mkdir(parents=True)
    for (name, text) in prompts.items():
        (out / 'prompts' / f'{name}.txt').write_text(text, encoding='utf-8')
    (out / 'task.txt').write_text(fixture.task, encoding='utf-8')
    arms = {}
    for arm in ('codex', 'opencode'):
        repo = out / 'arms' / arm / 'repo'
        arms[arm] = {'repo': str(repo), 'base': make_checkout(repo, fixture), 'prompt_sha256': A.sha256_bytes(prompts[arm].encode()), 'task_sha256': A.sha256_bytes(fixture.task.encode())}
    machine = machine_info(bins)
    machine['label'] = args.label or platform.node()
    manifest = {'protocol': A.PROTOCOL, 'fixture': fixture.name, 'frozen_utc': now(), 'state': 'prepared', 'machine': machine, 'measurement_kind': 'cli', 'models': {'codex_cloud': args.codex_cloud_model, 'codex_child': args.child_model, 'opencode_cloud': args.opencode_cloud_model, 'local': args.local_model, 'effort': args.effort}, 'budget': {'wall_clock_seconds_per_arm': budget, 'initial': 1, 'repair': 1, 'max_workers': MAX_WORKERS}, 'check': {arm: fixture.check_argv(arm) for arm in ('codex', 'opencode')}, 'expected_tests': fixture.expected_tests, 'allowed_changed': fixture.allowed_changed, 'frozen_files': fixture.frozen_files, 'excluded': fixture.excluded, 'task': fixture.task, 'fixture_sha256': fixture_hashes(fixture), 'native_config': {'path': snapshot['path'], 'raw_sha256': snapshot['raw_sha256'], 'snapshot': snapshot['snapshot'], 'stats': snapshot['stats']}, 'native_profile': {'blockers': profile_blockers, 'observed': profile_observed}, 'binaries': {k: str(Path(v).expanduser()) if v else None for (k, v) in bins.items()}, 'codex_home': str(Path(args.codex_home).expanduser()) if args.codex_home else None, 'opencode_db': str(Path(args.opencode_db).expanduser()) if args.opencode_db else None, 'permission_policy': args.permission_policy, 'arms': arms, 'simulators': {}, 'completed_arms': [], 'owned_paths': [str(out / 'arms' / a / 'repo') for a in ('codex', 'opencode')], 'notes': ['CLI arms measure CLI clients only; a desktop App session is a separate client label imported by `finish`.', 'Token counts are raw model tokens, not quota or price; cross-Mac cache state is an unknown caveat.']}
    manifest['frozen_fields_sha256'] = frozen_fields_sha256(manifest)
    save_manifest(out, manifest)
    blockers = list(profile_blockers)
    interrupted = False
    try:
        for arm in ('codex', 'opencode'):
            if fixture.needs_simulator:
                create_owned_simulator(out, manifest, arm, fixture.simulator(arm))
            # The baseline proves the frozen starting point on this Mac and warms each arm's own build folder equally.
            baseline = run_check(Path(arms[arm]['repo']), out / 'arms' / arm, 'baseline', fixture.default_budget, manifest, arm)
            arms[arm]['baseline'] = {key: baseline.get(key) for key in ('tests_run', 'failures', 'errors', 'returncode', 'log', 'seconds')}
            blockers += baseline_blockers(fixture, baseline)
            if git(Path(arms[arm]['repo']), 'status', '--porcelain'):
                blockers.append(f'the {arm} checkout is not clean after the baseline check; the fixture writes outside its excluded build folder')
    except A.PreflightBlocker as exc:
        blockers.append(str(exc))
    except KeyboardInterrupt:
        interrupted = True
        blockers.append(f'preparation interrupted during the {arm} baseline; partial logs and both checkouts are retained')
        manifest['state'] = 'preparation_interrupted'
        manifest['preparation_interruption'] = {'utc': now(), 'arm': arm, 'exit_code': 130,
                                              'log': str(out / 'arms' / arm / 'baseline.check.log')}
        (out / 'preparation-interruption.json').write_text(json.dumps(manifest['preparation_interruption'], indent=2), encoding='utf-8')
    finally:
        manifest['preparation_blockers'] = [b for b in blockers if b not in profile_blockers]
        # Always release owned baseline devices, including when the check was interrupted.
        # Blocked deletions keep their ownership records and partial evidence stays in place.
        manifest['baseline_simulators'] = release_simulators(out, manifest)
        if manifest['simulators']:
            blockers.append('baseline simulator cleanup is blocked; recorded ownership is retained for recovery')
            manifest['preparation_blockers'].append(blockers[-1])
        save_manifest(out, manifest)
    (out / 'DESKTOP.md').write_text(DESKTOP_STEPS + '\nCodex fixture: ' + arms['codex']['repo'] + '\n', encoding='utf-8')
    print(json.dumps({'out': str(out), 'state': manifest['state'], 'fixture': fixture.name, 'models': manifest['models'], 'budget': manifest['budget'], 'arms': arms, 'profile_blockers': profile_blockers, 'preparation_blockers': manifest['preparation_blockers']}, indent=2))
    if interrupted:
        return 130
    if blockers:
        print('PREFLIGHT BLOCKERS (nothing launched): ' + '; '.join(blockers), file=sys.stderr)
        return 2
    return 0

def descendants(pid):
    proc = subprocess.run(['pgrep', '-P', str(pid)], capture_output=True, text=True, check=False)
    kids = [int(x) for x in proc.stdout.split()] if proc.returncode == 0 else []
    return kids + [kid for child in kids for kid in descendants(child)]

def signal_group(pgid, sig):
    """Signal the owned process group; False once the group no longer exists."""
    try:
        os.killpg(pgid, sig)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

def terminate_group(pgid, grace=5.0):
    """SIGTERM, then SIGKILL after a grace period, every process left in the owned group."""
    if not signal_group(pgid, signal.SIGTERM):
        return
    end = time.monotonic() + grace
    while time.monotonic() < end:
        if not signal_group(pgid, 0):
            return
        time.sleep(0.1)
    signal_group(pgid, signal.SIGKILL)
    for _ in range(50):
        if not signal_group(pgid, 0):
            return
        time.sleep(0.1)

def launch(argv, cwd, evidence, timeout, name, env=None):
    evidence.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ if env is None else env, PYTHONDONTWRITEBYTECODE='1')
    stdout_path = evidence / f'{name}.stdout.log'
    stderr_path = evidence / f'{name}.stderr.log'
    start = time.time()
    with stdout_path.open('w', encoding='utf-8') as out_log, stderr_path.open('w', encoding='utf-8') as err_log:
        proc = subprocess.Popen(argv, cwd=str(cwd), env=env, stdout=out_log, stderr=err_log, start_new_session=True)
        pgid = os.getpgid(proc.pid)
        timed_out = False
        interrupted = False
        children_before_kill = []
        lingering = False
        try:
            proc.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
            timed_out = isinstance(exc, subprocess.TimeoutExpired)
            interrupted = isinstance(exc, KeyboardInterrupt)
            children_before_kill = descendants(proc.pid)
            for kid in children_before_kill:
                try:
                    os.kill(kid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
            terminate_group(pgid)
            for kid in children_before_kill:
                try:
                    os.kill(kid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        else:
            # The client exited, but anything still in its own session group is the arm's work
            # continuing past its end: it could keep spending or edit the checkout after the check.
            lingering = signal_group(pgid, 0)
            if lingering:
                terminate_group(pgid)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        code = proc.returncode
    survivors = []
    for kid in children_before_kill:
        try:
            os.kill(kid, 0)
            survivors.append(kid)
        except (ProcessLookupError, PermissionError):
            pass
    group_alive = signal_group(pgid, 0)
    record = {'argv': argv, 'cwd': str(cwd), 'start_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(start)), 'seconds': round(time.time() - start, 3), 'exit_code': code, 'timed_out': timed_out, 'deadline_seconds': timeout, 'pgid': pgid, 'children_before_kill': children_before_kill, 'lingering_group_terminated': lingering, 'process_group_still_alive': group_alive, 'surviving_children': survivors, 'stdout_log': str(stdout_path), 'stderr_log': str(stderr_path), 'deadline_kind': 'deterministic external wait/kill of the owned process tree', 'attempts': 1, 'outer_retry': False}
    if interrupted:
        record['interrupted'] = True
    (evidence / f'{name}.execution.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    if interrupted:
        raise KeyboardInterrupt()
    return record

parse_check = FX.parse_unittest

def check_argv(manifest, arm):
    """The frozen check for an arm; manifests from before the registry froze one shared argv."""
    check = manifest.get('check')
    return list(check.get(arm) or []) if isinstance(check, dict) else list(check or [])

def run_check(repo, evidence, name, timeout, manifest, arm):
    argv = check_argv(manifest, arm)
    log_path = evidence / f'{name}.check.log'
    if timeout <= 0:
        return {'tests_run': 0, 'failures': 0, 'errors': 0, 'all_tests_expected': False, 'ok': False, 'exit_code_zero': False, 'returncode': None, 'log': None, 'command': argv, 'skipped': 'arm deadline already expired; the independent check never started'}
    evidence.mkdir(parents=True, exist_ok=True)
    code = None
    started = time.monotonic()
    with log_path.open('w', encoding='utf-8') as log:
        try:
            proc = subprocess.Popen(argv, cwd=str(repo), stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                log.write(f'\ndeadline expired during the independent check: {exc}\n')
                code = -1
            finally:
                # A check script may spawn compilers or test runners. Stop its whole owned
                # group before parsing results or allowing the checkout to be archived.
                if signal_group(proc.pid, 0):
                    terminate_group(proc.pid)
                proc.wait()
        except OSError as exc:
            log.write(f'could not start the independent check: {exc}\n')
            code = 127
    result = fixture_of(manifest).parse_check(log_path.read_text(encoding='utf-8', errors='replace'), manifest.get('expected_tests'))
    result.update({'returncode': code, 'log': str(log_path), 'captured_outside_repo': not str(log_path).startswith(str(repo)), 'command': argv, 'seconds': round(time.monotonic() - started, 3)})
    result['exit_code_zero'] = code == 0
    result['ok'] = bool(result['ok'] and result['exit_code_zero'])
    return result

def scope_and_digest(repo, manifest, arm):
    changed = sorted((x for x in git(repo, 'diff', '--name-only', 'HEAD').split() if x))
    untracked = sorted((x for x in git(repo, 'ls-files', '--others', '--exclude-standard').split() if x))
    diff = subprocess.run(['git', '-C', str(repo), 'diff', '--binary', 'HEAD'], capture_output=True, check=False).stdout
    frozen_files = list(manifest.get('frozen_files') or [])
    frozen_ok = {name: A.sha256_file(repo / name) == manifest['fixture_sha256'].get(name) for name in frozen_files if (repo / name).exists()}
    frozen_intact = bool(frozen_files) and len(frozen_ok) == len(frozen_files) and all(frozen_ok.values())
    base = (manifest.get('arms', {}).get(arm) or {}).get('base')
    try:
        head = git(repo, 'rev-parse', 'HEAD')
    except A.PreflightBlocker:
        head = None
    base_intact = bool(base) and head == base
    scope_ok = not untracked and bool(changed) and (set(changed) <= set(manifest['allowed_changed'])) and frozen_intact and base_intact
    return {'changed': changed, 'untracked': untracked, 'digest': A.sha256_bytes(diff), 'diff_bytes': len(diff), 'frozen_files_intact': frozen_ok, 'frozen_intact': frozen_intact, 'frozen_base_commit': base, 'head_commit': head, 'base_intact': base_intact, 'scope_ok': scope_ok}

def assistant_texts_from_records(records, agent):
    texts = []
    for record in records:
        if (record['session'].get('agent') or '') != agent:
            continue
        for message in record['messages']:
            if message.get('type') != 'assistant':
                continue
            try:
                data = json.loads(message.get('data') or '{}')
            except ValueError:
                continue
            content = data.get('content')
            if isinstance(content, list):
                texts += [p.get('text', '') for p in content if isinstance(p, dict) and p.get('type') in ('text', 'output_text')]
            elif isinstance(data.get('text'), str):
                texts.append(data['text'])
    return '\n'.join((t for t in texts if t))

def codex_argv(manifest, repo, prompt):
    models = manifest['models']
    effort = models['effort']
    return [manifest['binaries']['codex'], 'exec', '--json', '-C', str(repo), '--model', models['codex_cloud'], '-c', f'model_reasoning_effort="{effort}"', '-c', 'agents.enabled=true', '-c', f'''agents.default_subagent_model="{models['codex_child']}"''', '-c', f'agents.default_subagent_reasoning_effort="{effort}"', '-c', f'agents.max_concurrent_threads_per_session={MAX_WORKERS}', '--sandbox', 'danger-full-access', '-c', 'approval_policy="never"', prompt]

def opencode_argv(manifest, prompt):
    return [manifest['binaries']['opencode'], 'run', '--standalone', '--format', 'json', '--agent', 'hybrid', '--model', manifest['models']['opencode_cloud'], prompt]

def root_thread_from_log(path):
    """The root is the FIRST thread.started event; later events may name worker threads."""
    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get('type') == 'thread.started' and event.get('thread_id'):
            return event['thread_id']
    return None

def session_ids_from_log(path):
    ids = []
    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            sid = event.get('sessionID') or event.get('session_id')
            if sid and sid not in ids:
                ids.append(sid)
    return ids

def archive_rollouts(catalog, ids, evidence):
    target = evidence / 'rollouts'
    target.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for sid in ids:
        record = catalog.get(sid) or {}
        paths = list(dict.fromkeys([record.get('path')] + list(record.get('rollout_paths') or [])))
        for index, raw in enumerate(path for path in paths if path):
            source = Path(raw)
            if not source.exists():
                continue
            name = f'{sid}.jsonl' if index == 0 else f'{sid}-duplicate-{index}.jsonl'
            dest = target / name
            shutil.copy2(source, dest)
            hashes[name] = A.sha256_file(dest)
    (evidence / 'rollouts-sha256.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    return {'archived': sorted(hashes), 'sha256': hashes, 'dir': str(target)}

def codex_expectations(manifest):
    models = manifest['models']
    budget = manifest['budget']
    return {'expected_root_model': models['codex_cloud'], 'expected_child_model': models['codex_child'], 'expected_effort': models['effort'], 'max_worker_turns': budget['initial'] + budget['repair'], 'max_workers': budget.get('max_workers', 1)}

def window_seconds(window):
    try:
        first = datetime.datetime.fromisoformat(window['first_event'].replace('Z', '+00:00'))
        last = datetime.datetime.fromisoformat(window['last_event'].replace('Z', '+00:00'))
        if first.utcoffset() is None or last.utcoffset() is None:
            return None
        seconds = (last - first).total_seconds()
        return round(seconds, 1) if seconds >= 0 else None
    except (AttributeError, KeyError, TypeError, ValueError):
        return None

def account_codex_evidence(manifest, evidence, root_id, client, codex_home):
    archived = evidence / 'rollouts'
    if archived.is_dir() and any(archived.glob('*.jsonl')):
        (catalog, source) = (A.scan_codex_rollouts(archived), str(archived))
    else:
        home = Path(codex_home) / 'sessions' if codex_home else None
        if home and home.is_dir() and any(home.glob('**/*.jsonl')):
            (catalog, source) = (A.scan_codex_rollouts(home), str(home))
        elif codex_home:
            (catalog, source) = (A.scan_codex_rollouts(Path(codex_home) / 'sessions'), str(Path(codex_home) / 'sessions'))
        else:
            raise A.PreflightBlocker('no archived Codex rollouts and no CODEX_HOME to read')
    ids = A.codex_tree(catalog, root_id)
    return (A.account_codex(catalog, ids, root_thread_id=root_id, client=client, **codex_expectations(manifest)), [source])

# Every artifact an offline acceptance decision is read from, sealed at execution time.  result.json
# carries the arm's own claims (check tests/returncode, duration, scope), the check and execution
# logs/receipts are the captured proof behind those claims, and the patch, rollouts and native records
# are the measured work itself.  attempts.json stays unsealed on purpose: it is an append-only failure
# ledger that later attempts legitimately extend.
SEALED_EVIDENCE = ('result.json', 'accounting.json', 'complete.patch', 'native-records.json',
                   'arm.stdout.log', 'arm.stderr.log', 'arm.execution.json', 'final.check.log')

def seal_arm_evidence(evidence):
    """Digest every retained artifact at execution time so an offline report can verify it.

    Sealing the captured logs and the recorded result as well as the patch, rollouts and native records
    means a later edit to a saved returncode, test count, duration or scope cannot keep an arm accepted.
    """
    entries = {}
    for name in SEALED_EVIDENCE:
        if (evidence / name).exists():
            entries[name] = A.sha256_file(evidence / name)
    rollouts = evidence / 'rollouts-sha256.json'
    if rollouts.exists():
        try:
            recorded = json.loads(rollouts.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            recorded = {}
        for name in sorted(recorded):
            entries[f'rollouts/{name}'] = recorded[name]
    (evidence / 'evidence-sha256.json').write_text(json.dumps({'sealed_utc': now(), 'files': entries}, indent=2), encoding='utf-8')
    return entries

def verify_retained_evidence(evidence):
    """Tampered or missing archived evidence blocks acceptance; it never falls back silently."""
    problems = []
    entries = {}
    seal_path = evidence / 'evidence-sha256.json'
    if seal_path.exists():
        try:
            entries = (json.loads(seal_path.read_text(encoding='utf-8')) or {}).get('files') or {}
        except (OSError, ValueError):
            problems.append('the retained evidence seal is unreadable, so nothing can be re-verified offline')
    else:
        problems.append('the retained evidence was never sealed during execution, so nothing can be re-verified offline')
    required = {'result.json', 'accounting.json', 'complete.patch', 'final.check.log'}
    required.update(name for name in SEALED_EVIDENCE if (evidence / name).exists())
    required.update('rollouts/' + path.name for path in (evidence / 'rollouts').glob('*.jsonl'))
    for name in sorted(required - set(entries)):
        problems.append(f'retained evidence {name} has no execution-time sealed digest')
    for (name, expected) in sorted(entries.items()):
        path = evidence / name
        if not path.exists():
            problems.append(f'retained evidence {name} is missing from the archive')
        else:
            actual = A.sha256_file(path)
            if actual != expected:
                problems.append(f'retained evidence {name} no longer hashes to its sealed digest (sealed {expected[:12]}, now {actual[:12]}): the archive was edited after the run')
    patch_path = evidence / 'complete.patch'
    if not patch_path.exists():
        problems.append('the archived complete.patch is missing, so the reviewed digest cannot be recomputed')
    return {'verified': not problems, 'problems': problems, 'sealed_files': len(entries),
            'patch_sha256': A.sha256_file(patch_path) if patch_path.exists() else None}

def unknown_cost_accounting(reason):
    """A failed arm still owes its spend: usage is unknown, never zero."""
    return {'cost_state': 'unknown', 'attempted': True, 'routing_ok': False, 'usage_complete': False,
            'blockers': [reason], 'cloud_total': None, 'known_lower_bound': None, 'local_total': None,
            'unknown_maintenance_total': None, 'cloud_cost_range': {'status': 'unknown', 'lower_bound': None, 'upper_bound': None},
            'sessions': [], 'local_dispatches': 0, 'root_final_text': '', 'root_final_text_source': None}

def record_arm_failure(out, manifest, arm, client, blockers, execution=None, stage='arm', accounting=None):
    """Persist a failed arm as result.json plus a durable attempt record; failed spend is never dropped."""
    evidence = out / 'arms' / arm
    evidence.mkdir(parents=True, exist_ok=True)
    reason = '; '.join(blockers) or f'the {arm} arm failed during {stage}'
    if not (evidence / 'complete.patch').exists():
        repo = Path((manifest.get('arms', {}).get(arm) or {}).get('repo') or '')
        diff = subprocess.run(['git', '-C', str(repo), 'diff', '--binary', 'HEAD'], capture_output=True, check=False).stdout if repo.is_dir() else b''
        if diff:
            (evidence / 'complete.patch').write_bytes(diff)
    record = {'arm': arm, 'client': client, 'protocol': A.PROTOCOL, 'accepted': False, 'attempted': True,
              'stage': stage, 'blockers': list(blockers), 'gates': {}, 'check': {'skipped': f'{stage} failed before the independent check', 'ok': False, 'all_tests_expected': False, 'tests_run': 0, 'failures': 0, 'errors': 0, 'returncode': None},
              'scope': {'scope_ok': False, 'frozen_intact': False, 'base_intact': False, 'untracked': [], 'changed': [], 'digest': ''},
              'verdict': {'status': 'missing', 'digest_matches': False}, 'verdict_source': {'kind': client, 'authoritative': False},
              'execution': execution or {'argv': None, 'exit_code': None, 'timed_out': False, 'seconds': None, 'total_seconds': None},
              'accounting': accounting or unknown_cost_accounting(reason), 'frozen_utc': manifest.get('frozen_utc'),
              'models': manifest.get('models'), 'budget': manifest.get('budget'), 'machine': manifest.get('machine'),
              'cost_state': 'unknown', 'failure_stage': stage,
              'honesty': ['a failed arm keeps its attempted marker and unknown cost; unknown is never zero']}
    (evidence / 'result.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    record_attempt(out, arm, stage, blockers)
    seal_arm_evidence(evidence)
    return record

def record_attempt(out, arm, stage, blockers):
    path = out / 'arms' / arm / 'attempts.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        attempts = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    except (OSError, ValueError):
        attempts = []
    attempts.append({'utc': now(), 'stage': stage, 'attempted': True, 'cost_state': 'unknown', 'blockers': list(blockers)})
    path.write_text(json.dumps(attempts, indent=2), encoding='utf-8')
    return attempts

def evaluate_arm(arm, client, manifest, accounting, check, scope, verdict, execution, verdict_source, *, extra_gates=None, extra_blockers=None):
    launch_blockers = permission_blockers(execution.get('argv') or [])
    budget_seconds = (manifest.get('budget') or {}).get('wall_clock_seconds_per_arm')
    elapsed = execution.get('total_seconds', execution.get('seconds'))
    within_total_budget = bool(elapsed is not None and budget_seconds is not None and elapsed <= budget_seconds and not execution.get('timed_out'))
    gates = {'tests_all_and_pass': check['ok'] and check['all_tests_expected'], 'check_exit_clean': check.get('returncode') == 0, 'scope_only_allowed_paths': scope['scope_ok'], 'frozen_test_and_readme_intact': scope['frozen_intact'], 'frozen_base_commit_intact': scope['base_intact'], 'no_untracked_source': not scope['untracked'], 'semantic_verdict_pass': verdict['status'] == 'pass', 'verdict_bound_to_current_digest': verdict['digest_matches'], 'verdict_from_authoritative_reviewer': bool(verdict_source.get('authoritative')), 'routing_expected': accounting['routing_ok'], 'usage_complete': accounting['usage_complete'], 'within_deadline': not execution.get('timed_out'), 'within_total_budget': within_total_budget, 'clean_exit': execution.get('exit_code') == 0, 'native_permissions_not_bypassed': not launch_blockers}
    gates.update(extra_gates or {})
    blockers = list(accounting['blockers'])
    if not gates['native_permissions_not_bypassed']:
        blockers.extend(launch_blockers)
    if not gates['frozen_base_commit_intact']:
        blockers.append(f"the measured checkout is at HEAD {scope.get('head_commit')!r} instead of the frozen fixture base {scope.get('frozen_base_commit')!r}; the diff under review is not the frozen task")
    if not gates['routing_expected']:
        blockers.append('recorded routing is not the frozen root/child model and effort')
    if not gates['usage_complete']:
        blockers.append('usage is incomplete; the retained total is a lower bound, not a completion')
    if not gates['verdict_from_authoritative_reviewer']:
        blockers.append('the verdict did not come from the authoritative reviewer channel')
    if not (gates['frozen_test_and_readme_intact'] and gates['no_untracked_source']):
        blockers.append('frozen fixture files changed or untracked source appeared')
    if not gates['tests_all_and_pass']:
        if check.get('skipped'):
            blockers.append(f"the independent check never ran: {check['skipped']}; unverified tests never accept an arm")
        else:
            blockers.append(f"check reported {check['tests_run']} tests, {check['failures']} failures, {check['errors']} errors with exit {check.get('returncode')} (expected {manifest['expected_tests']} tests, 0 failures, exit 0)")
    if not gates['check_exit_clean']:
        blockers.append(f"the independent check process exited {check.get('returncode')}; a check that does not exit 0 (including a killed or unstartable check) never accepts")
    if not gates['within_total_budget']:
        label = 'desktop App session window plus final verification' if execution.get('deadline_enforced') is False else 'arm wall clock including the final check, accounting, scope and verdict work'
        if elapsed is None:
            blockers.append(f'the total arm elapsed time is unknown, so it can never be shown to fit the frozen {budget_seconds}s budget; an unknown duration is never an accepted arm')
        elif budget_seconds is None:
            blockers.append('the frozen per-arm wall clock budget is missing from the manifest; nothing can be shown to be within budget')
        elif execution.get('timed_out'):
            blockers.append(f'the arm exceeded the frozen {budget_seconds}s budget before finishing')
        else:
            blockers.append(f'the arm used {elapsed}s of the frozen {budget_seconds}s budget ({label}); going over the frozen budget is never accepted, however the individual steps behaved')
    if not gates['scope_only_allowed_paths']:
        blockers.append(f"scope drift: changed={scope['changed']} untracked={scope['untracked']}")
    if execution.get('timed_out'):
        blockers.append(f"arm exceeded the {execution.get('deadline_seconds')} s deterministic deadline; retained partial usage is a lower bound")
    if not gates['clean_exit']:
        blockers.append(f"the client exited {execution.get('exit_code')}; a nonzero exit is never an accepted arm")
    if verdict['status'] == 'forged':
        blockers.append('only quoted/fenced VERDICT text was found; a real verdict is missing')
    elif verdict['status'] != 'pass':
        blockers.append(f"no substantive semantic PASS verdict ({verdict['status']}); passing tests alone never accept")
    elif not verdict['digest_matches']:
        blockers.append('verdict digest does not equal the current complete-diff digest')
    blockers.extend(extra_blockers or [])
    return {'arm': arm, 'client': client, 'protocol': A.PROTOCOL, 'gates': gates, 'accepted': bool(all(gates.values()) and not blockers), 'blockers': blockers, 'check': check, 'scope': scope, 'verdict': verdict, 'verdict_source': verdict_source, 'execution': execution, 'accounting': accounting, 'frozen_utc': manifest['frozen_utc'], 'models': manifest['models'], 'budget': manifest['budget'], 'machine': manifest['machine'], 'task_sha256': A.sha256_bytes(manifest['task'].encode()), 'fixture_sha256': manifest['fixture_sha256'], 'honesty': ['CLI exit code 0 does not prove acceptance', 'raw model tokens are not quota or price']}

def run_codex_arm(out, manifest, client='codex-cli', root_id=None):
    arm = 'codex'
    repo = Path(manifest['arms'][arm]['repo'])
    evidence = out / 'arms' / arm
    budget = manifest['budget']['wall_clock_seconds_per_arm']
    arm_start = time.monotonic()
    deadline = arm_start + budget
    env = dict(os.environ)
    if manifest.get('codex_home'):
        env['CODEX_HOME'] = manifest['codex_home']
    execution = None
    try:
        if root_id is None:
            prompt = (out / 'prompts' / 'codex.txt').read_text(encoding='utf-8')
            execution = launch(codex_argv(manifest, repo, prompt), repo, evidence, max(deadline - time.monotonic(), 1.0), 'arm', env=env)
            execution['frozen_budget_seconds'] = budget
            root_id = root_thread_from_log(Path(execution['stdout_log']))
            if not root_id:
                return record_arm_failure(out, manifest, arm, client, ['no thread.started root thread id in the Codex CLI output: the session whose usage would be measured is unknown, so the spend is unknown and can never be accepted'], execution, stage='launch')
        else:
            execution = {'argv': None, 'exit_code': 0, 'timed_out': False, 'seconds': None, 'client_imported': True, 'deadline_kind': 'retrospective: a desktop App session is not killable by this tool'}
        catalog = A.scan_codex_rollouts(Path(manifest['codex_home']) / 'sessions')
        if root_id not in catalog:
            return record_arm_failure(out, manifest, arm, client, [f"no rollout for root thread {root_id} under {manifest['codex_home']}/sessions"], execution, stage='evidence')
        if client == 'codex-app':
            recorded_cwd = (catalog[root_id].get('cwd') or '')
            if Path(recorded_cwd).resolve() != repo.resolve():
                return record_arm_failure(out, manifest, arm, client, [f'Codex App root cwd {recorded_cwd!r} is not the prepared fixture {repo}; refusing (wrong project / solution transfer)'], execution, stage='evidence')
        evidence.mkdir(parents=True, exist_ok=True)
        archived = archive_rollouts(catalog, A.codex_tree(catalog, root_id), evidence)
        (accounting, sources) = account_codex_evidence(manifest, evidence, root_id, client, Path(manifest['codex_home']) if manifest.get('codex_home') else None)
        check = run_check(repo, evidence, 'final', max(int(deadline - time.monotonic()), 0), manifest, arm)
        scope = scope_and_digest(repo, manifest, arm)
        (evidence / 'complete.patch').write_bytes(subprocess.run(['git', '-C', str(repo), 'diff', '--binary', 'HEAD'], capture_output=True, check=False).stdout)
        verdict = A.semantic_verdict(accounting['root_final_text'], scope['digest'])
        final_seconds = round(time.monotonic() - arm_start, 3)
        execution['final_verification_seconds'] = final_seconds
        if execution.get('client_imported'):
            recorded = window_seconds(accounting.get('recorded_window') or {})
            execution['seconds'] = recorded
            execution['recorded_window'] = accounting.get('recorded_window')
            execution['deadline_enforced'] = False
            execution['total_seconds'] = None if recorded is None else round(recorded + final_seconds, 3)
        else:
            execution['deadline_enforced'] = True
            execution['total_seconds'] = final_seconds
        result = evaluate_arm(arm, client, manifest, accounting, check, scope, verdict, execution, {'kind': client, 'source': accounting['root_final_text_source'], 'authoritative': True})
        result['rollouts'] = archived
        result['accounting_sources'] = sources
        (evidence / 'accounting.json').write_text(json.dumps(accounting, indent=2), encoding='utf-8')
        (evidence / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        seal_arm_evidence(evidence)
        return result
    except Exception as exc:
        return record_arm_failure(out, manifest, arm, client, [f'the Codex arm failed during {type(exc).__name__}: {exc}; the attempt is retained with unknown cost'], execution, stage='crash')

def opencode_expectations(manifest):
    models = manifest['models']
    cloud = models['opencode_cloud'].split('/', 1)
    return {'expected_cloud_provider': cloud[0], 'expected_cloud_model': cloud[1].split('#')[0], 'expected_local_provider': models['local'].split('/', 1)[0], 'expected_local_model': models['local']}

def finish_opencode_arm(out, manifest, execution, snapshot, root_ids, client='opencode-cli', remaining=120, arm_start=None):
    arm = 'opencode'
    repo = Path(manifest['arms'][arm]['repo'])
    evidence = out / 'arms' / arm
    budget = manifest['budget']
    accounting = A.account_opencode(snapshot, root_session_ids=root_ids, max_local_dispatches=budget['initial'] + budget['repair'], max_workers=budget.get('max_workers', 1), client=client, **opencode_expectations(manifest))
    check = run_check(repo, evidence, 'final', remaining, manifest, arm)
    scope = scope_and_digest(repo, manifest, arm)
    (evidence / 'complete.patch').write_bytes(subprocess.run(['git', '-C', str(repo), 'diff', '--binary', 'HEAD'], capture_output=True, check=False).stdout)
    review_text = assistant_texts_from_records(snapshot['records'], 'review')
    verdict = A.semantic_verdict(review_text, scope['digest'])
    final_seconds = round(time.monotonic() - arm_start, 3) if arm_start else None
    execution['final_verification_seconds'] = final_seconds
    execution['deadline_enforced'] = True
    execution['total_seconds'] = final_seconds if final_seconds is not None else execution.get('seconds')
    result = evaluate_arm(arm, client, manifest, accounting, check, scope, verdict, execution, {'kind': 'native review subagent on the inherited cloud caller model', 'source': 'review agent assistant messages', 'authoritative': bool(accounting['review_sessions'])})
    (evidence / 'accounting.json').write_text(json.dumps(accounting, indent=2), encoding='utf-8')
    (evidence / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    seal_arm_evidence(evidence)
    return result

def run_opencode_arm(out, manifest):
    arm = 'opencode'
    repo = Path(manifest['arms'][arm]['repo'])
    evidence = out / 'arms' / arm
    prompt = (out / 'prompts' / 'opencode.txt').read_text(encoding='utf-8')
    arm_start = time.monotonic()
    deadline = arm_start + manifest['budget']['wall_clock_seconds_per_arm']
    execution = None
    try:
        execution = launch(opencode_argv(manifest, prompt), repo, evidence, max(deadline - time.monotonic(), 1.0), 'arm', env=dict(os.environ, PWD=str(repo)))
        execution['frozen_budget_seconds'] = manifest['budget']['wall_clock_seconds_per_arm']
        root_ids = session_ids_from_log(Path(execution['stdout_log']))
        snapshot = A.snapshot_opencode(Path(manifest['opencode_db']), [str(repo)], root_ids)
        (evidence / 'native-records.json').write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
    except Exception as exc:
        return record_arm_failure(out, manifest, arm, 'opencode-cli', [f'the Hybrid arm produced no readable native session evidence: {type(exc).__name__}: {exc}; its spend stays unknown and is still retained'], execution, stage='evidence')
    return finish_opencode_arm(out, manifest, execution, snapshot, root_ids, remaining=max(int(deadline - time.monotonic()), 0), arm_start=arm_start)

def compat_key(manifest):
    models = manifest['models']
    return {'protocol': manifest['protocol'], 'fixture': manifest.get('fixture') or DEFAULT_FIXTURE, 'task_sha256': A.sha256_bytes(manifest['task'].encode()), 'prompt_sha256': {name: arm.get('prompt_sha256') for (name, arm) in manifest['arms'].items()}, 'fixture_sha256': manifest['fixture_sha256'], 'models': {key: models[key] for key in ('codex_cloud', 'codex_child', 'opencode_cloud', 'effort')}, 'budget': manifest['budget'], 'check': manifest['check'], 'allowed_changed': manifest['allowed_changed'], 'expected_tests': manifest['expected_tests'], 'measurement_kind': manifest.get('measurement_kind')}

def compare_runs(outs):
    manifests = {str(out): load_manifest(out) for out in outs}
    keys = {label: compat_key(manifest) for (label, manifest) in manifests.items()}
    base = str(outs[0])
    blockers = []
    for label in list(manifests)[1:]:
        for field in keys[base]:
            if keys[base][field] != keys[label][field]:
                blockers.append(f'{label} differs from {base} in frozen field {field!r}: incomparable round')
    differences = {'local_models': {label: m['models']['local'] for (label, m) in manifests.items()}, 'hardware': {label: {k: m['machine'].get(k) for k in ('label', 'machine', 'macos', 'physical_memory_bytes', 'cpu_count', 'hardware')} for (label, m) in manifests.items()}, 'measurement_kind': {label: m['measurement_kind'] for (label, m) in manifests.items()}}
    return (blockers, differences)

def ratio_block(arms, threshold=None):
    threshold = TARGETS['cloud_vs_codex'] if threshold is None else threshold
    (codex, hybrid) = (arms.get('codex'), arms.get('opencode'))
    if not codex or not hybrid:
        return {'status': 'undefined', 'reason': 'both arms must be present', 'threshold': threshold}
    comparable = bool(codex.get('accepted')) and bool(hybrid.get('accepted')) and (codex.get('protocol') == hybrid.get('protocol') == A.PROTOCOL) and codex.get('accounting', {}).get('routing_ok') and hybrid.get('accounting', {}).get('routing_ok') and codex.get('accounting', {}).get('usage_complete') and hybrid.get('accounting', {}).get('usage_complete')
    if not comparable:
        return {'status': 'undefined', 'threshold': threshold, 'reason': 'defined only when both arms are accepted with complete routing and usage on compatible protocol'}

    def bounds(arm):
        acc = arm.get('accounting') or {}
        rng = acc.get('cloud_cost_range') or {}
        lower = rng.get('lower_bound', acc.get('known_lower_bound'))
        upper = rng.get('upper_bound', lower)
        if acc.get('usage_complete') is False or lower is None:
            return (None, None)
        return (float(lower), float(max(upper or lower, lower)))
    (codex_low, codex_high) = bounds(codex)
    (hybrid_low, hybrid_high) = bounds(hybrid)
    if not codex_high:
        return {'status': 'undefined', 'threshold': threshold, 'reason': 'Codex cloud total is unknown'}
    if hybrid_low is None:
        return {'status': 'undefined', 'threshold': threshold, 'reason': 'Hybrid cloud total has unattributable usage'}
    (low, high) = (hybrid_low / codex_high, hybrid_high / codex_low if codex_low else float('inf'))
    status = 'measured' if low == high else 'target_met' if high <= threshold else 'not_met' if low > threshold else 'indeterminate'
    return {'status': status, 'threshold': threshold, 'lower_bound': low, 'upper_bound': high, 'hybrid_cloud_over_codex_cloud': low if low == high else None, 'target_met': True if high <= threshold else False if low > threshold else None, 'note': 'exact only when both arms are gap-free; otherwise rigorous bounds decide and unknown maintenance can never fake a pass'}

TARGETS = {'cloud_vs_codex': 0.5, 'share': 0.35, 'stretch_share': 0.20}

def seat_metrics(arms):
    """Tokens by seat for both arms, Hybrid's cloud share, Hybrid cloud against the whole Codex cloud, and targets.

    Codex cloud is its Sol planner plus its Luna workers; Hybrid cloud is its Sol planner and reviewer. Every
    figure is withheld (None) when the evidence behind it is incomplete or failed verification.
    """
    seats, usable = {}, {}
    for (arm, result) in arms.items():
        accounting = result.get('accounting') or {}
        verified = (result.get('evidence') or {}).get('verified', True)
        seats[arm] = accounting.get('seats') if verified else None
        usable[arm] = bool(seats[arm]) and bool(accounting.get('usage_complete')) and not (seats[arm].get('unknown') or {}).get('total')
    hybrid, codex = seats.get('opencode'), seats.get('codex')
    share = {'value': None, 'exact': False, 'lower_bound': None, 'upper_bound': None,
             'value_basis': 'attributed requests only; unknown maintenance excluded'}
    if hybrid and usable.get('opencode'):
        total = hybrid['planner']['total'] + hybrid['worker']['total']
        maintenance = (arms['opencode'].get('accounting') or {}).get('unknown_maintenance_total')
        share.update({'value': hybrid['planner']['total'] / total if total else None, 'exact': maintenance == 0})
        if isinstance(maintenance, (int, float)) and maintenance >= 0 and total + maintenance > 0:
            share.update({'lower_bound': hybrid['planner']['total'] / (total + maintenance),
                          'upper_bound': (hybrid['planner']['total'] + maintenance) / (total + maintenance)})
    both_accepted = all(bool((arms.get(arm) or {}).get('accepted')) for arm in ('codex', 'opencode'))
    ratio = {'value': None, 'hybrid_cloud': None, 'codex_cloud': None, 'lower_bound': None, 'upper_bound': None,
             'value_basis': 'attributed requests only; unknown maintenance excluded'}
    if hybrid and codex and usable.get('opencode') and usable.get('codex'):
        codex_cloud = codex['planner']['total'] + codex['worker']['total']
        ratio.update({'value': hybrid['planner']['total'] / codex_cloud if codex_cloud else None,
                      'hybrid_cloud': hybrid['planner']['total'], 'codex_cloud': codex_cloud})
        maintenance = (arms['opencode'].get('accounting') or {}).get('unknown_maintenance_total')
        if codex_cloud and isinstance(maintenance, (int, float)) and maintenance >= 0:
            ratio.update({'lower_bound': hybrid['planner']['total'] / codex_cloud,
                          'upper_bound': (hybrid['planner']['total'] + maintenance) / codex_cloud})
    targets = {'both_arms_accepted': both_accepted,
               'hybrid_cloud_at_most_half_of_codex': bool(both_accepted and ratio['upper_bound'] is not None and ratio['upper_bound'] <= TARGETS['cloud_vs_codex']),
               'hybrid_cloud_share_at_most_0.35': bool(both_accepted and share['upper_bound'] is not None and share['upper_bound'] <= TARGETS['share']),
               'stretch_cloud_share_at_most_0.20': bool(both_accepted and share['upper_bound'] is not None and share['upper_bound'] <= TARGETS['stretch_share'])}
    return {'seats': seats, 'hybrid_cloud_share': share, 'cloud_vs_codex': ratio, 'targets': targets,
            'note': 'targets require both arms accepted and the entire uncertainty interval within threshold; value is an attributed-only estimate; figures are withheld while usage is incomplete or unattributed'}

def archive_and_cleanup(out, manifest, arm):
    repo = Path(manifest['arms'][arm]['repo'])
    if not repo.exists():
        return {'arm': arm, 'status': 'already_removed'}
    report = {'arm': arm, 'repo': str(repo), 'checkout_preserved': True}
    links = ([] if not os.path.islink(str(out)) else [(str(out), os.readlink(str(out)))]) + [entry for entry in symlinked_components(repo, out) if entry[1] != 'outside the run output tree']
    if links:
        report.update({'status': 'blocked_symlinked_path', 'symlinks': links, 'blocker': f'{repo} is reached through symlinked path component(s) {[entry[0] for entry in links]} inside the run tree; nothing is read, archived or deleted behind a symlink'})
        return report
    expected = (out / 'arms' / arm / 'repo').resolve()
    real = repo.resolve()
    if real != expected or not str(real).startswith(str(out.resolve()) + os.sep):
        report.update({'status': 'blocked_not_owned', 'blocker': f'only {expected} may be deleted; owned_paths is forgeable data and never authorizes a delete'})
        return report
    archives = out / 'archives'
    archives.mkdir(parents=True, exist_ok=True)
    tar_path = archives / f'{arm}-repo.tar.gz'
    bundle_path = archives / f'{arm}.bundle'
    exec_rec = {}
    try:
        exec_rec = json.loads((out / 'arms' / arm / 'result.json').read_text(encoding='utf-8')).get('execution') or {}
    except (OSError, ValueError):
        exec_rec = {}
    alive = []
    for pid in list(exec_rec.get('surviving_children') or []) + list(exec_rec.get('children_before_kill') or []):
        try:
            os.kill(int(pid), 0)
            alive.append(int(pid))
        except (OSError, ValueError, TypeError):
            pass
    pgid = exec_rec.get('pgid')
    group_alive = bool(exec_rec.get('process_group_still_alive')) and (not isinstance(pgid, int) or signal_group(pgid, 0))
    if group_alive or alive:
        report.update({'status': 'blocked_owned_processes_alive', 'alive_pids': alive, 'blocker': 'an owned process tree is still alive; a reparented child is still ours, so cleanup waits'})
        return report
    try:
        listing = []
        symlinks = []
        with tarfile.open(tar_path, 'w:gz') as tar:
            for path in sorted(repo.rglob('*')):
                if path.is_symlink():
                    symlinks.append({'name': f'{arm}/' + str(path.relative_to(repo)), 'target': str((path.parent / os.readlink(path)).resolve())})
                    tar.add(path, arcname=f'{arm}/' + str(path.relative_to(repo)))
                elif path.is_file():
                    arcname = f'{arm}/' + str(path.relative_to(repo))
                    tar.add(path, arcname=arcname)
                    listing.append({'name': arcname, 'size': path.stat().st_size, 'sha256': A.sha256_file(path)})
        escapes = [s for s in symlinks if not s['target'].startswith(str(out.resolve()) + os.sep)]
        report['tar_symlinks'] = symlinks
        if escapes:
            report.update({'status': 'blocked_symlink_escape', 'symlinks': escapes, 'blocker': "a checkout symlink points outside this run's output tree; refusing to touch it"})
            return report
        with tarfile.open(tar_path, 'r:gz') as verify:
            members = {}
            for member in verify.getmembers():
                if member.isfile():
                    members[member.name] = (member.size, A.sha256_bytes(verify.extractfile(member).read()))
        report['tar_members'] = len(members)
        report['tar_verified'] = bool(listing) and all((members.get(entry['name']) == (entry['size'], entry['sha256']) for entry in listing))
        report['tar_sha256'] = A.sha256_file(tar_path)
        git(repo, 'bundle', 'create', str(bundle_path), 'HEAD')
        # `git bundle verify` needs a repository; use the checkout itself, never whatever cwd we run from.
        report['bundle_verified'] = subprocess.run(['git', '-C', str(repo), 'bundle', 'verify', str(bundle_path.resolve())], capture_output=True, check=False).returncode == 0
        report['bundle_sha256'] = A.sha256_file(bundle_path)
    except (A.PreflightBlocker, OSError, tarfile.TarError) as exc:
        report.update({'status': 'blocked_archive_failed', 'blocker': str(exc)})
        return report
    if not (report['tar_verified'] and report['bundle_verified']):
        report.update({'status': 'blocked_verification_failed'})
        return report
    shutil.rmtree(repo)
    report.update({'status': 'archived_and_removed', 'checkout_preserved': False, 'removed_owned_path': str(repo)})
    return report

CHECK_DEFAULTS = {'ok': False, 'all_tests_expected': False, 'tests_run': 0, 'failures': 0, 'errors': 0, 'returncode': None}
SCOPE_DEFAULTS = {'scope_ok': False, 'frozen_intact': False, 'base_intact': False, 'untracked': [], 'changed': [], 'digest': '', 'head_commit': None, 'frozen_base_commit': None}
EXECUTION_DEFAULTS = {'argv': None, 'exit_code': None, 'timed_out': False, 'seconds': None, 'total_seconds': None}

def part(retained, key, defaults):
    return {**defaults, **(retained.get(key) or {})}

def offline_gates(evidence_state, desktop):
    gates = {'retained_evidence_verified': bool(evidence_state.get('verified'))}
    blockers = [f'retained evidence failed verification: {problem}' for problem in (evidence_state.get('problems') or [])]
    if desktop is not None:
        within = desktop.get('status') == 'within_budget'
        gates['desktop_window_within_budget'] = within
        if not within:
            blockers.append(f"desktop App retrospective gate is {desktop.get('status')}: recorded window {desktop.get('recorded_seconds')}s against the frozen {desktop.get('budget_seconds')}s budget; this tool neither started nor killed the App session, so an exceeded or unknown desktop window is never an accepted measurement")
    return (gates, blockers)

def recompute_offline_acceptance(manifest, arm, retained, accounting, evidence_state):
    """Re-run every gate against archived usage and the archived patch digest; stale acceptance never survives."""
    retained['accounting'] = accounting
    retained['scope'] = part(retained, 'scope', SCOPE_DEFAULTS)
    retained['scope']['digest'] = evidence_state.get('patch_sha256') or ''
    (gates, blockers) = offline_gates(evidence_state, retained.get('desktop_gate'))
    result = evaluate_arm(arm, retained.get('client'), manifest, accounting, part(retained, 'check', CHECK_DEFAULTS), retained['scope'], retained.get('verdict') or {'status': 'absent', 'digest_matches': False}, part(retained, 'execution', EXECUTION_DEFAULTS), part(retained, 'verdict_source', {'kind': None, 'authoritative': False}), extra_gates=gates, extra_blockers=blockers)
    merged = dict(retained)
    for key in ('gates', 'accepted', 'blockers', 'check', 'execution', 'models', 'budget', 'machine', 'task_sha256', 'fixture_sha256', 'protocol'):
        merged[key] = result[key]
    merged['reaccounted_offline'] = True
    merged['evidence'] = evidence_state
    return merged

def reaccount_arm(out, manifest, arm):
    """Offline re-accounting from retained evidence only: no live home, database or config is read."""
    evidence = out / 'arms' / arm
    state = verify_retained_evidence(evidence)
    retained_path = evidence / 'result.json'
    retained = json.loads(retained_path.read_text(encoding='utf-8')) if retained_path.exists() else None
    if retained is None:
        missing = {'arm': arm, 'client': None, 'accepted': False, 'attempted': False, 'gates': {},
                   'blockers': [f'no retained {arm} result.json: the arm was never executed, so nothing can be accepted'],
                   'check': dict(CHECK_DEFAULTS), 'scope': dict(SCOPE_DEFAULTS), 'execution': dict(EXECUTION_DEFAULTS),
                   'verdict': {'status': 'absent', 'digest_matches': False}, 'accounting': unknown_cost_accounting('the arm was never executed')}
        return recompute_offline_acceptance(manifest, arm, missing, missing['accounting'], state)
    if arm == 'codex':
        root_id = (retained.get('accounting') or {}).get('root_thread_id')
        if not root_id:
            retained['reaccount_source'] = ['retained (the archived result carries no Codex root thread id)']
            state['problems'].append('the archived Codex result carries no root thread id, so usage cannot be recomputed')
            state['verified'] = False
            return recompute_offline_acceptance(manifest, arm, retained, retained.get('accounting') or unknown_cost_accounting('no archived root thread id'), state)
        try:
            # Offline re-accounting passes NO live CODEX_HOME: a missing or emptied archive fails
            # closed instead of quietly falling back to whatever sessions the original machine kept.
            (accounting, sources) = account_codex_evidence(manifest, evidence, root_id, retained.get('client'), None)
            retained['reaccount_source'] = sources
        except A.PreflightBlocker as exc:
            accounting = retained.get('accounting') or unknown_cost_accounting('archived rollouts unreadable')
            retained['reaccount_source'] = [f'retained (archived rollouts unreadable: {exc})']
            state['problems'].append(f'the archived Codex rollouts cannot be re-accounted: {exc}')
            state['verified'] = False
        text = accounting.get('root_final_text', '')
    else:
        records_path = evidence / 'native-records.json'
        if not records_path.exists():
            accounting = retained.get('accounting') or unknown_cost_accounting('no archived native records')
            retained['reaccount_source'] = ['retained (no archived native records; an offline report never opens a live database)']
            state['problems'].append('archived native-records.json is missing, so Hybrid usage cannot be recomputed')
            state['verified'] = False
            text = ''
        else:
            snapshot = json.loads(records_path.read_text(encoding='utf-8'))
            accounting = A.account_opencode(snapshot, root_session_ids=(retained.get('accounting') or {}).get('root_session_ids', []), max_local_dispatches=manifest['budget']['initial'] + manifest['budget']['repair'], max_workers=manifest['budget'].get('max_workers', 1), client=(retained.get('client') or 'opencode-cli'), **opencode_expectations(manifest))
            retained['reaccount_source'] = ['archived native records']
            text = assistant_texts_from_records(snapshot['records'], 'review')
    retained['verdict'] = A.semantic_verdict(text, state.get('patch_sha256') or '')
    return recompute_offline_acceptance(manifest, arm, retained, accounting, state)

def build_report(out, manifest):
    arms = {}
    for arm in manifest['completed_arms']:
        result = reaccount_arm(out, manifest, arm)
        accounting = result.get('accounting') or {}
        result['cloud_tokens'] = accounting.get('cloud_total')
        result['cloud_tokens_lower_bound'] = accounting.get('known_lower_bound')
        result['local_tokens'] = accounting.get('local_total')
        result['unknown_maintenance'] = accounting.get('unknown_maintenance_total', 0)
        if not (result.get('evidence') or {}).get('verified', True):
            result['totals_withheld'] = 'retained evidence failed verification: no exact or bounded total is published for an edited or missing archive'
            result.update({'cloud_tokens': None, 'cloud_tokens_lower_bound': None, 'local_tokens': None, 'unknown_maintenance': None})
        arms[arm] = result
    integrity = report_config_integrity(manifest)
    if integrity['changed']:
        for result in arms.values():
            result['accepted'] = False
            result.setdefault('gates', {})['installed_native_config_unchanged'] = False
            result['blockers'] = list(result.get('blockers') or []) + [f"installed native config {integrity['path']} changed from {str(integrity['frozen_sha256'])[:12]} to {str(integrity['current_sha256'])[:12]} while this run was measured; a global configuration edit invalidates every arm"]
    elif not integrity.get('verified'):
        for result in arms.values():
            result['accepted'] = False
            result.setdefault('gates', {})['installed_native_config_unchanged'] = False
            result['blockers'] = list(result.get('blockers') or []) + [f"the execution closeout recorded native config status {integrity.get('status')!r} for {str(integrity.get('path'))}; an installed native config whose integrity window was never captured unchanged cannot claim verified acceptance"]
    seal_blockers = frozen_manifest_blockers(manifest)
    if seal_blockers:
        for result in arms.values():
            result['accepted'] = False
            result.setdefault('gates', {})['frozen_manifest_sealed'] = False
            result['blockers'] = list(result.get('blockers') or []) + seal_blockers
    completed = [arm for (arm, result) in arms.items() if result.get('accepted')]
    for result in arms.values():
        result['cloud_tokens_per_accepted_task'] = result['cloud_tokens'] if result.get('accepted') else None
    per_task = {}
    for (arm, result) in arms.items():
        own = 1 if result.get('accepted') else 0
        tokens = result.get('cloud_tokens')
        per_task[arm] = tokens / own if own and tokens is not None else None
    metrics = {'cloud_tokens_per_completed_task': per_task, 'per_arm_completed_tasks': {arm: 1 if r.get('accepted') else 0 for (arm, r) in arms.items()}, 'per_task_note': "each arm carries its own 1 or 0 completed task; a failed arm reports null per-task with its spend retained", 'undefined_reason': None if completed else '0 completed tasks: per-task metrics are undefined, never zero', 'failed_attempts_included': True, 'ratio': ratio_block(arms), **seat_metrics(arms), 'runner_authoring_cost': {'status': 'not_measured', 'reason': 'the runner launches no billing model itself; external authoring cost is reported separately'}}
    return {'protocol': A.PROTOCOL, 'generated_utc': now(), 'out': str(out), 'machine': manifest['machine'], 'models': manifest['models'], 'budget': manifest['budget'], 'measurement_kind': manifest['measurement_kind'], 'native_config_integrity': integrity, 'frozen_fields_sha256': manifest.get('frozen_fields_sha256'), 'frozen_fields_verified': not seal_blockers, 'arms': arms, 'accepted_arms': sorted(completed), 'completed_tasks': len(completed), 'cleanup': retained_cleanup_receipts(out), 'metrics': metrics, 'caveats': manifest['notes'] + ['App sessions are labelled codex-app, never a CLI measurement', 'unknown maintenance is bounded, never an exact total', 'a changed installed native config invalidates every arm; the runner never edits it', 'report renders retained evidence only: it launches nothing, deletes nothing and needs no original home, database or config']}

def render_markdown(report):
    machine = report['machine']
    lines = [f"# Benchmark report `{report['out']}`", '', f"* protocol `{report['protocol']}`, generated {report['generated_utc']}, measurement kind `{report['measurement_kind']}`", f"* machine `{machine['label']}` — {machine['platform']}, python {machine['python']}, git {machine['git']}, codex {machine['codex']}, opencode {machine['opencode']}, RAM {machine['physical_memory_bytes']} bytes", f"* models `{json.dumps(report['models'])}`", f"* budget `{json.dumps(report['budget'])}` per arm (1 initial + 1 repair)", f"* accepted arms: {', '.join(report['accepted_arms']) or 'none'}", '']
    if machine.get('hardware'):
        lines += [f"* hardware `{json.dumps(machine['hardware'])}`", '']
    header = ('arm', 'client', 'accepted', 'cloud', 'cloud>=lower', 'local', 'unknown maint', 'seconds', 'tests', 'exit/timeout', 'failed gates')
    lines += ['| ' + ' | '.join(header) + ' |', '|' + '---|' * len(header)]
    for (arm, result) in sorted(report['arms'].items()):
        (check, execution) = (result.get('check') or {}, result.get('execution') or {})
        failed = [name for (name, ok) in (result.get('gates') or {}).items() if not ok]
        lines.append('| ' + ' | '.join((str(v) for v in (arm, result.get('client'), result.get('accepted'), result.get('cloud_tokens'), result.get('cloud_tokens_lower_bound'), result.get('local_tokens'), result.get('unknown_maintenance'), execution.get('seconds'), f"{check.get('tests_run')}T/{check.get('failures')}F/{check.get('errors')}E", f"{execution.get('exit_code')}/{execution.get('timed_out')}", ', '.join(failed) or 'none'))) + ' |')
    metrics = report['metrics']
    lines += ['', '## Tokens by seat', '', '| arm | seat | model | uncached input | cached input | output | reasoning | total |', '|---|---|---|---|---|---|---|---|']
    for (arm, seats) in sorted((metrics.get('seats') or {}).items()):
        for seat in ('planner', 'worker', 'unknown'):
            usage = (seats or {}).get(seat)
            if usage and (seat != 'unknown' or usage.get('total')):
                lines.append(f"| {arm} | {seat} | {usage.get('model') or 'unattributed'} | " + ' | '.join(str(usage.get(key)) for key in ('uncached_input', 'cached_input', 'output', 'reasoning', 'total')) + ' |')
    share, ratio = metrics.get('hybrid_cloud_share') or {}, metrics.get('cloud_vs_codex') or {}
    fmt = lambda value: 'n/a' if value is None else f'{value:.3f}'
    lines += ['', f"* Hybrid cloud share (attributed requests): {fmt(share.get('value'))}; full interval [{fmt(share.get('lower_bound'))}, {fmt(share.get('upper_bound'))}]",
              f"* Hybrid cloud / Codex cloud (attributed requests): {fmt(ratio.get('value'))}; full interval [{fmt(ratio.get('lower_bound'))}, {fmt(ratio.get('upper_bound'))}]", '', '## Targets', '']
    lines += [f"* {name}: {'PASS' if ok else 'FAIL'}" for (name, ok) in (metrics.get('targets') or {}).items()]
    lines += ['', '## Blockers', '']
    for (arm, result) in sorted(report['arms'].items()):
        lines.append(f'* **{arm}**: ' + ('; '.join(result.get('blockers') or []) or 'none'))
    lines += ['', '## Metrics', '', '```json', json.dumps(report['metrics'], indent=2), '```', '', '## Caveats', '']
    lines += [f'* {note}' for note in report['caveats']]
    return '\n'.join(lines) + '\n'

def read_cleanup_receipts(out):
    path = out / 'archive-verification.json'
    try:
        receipts = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    except (OSError, ValueError):
        receipts = []
    return [entry for entry in receipts if isinstance(entry, dict)]

def retained_cleanup_receipts(out):
    return [dict(entry, retained_receipt=True) for entry in read_cleanup_receipts(out)]

def closeout(out, manifest, arms=None):
    """Execution closeout only: archive, verify, then remove the owned checkouts. A report never deletes."""
    previous = {entry.get('arm'): entry for entry in read_cleanup_receipts(out) if entry.get('status') == 'archived_and_removed'}
    receipts = []
    for arm in manifest['completed_arms'] if arms is None else arms:
        earlier = previous.get(arm)
        if earlier and not Path(manifest['arms'][arm]['repo']).exists():
            receipts.append(dict(earlier, receipt='retained from the first verified closeout'))
            continue
        entry = archive_and_cleanup(out, manifest, arm)
        if entry.get('status') != 'archived_and_removed' and earlier:
            entry = dict(earlier, receipt='retained from the first verified closeout')
        receipts.append(entry)
    (out / 'archive-verification.json').write_text(json.dumps(receipts, indent=2), encoding='utf-8')
    if manifest.get('simulators'):
        manifest['simulators_released'] = release_simulators(out, manifest)
        save_manifest(out, manifest)
    return receipts

def write_report(out, manifest):
    """Offline renderer: writes report.json/REPORT.md and touches nothing else."""
    report = build_report(out, manifest)
    (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (out / 'REPORT.md').write_text(render_markdown(report), encoding='utf-8')
    return report

def launch_input_blockers(out, manifest, launch_arms):
    """Before any live work: the task, prompts, native profile and fixture must still be the frozen bytes."""
    blockers = []
    task_path = out / 'task.txt'
    if not task_path.exists() or A.sha256_file(task_path) != A.sha256_bytes(manifest['task'].encode('utf-8')):
        blockers.append('task.txt on disk no longer matches the task frozen into the prompts; refusing to launch against edited instructions')
    for (arm, record) in manifest['arms'].items():
        prompt_path = out / 'prompts' / f'{arm}.txt'
        prompt_text = prompt_path.read_text(encoding='utf-8') if prompt_path.exists() else ''
        if A.sha256_bytes(prompt_text.encode('utf-8')) != record.get('prompt_sha256'):
            blockers.append(f'the frozen prompt for {arm} changed after prepare; the measured round would not be the prepared round')
        elif arm == 'codex' and manifest['models'].get('codex_child') not in prompt_text:
            blockers.append(f"the frozen {arm} prompt never names the frozen worker model {manifest['models'].get('codex_child')!r}; the prompt and the recorded routing must agree")
        if arm not in launch_arms:
            continue
        repo = Path(record['repo'])
        drift = {name: digest for (name, digest) in manifest['fixture_sha256'].items() if not (repo / name).exists() or A.sha256_file(repo / name) != digest}
        if drift:
            blockers.append(f'the {arm} checkout is not the pristine frozen fixture input ({sorted(drift)}); an arm starts from the frozen bytes or not at all')
        try:
            head = git(repo, 'rev-parse', 'HEAD')
        except A.PreflightBlocker:
            head = None
        if head != record.get('base'):
            blockers.append(f'the {arm} checkout HEAD is {head!r} instead of the frozen fixture base {record.get("base")!r}')
        try:
            status = git(repo, 'status', '--porcelain', '--untracked-files=all')
        except A.PreflightBlocker as exc:
            blockers.append(f'the {arm} checkout status cannot be verified: {exc}')
        else:
            if status:
                blockers.append(f'the {arm} checkout is not the pristine frozen fixture input (tracked or untracked changes); refusing to launch')
    config = manifest.get('native_config') or {}
    try:
        current = A.config_snapshot(Path(config.get('path')), os.environ)
    except A.PreflightBlocker as exc:
        blockers.append(f'the installed native config cannot be re-read before launch: {exc}')
        return blockers
    if current['raw_sha256'] != config.get('raw_sha256'):
        blockers.append('the installed native config no longer matches the digest frozen by prepare; refusing to launch an arm against edited global configuration')
    if current['snapshot'] != config.get('snapshot'):
        blockers.append('the resolved native config values (including non-secret sidecar references) differ from the snapshot frozen by prepare; the profile this launch would inherit is not the profile that was validated')
    for blocker in A.validate_native_profile(current, manifest['models'].get('local'))[0]:
        if blocker not in blockers:
            blockers.append(blocker)
    return blockers

def preflight(manifest, out=None, launch_arms=('codex', 'opencode')):
    blockers = list(manifest['native_profile']['blockers'])
    blockers.extend(manifest.get('preparation_blockers') or [])
    if manifest.get('fixture'):
        for arm in launch_arms:
            baseline = (manifest['arms'].get(arm) or {}).get('baseline')
            if not baseline:
                blockers.append(f'the {arm} baseline check never ran during prepare, so the frozen starting point is unproven on this Mac')

    blockers.extend(frozen_manifest_blockers(manifest))
    blockers.extend(model_blockers(manifest))
    blockers.extend(budget_blockers((manifest.get('budget') or {}).get('wall_clock_seconds_per_arm')))
    for name in ('codex', 'opencode'):
        binary = manifest['binaries'].get(name)
        if not binary:
            blockers.append(f'--{name}-bin is required for a live arm')
        elif not Path(binary).exists() and (not shutil.which(binary)):
            blockers.append(f'{name} binary is not runnable: {binary}')
    db = manifest.get('opencode_db')
    if db and (not Path(db).exists()):
        blockers.append(f'OpenCode database not found: {db}')
    if not manifest.get('codex_home'):
        blockers.append('--codex-home is required so real rollouts can be read')
    integrity = config_integrity(manifest)
    if integrity['changed']:
        blockers.append(f"installed native config {integrity['path']} no longer matches the digest frozen by prepare: refusing to launch an arm against edited global configuration")
    if out is not None:
        blockers.extend(launch_input_blockers(out, manifest, list(launch_arms)))
    for planned in (codex_argv(manifest, Path(manifest['arms']['codex']['repo']), '<frozen prompt>'), opencode_argv(manifest, '<frozen prompt>')):
        blockers.extend(permission_blockers(planned))
    return blockers

def desktop_gate_record(manifest, window):
    budget = manifest['budget']['wall_clock_seconds_per_arm']
    recorded = window_seconds(window or {})
    return {'budget_seconds': budget, 'recorded_seconds': recorded, 'enforced': False,
            'status': 'unknown' if recorded is None else 'within_budget' if recorded <= budget else 'exceeded',
            'note': 'RETROSPECTIVE desktop gate: this tool neither started nor killed the App session, so an exceeded or unknown budget is a recorded failure, never an enforced App wall clock; the final check and accounting time is added to the recorded window'}

def prepared_option_mismatches(args, manifest):
    """Options given to a later `run` that differ from what `prepare` froze into the manifest."""
    models = manifest.get('models') or {}
    expand = lambda value: str(Path(value).expanduser()) if value else None
    timeout = fixture_of({'fixture': args.fixture}).default_budget if args.timeout is None else args.timeout
    frozen = {'--fixture': (args.fixture, manifest.get('fixture') or DEFAULT_FIXTURE),
              '--local-model': (args.local_model, models.get('local')),
              '--codex-cloud-model': (args.codex_cloud_model, models.get('codex_cloud')),
              '--opencode-cloud-model': (args.opencode_cloud_model, models.get('opencode_cloud')),
              '--child-model': (args.child_model, models.get('codex_child')),
              '--effort': (args.effort, models.get('effort')),
              '--timeout': (timeout, (manifest.get('budget') or {}).get('wall_clock_seconds_per_arm')),
              '--codex-bin': (expand(args.codex_bin), (manifest.get('binaries') or {}).get('codex')),
              '--opencode-bin': (expand(args.opencode_bin), (manifest.get('binaries') or {}).get('opencode')),
              '--codex-home': (expand(args.codex_home), manifest.get('codex_home')),
              '--opencode-db': (expand(args.opencode_db), manifest.get('opencode_db')),
              '--opencode-config': (expand(args.opencode_config), (manifest.get('native_config') or {}).get('path')),
              '--permission-policy': (args.permission_policy, manifest.get('permission_policy'))}
    if args.label:
        frozen['--label'] = (args.label, (manifest.get('machine') or {}).get('label'))
    return [f'{flag} {given!r} differs from the prepared {kept!r}' for (flag, (given, kept)) in frozen.items() if given != kept]

def cmd_run(args):
    if Path(args.out).exists():
        out = resolve_out(args.out, fresh=False)
        manifest = load_manifest(out)
        if manifest['completed_arms'] or manifest.get('live_started'):
            print(f"refusing to re-run arms already completed in {out}: {manifest['completed_arms']} (started={bool(manifest.get('live_started'))}); a partially started arm is never retried for free", file=sys.stderr)
            return 2
        mismatches = prepared_option_mismatches(args, manifest)
        if mismatches:
            print('refusing to run a prepared round with different options (nothing launched): ' + '; '.join(mismatches) + '; repeat the exact prepare options or use a fresh --out', file=sys.stderr)
            return 2
    else:
        if cmd_prepare(args) == 2 and (args.live or not (Path(args.out).exists() and (Path(args.out) / 'manifest.json').exists())):
            return 2
        out = resolve_out(args.out, fresh=False)
        manifest = load_manifest(out)
    if not args.live:
        plan = {'state': 'preparation_only', 'live': False, 'models_launched': False, 'blockers': preflight(manifest, out), 'planned_argv': {'codex': codex_argv(manifest, Path(manifest['arms']['codex']['repo']), '<frozen prompt>'), 'opencode': opencode_argv(manifest, '<frozen prompt>')}, 'budget': manifest['budget'], 'out': str(out)}
        (out / 'dry-run-plan.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
        print(json.dumps(plan, indent=2))
        return 0
    blockers = preflight(manifest, out)
    if blockers:
        print('PREFLIGHT BLOCKERS (nothing launched): ' + '; '.join(blockers), file=sys.stderr)
        return 2
    results = {}
    interrupted = False
    manifest['live_started'] = now()
    manifest['live_attempt_evidence'] = {arm: {'attempted': True, 'attempts': 1, 'cost_state': 'unknown'} for arm in ('codex', 'opencode')}
    save_manifest(out, manifest)
    for arm in ('codex', 'opencode'):
        try:
            blockers = preflight(manifest, out, launch_arms=(arm,))
            if blockers:
                raise A.PreflightBlocker('; '.join(blockers))
            start_arm_simulator(out, manifest, arm)
            result = run_codex_arm(out, manifest) if arm == 'codex' else run_opencode_arm(out, manifest)
        except KeyboardInterrupt:
            interrupted = True
            receipt = out / 'arms' / arm / 'arm.execution.json'
            try:
                execution = json.loads(receipt.read_text(encoding='utf-8')) if receipt.exists() else None
            except (OSError, ValueError):
                execution = None
            result = record_arm_failure(out, manifest, arm, 'codex-cli' if arm == 'codex' else 'opencode-cli',
                                        [f'the {arm} arm was interrupted; incomplete work is rejected and its spend remains unknown'],
                                        execution, stage='interrupted')
        except Exception as exc:
            result = record_arm_failure(out, manifest, arm, 'codex-cli' if arm == 'codex' else 'opencode-cli', [f'the {arm} arm failed outside its own evidence handling: {type(exc).__name__}: {exc}; the attempt is retained with unknown cost'], None, stage='crash')
        results[arm] = result
        manifest['live_attempt_evidence'][arm] = {'attempted': True, 'attempts': 1, 'accepted': bool(result.get('accepted')), 'cost_state': (result.get('accounting') or {}).get('cost_state') or ('recorded' if (result.get('accounting') or {}).get('cloud_total') is not None or (result.get('accounting') or {}).get('known_lower_bound') is not None else 'unknown')}
        manifest['completed_arms'] = sorted(set(manifest['completed_arms']) | {arm})
        save_manifest(out, manifest)
        if interrupted:
            manifest['state'] = 'interrupted'
            for pending in set(manifest['arms']) - set(results):
                manifest['live_attempt_evidence'][pending] = {'attempted': False, 'attempts': 0, 'cost_state': 'not_attempted'}
            break
    manifest['config_integrity_final'] = config_integrity(manifest)
    save_manifest(out, manifest)
    closeout(out, manifest, arms=tuple(manifest['arms']) if interrupted else None)
    report = write_report(out, manifest)
    print(json.dumps({'arms': {arm: {key: results[arm].get(key) for key in ('accepted', 'blockers')} for arm in results}, 'report': str(out / 'REPORT.md'), 'ratio': report['metrics']['ratio'], 'cleanup': report['cleanup']}, indent=2))
    return 130 if interrupted else 0

def cmd_finish(args):
    out = resolve_out(args.out, fresh=False)
    manifest = load_manifest(out)
    if 'codex' in manifest['completed_arms']:
        print('refusing to import the Codex arm twice', file=sys.stderr)
        return 2
    if fixture_of(manifest).needs_simulator:
        print(f"refusing a desktop App import for the {manifest.get('fixture')} fixture: its arms need a run-owned simulator that only `run --live` creates; use the CLI arms", file=sys.stderr)
        return 2
    blockers = preflight(manifest, out, launch_arms=('opencode',))
    if blockers:
        print('PREFLIGHT BLOCKERS: ' + '; '.join(blockers), file=sys.stderr)
        return 2
    if not args.live:
        print(json.dumps({'state': 'finish_dry_inspect', 'live': False, 'models_launched': False, 'app_session_imported': False, 'codex_thread': args.codex_thread, 'out': str(out), 'note': 'finish without --live inspects only: it consumes neither the App import nor the Hybrid arm, so `finish OUT --codex-thread ID --live` still works later'}, indent=2))
        return 0
    home = manifest.get('codex_home')
    catalog = A.scan_codex_rollouts(Path(home) / 'sessions') if home else {}
    guard = []
    if args.codex_thread not in catalog:
        guard.append(f"no rollout for root thread {args.codex_thread} under {Path(home or '<CODEX_HOME unset>')} / sessions: App completion is unknown")
    else:
        tree = A.codex_tree(catalog, args.codex_thread)
        unfinished = [f"{sid}:{(catalog.get(sid) or {}).get('completion')}" for sid in tree if (catalog.get(sid) or {}).get('completion') != 'complete']
        unrollowned = [sid for sid in tree if sid not in catalog]
        if unfinished:
            guard.append(f'Codex root or child turn still active, aborted or unknown: {", ".join(unfinished)}')
        if unrollowned:
            guard.append(f'observed spawned Codex session(s) with no rollout file: {", ".join(unrollowned)}')
    if guard:
        record_attempt(out, 'codex', 'app-import-guard', guard)
        print(json.dumps({'codex_app': {'accepted': False, 'blockers': guard, 'hybrid_launched': False, 'live_started': False, 'rollouts_archived': False, 'state': manifest['state'], 'note': 'completion is read from the fresh CODEX_HOME catalog before any final check, archive or paid Hybrid launch; both checkouts and the prepared state stay untouched, so the same thread can be imported again once finished'}}, indent=2))
        return 2
    manifest['live_started'] = now()
    manifest['live_attempt_evidence'] = {'codex': {'attempted': True, 'attempts': 1, 'cost_state': 'unknown'}, 'opencode': {'attempted': True, 'attempts': 1, 'cost_state': 'unknown'}}
    save_manifest(out, manifest)
    result = run_codex_arm(out, manifest, client='codex-app', root_id=args.codex_thread)
    gate = desktop_gate_record(manifest, (result.get('accounting') or {}).get('recorded_window'))
    result['desktop_gate'] = gate
    if gate['status'] != 'within_budget':
        (gates, blockers) = offline_gates({'verified': True, 'problems': []}, gate)
        result['gates'] = {**(result.get('gates') or {}), **gates}
        result['blockers'] = list(result['blockers']) + blockers
        result['accepted'] = False
    (out / 'arms' / 'codex' / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    seal_arm_evidence(out / 'arms' / 'codex')
    if not result['accepted']:
        print(json.dumps({'codex_app': {'accepted': False, 'blockers': result['blockers'], 'hybrid_launched': False, 'checkout_removed': False, 'state': manifest['state'], 'note': 'a rejected App import is kept as evidence: no paid Hybrid launch, no archive or removal, the same thread can be imported again'}}, indent=2))
        return 2
    manifest['completed_arms'] = sorted(set(manifest['completed_arms']) | {'codex'})
    manifest['measurement_kind'] = 'codex-app-imported+opencode-cli'
    save_manifest(out, manifest)
    interrupted = False
    try:
        blockers = preflight(manifest, out, launch_arms=('opencode',))
        if blockers:
            raise A.PreflightBlocker('; '.join(blockers))
        opencode = run_opencode_arm(out, manifest)
    except KeyboardInterrupt:
        interrupted = True
        receipt = out / 'arms' / 'opencode' / 'arm.execution.json'
        try:
            execution = json.loads(receipt.read_text(encoding='utf-8')) if receipt.exists() else None
        except (OSError, ValueError):
            execution = None
        opencode = record_arm_failure(out, manifest, 'opencode', 'opencode-cli',
                                      ['the Hybrid arm was interrupted after App import; incomplete work is rejected and its spend remains unknown'],
                                      execution, stage='interrupted')
        manifest['state'] = 'interrupted'
    except Exception as exc:
        opencode = record_arm_failure(out, manifest, 'opencode', 'opencode-cli',
                                      [f'the Hybrid arm failed after App import: {type(exc).__name__}: {exc}; the attempt is retained with unknown cost'],
                                      stage='crash')
    manifest['completed_arms'] = sorted(set(manifest['completed_arms']) | {'opencode'})
    save_manifest(out, manifest)
    opencode_summary = {key: opencode.get(key) for key in ('accepted', 'blockers')}
    manifest['config_integrity_final'] = config_integrity(manifest)
    save_manifest(out, manifest)
    closeout(out, manifest)
    write_report(out, manifest)
    print(json.dumps({'codex_app': {key: result.get(key) for key in ('accepted', 'blockers', 'desktop_gate')}, 'opencode': opencode_summary}, indent=2))
    return 130 if interrupted else 0

def cmd_report(args):
    out = resolve_out(args.out, fresh=False)
    report = write_report(out, load_manifest(out))
    print(json.dumps({'accepted_arms': report['accepted_arms'], 'ratio': report['metrics']['ratio'], 'report': str(out / 'REPORT.md'), 'cleanup': report['cleanup'], 'offline_render': True, 'deleted_or_archived': False}, indent=2))
    return 0

def spread(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return {'median': None, 'min': None, 'max': None, 'rounds_with_value': 0}
    middle = len(values) // 2
    median = values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2
    return {'median': median, 'min': values[0], 'max': values[-1], 'rounds_with_value': len(values)}

def summarise_rounds(reports):
    """Reliability and token figures across repeated rounds; a missing value is never counted as zero."""
    accepted = {arm: f"{sum(1 for r in reports if (r['arms'].get(arm) or {}).get('accepted'))}/{sum(1 for r in reports if arm in r['arms'])}" for arm in ('codex', 'opencode')}
    return {'rounds': len(reports), 'accepted': accepted,
            'hybrid_cloud_share': spread([(r['metrics'].get('hybrid_cloud_share') or {}).get('value') for r in reports]),
            'cloud_vs_codex': spread([(r['metrics'].get('cloud_vs_codex') or {}).get('value') for r in reports]),
            'targets_held_every_round': bool(reports) and all(all(ok for (name, ok) in ((r['metrics'].get('targets') or {'missing': False}).items()) if not name.startswith('stretch')) for r in reports)}

def cmd_compare(args):
    outs = [resolve_out(raw, fresh=False) for raw in args.outs]
    (blockers, differences) = compare_runs(outs)
    reports = {str(out): build_report(out, load_manifest(out)) for out in outs}
    rows = []
    for (label, report) in reports.items():
        for (arm, result) in sorted(report['arms'].items()):
            accounting = result.get('accounting') or {}
            calls = accounting.get('local_dispatches') or sum((session.get('tool_calls', 0) for session in accounting.get('sessions', [])))
            rows.append({'run': Path(label).name, 'arm': arm, 'client': result.get('client'), 'label': report['machine']['label'], 'accepted': result.get('accepted'), 'cloud': result.get('cloud_tokens'), 'lower_bound': result.get('cloud_tokens_lower_bound'), 'local': result.get('local_tokens'), 'unknown_maintenance': result.get('unknown_maintenance'), 'seconds': (result.get('execution') or {}).get('seconds'), 'calls': calls})
    ratios = {}
    for (label, report) in reports.items():
        ratios[label] = report['metrics']['ratio']
    rounds = summarise_rounds(list(reports.values()))
    comparison = {'blockers': blockers, 'compatibility_differences': differences, 'rows': rows, 'ratios': ratios, 'rounds': rounds, 'caveats': ['every report here is recomputed from sealed retained evidence; a cached report.json is never trusted', 'cached prefix state differs per Mac and stays an unknown caveat', 'raw tokens are not quota or price', 'failed/timeout cost is retained, never dropped']}
    target = Path(args.out_dir).resolve() if args.out_dir else outs[0]
    target.mkdir(parents=True, exist_ok=True)
    (target / 'comparison.json').write_text(json.dumps(comparison, indent=2), encoding='utf-8')
    columns = list(rows[0]) if rows else ['run']
    lines = ['# Cross-run comparison', '', '| ' + ' | '.join(columns) + ' |', '|' + '---|' * len(columns)]
    lines += ['| ' + ' | '.join((str(row.get(key)) for key in columns)) + ' |' for row in rows]
    lines += ['', '## Rounds', '', f"* accepted: {rounds['accepted']}",
              f"* Hybrid cloud share: {json.dumps(rounds['hybrid_cloud_share'])}",
              f"* Hybrid cloud / Codex cloud: {json.dumps(rounds['cloud_vs_codex'])}",
              f"* all targets held in every round: {rounds['targets_held_every_round']}"]
    lines += ['', '## Ratios', '', '```json', json.dumps(ratios, indent=2), '```', '', '## Compatibility blockers', '']
    lines += [f'* {blocker}' for blocker in blockers] or ['* none']
    lines += ['', '## Intended differences (allowed to differ)', '', '```json', json.dumps(differences, indent=2), '```']
    (target / 'COMPARISON.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))
    return 2 if blockers else 0

def parser():
    root = argparse.ArgumentParser(prog='benchmarks/run.py', description='portable two-arm benchmark')
    sub = root.add_subparsers(dest='command', required=True)

    def common(cmd):
        cmd.add_argument('--out', required=True, help='fresh directory OUTSIDE this repository')
        cmd.add_argument('--local-model', required=True, help='installed local model id, e.g. omlx/<id>')
        cmd.add_argument('--label', help="this Mac's label")
        cmd.add_argument('--fixture', default=DEFAULT_FIXTURE, choices=sorted(FX.FIXTURES), help='frozen benchmark task (default ttl-python)')
        cmd.add_argument('--timeout', type=int, default=None, help="per-arm wall clock in seconds (default: the fixture's, 180 for ttl-python, 1200 for swiftui-list)")
        cmd.add_argument('--codex-bin', default='codex')
        cmd.add_argument('--opencode-bin', default='opencode')
        cmd.add_argument('--codex-home', default=str(Path.home() / '.codex'))
        cmd.add_argument('--opencode-db', default=str(Path.home() / '.local/share/opencode/opencode.db'))
        cmd.add_argument('--opencode-config', default=str(Path.home() / '.config/opencode/opencode.json'))
        cmd.add_argument('--codex-cloud-model', default=DEFAULT_CLOUD_CODEX)
        cmd.add_argument('--opencode-cloud-model', default=DEFAULT_CLOUD_OPENCODE)
        cmd.add_argument('--child-model', default=DEFAULT_CHILD_MODEL)
        cmd.add_argument('--effort', default=DEFAULT_EFFORT, help='frozen reasoning effort for the cloud root and the delegated worker')
        cmd.add_argument('--permission-policy', default='installed native denials preserved; --auto not used')
        cmd.add_argument('--live', action='store_true', help='launch the arms; without it nothing launches')
    common(sub.add_parser('prepare', help='freeze a fresh run (launches no model)'))
    common(sub.add_parser('run', help='prepare if needed, then both CLI arms'))
    finish = sub.add_parser('finish', help='import a real Codex App session, then Hybrid')
    finish.add_argument('out')
    finish.add_argument('--codex-thread', required=True)
    finish.add_argument('--live', action='store_true')
    report = sub.add_parser('report', help='offline re-accounting; launches no model')
    report.add_argument('out')
    compare = sub.add_parser('compare', help='offline cross-Mac comparison')
    compare.add_argument('outs', nargs='+')
    compare.add_argument('--out-dir')
    return root
HANDLERS = {'prepare': cmd_prepare, 'run': cmd_run, 'finish': cmd_finish, 'report': cmd_report, 'compare': cmd_compare}

def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return HANDLERS[args.command](args)
    except A.PreflightBlocker as exc:
        print(f'BLOCKER: {exc}', file=sys.stderr)
        return 2
if __name__ == '__main__':
    sys.exit(main())
