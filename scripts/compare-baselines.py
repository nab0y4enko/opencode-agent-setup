"""Verify completed benchmark artifacts against Git and read-only native records.

Does not start inference. Run after stage-commit-smoke.py and build-only-baseline.py.
"""
import argparse
import hashlib
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location

ROOT = pathlib.Path(__file__).resolve().parent.parent


def module(name, file):
    spec = spec_from_file_location(name, ROOT / 'scripts' / file)
    loaded = module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def reconcile(report, db, outcomes=('succeeded',)):
    """Independently sum raw stored counters; do not use the usage analyzer."""
    root = report['usage']['root']['id']
    sessions = db.execute('''WITH RECURSIVE tree(id) AS (
      SELECT id FROM session_v2 WHERE id=? UNION ALL
      SELECT s.id FROM session_v2 s JOIN tree t ON s.parent_id=t.id
    ) SELECT s.id,s.agent,s.model,s.time_idle,s.idle_outcome FROM session_v2 s JOIN tree t ON s.id=t.id''', (root,)).fetchall()
    assert {s[0] for s in sessions} == {s['id'] for s in report['usage']['sessions']}, 'Session tree mismatch'
    assert all(s[3] and s[4] in outcomes for s in sessions), 'A session has an unexpected or incomplete outcome'
    result = {}
    recorded = []
    for sid, agent, model, idle, outcome in sessions:
        counters = dict.fromkeys(('input', 'output', 'reasoning', 'cacheRead', 'cacheWrite'), 0)
        tools = {}
        rows = db.execute("SELECT data FROM session_message WHERE session_id=? AND type IN ('assistant','compaction') ORDER BY seq", (sid,)).fetchall()
        for row in rows:
            data = json.loads(row[0])
            for part in data.get('content', []):
                if part.get('type') == 'tool':
                    tool = part.get('name', 'unknown')
                    tools[tool] = tools.get(tool, 0) + 1
            tokens = data.get('tokens') or {}
            cache = tokens.get('cache') or {}
            for key in ('input', 'output', 'reasoning'):
                counters[key] += tokens.get(key, 0)
            counters['cacheRead'] += cache.get('read', 0)
            counters['cacheWrite'] += cache.get('write', 0)
            recorded.append(data.get('cost'))
        actual = next(s for s in report['usage']['sessions'] if s['id'] == sid)
        assert counters == actual['tokens'], f'Token mismatch for {sid}'
        if agent == 'orchestrator':
            assert set(tools) <= {'subagent', 'read', 'glob', 'grep', 'list', 'lsp', 'question'}, 'Coordinator exceeded read/delegation scope'
        if agent == 'cloud-reviewer':
            assert set(tools) <= {'read'}, 'Reviewer exceeded read-only scope'
        if agent in ('general', 'cloud-reviewer'):
            assert 'subagent' not in tools, 'Worker delegated unexpectedly'
        result[sid] = {'agent': agent, 'model': json.loads(model), 'messages': len(rows), 'tokens': counters, 'tools': tools, 'outcome': outcome}
    total = {key: sum(s['tokens'][key] for s in result.values()) for key in counters}
    assert total == report['usage']['totals']['all']['raw'], 'Aggregate token mismatch'
    return {'sessions': result, 'raw': total, 'recorded_cost_values': sorted(set(recorded), key=lambda x: -1 if x is None else x),
            'recorded_cost_sum': sum(c or 0 for c in recorded),
            'actual_dollar_cost': None if any(c is None or c == 0 for c in recorded) else sum(recorded)}


