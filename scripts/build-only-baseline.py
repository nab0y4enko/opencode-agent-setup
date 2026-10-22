"""Explicit inference harness for two Build-only stage commits in a disposable repo.

Importing this module is safe: only main() starts OpenCode. Acceptance comes from
verify-baseline-result.py, not merely successful process exits.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
from importlib.util import module_from_spec, spec_from_file_location

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL = 'openai/gpt-6.1-sol#high'
def baseline_config():
    return {'warming': False, 'agents': {'build': {
        'model': MODEL, 'request': {'body': {'service_tier': 'default'}}}}}


def baseline_environment(job):
    # Auth remains in the normal data directory; global profile/plugins cannot
    # replace native Build instructions, permissions or tool availability.
    config_home = job.parent / 'isolated-config'
    config_home.mkdir(exist_ok=True)
    return dict(os.environ, PWD=str(job), XDG_CONFIG_HOME=str(config_home))


def git(job, *args):
    return subprocess.check_output(['git', *args], cwd=job, text=True).strip()


def summarize_events(text):
    evidence = {'count': 0, 'sessionIDs': [], 'delegationCalls': [], 'parseErrors': []}
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError('event is not an object')
        except (ValueError, TypeError):
            evidence['parseErrors'].append(number)
            continue
        evidence['count'] += 1
        part = event.get('part') or {}
        for sid in (event.get('sessionID'), part.get('sessionID')):
            if sid and sid not in evidence['sessionIDs']:
                evidence['sessionIDs'].append(sid)
        tool = part.get('tool', part.get('name', ''))
        if event.get('type') == 'tool_use' and tool in ('subagent', 'task', 'delegate', 'spawn_agent'):
            evidence['delegationCalls'].append(tool)
    return evidence


def interrupt_sessions(events_text, runner=None):
    """A killed CLI can leave its native execution alive; cancel only captured IDs."""
    runner = runner or subprocess.run
    ids = summarize_events(events_text)['sessionIDs']
    if not ids:
        return [{'interrupted': False, 'error': 'No session ID in partial events; cancellation could not be confirmed'}]
    outcomes = []
    for sid in ids:
        outcome = {'sessionID': sid, 'interrupted': False}
        try:
            result = runner(['opencode', 'api', 'session.interrupt', '--param', 'sessionID=' + sid],
                            capture_output=True, text=True, timeout=15)
            if result.returncode:
                outcome['error'] = result.stderr[-500:] or f'Interrupt exited {result.returncode}'
            else:
                response = json.loads(result.stdout)
                outcome['interrupted'] = response.get('interrupted') is True
                if not outcome['interrupted']:
                    outcome['error'] = 'Native API did not confirm interruption (execution may already have ended)'
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            outcome['error'] = str(error)
        outcomes.append(outcome)
    return outcomes


def tests_at(job):
    result = subprocess.run(['python3', '-m', 'unittest', '-v'], cwd=job, capture_output=True, text=True, timeout=30)
    return result.returncode, result.stdout + result.stderr


def collect_checkpoints(job, commits):
    """Replay only the fixture files; never check out or change the agent's tree."""
    checkpoints = []
    for index, commit in enumerate(commits[:2], 1):
        sha = commit['sha']
        with tempfile.TemporaryDirectory(prefix='baseline-checkpoint-') as temporary:
            snapshot = pathlib.Path(temporary)
            for file in ('fixture.py', 'test_fixture.py'):
                (snapshot / file).write_bytes(subprocess.check_output(['git', 'show', f'{sha}:{file}'], cwd=job))
            code, output = tests_at(snapshot)
            patch = git(job, 'show', '--format=', '--root', '--no-ext-diff', sha)
            def artifact(name):
                file = job / 'evidence' / name
                return file.read_text() if file.is_file() else ''
            checkpoint = {'sha': sha, 'independent_test_exit': code, 'tests': output, 'patch': patch,
                          'artifact_patch': artifact(f'stage{index}.patch'), 'artifact_tests': artifact(f'stage{index}-tests.txt')}
            if index == 2:
                # Stage-2 tests must fail on stage-1 source independently of the model's claimed red run.
                (snapshot / 'fixture.py').write_bytes(subprocess.check_output(['git', 'show', f'{commits[0]["sha"]}:fixture.py'], cwd=job))
                shutil.rmtree(snapshot / '__pycache__', ignore_errors=True)
                red_code, red_output = tests_at(snapshot)
                checkpoint.update(regression_exit=red_code, regression_tests=red_output,
                                  artifact_red_tests=artifact('stage2-red-tests.txt'))
            checkpoints.append(checkpoint)
    return checkpoints