def verify_checkpoints(report, capture, verifier):
    checkpoints = capture.collect_checkpoints(pathlib.Path(report['workspace']), report['commits'])
    assert len(checkpoints) == 2, 'Missing stage checkpoints'
    for index, cp in enumerate(checkpoints):
        count = index + 3
        assert cp['independent_test_exit'] == 0 and verifier.test_run(cp['tests'], count), 'Stage replay failed'
        assert cp['patch'].strip() == cp['artifact_patch'].strip() and cp['patch'].strip(), 'Patch artifact differs'
        assert verifier.test_run(cp['artifact_tests'], count), 'Passing test artifact missing'
        if index == 1:
            assert cp['regression_exit'] != 0 and verifier.test_run(cp['regression_tests'], 4, False), 'Regression is ineffective'
            assert 'ValueError not raised' in cp['regression_tests'], 'Unexpected regression failure'
            assert verifier.test_run(cp['artifact_red_tests'], 4, False) and 'ValueError not raised' in cp['artifact_red_tests'], 'Missing model red evidence'
    return checkpoints


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--failed-build-attempt', action='append', default=[], type=pathlib.Path,
                        help='Explicit archived failed result with capturedUsage; retained in total effort')
    args = parser.parse_args()
    artifacts = ROOT / 'artifacts'
    reports = {name: json.loads((artifacts / file).read_text()) for name, file in
               [('mixed', 'stage-commit-result.json'), ('buildOnly', 'build-only-result.json')]}
    capture = module('capture', 'build-only-baseline.py')
    verifier = module('verifier', 'verify-baseline-result.py')
    stage = subprocess.run([sys.executable, str(ROOT / 'scripts/verify-stage-result.py'), str(artifacts / 'stage-commit-result.json')], capture_output=True, text=True, timeout=30)
    assert stage.returncode == 0, stage.stdout + stage.stderr
    assert not verifier.verify(reports['buildOnly']), verifier.verify(reports['buildOnly'])
    dbpath = pathlib.Path(os.environ.get('XDG_DATA_HOME', pathlib.Path.home() / '.local/share')) / 'opencode/opencode.db'
    starting = []
    verified = {}
    failed_attempts = []
    with sqlite3.connect(dbpath.as_uri() + '?mode=ro', uri=True) as db:
        for name, report in reports.items():
            job = pathlib.Path(report['workspace'])
            expected = ({'orchestrator': 'openai/gpt-6.1-sol#medium', 'general': 'omlx/qwen-3.8-nf-splash#default',
                         'build': 'openai/gpt-6.1-sol#high', 'cloud-reviewer': 'openai/gpt-6.1-sol#high'}
                        if name == 'mixed' else {'build': 'openai/gpt-6.1-sol#high'})
            if name == 'mixed' and report.get('profile') == 'local-first':
                expected = {'orchestrator': 'omlx/qwen-3.8-nf-splash#default', 'general': 'omlx/qwen-3.8-nf-splash#default'}
            if name == 'mixed' and report.get('profile') == 'cloud-led':
                expected = {'orchestrator': 'openai/gpt-6.1-sol#medium', 'general': 'omlx/qwen-3.8-nf-splash#default'}
            assert {b['agent'] for b in report['usage']['breakdown']} == set(expected), 'Unexpected actual agents'
            assert all(b['model'] == expected[b['agent']] and b['errors'] == 0 for b in report['usage']['breakdown']), 'Actual model/error mismatch'
            initial = capture.git(job, 'rev-parse', report['commits'][0]['sha'] + '^')
            blobs = {file: hashlib.sha256(subprocess.check_output(['git', 'show', initial + ':' + file], cwd=job)).hexdigest()
                     for file in ('.gitignore', 'fixture.py', 'test_fixture.py', 'unrelated.txt')}
            starting.append(blobs)
            # Recheck the live final tree; artifact success alone is insufficient.
            code, output = capture.tests_at(job)
            assert code == 0 and verifier.test_run(output, 4), 'Final tests failed'
            grid = subprocess.run([sys.executable, '-c', '''from fixture import clamp
checks=0
for low in range(-3,4):
 for high in range(-3,4):
  for value in range(-6,7):
   if low > high:
    try: clamp(value,low,high)
    except ValueError: pass
    else: raise AssertionError('inverted bounds accepted')
   else: assert clamp(value,low,high) == max(low,min(value,high))
   checks+=1
print(checks)
'''], cwd=job, capture_output=True, text=True, timeout=30)
            assert grid.returncode == 0, grid.stdout + grid.stderr
            assert capture.git(job, 'status', '--porcelain') == '', 'Final worktree is dirty'
            for file in ('.gitignore', 'unrelated.txt'):
                assert hashlib.sha256((job / file).read_bytes()).hexdigest() == blobs[file], 'Unrelated file changed'
            verified[name] = {'profile': report.get('profile', 'native' if name == 'buildOnly' else 'legacy'), 'root': report['usage']['root']['id'], 'workspace': str(job), 'initial_file_sha256': blobs,
                              'model_run_seconds': report['model_run_seconds'],
                              'commits': report['commits'], 'final_tests': output,
                              'independent_integer_cases': int(grid.stdout),
                              'checkpoints': verify_checkpoints(report, capture, verifier),
                              'native_reconciliation': reconcile(report, db),
                              'totals': report['usage']['totals'], 'byAgent': report['usage']['byAgent']}
        for failed_path in args.failed_build_attempt:
            failed = json.loads(failed_path.read_text())
            failed['usage'] = failed['capturedUsage']
            assert failed['error'] == 'timeout' and all(i['interrupted'] for i in failed['interrupts']), 'Unconfirmed failed-attempt cleanup'
            failed_job = pathlib.Path(failed['workspace'])
            initial = capture.git(failed_job, 'rev-list', '--max-parents=0', 'HEAD')
            assert {file: hashlib.sha256(subprocess.check_output(['git', 'show', initial + ':' + file], cwd=failed_job)).hexdigest()
                    for file in starting[1]} == starting[1], 'Failed attempt used a different fixture'
            failed_attempts.append({'approach': 'buildOnly', 'root': failed['usage']['root']['id'],
                                    'attempt_elapsed_seconds': failed['elapsed_seconds'],
                                    'error': failed['error'], 'native_reconciliation': reconcile(failed, db, outcomes=('interrupted',)),
                                    'totals': failed['usage']['totals']})
    assert starting[0] == starting[1], 'Starting task fixtures differ'
    mixed, build = (verified[name] for name in ('mixed', 'buildOnly'))
    comparisons = {'mixed_time_ratio': mixed['model_run_seconds'] / build['model_run_seconds'],
                   'mixed_cloud_input_ratio': mixed['totals']['cloud']['raw']['input'] / build['totals']['cloud']['raw']['input'],
                   'mixed_cloud_weighted_ratio': mixed['totals']['cloud']['weighted'] / build['totals']['cloud']['weighted']}
    all_attempts = {}
    for name, run in verified.items():
        failed = [a for a in failed_attempts if a['approach'] == name]
        totals = [run['totals'], *[a['totals'] for a in failed]]
        all_attempts[name] = {'attempts': 1 + len(failed),
                              'summed_attempt_seconds': run['model_run_seconds'] + sum(a['attempt_elapsed_seconds'] for a in failed),
                              'raw': {group: {key: sum(t[group]['raw'][key] for t in totals) for key in totals[0][group]['raw']}
                                      for group in ('cloud', 'local', 'all')},
                              'actual_dollar_cost': None}
    evidence = {'passed': True, 'scope': 'One accepted run per approach; mixed first. Explicit failed attempts retained. Completed run timing covers CLI launch through exit; failed timing includes interruption. Inter-attempt gaps excluded. No invoice data or energy measurement.',
                'runs': verified, 'failed_attempts': failed_attempts, 'all_attempts': all_attempts, 'comparison': comparisons}
    (artifacts / 'baseline-comparison.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({'passed': True, 'comparison': comparisons, 'runs': {name: {key: value for key, value in run.items() if key in ('root', 'model_run_seconds', 'totals', 'byAgent')} for name, run in verified.items()}}, indent=2))


if __name__ == '__main__':
    main()