def main():
    base = pathlib.Path(tempfile.mkdtemp(prefix='build-only-baseline-')).resolve()
    job = base / 'repo'
    job.mkdir()
    artifacts = ROOT / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    env = baseline_environment(job)
    (job / 'opencode.json').write_text(json.dumps(baseline_config(), indent=2))
    (job / '.gitignore').write_text('opencode.json\nevidence/\n__pycache__/\n')
    (job / 'evidence').mkdir()
    (job / 'fixture.py').write_text('def clamp(value, low, high):\n    return min(value, low)\n')
    (job / 'test_fixture.py').write_text('import unittest\nfrom fixture import clamp\nclass Tests(unittest.TestCase):\n def test_low(self): self.assertEqual(clamp(-2,0,10),0)\n def test_middle(self): self.assertEqual(clamp(4,0,10),4)\n def test_high(self): self.assertEqual(clamp(15,0,10),10)\n')
    (job / 'unrelated.txt').write_text('baseline\n')
    git(job, 'init', '-b', 'stage-smoke')
    git(job, 'add', '.gitignore', 'fixture.py', 'test_fixture.py', 'unrelated.txt')
    git(job, 'commit', '-m', 'test: baseline broken clamp fixture')
    baseline = git(job, 'rev-parse', 'HEAD')
    prompt = f'''Perform two dependent implementation stages yourself in this disposable repo. Do not delegate to any subagent.
Stage 1: fix ONLY fixture.py so clamp returns low below the range, high above it, and the original value inside it. test_fixture.py has 3 tests and must remain unchanged. Run python3 -m unittest -v. Write git diff output to evidence/stage1.patch and full passing unittest output to evidence/stage1-tests.txt, then commit only fixture.py.
Stage 2: add a regression test requiring ValueError when low > high; run python3 -m unittest -v and save its failing four-test output to evidence/stage2-red-tests.txt. Implement validation, rerun python3 -m unittest -v (exactly 4 tests expected). Write git diff output to evidence/stage2.patch and full passing unittest output to evidence/stage2-tests.txt, then commit this stage separately; never amend stage 1.
Do not change opencode.json, .gitignore or unrelated.txt. Return a concise stage table with commit SHAs and validation. Initial HEAD: {baseline}.'''
    start = time.monotonic()
    report = {'workspace': str(job), 'opencode_exit': None, 'usage': None}
    events_text = ''
    try:
        result = subprocess.run(['opencode', 'run', '--agent', 'build', '--model', MODEL, '--standalone', '--auto', '--format', 'json', prompt],
                                cwd=job, env=env, capture_output=True, text=True, timeout=300)
        report['model_run_seconds'] = round(time.monotonic() - start, 3)
        events_text = result.stdout
        report.update(opencode_exit=result.returncode, stderr=result.stderr[-1000:])
        code, output = tests_at(job)
        commits = [dict(zip(('sha', 'subject'), line.split('\t', 1)))
                   for line in git(job, 'log', '--reverse', '--format=%H%x09%s', baseline + '..HEAD').splitlines() if line]
        for commit in commits:
            commit['files'] = git(job, 'diff-tree', '--no-commit-id', '--name-only', '-r', commit['sha']).splitlines()
        report.update(independent_test_exit=code, tests=output, commits=commits, status=git(job, 'status', '--porcelain'),
                      checkpoints=collect_checkpoints(job, commits), events=summarize_events(events_text))
        roots = report['events']['sessionIDs']
        selection = ['--session', roots[0]] if len(roots) == 1 else ['--directory', str(job)]
        usage = subprocess.run(['node', str(ROOT / 'bin/setup.js'), 'usage', *selection, '--json'],
                               cwd=ROOT, capture_output=True, text=True, timeout=30)
        if usage.returncode == 0:
            report['usage'] = json.loads(usage.stdout)
            report['children'] = [s for s in report['usage'].get('sessions', []) if s.get('id') != report['usage']['root']['id']]
        else:
            report['usage_error'] = usage.stderr[-500:]
    except subprocess.TimeoutExpired as error:
        if error.cmd and error.cmd[:2] == ['opencode', 'run']:
            events_text = error.stdout or events_text
            if isinstance(events_text, bytes):
                events_text = events_text.decode(errors='replace')
            report['interrupts'] = interrupt_sessions(events_text)
        report['error'] = 'timeout'
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report['error'] = str(error)
    report['elapsed_seconds'] = round(time.monotonic() - start, 2)
    (artifacts / 'build-only-events.jsonl').write_text(events_text)
    spec = spec_from_file_location('baseline_verifier', ROOT / 'scripts/verify-baseline-result.py')
    verifier = module_from_spec(spec)
    spec.loader.exec_module(verifier)
    report['verification'] = {'failures': verifier.verify(report)}
    report['verification']['passed'] = not report['verification']['failures']
    (artifacts / 'build-only-result.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k not in ('usage', 'checkpoints')}, indent=2))
    if not report['verification']['passed']:
        return 1
    mixed = artifacts / 'stage-usage.json'
    if mixed.exists():
        compare = subprocess.run(['node', str(ROOT / 'bin/setup.js'), 'usage', '--session', json.loads(mixed.read_text())['root']['id'],
                                  '--compare', report['usage']['root']['id']], cwd=ROOT, capture_output=True, text=True, timeout=30)
        (artifacts / 'usage-comparison.txt').write_text(compare.stdout)
        print(compare.stdout.split('Comparison', 1)[-1])
    return 0


if __name__ == '__main__':
    sys.exit(main())
