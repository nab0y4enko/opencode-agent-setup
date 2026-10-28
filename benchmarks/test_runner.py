"""Offline runner tests: fake CLIs exercise the real gates. No network, no model, no paid call."""
import contextlib
import io
import json
import os
import sqlite3
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent))
import accounting as A
import fixtures as FX
import run as R
import test_runner_helpers as H
(ROOT, CHILD) = (H.ROOT_ID, H.CHILD_ID)
(SOL, LUNA) = ('gpt-6.1-sol', 'gpt-6-luna')
LOCAL = 'omlx/qwen-3.8-nf-splash'
SHA = 'a' * 64
(FAKE_ROOT, FAKE_CHILD) = ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002')
OPENCODE_KW = dict(expected_cloud_provider='openai', expected_cloud_model=SOL, expected_local_provider='omlx', expected_local_model=LOCAL)

def hybrid(**kwargs):
    kwargs.setdefault('verdict_text', 'VERDICT: PASS ' + SHA)
    return A.account_opencode(H.hybrid_snapshot('root0', '/tmp/fixture', **kwargs), root_session_ids=['root0'], **OPENCODE_KW)

def codex_catalog(child_usage=True, child_model=LUNA, root_model=SOL, effort='medium', root_edits=0, timestamps=True):
    root = H.catalog_entry(ROOT, model=root_model, effort=effort, edit_calls=root_edits, total=H.usage(1000, 400, 200, 50), assistant='VERDICT: PASS ' + SHA)
    child = H.catalog_entry(CHILD, parent_id=ROOT, model=child_model, effort=effort, total=H.usage(500, 100, 100, 20) if child_usage else None)
    if not timestamps:
        for entry in (root, child):
            entry['first_event'] = entry['last_event'] = None
    return {ROOT: root, CHILD: child}

def codex_accounting(catalog=None, **overrides):
    catalog = catalog or codex_catalog(**overrides)
    kwargs = dict(root_thread_id=ROOT, expected_root_model=SOL, expected_child_model=LUNA)
    return A.account_codex(catalog, sorted(catalog), **kwargs)

class AccountingEvidenceFeedsTheRunnerGates(unittest.TestCase):
    """What the runner reads out of accounting. The per-doubt unit assertions live in
    test_accounting.py (CodexUsage, CodexFailClosed, CodexRolloutFiles, VerdictSemantics,
    OpenCodeAccounting), so each behavior is asserted exactly once across the suite."""

    def test_codex_totals_window_and_final_text_reach_the_codex_gates(self):
        result = codex_accounting()
        self.assertEqual(result['cloud_total'], 1800)
        self.assertEqual(result['root_final_text'], 'VERDICT: PASS ' + SHA)
        self.assertTrue(result['recorded_window']['first_event'])
        self.assertTrue(result['routing_ok'] and result['usage_complete'], result['blockers'])
        self.assertTrue(result['recorded_window']['first_event'] and not codex_accounting(timestamps=False)['recorded_window']['first_event'])
        gap = codex_accounting(child_usage=False)
        self.assertIsNone(gap['cloud_total'])
        self.assertEqual(gap['known_lower_bound'], 1200)
        self.assertFalse(gap['usage_complete'])

    def test_rollout_files_are_scanned_into_the_tree_the_runner_accounts(self):
        with tempfile.TemporaryDirectory() as raw:
            sessions = Path(raw) / 'sessions' / '2026-10-26'
            H.write_rollout(sessions / (ROOT + '.jsonl'), ROOT, '/tmp/fixture', usage_total=H.usage(300, 100, 50, 10), assistant='VERDICT: PASS ' + SHA, spawn_ids=(CHILD,))
            H.write_rollout(sessions / (CHILD + '.jsonl'), CHILD, '/tmp/fixture', parent_id=ROOT, model=LUNA, usage_total=H.usage(100, 0, 20, 0))
            catalog = A.scan_codex_rollouts(Path(raw) / 'sessions')
            self.assertEqual(A.codex_tree(catalog, ROOT), sorted([ROOT, CHILD]))
            self.assertEqual(catalog[ROOT]['completion'], 'complete')
            self.assertRaises(A.PreflightBlocker, A.codex_tree, catalog, 'missing-thread')

    def test_hybrid_completion_and_routing_doubts_are_visible_to_the_runner(self):
        result = hybrid()
        self.assertEqual((result['known_lower_bound'], result['local_total'], result['unknown_maintenance_total']), (2000, 700, 200))
        self.assertEqual(result['cloud_cost_range']['status'], 'cloud_exact_unknown')
        self.assertEqual([session['idle_outcome'] for session in result['sessions']], ['ready'] * 3)
        self.assertEqual(hybrid(maintenance_extra=0)['cloud_total'], 2000)
        for (label, kwargs) in (('no idle outcome', {'idle': ''}), ('no idle timestamp', {'time_idle': None}), ('low reasoning variant', {'cloud_variant': 'low'}), ('third dispatch', {'dispatches': 3}), ('root implemented', {'root_edit': True}), ('no reviewer session', {'include_review': False}), ('wrong reviewer model', {'review_model_id': 'gpt-4o-mini'}), ('answer without a recorded model', {'root_answer_model': False})):
            with self.subTest(case=label):
                doubt = hybrid(**kwargs)
                self.assertFalse(doubt['routing_ok'] and doubt['usage_complete'], (label, doubt['blockers']))
                self.assertTrue(doubt['blockers'], label)

class AcceptanceGates(unittest.TestCase):
    manifest = {'expected_tests': 12, 'allowed_changed': ['ttl_cache.py'], 'frozen_files': [], 'fixture_sha256': {}, 'frozen_utc': 'now', 'models': {}, 'budget': {'initial': 1, 'repair': 1, 'wall_clock_seconds_per_arm': 180}, 'machine': {}, 'task': 'task'}

    def evaluate(self, verdict_source=None, **overrides):
        parts = {'check': {'ok': True, 'all_tests_expected': True, 'tests_run': 12, 'failures': 0, 'errors': 0, 'returncode': 0}, 'scope': {'scope_ok': True, 'frozen_intact': True, 'base_intact': True, 'untracked': [], 'changed': ['ttl_cache.py'], 'digest': SHA}, 'verdict': {'status': 'pass', 'digest_matches': True}, 'accounting': {'routing_ok': True, 'usage_complete': True, 'blockers': [], 'known_lower_bound': 100}, 'execution': {'exit_code': 0, 'timed_out': False, 'argv': ['codex', 'exec', '--json'], 'seconds': 12, 'total_seconds': 12, 'deadline_enforced': True}}
        for (name, updates) in overrides.items():
            parts[name].update(updates)
        source = verdict_source or {'kind': 'cli', 'authoritative': True}
        return R.evaluate_arm('codex', 'codex-cli', self.manifest, parts['accounting'], parts['check'], parts['scope'], parts['verdict'], parts['execution'], source)

    def test_clean_arm_is_accepted_with_every_gate_green(self):
        result = self.evaluate()
        self.assertTrue(result['accepted'])
        self.assertEqual(result['blockers'], [])
        self.assertTrue(all(result['gates'].values()), result['gates'])

    def test_each_refusal_names_its_gate_and_a_reason(self):
        cases = {'semantic_verdict_pass': ({'verdict': {'status': 'forged', 'digest_matches': False}}, 'fenced VERDICT'),
                 'verdict_bound_to_current_digest': ({'verdict': {'status': 'pass', 'digest_matches': False}}, 'digest does not equal'),
                 'verdict_from_authoritative_reviewer': ({'verdict_source': {'kind': 'app', 'authoritative': False}}, 'authoritative reviewer channel'),
                 'routing_expected': ({'accounting': {'routing_ok': False}}, 'frozen root/child model'),
                 'usage_complete': ({'accounting': {'usage_complete': False}}, 'lower bound'),
                 'scope_only_allowed_paths': ({'scope': {'scope_ok': False, 'untracked': ['extra.py']}}, 'scope drift'),
                 'frozen_test_and_readme_intact': ({'scope': {'scope_ok': False, 'frozen_intact': False}}, 'frozen fixture files changed'),
                 'frozen_base_commit_intact': ({'scope': {'scope_ok': False, 'base_intact': False}}, 'frozen fixture base'),
                 'tests_all_and_pass': ({'check': {'ok': False, 'tests_run': 11}}, 'check reported 11 tests'),
                 'within_deadline': ({'execution': {'timed_out': True}}, 'deterministic deadline'),
                 'check_exit_clean': ({'check': {'returncode': 3}}, 'check process exited 3'),
                 'within_total_budget': ({'execution': {'total_seconds': 181}}, 'going over the frozen budget'),
                 'clean_exit': ({'execution': {'exit_code': 3}}, 'exited 3'),
                 'native_permissions_not_bypassed': ({'execution': {'argv': ['codex', '--yolo']}}, 'bypasses installed native permission')}
        for (gate, (overrides, phrase)) in cases.items():
            overrides = dict(overrides)
            with self.subTest(gate=gate):
                source = overrides.pop('verdict_source', None)
                result = self.evaluate(verdict_source=source, **overrides)
                self.assertFalse(result['gates'][gate])
                self.assertFalse(result['accepted'])
                self.assertTrue(any((phrase in blocker) for blocker in result['blockers']), (gate, result['blockers']))

    def test_independent_check_must_be_all_twelve_and_green(self):
        self.assertTrue(R.parse_check('Ran 12 tests in 0.1s\n\nOK\n', 12)['ok'])
        for (label, log) in (('one test short', 'Ran 11 tests in 0.1s\n\nOK\n'), ('a failure', 'Ran 12 tests in 0.1s\n\nFAILED (failures=1)\n'), ('an error', 'Ran 12 tests in 0.1s\n\nFAILED (errors=2)\n')):
            with self.subTest(case=label):
                self.assertFalse(R.parse_check(log, 12)['ok'])
        self.assertFalse(R.parse_check('Ran 12 tests in 0.1s\n\nOK\n', 13)['all_tests_expected'])

    def test_doubtful_native_routing_or_usage_refuses_a_otherwise_green_arm(self):
        for (label, accounting) in (('wrong reviewer', hybrid(review_model_id='gpt-4o-mini')), ('third dispatch', hybrid(dispatches=3)), ('no idle outcome', hybrid(idle='')), ('low reasoning variant', hybrid(cloud_variant='low')), ('root implemented', hybrid(root_edit=True))):
            with self.subTest(case=label):
                result = self.evaluate(accounting=accounting)
                self.assertFalse(result['accepted'])
                self.assertTrue(result['blockers'])

    def test_a_green_suite_never_outvotes_a_nonzero_check_exit_or_a_spent_budget(self):
        for (label, overrides, phrase) in (('the check process exited 3', {'check': {'returncode': 3}}, 'check process exited 3'),
                                           ('the check never started', {'check': {'ok': False, 'returncode': None, 'skipped': 'arm deadline already expired'}}, 'never ran'),
                                           ('181s spent of a 180s budget', {'execution': {'total_seconds': 181}}, '181s of the frozen 180s budget'),
                                           ('duration never recorded', {'execution': {'total_seconds': None, 'seconds': None}}, 'unknown duration'),
                                           ('desktop window over budget', {'execution': {'total_seconds': 220, 'deadline_enforced': False}}, 'desktop App session window plus final verification')):
            with self.subTest(case=label):
                result = self.evaluate(**overrides)
                self.assertFalse(all(result['gates'].values()), (label, result['gates']))
                self.assertFalse(result['accepted'])
                self.assertTrue(any((phrase in blocker) for blocker in result['blockers']), (label, result['blockers']))

class LaunchPolicy(unittest.TestCase):
    manifest = {'models': {'codex_cloud': SOL, 'codex_child': LUNA, 'opencode_cloud': 'openai/' + SOL + '#medium', 'local': LOCAL, 'effort': 'medium'}, 'binaries': {'codex': '/usr/local/bin/codex', 'opencode': '/usr/local/bin/opencode'}, 'arms': {'codex': {'repo': '/tmp/arm/repo'}}}

    def test_planned_argv_overrides_only_the_session(self):
        codex = R.codex_argv(self.manifest, Path('/tmp/arm/repo'), 'prompt')
        self.assertEqual(R.permission_blockers(codex), [])
        self.assertEqual(R.permission_blockers(R.opencode_argv(self.manifest, 'prompt')), [])
        self.assertIn('--sandbox', codex)
        # Full access is the owner's daily Codex mode and was approved for the benchmark; it is chosen
        # through the documented sandbox mode, never through a bypass flag.
        self.assertEqual(codex[codex.index('--sandbox') + 1], 'danger-full-access')
        self.assertIn('agents.max_concurrent_threads_per_session=4', codex)
        self.assertNotIn('--config', codex)
        self.assertEqual(codex[codex.index('--model') + 1], SOL)

    def test_bypassed_permissions_or_global_config_are_refused(self):
        for argv in (['codex', '--yolo', 'exec'], ['codex', '--dangerously-bypass-approvals-and-sandbox'], ['opencode', 'run', '--auto'], ['codex', '--config', 'model=x'], ['opencode', '--global']):
            with self.subTest(argv=argv):
                self.assertTrue(R.permission_blockers(argv))

    def test_output_must_be_fresh_and_outside_the_repository(self):
        self.assertRaises(A.PreflightBlocker, R.resolve_out, str(R.REPO_ROOT / 'runs' / 'here'), fresh=True)
        with tempfile.TemporaryDirectory() as raw:
            existing = Path(raw) / 'used'
            existing.mkdir()
            self.assertRaises(A.PreflightBlocker, R.resolve_out, str(existing), fresh=True)
            self.assertRaises(A.PreflightBlocker, R.resolve_out, str(existing), fresh=False)
            prepared = Path(raw) / 'prepared'
            prepared.mkdir()
            (prepared / 'manifest.json').write_text('{}', encoding='utf-8')
            self.assertEqual(R.resolve_out(str(prepared), fresh=False), prepared.resolve())

    def test_help_is_runnable_and_lists_every_command(self):
        text = R.parser().format_help()
        for command in ('prepare', 'run', 'finish', 'report', 'compare'):
            self.assertIn(command, text)

class OwnedCleanup(unittest.TestCase):

    def setUp(self):
        self.raw = tempfile.mkdtemp()
        self.out = Path(self.raw) / 'out'
        self.user = Path(self.raw) / 'user-work'
        self.user.mkdir()
        (self.user / 'precious.txt').write_text('do not delete', encoding='utf-8')
        self.repo = self.out / 'arms' / 'codex' / 'repo'
        self.repo.mkdir(parents=True)
        (self.repo / 'ttl_cache.py').write_text('x = 1\n', encoding='utf-8')
        self.git('-C', str(self.repo), 'init', '-q')
        self.git('-c', 'user.email=t@example.invalid', '-c', 'user.name=t', '-C', str(self.repo), 'add', '-A')
        self.git('-c', 'user.email=t@example.invalid', '-c', 'user.name=t', '-C', str(self.repo), 'commit', '-q', '-m', 'seed')

    def tearDown(self):
        shutil.rmtree(self.raw, ignore_errors=True)

    def git(self, *args):
        subprocess.run(['git', *args], check=True, capture_output=True)

    def manifest(self, repo):
        return {'arms': {'codex': {'repo': str(repo)}}, 'owned_paths': [str(repo), str(self.user)]}

    def test_a_forged_manifest_cannot_delete_a_user_path(self):
        report = R.archive_and_cleanup(self.out, self.manifest(self.user), 'codex')
        self.assertEqual(report['status'], 'blocked_not_owned')
        self.assertTrue((self.user / 'precious.txt').exists())

    def test_a_symlink_pointing_outside_the_run_blocks_cleanup(self):
        (self.repo / 'escape').symlink_to(self.user / 'precious.txt')
        report = R.archive_and_cleanup(self.out, self.manifest(self.repo), 'codex')
        self.assertEqual(report['status'], 'blocked_symlink_escape')
        self.assertTrue(self.repo.exists())
        self.assertTrue((self.user / 'precious.txt').exists())

    def test_verified_archive_and_bundle_remove_only_the_owned_checkout(self):
        (self.repo / 'internal.lnk').symlink_to(self.repo / 'ttl_cache.py')
        report = R.archive_and_cleanup(self.out, self.manifest(self.repo), 'codex')
        self.assertEqual(report['status'], 'archived_and_removed')
        self.assertTrue(report['tar_verified'] and report['bundle_verified'])
        self.assertEqual(len(report['tar_sha256']), 64)
        self.assertFalse(self.repo.exists())
        self.assertTrue((self.out / 'archives' / 'codex-repo.tar.gz').exists())
        self.assertTrue((self.user / 'precious.txt').exists())

    def test_an_alive_owned_process_tree_defers_removal(self):
        (self.out / 'arms' / 'codex').mkdir(parents=True, exist_ok=True)
        (self.out / 'arms' / 'codex' / 'result.json').write_text(json.dumps({'execution': {'process_group_still_alive': True}}), encoding='utf-8')
        report = R.archive_and_cleanup(self.out, self.manifest(self.repo), 'codex')
        self.assertEqual(report['status'], 'blocked_owned_processes_alive')
        self.assertTrue(self.repo.exists())

    def test_a_recorded_process_group_that_has_since_exited_no_longer_blocks_cleanup(self):
        finished = subprocess.Popen(['true'], start_new_session=True)
        finished.wait()
        (self.out / 'arms' / 'codex').mkdir(parents=True, exist_ok=True)
        (self.out / 'arms' / 'codex' / 'result.json').write_text(json.dumps({'execution': {'process_group_still_alive': True, 'pgid': finished.pid}}), encoding='utf-8')
        report = R.archive_and_cleanup(self.out, self.manifest(self.repo), 'codex')
        self.assertEqual(report['status'], 'archived_and_removed', report)
        self.assertFalse(self.repo.exists())

    def test_the_bundle_verifies_from_a_copied_checkout_without_any_git_repository_around_it(self):
        elsewhere = tempfile.mkdtemp()
        previous = os.getcwd()
        try:
            os.chdir(elsewhere)
            report = R.archive_and_cleanup(self.out, self.manifest(self.repo), 'codex')
        finally:
            os.chdir(previous)
            shutil.rmtree(elsewhere, ignore_errors=True)
        self.assertEqual(report['status'], 'archived_and_removed', report)
        self.assertTrue(report['bundle_verified'])

    def test_the_archive_preserves_the_build_folder_and_still_verifies(self):
        build = self.repo / '.bench-build' / 'DerivedData'
        build.mkdir(parents=True)
        (build / 'huge.o').write_bytes(b'0' * 4096)
        manifest = dict(self.manifest(self.repo), excluded=['.bench-build/'])
        report = R.archive_and_cleanup(self.out, manifest, 'codex')
        self.assertEqual(report['status'], 'archived_and_removed', report)
        with tarfile.open(self.out / 'archives' / 'codex-repo.tar.gz') as tar:
            names = tar.getnames()
        self.assertIn('codex/ttl_cache.py', names)
        self.assertIn('codex/.bench-build/DerivedData/huge.o', names)

    def test_a_symlinked_component_inside_the_run_is_refused_before_archive_or_delete(self):
        outside = Path(self.raw) / 'unrelated-tree'
        outside.mkdir()
        shutil.move(str(self.repo), str(outside / 'repo'))
        (self.out / 'arms' / 'codex' / 'repo').symlink_to(outside / 'repo')
        report = R.archive_and_cleanup(self.out, self.manifest(self.repo), 'codex')
        self.assertEqual(report['status'], 'blocked_symlinked_path')
        self.assertTrue((outside / 'repo' / 'ttl_cache.py').exists())
        self.assertFalse((self.out / 'archives' / 'codex-repo.tar.gz').exists())

    def test_a_symlinked_run_root_is_refused_before_its_resolve_can_reach_another_tree(self):
        elsewhere = Path(self.raw) / 'someone-elses-home'
        elsewhere.mkdir()
        shutil.move(str(self.out), str(elsewhere / 'run'))
        self.out.symlink_to(elsewhere / 'run')
        report = R.archive_and_cleanup(self.out, {'arms': {'codex': {'repo': str(self.out / 'arms' / 'codex' / 'repo')}}, 'owned_paths': []}, 'codex')
        self.assertEqual(report['status'], 'blocked_symlinked_path')
        self.assertTrue((elsewhere / 'run' / 'arms' / 'codex' / 'repo' / 'ttl_cache.py').exists())
        self.assertFalse((elsewhere / 'run' / 'archives').exists())
class CliEventLogs(unittest.TestCase):

    def test_the_root_thread_is_the_first_thread_started_event(self):
        with tempfile.TemporaryDirectory() as raw:
            log = Path(raw) / 'arm.stdout.log'
            log.write_text('\n'.join([json.dumps({'type': 'thread.started', 'thread_id': 'root-thread'}),
                                       json.dumps({'type': 'item.completed', 'thread_id': 'worker-thread'}),
                                       json.dumps({'type': 'thread.started', 'thread_id': 'worker-thread'}),
                                       'not json']), encoding='utf-8')
            self.assertEqual(R.root_thread_from_log(log), 'root-thread')
            log.write_text(json.dumps({'type': 'turn.completed'}), encoding='utf-8')
            self.assertIsNone(R.root_thread_from_log(log))

class FixtureCheckout(unittest.TestCase):

    def test_user_git_hooks_and_commit_signing_never_touch_the_frozen_baseline(self):
        with tempfile.TemporaryDirectory() as raw:
            hooks = Path(raw) / 'hooks'
            hooks.mkdir()
            (hooks / 'pre-commit').write_text('#!/bin/sh\necho hook-ran > "$(git rev-parse --git-dir)/../HOOK"\nexit 1\n', encoding='utf-8')
            (hooks / 'pre-commit').chmod(0o755)
            config = Path(raw) / 'gitconfig'
            config.write_text(f'[core]\n\thooksPath = {hooks}\n[commit]\n\tgpgsign = true\n[gpg]\n\tprogram = /nonexistent/gpg\n', encoding='utf-8')
            with mock.patch.dict(os.environ, {'GIT_CONFIG_GLOBAL': str(config)}):
                base = R.make_checkout(Path(raw) / 'repo', FX.get('ttl-python'))
            self.assertEqual(len(base), 40)
            self.assertFalse((Path(raw) / 'repo' / 'HOOK').exists())
            self.assertEqual(R.git(Path(raw) / 'repo', 'status', '--porcelain'), '')

class FixtureRegistry(unittest.TestCase):

    def test_ttl_python_keeps_its_original_task_check_and_budget(self):
        fixture = FX.get('ttl-python')
        self.assertEqual((fixture.expected_tests, fixture.expected_baseline_failures, fixture.default_budget), (12, 3, 180))
        self.assertEqual(fixture.allowed_changed, ['ttl_cache.py'])
        self.assertEqual(fixture.check_argv('codex'), ['python3', '-m', 'unittest', '-v'])
        self.assertEqual(A.sha256_bytes(fixture.task.encode()), 'b50159fe05707e38ee1b1ba9535dbb03f3ef70ff54f0b3cfbcf228d6e410d406')
        self.assertEqual(fixture.files(), ['README.md', 'test_ttl_cache.py', 'ttl_cache.py'])

    def test_swiftui_list_runs_its_frozen_check_on_the_arm_simulator(self):
        fixture = FX.get('swiftui-list')
        self.assertEqual(fixture.check_argv('opencode'), ['./check.sh', 'bench-opencode'])
        self.assertEqual((fixture.expected_tests, fixture.expected_baseline_failures), (12, 5))
        self.assertTrue(set(fixture.frozen_files) | set(fixture.allowed_changed) <= set(fixture.files()))
        self.assertFalse(set(fixture.frozen_files) & set(fixture.allowed_changed))
        prompts = R.build_prompts(fixture=fixture)
        self.assertIn('./check.sh bench-codex', prompts['codex'])
        self.assertIn('./check.sh bench-opencode', prompts['opencode'])
        self.assertTrue(prompts['codex'].startswith(fixture.task) and prompts['opencode'].startswith(fixture.task))

    def test_unknown_fixture_is_a_preflight_blocker(self):
        with self.assertRaises(A.PreflightBlocker):
            R.fixture_of({'fixture': 'kotlin-app'})

    def test_check_summary_fails_closed(self):
        parse = FX.get('swiftui-list').parse_check
        green = parse('TESTS total=12 passed=12 failed=0 skipped=0\n')
        self.assertTrue(green['ok'])
        red = parse('TESTS total=12 passed=7 failed=5 skipped=0\n' + ''.join(f'FAILED T/t{i}(): x\n' for i in range(5)))
        self.assertEqual((red['ok'], red['failures'], len(red['failed_tests'])), (False, 5, 5))
        for broken in ('', 'TESTS total=0 passed=0 failed=0 skipped=0\nERROR no result bundle\n',
                       'TESTS total=12 passed=12 failed=0 skipped=0\nTESTS total=12 passed=12 failed=0 skipped=0\n',
                       'TESTS total=12 passed=11 failed=0 skipped=1\n', 'TESTS total=12 passed=10 failed=0 skipped=0\n',
                       'TESTS total=11 passed=11 failed=0 skipped=0\n'):
            with self.subTest(broken=broken):
                self.assertFalse(parse(broken)['ok'])
        self.assertEqual(parse('')['tests_run'], 0)

class SimulatorLifecycle(unittest.TestCase):
    """Only simulators this run created, recorded by UDID and still carrying its name, are ever deleted."""

    RUNTIMES = {'runtimes': [{'platform': 'iOS', 'isAvailable': True, 'version': '27.0', 'identifier': 'rt-27',
                              'supportedDeviceTypes': [{'productFamily': 'iPhone', 'identifier': 'dt-iphone'}]}]}

    def fake(self, devices):
        calls = []

        def simctl(*args):
            calls.append(args)
            if args[:2] == ('list', 'devices'):
                return json.dumps({'devices': {'rt-27': devices}})
            if args[:2] == ('list', 'runtimes'):
                return json.dumps(self.RUNTIMES)
            if args[0] == 'create':
                return 'NEW-UDID\n'
            return ''
        return calls, mock.patch.object(R, 'simctl', simctl)

    def test_an_existing_bench_simulator_is_refused_and_untouched(self):
        (calls, patch) = self.fake([{'name': 'bench-codex', 'udid': 'THEIRS', 'state': 'Booted'}])
        with patch, self.assertRaises(A.PreflightBlocker):
            R.simulator_create('bench-codex')
        self.assertFalse([c for c in calls if c[0] in ('create', 'delete', 'shutdown', 'erase')])

    def test_create_records_the_newest_runtime_and_an_iphone(self):
        (calls, patch) = self.fake([])
        with patch:
            record = R.simulator_create('bench-codex')
        self.assertEqual((record['udid'], record['runtime'], record['device_type']), ('NEW-UDID', 'rt-27', 'dt-iphone'))
        self.assertIn(('create', 'bench-codex', 'dt-iphone', 'rt-27'), calls)

    def test_delete_only_the_recorded_device_with_a_matching_name(self):
        record = {'name': 'bench-codex', 'udid': 'U1'}
        (calls, patch) = self.fake([{'name': 'renamed-by-user', 'udid': 'U1', 'state': 'Shutdown'}])
        with patch:
            self.assertEqual(R.simulator_delete(record)['status'], 'blocked_name_mismatch')
        self.assertFalse([c for c in calls if c[0] == 'delete'])
        (calls, patch) = self.fake([{'name': 'bench-codex', 'udid': 'U1', 'state': 'Booted'},
                                    {'name': 'bench-codex-mine', 'udid': 'U2', 'state': 'Booted'}])
        with patch:
            self.assertEqual(R.simulator_delete(record)['status'], 'deleted')
        self.assertEqual([c for c in calls if c[0] in ('shutdown', 'delete')], [('shutdown', 'U1'), ('delete', 'U1')])
        (calls, patch) = self.fake([])
        with patch:
            self.assertEqual(R.simulator_delete(record)['status'], 'already_absent')

    def test_a_wrong_baseline_blocks_the_run(self):
        fixture = FX.get('swiftui-list')
        self.assertEqual(R.baseline_blockers(fixture, {'tests_run': 12, 'failures': 5, 'errors': 0}), [])
        for wrong in ({'tests_run': 12, 'failures': 0, 'errors': 0}, {'tests_run': 0, 'failures': 0, 'errors': 1},
                      {'tests_run': 11, 'failures': 5, 'errors': 0}):
            with self.subTest(wrong=wrong):
                self.assertTrue(R.baseline_blockers(fixture, wrong))

class FakeCliHarness(unittest.TestCase):
    timeout = 60

    def setUp(self):
        self.raw = Path(tempfile.mkdtemp())
        self.home = self.raw / 'codexhome'
        self.home.mkdir()
        self.db = H.make_db(self.raw / 'opencode.db', [])
        self.config = H.native_config(self.raw / 'native', 'omlx/test-local')
        self.out = self.raw / 'run'
        self.opencode = H.write_fake(self.raw / 'bin', 'opencode', H.FAKE_OPENCODE, {'db': str(self.db), 'root_id': 'ses_root', 'child_id': 'ses_local', 'review_id': 'ses_review', 'local_model_id': 'test-local'})

    def tearDown(self):
        shutil.rmtree(self.raw, ignore_errors=True)

    def codex(self, **overrides):
        cfg = {'codex_home': str(self.home), 'root_id': FAKE_ROOT, 'child_id': FAKE_CHILD, 'root_model': SOL, 'child_model': LUNA, 'root_input': 100, 'root_cached': 80, 'root_output': 20, 'root_reasoning': 5, 'root_total': 120, 'child_input': 50, 'child_cached': 40, 'child_output': 10, 'child_reasoning': 2, 'child_total': 60}
        cfg.update(overrides)
        return H.write_fake(self.raw / 'bin', 'codex', H.FAKE_CODEX, cfg)

    def frozen(self, codex_cfg=None):
        return ['--out', str(self.out), '--label', 'mac-test', '--local-model', 'omlx/test-local', '--codex-bin', self.codex(**(codex_cfg or {})), '--opencode-bin', self.opencode, '--codex-home', str(self.home), '--opencode-db', str(self.db), '--opencode-config', self.config, '--timeout', str(self.timeout)]

    def cli(self, argv):
        captured = io.StringIO()
        with contextlib.ExitStack() as streams:
            streams.enter_context(contextlib.redirect_stdout(captured))
            streams.enter_context(contextlib.redirect_stderr(captured))
            code = R.main(argv)
        return (code, captured.getvalue())

    def live(self, codex_cfg=None):
        return self.cli(['run'] + self.frozen(codex_cfg) + ['--live'])

    def arm(self, name):
        return json.loads((self.out / 'arms' / name / 'result.json').read_text('utf-8'))

    def report(self):
        return json.loads((self.out / 'report.json').read_text('utf-8'))

    def hybrid_rows(self):
        conn = sqlite3.connect(str(self.db))
        try:
            return conn.execute('select count(*) from session_v2').fetchone()[0]
        except sqlite3.Error:
            return 0

class TwoArmFakeRun(FakeCliHarness):

    def test_run_without_live_launches_no_model_and_freezes_the_plan(self):
        (code, text) = self.cli(['run'] + self.frozen())
        self.assertEqual(code, 0, text)
        self.assertEqual(list(self.home.rglob('*.jsonl')), [])
        self.assertFalse((self.out / 'arms' / 'codex' / 'arm.stdout.log').exists())
        self.assertEqual(self.hybrid_rows(), 0)
        plan = json.loads((self.out / 'dry-run-plan.json').read_text('utf-8'))
        self.assertFalse(plan['models_launched'])
        self.assertEqual(plan['blockers'], [])
        self.assertEqual(plan['budget'], {'wall_clock_seconds_per_arm': 60, 'initial': 1, 'repair': 1, 'max_workers': 4})
        self.assertIn('--sandbox', plan['planned_argv']['codex'])
        self.assertIn('hybrid', plan['planned_argv']['opencode'])

    def test_both_arms_are_measured_then_the_report_regenerates_offline(self):
        (code, text) = self.live()
        self.assertEqual(code, 0, text)
        codex = self.arm('codex')
        self.assertTrue(codex['accepted'], codex['blockers'])
        self.assertEqual(codex['accounting']['cloud_total'], 180)
        self.assertEqual(codex['client'], 'codex-cli')
        hybrid = self.arm('opencode')
        self.assertTrue(hybrid['accepted'], hybrid['blockers'])
        self.assertEqual((hybrid['accounting']['local_total'], hybrid['accounting']['known_lower_bound'], hybrid['accounting']['unknown_maintenance_total']), (700, 2000, 200))
        self.assertIsNone(hybrid['accounting']['cloud_total'])
        self.assertEqual(hybrid['accounting']['cloud_cost_range']['status'], 'cloud_exact_unknown')
        report = self.report()
        self.assertEqual(report['accepted_arms'], ['codex', 'opencode'])
        self.assertEqual(report['native_config_integrity']['status'], 'unchanged')
        self.assertEqual(report['metrics']['cloud_tokens_per_completed_task']['codex'], 180.0)
        self.assertIsNone(report['metrics']['cloud_tokens_per_completed_task']['opencode'])
        self.assertEqual(report['metrics']['per_arm_completed_tasks'], {'codex': 1, 'opencode': 1})
        self.assertIn('# Benchmark report', (self.out / 'REPORT.md').read_text('utf-8'))
        manifest = R.load_manifest(self.out)
        for arm in ('codex', 'opencode'):
            self.assertFalse(Path(manifest['arms'][arm]['repo']).exists())
            self.assertTrue((self.out / 'archives' / (arm + '-repo.tar.gz')).exists())
        self.assertTrue((self.out / 'archives' / (arm + '.bundle')).exists())
        for cleanup in report['cleanup']:
            self.assertEqual(cleanup['status'], 'archived_and_removed')
        self.assertTrue((self.out / 'prompts' / 'codex-app.txt').read_text('utf-8').startswith('Fix the TTLCache expiry'))
        manifest.update({'codex_home': str(self.raw / 'gone'), 'opencode_db': str(self.raw / 'gone.db')})
        R.save_manifest(self.out, manifest)
        (code, text) = self.cli(['report', str(self.out)])
        self.assertEqual(code, 0, text)
        offline = self.report()
        self.assertEqual(offline['arms']['codex']['cloud_tokens'], 180)
        self.assertEqual(offline['metrics']['cloud_tokens_per_completed_task'], report['metrics']['cloud_tokens_per_completed_task'])
        self.assertEqual(offline['accepted_arms'], ['codex', 'opencode'])
        self.assertIn('arms/codex/rollouts', json.dumps(offline['arms']['codex']['reaccount_source']))

    def test_second_live_run_is_refused_instead_of_retrying_a_started_arm(self):
        self.assertEqual(self.live()[0], 0)
        (code, text) = self.live()
        self.assertEqual(code, 2)
        self.assertIn('refusing to re-run arms already completed', text)

    def test_existing_or_inside_repository_output_is_refused(self):
        (code, text) = self.cli(['report', str(self.raw / 'never-prepared')])
        self.assertEqual(code, 2)
        self.assertIn('not a prepared run', text)
        inside = R.REPO_ROOT / 'benchmarks' / 'results' / 'should-never-exist'
        self.assertRaises(A.PreflightBlocker, R.resolve_out, str(inside), fresh=True)
        self.out.mkdir()
        (code, text) = self.cli(['run'] + self.frozen() + ['--live'])
        self.assertEqual(code, 2)
        self.assertIn('not a prepared run', text)
        (code, text) = self.cli(['prepare'] + self.frozen())
        self.assertEqual(code, 2)
        self.assertIn('needs a fresh directory', text)

    def test_config_edited_after_prepare_blocks_every_launch(self):
        self.assertEqual(self.cli(['prepare'] + self.frozen())[0], 0)
        config = Path(self.config)
        config.write_text(config.read_text('utf-8') + '\n', encoding='utf-8')
        (config.parent / 'opencode.json').write_text('{"agents": {"general": {"model": "omlx/test-local"}}}', encoding='utf-8')
        (code, text) = self.cli(['run'] + self.frozen() + ['--live'])
        self.assertEqual(code, 2)
        self.assertIn('refusing to launch an arm against edited global configuration', text)
        self.assertEqual(list(self.home.rglob('*.jsonl')), [])
        self.assertEqual(self.hybrid_rows(), 0)

    def test_config_changed_during_a_run_invalidates_the_reported_arms(self):
        run_opencode = R.run_opencode_arm
        def change_config_before_closeout(out, manifest):
            result = run_opencode(out, manifest)
            Path(self.config).write_text('{"agents": {"general": {"model": "omlx/other-local"}}}', encoding='utf-8')
            return result
        with mock.patch.object(R, 'run_opencode_arm', side_effect=change_config_before_closeout):
            self.assertEqual(self.live()[0], 0)
        self.assertEqual(self.cli(['report', str(self.out)])[0], 0)
        report = self.report()
        self.assertEqual(report['native_config_integrity']['status'], 'changed')
        self.assertEqual(report['accepted_arms'], [])
        for arm in ('codex', 'opencode'):
            self.assertFalse(report['arms'][arm]['accepted'])
            self.assertFalse(report['arms'][arm]['gates']['installed_native_config_unchanged'])
            self.assertTrue(any(('global configuration edit invalidates' in blocker) for blocker in report['arms'][arm]['blockers']))
        self.assertEqual(report['metrics']['ratio']['status'], 'undefined')

    def test_report_shows_tokens_by_seat_share_ratio_and_targets(self):
        self.assertEqual(self.live()[0], 0)
        report = self.report()
        seats = report['metrics']['seats']
        self.assertEqual((seats['codex']['planner']['model'], seats['codex']['planner']['total']), (SOL, 120))
        self.assertEqual((seats['codex']['worker']['model'], seats['codex']['worker']['total']), (LUNA, 60))
        self.assertEqual((seats['opencode']['planner']['total'], seats['opencode']['worker']['total']), (2000, 700))
        self.assertEqual(seats['opencode']['worker']['model'], 'omlx/test-local')
        metrics = report['metrics']
        self.assertAlmostEqual(metrics['hybrid_cloud_share']['value'], 2000 / 2700)
        self.assertFalse(metrics['hybrid_cloud_share']['exact'], 'a 200-token maintenance gap makes the share a bound')
        self.assertAlmostEqual(metrics['cloud_vs_codex']['value'], 2000 / 180)
        self.assertEqual(metrics['targets'], {'both_arms_accepted': True, 'hybrid_cloud_at_most_half_of_codex': False,
                                              'hybrid_cloud_share_at_most_0.35': False, 'stretch_cloud_share_at_most_0.20': False})
        markdown = (self.out / 'REPORT.md').read_text('utf-8')
        self.assertIn('## Tokens by seat', markdown)
        self.assertIn(f'| codex | planner | {SOL} |', markdown)
        self.assertIn('| opencode | worker | omlx/test-local |', markdown)
        self.assertIn('## Targets', markdown)

    def test_compare_summarises_repeated_rounds(self):
        self.assertEqual(self.live()[0], 0)
        second = self.raw / 'round-2'
        shutil.copytree(self.out, second)
        (code, text) = self.cli(['compare', str(self.out), str(second), '--out-dir', str(self.raw / 'cmp')])
        self.assertEqual(code, 0, text)
        rounds = json.loads((self.raw / 'cmp' / 'comparison.json').read_text('utf-8'))['rounds']
        self.assertEqual(rounds['accepted'], {'codex': '2/2', 'opencode': '2/2'})
        self.assertAlmostEqual(rounds['hybrid_cloud_share']['median'], 2000 / 2700)
        self.assertAlmostEqual(rounds['cloud_vs_codex']['median'], 2000 / 180)
        self.assertIn('## Rounds', (self.raw / 'cmp' / 'COMPARISON.md').read_text('utf-8'))

    def test_compare_accepts_only_the_intended_differences_and_refuses_a_mismatch(self):
        self.assertEqual(self.live()[0], 0)
        other = self.raw / 'other-mac'
        other.mkdir()
        copied = R.load_manifest(self.out)
        copied['models']['local'] = 'mlx/another-local'
        copied['machine']['label'] = 'other-mac'
        (other / 'manifest.json').write_text(json.dumps(copied), encoding='utf-8')
        (code, text) = self.cli(['compare', str(self.out), str(other), '--out-dir', str(self.raw / 'cmp')])
        self.assertEqual(code, 0, text)
        comparison = json.loads((self.raw / 'cmp' / 'comparison.json').read_text('utf-8'))
        self.assertEqual(comparison['blockers'], [])
        self.assertEqual(sorted(comparison['local_models'].values()) if 'local_models' in comparison else sorted(comparison['compatibility_differences']['local_models'].values()), ['mlx/another-local', 'omlx/test-local'])
        copied['task'] = 'a different frozen task'
        (other / 'manifest.json').write_text(json.dumps(copied), encoding='utf-8')
        (code, text) = self.cli(['compare', str(self.out), str(other)])
        self.assertEqual(code, 2)
        self.assertIn('task_sha256', text)
        self.assertIn('incomparable round', (self.out / 'COMPARISON.md').read_text('utf-8'))

class NegativeArms(FakeCliHarness):

    def test_every_doubt_refuses_the_codex_arm_and_names_the_reason(self):
        cases = (('no verdict at all', {'verdict_style': 'none'}, 'substantive semantic PASS'),
                 ('fenced verdict is decoration', {'verdict_style': 'fenced'}, 'fenced VERDICT'),
                 ('reviewer said FAIL', {'verdict_style': 'fail'}, 'substantive semantic PASS'),
                 ('verdict bound to another digest', {'verdict_style': 'stale'}, 'digest does not equal'),
                 ('independent check failed', {'apply_fix': False}, 'check reported 12 tests'),
                 ('untracked source appeared', {'extra_file': 'extra.py'}, 'scope drift'),
                 ('worker on the wrong model', {'child_model': 'gpt-4o-mini'}, 'expected gpt-6-luna'),
                 ('worker on the wrong effort', {'child_effort': 'high'}, 'effort is read from the rollout'),
                 ('root implemented instead of reviewing', {'root_edits': 1}, 'root must plan and review only'),
                 ('no Luna child was spawned', {'no_child': True}, 'no Luna child session was spawned'),
                 ('child turn never completed', {'child_active': True}, 'task_complete marker'),
                 ('checkout base moved', {'empty_commit': True}, 'frozen fixture base'),
                 ('client exited nonzero', {'exit_code': 3}, 'exited 3'))
        for (index, (label, cfg, phrase)) in enumerate(cases):
            with self.subTest(case=label):
                self.out = self.raw / ('negative-' + str(index))
                (code, text) = self.live(cfg)
                self.assertEqual(code, 0, text)
                result = self.arm('codex')
                self.assertFalse(result['accepted'], (label, result['blockers']))
                self.assertFalse(all(result['gates'].values()))
                self.assertTrue(any((phrase in blocker) for blocker in result['blockers']), (label, result['blockers']))
                report = self.report()
                self.assertEqual(report['metrics']['per_arm_completed_tasks']['codex'], 0)
                self.assertEqual(report['metrics']['ratio']['status'], 'undefined')
                self.assertNotIn('codex', report['accepted_arms'])
                self.assertTrue(report['metrics']['failed_attempts_included'])

    def test_unrecorded_worker_usage_stays_a_lower_bound_and_is_still_counted(self):
        (code, text) = self.live({'child_usage': False})
        self.assertEqual(code, 0, text)
        result = self.arm('codex')
        self.assertFalse(result['accepted'])
        self.assertFalse(result['accounting']['usage_complete'])
        self.assertIsNone(result['accounting']['cloud_total'])
        self.assertEqual(result['accounting']['known_lower_bound'], 120)
        report = self.report()
        self.assertEqual(report['arms']['codex']['cloud_tokens'], None)
        self.assertEqual(report['arms']['codex']['cloud_tokens_lower_bound'], 120)
        self.assertIsNone(report['metrics']['cloud_tokens_per_completed_task']['codex'])
        self.assertTrue(report['metrics']['failed_attempts_included'])
        self.assertEqual(report['metrics']['per_arm_completed_tasks'], {'codex': 0, 'opencode': 1})
        self.assertEqual(report['accepted_arms'], ['opencode'])

    def test_deadline_kills_the_arm_and_keeps_durable_evidence(self):
        self.timeout = 2
        (code, text) = self.live({'sleep': 60})
        self.assertEqual(code, 0, text)
        result = self.arm('codex')
        self.assertFalse(result['accepted'])
        self.assertTrue(result['execution']['timed_out'])
        self.assertEqual(result['execution']['frozen_budget_seconds'], 2)
        self.assertAlmostEqual(result['execution']['deadline_seconds'], 2, delta=0.5)
        self.assertFalse(result['gates']['within_deadline'])
        self.assertTrue(any(('deterministic deadline' in blocker) for blocker in result['blockers']))
        execution = json.loads((self.out / 'arms' / 'codex' / 'arm.execution.json').read_text('utf-8'))
        self.assertTrue(execution['timed_out'])
        self.assertEqual(execution['surviving_children'], [])
        self.assertFalse(execution['process_group_still_alive'])
        self.assertTrue((self.out / 'arms' / 'codex' / 'complete.patch').read_bytes())
        report = self.report()
        cleanup = {entry['arm']: entry for entry in report['cleanup']}
        self.assertEqual(cleanup['codex']['status'], 'archived_and_removed')
        self.assertTrue(cleanup['codex']['tar_verified'])
        self.assertEqual(report['metrics']['per_arm_completed_tasks']['codex'], 0)

    def test_a_helper_left_running_in_the_owned_group_is_terminated_before_the_check(self):
        marker = self.raw / 'lingering.pid'
        (code, text) = self.live({'linger': str(marker)})
        self.assertEqual(code, 0, text)
        pid = int(marker.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        execution = json.loads((self.out / 'arms' / 'codex' / 'arm.execution.json').read_text('utf-8'))
        self.assertFalse(execution['timed_out'])
        self.assertTrue(execution['lingering_group_terminated'])
        self.assertFalse(execution['process_group_still_alive'])
        self.assertTrue(self.arm('codex')['accepted'], self.arm('codex')['blockers'])
        cleanup = {entry['arm']: entry for entry in self.report()['cleanup']}
        self.assertEqual(cleanup['codex']['status'], 'archived_and_removed')

    def test_a_live_rerun_with_options_that_differ_from_the_prepared_run_is_refused(self):
        (code, text) = self.cli(['prepare'] + self.frozen())
        self.assertEqual(code, 0, text)
        argv = self.frozen()
        argv[argv.index('--timeout') + 1] = str(self.timeout + 1)
        argv[argv.index('--local-model') + 1] = 'omlx/another-model'
        (code, text) = self.cli(['run'] + argv + ['--live'])
        self.assertEqual(code, 2, text)
        self.assertIn('--timeout', text)
        self.assertIn('--local-model', text)
        self.assertFalse((self.out / 'arms' / 'codex' / 'arm.stdout.log').exists())
        self.assertFalse(R.load_manifest(self.out).get('live_started'))
        (code, text) = self.cli(['run'] + self.frozen())
        self.assertEqual(code, 0, text)

class DesktopAppImport(FakeCliHarness):

    def prepare(self):
        (code, text) = self.cli(['prepare'] + self.frozen())
        self.assertEqual(code, 0, text)
        return R.load_manifest(self.out)

    def app_session(self, cwd, *, completion='complete'):
        repo = Path(cwd)
        (repo / 'ttl_cache.py').write_text((repo / 'ttl_cache.py').read_text('utf-8').replace('self._clock() > deadline', 'self._clock() >= deadline'), encoding='utf-8')
        diff = subprocess.run(['git', '-C', str(repo), 'diff', '--binary', 'HEAD'], capture_output=True).stdout
        sessions = self.home / 'sessions' / '2026-10-26'
        H.write_rollout(sessions / (ROOT + '.jsonl'), ROOT, str(repo), model=SOL, usage_total=H.usage(100, 80, 20, 5), assistant='Reviewed the complete diff.\nVERDICT: PASS ' + A.sha256_bytes(diff), spawn_ids=(CHILD,), completion=completion)
        H.write_rollout(sessions / (CHILD + '.jsonl'), CHILD, str(repo), parent_id=ROOT, model=LUNA, usage_total=H.usage(50, 40, 10, 2), completion=completion)

    def test_app_import_is_labelled_desktop_and_stays_distinct_from_cli(self):
        manifest = self.prepare()
        self.assertEqual(manifest['measurement_kind'], 'cli')
        self.assertTrue((self.out / 'DESKTOP.md').exists())
        self.app_session(manifest['arms']['codex']['repo'])
        (code, text) = self.cli(['finish', str(self.out), '--codex-thread', ROOT, '--live'])
        self.assertEqual(code, 0, text)
        imported = self.arm('codex')
        self.assertTrue(imported['accepted'], imported['blockers'])
        self.assertEqual(imported['client'], 'codex-app')
        self.assertTrue(imported['execution']['client_imported'])
        self.assertEqual(imported['desktop_gate']['status'], 'within_budget')
        self.assertEqual(imported['desktop_gate']['recorded_seconds'], 30.0)
        self.assertFalse(imported['desktop_gate']['enforced'])
        self.assertEqual(sorted(imported['rollouts']['archived']), sorted([ROOT + '.jsonl', CHILD + '.jsonl']))
        self.assertTrue(self.arm('opencode')['accepted'])
        report = self.report()
        self.assertEqual(report['measurement_kind'], 'codex-app-imported+opencode-cli')
        self.assertEqual(report['accepted_arms'], ['codex', 'opencode'])
        self.assertIn('App sessions are labelled codex-app', ' '.join(report['caveats']))

    def test_a_still_running_app_session_is_not_imported_and_costs_nothing(self):
        manifest = self.prepare()
        self.app_session(manifest['arms']['codex']['repo'], completion='active')
        (code, text) = self.cli(['finish', str(self.out), '--codex-thread', ROOT, '--live'])
        self.assertEqual(code, 2)
        self.assertIn('"hybrid_launched": false', text)
        self.assertIn('still active, aborted or unknown', text)
        self.assertFalse((self.out / 'arms' / 'opencode' / 'arm.stdout.log').exists())
        self.assertEqual(self.hybrid_rows(), 0)
        self.assertEqual(R.load_manifest(self.out)['completed_arms'], [])

    def test_a_desktop_session_in_the_wrong_project_is_refused_as_solution_transfer(self):
        manifest = self.prepare()
        elsewhere = self.raw / 'someone-elses-checkout'
        shutil.copytree(manifest['arms']['codex']['repo'], elsewhere, symlinks=True)
        self.app_session(elsewhere)
        (code, text) = self.cli(['finish', str(self.out), '--codex-thread', ROOT, '--live'])
        self.assertEqual(code, 2)
        self.assertIn('is not the prepared fixture', self.arm('codex')['blockers'][0])
        self.assertFalse(self.arm('codex')['accepted'])
        self.assertFalse((self.out / 'arms' / 'opencode' / 'arm.stdout.log').exists())

    def test_finish_without_live_inspects_and_leaves_the_import_unused(self):
        manifest = self.prepare()
        self.app_session(manifest['arms']['codex']['repo'])
        (code, text) = self.cli(['finish', str(self.out), '--codex-thread', ROOT])
        self.assertEqual(code, 0, text)
        self.assertIn('finish_dry_inspect', text)
        self.assertEqual(R.load_manifest(self.out)['completed_arms'], [])
        self.assertEqual(self.hybrid_rows(), 0)
        self.assertEqual(self.cli(['finish', str(self.out), '--codex-thread', ROOT, '--live'])[0], 0)
        self.assertEqual(self.arm('codex')['client'], 'codex-app')

    def test_the_desktop_window_plus_final_verification_is_the_measured_arm_duration(self):
        manifest = self.prepare()
        self.app_session(manifest['arms']['codex']['repo'])
        self.assertEqual(self.cli(['finish', str(self.out), '--codex-thread', ROOT, '--live'])[0], 0)
        execution = self.arm('codex')['execution']
        self.assertEqual(execution['seconds'], 30.0)
        self.assertIsNotNone(execution['final_verification_seconds'])
        self.assertGreater(execution['total_seconds'], 30.0)
        self.assertFalse(execution['deadline_enforced'])
        self.assertTrue(self.arm('codex')['gates']['within_total_budget'])

    def test_a_desktop_session_that_overspent_the_frozen_budget_is_recorded_never_enforced(self):
        self.out = self.raw / 'tight-budget'
        (code, text) = self.cli(['prepare'] + self.frozen() + ['--timeout', '20'])
        self.assertEqual(code, 0, text)
        manifest = R.load_manifest(self.out)
        self.assertEqual(manifest['budget']['wall_clock_seconds_per_arm'], 20)
        self.app_session(manifest['arms']['codex']['repo'])
        (code, text) = self.cli(['finish', str(self.out), '--codex-thread', ROOT, '--live'])
        self.assertEqual(code, 2)
        imported = self.arm('codex')
        self.assertEqual(imported['desktop_gate']['status'], 'exceeded')
        self.assertFalse(imported['desktop_gate']['enforced'])
        self.assertFalse(imported['accepted'])
        self.assertIn('desktop App retrospective gate is exceeded', ' '.join(imported['blockers']))
        self.assertIn('never an enforced App wall clock', imported['desktop_gate']['note'])
        self.assertFalse((self.out / 'arms' / 'opencode' / 'arm.stdout.log').exists())
        self.assertEqual(self.hybrid_rows(), 0)

class FrozenLaunchInputs(FakeCliHarness):

    def test_the_frozen_prompt_names_the_assigned_child_model_and_effort(self):
        (code, text) = self.cli(['prepare'] + self.frozen() + ['--child-model', 'gpt-5-mini-worker', '--effort', 'medium', '--opencode-cloud-model', 'openai/gpt-6.1-sol#medium'])
        self.assertEqual(code, 0, text)
        prompt = (self.out / 'prompts' / 'codex.txt').read_text('utf-8')
        self.assertIn('gpt-5-mini-worker at medium effort', prompt)
        self.assertNotIn('gpt-6-luna', prompt)
        self.assertIn('gpt-5-mini-worker at medium effort', (self.out / 'prompts' / 'codex-app.txt').read_text('utf-8'))
        manifest = R.load_manifest(self.out)
        self.assertEqual((manifest['models']['codex_child'], manifest['models']['effort']), ('gpt-5-mini-worker', 'medium'))
        self.assertEqual(A.sha256_bytes(prompt.encode('utf-8')), manifest['arms']['codex']['prompt_sha256'])
        self.assertEqual(self.cli(['run'] + self.frozen() + ['--child-model', 'gpt-5-mini-worker', '--effort', 'medium', '--opencode-cloud-model', 'openai/gpt-6.1-sol#medium'])[0], 0)
        plan = json.loads((self.out / 'dry-run-plan.json').read_text('utf-8'))
        self.assertEqual(plan['blockers'], [])
        self.assertTrue(any(('gpt-5-mini-worker' in part) for part in plan['planned_argv']['codex']), plan['planned_argv']['codex'])

    def test_unmatched_cloud_models_or_effort_are_refused_before_anything_launches(self):
        for (index, (label, extra, phrase)) in enumerate((('unknown effort', ['--effort', 'turbo'], 'reasoning effort'),
                                                          ('routed codex cloud model', ['--codex-cloud-model', 'omlx/gpt-6.1-sol'], 'bare cloud model id'),
                                                          ('hybrid effort mismatch', ['--opencode-cloud-model', 'openai/gpt-6.1-sol#low'], 'mismatched effort'),
                                                          ('no child model', ['--child-model', ''], 'child-model is required'))):
            with self.subTest(case=label):
                self.out = self.raw / ('unmatched-' + str(index))
                (code, text) = self.cli(['run'] + self.frozen() + extra)
                self.assertEqual(code, 2, text)
                self.assertIn(phrase, text)
                self.assertEqual(list(self.home.rglob('*.jsonl')), [])
                self.assertEqual(self.hybrid_rows(), 0)

    def test_an_edited_frozen_contract_or_a_dirty_fixture_refuses_the_launch(self):
        self.assertEqual(self.cli(['prepare'] + self.frozen())[0], 0)
        manifest = R.load_manifest(self.out)
        manifest['task'] = manifest['task'] + ' quietly rewritten'
        R.save_manifest(self.out, manifest)
        (code, text) = self.cli(['run'] + self.frozen() + ['--live'])
        self.assertEqual(code, 2)
        self.assertIn('frozen manifest contract changed', text)
        self.assertEqual(list(self.home.rglob('*.jsonl')), [])
        manifest = R.load_manifest(self.out)
        manifest['task'] = R.TASK
        manifest['frozen_fields_sha256'] = R.frozen_fields_sha256(manifest)
        R.save_manifest(self.out, manifest)
        self.assertEqual(R.frozen_manifest_blockers(R.load_manifest(self.out)), [])
        (Path(manifest['arms']['codex']['repo']) / 'ttl_cache.py').write_text('def get(key):\n    return None\n', encoding='utf-8')
        (code, text) = self.cli(['run'] + self.frozen() + ['--live'])
        self.assertEqual(code, 2)
        self.assertIn('pristine frozen fixture input', text)
        self.assertEqual(list(self.home.rglob('*.jsonl')), [])
        self.assertEqual(self.hybrid_rows(), 0)

    def test_no_credential_or_native_config_write_is_ever_persisted(self):
        (code, text) = self.cli(['prepare'] + self.frozen())
        self.assertEqual(code, 0, text)
        bundle = json.dumps(R.load_manifest(self.out)) + ''.join((path.read_text('utf-8', errors='replace') for path in sorted(self.out.rglob('*.json')) + sorted(self.out.rglob('*.md')) + sorted(self.out.rglob('*.txt'))))
        self.assertNotIn('SECRET-DO-NOT-COPY', bundle)
        self.assertIn('http://127.0.0.1:9/v1', json.dumps(R.load_manifest(self.out)['native_config']['snapshot']))
        self.assertEqual(Path(self.config).read_text('utf-8'), (Path(self.config).parent / 'opencode.json').read_text('utf-8'))

    def test_a_mutated_manifest_cannot_keep_arms_accepted_offline(self):
        self.assertEqual(self.live()[0], 0)
        self.assertEqual(self.report()['accepted_arms'], ['codex', 'opencode'])
        manifest = R.load_manifest(self.out)
        manifest['budget']['wall_clock_seconds_per_arm'] = 100000
        R.save_manifest(self.out, manifest)
        (code, text) = self.cli(['report', str(self.out)])
        self.assertEqual(code, 0, text)
        report = self.report()
        self.assertEqual(report['accepted_arms'], [])
        self.assertFalse(report['frozen_fields_verified'])
        for arm in ('codex', 'opencode'):
            self.assertFalse(report['arms'][arm]['accepted'])
            self.assertFalse(report['arms'][arm]['gates']['frozen_manifest_sealed'])
            self.assertTrue(any(('frozen manifest contract changed' in blocker) for blocker in report['arms'][arm]['blockers']), arm)
        self.assertEqual(report['metrics']['ratio']['status'], 'undefined')

class OfflineEvidenceAndRecovery(FakeCliHarness):
    NO_ROOT_ID = 'import json\nprint(json.dumps({"type": "turn.completed"}), flush=True)\n'
    GHOST_ROOT_ID = 'import json\nprint(json.dumps({"type": "thread.started", "thread_id": "0ghost"}), flush=True)\n'

    def test_a_cli_that_never_reports_a_root_thread_stays_durable_with_unknown_cost(self):
        codex = H.write_fake(self.raw / 'bin', 'codex-ghost', self.NO_ROOT_ID, {})
        (code, text) = self.cli(['run'] + self.frozen() + ['--codex-bin', codex, '--live'])
        self.assertEqual(code, 0, text)
        result = self.arm('codex')
        self.assertFalse(result['accepted'])
        self.assertTrue(result['attempted'])
        self.assertIn('no thread.started root thread id', ' '.join(result['blockers']))
        self.assertEqual(result['accounting']['cost_state'], 'unknown')
        self.assertIsNone(result['accounting']['known_lower_bound'])
        self.assertEqual(json.loads((self.out / 'arms' / 'codex' / 'attempts.json').read_text('utf-8'))[0]['cost_state'], 'unknown')
        self.assertEqual(R.load_manifest(self.out)['live_attempt_evidence']['codex']['cost_state'], 'unknown')
        self.assertTrue(self.arm('opencode')['accepted'])
        report = self.report()
        self.assertEqual(report['accepted_arms'], ['opencode'])
        self.assertIsNone(report['arms']['codex']['cloud_tokens'])
        self.assertIsNone(report['arms']['codex']['cloud_tokens_lower_bound'])
        self.assertEqual(report['metrics']['per_arm_completed_tasks'], {'codex': 0, 'opencode': 1})
        self.assertEqual(report['metrics']['ratio']['status'], 'undefined')

    def test_a_reported_thread_with_no_rollout_is_recorded_instead_of_inventing_usage(self):
        codex = H.write_fake(self.raw / 'bin', 'codex-ghost', self.GHOST_ROOT_ID, {})
        (code, text) = self.cli(['run'] + self.frozen() + ['--codex-bin', codex, '--live'])
        self.assertEqual(code, 0, text)
        result = self.arm('codex')
        self.assertFalse(result['accepted'])
        self.assertIn('no rollout for root thread 0ghost', ' '.join(result['blockers']))
        self.assertEqual(result['accounting']['cost_state'], 'unknown')
        self.assertIsNone(result['accounting']['cloud_total'])
        self.assertEqual(self.report()['metrics']['per_arm_completed_tasks']['codex'], 0)

    def test_an_unreadable_native_database_is_persisted_as_attempted_cost_unknown(self):
        broken = self.raw / 'not-a-database.db'
        broken.write_text('this is not a sqlite database\n', encoding='utf-8')
        argv = self.frozen()
        argv[argv.index('--opencode-db') + 1] = str(broken)
        (code, text) = self.cli(['run'] + argv + ['--live'])
        self.assertEqual(code, 0, text)
        result = self.arm('opencode')
        self.assertFalse(result['accepted'])
        self.assertIn('no readable native session evidence', ' '.join(result['blockers']))
        self.assertEqual(result['accounting']['cost_state'], 'unknown')
        report = self.report()
        self.assertEqual(report['accepted_arms'], ['codex'])
        self.assertEqual(report['metrics']['per_arm_completed_tasks'], {'codex': 1, 'opencode': 0})

    def test_a_launch_error_is_recorded_instead_of_vanishing(self):
        self.assertEqual(self.cli(['prepare'] + self.frozen())[0], 0)
        with mock.patch.object(R, 'launch', side_effect=OSError(13, 'Permission denied')):
            (code, text) = self.live()
        self.assertEqual(code, 0, text)
        for arm in ('codex', 'opencode'):
            result = self.arm(arm)
            self.assertFalse(result['accepted'])
            self.assertTrue(result['attempted'])
            self.assertIn('Permission denied', ' '.join(result['blockers']))
            self.assertEqual(result['accounting']['cost_state'], 'unknown')
        report = self.report()
        self.assertEqual(report['accepted_arms'], [])
        self.assertEqual(report['metrics']['cloud_tokens_per_completed_task'], {'codex': None, 'opencode': None})

    def test_appending_bytes_to_the_archived_patch_refuses_acceptance_instead_of_a_stale_pass(self):
        self.assertEqual(self.live()[0], 0)
        self.assertEqual(self.report()['accepted_arms'], ['codex', 'opencode'])
        patch = self.out / 'arms' / 'codex' / 'complete.patch'
        patch.write_bytes(patch.read_bytes() + b'\n+forged after the run\n')
        (code, text) = self.cli(['report', str(self.out)])
        self.assertEqual(code, 0, text)
        report = self.report()
        codex = report['arms']['codex']
        self.assertFalse(codex['accepted'])
        self.assertFalse(codex['verdict']['digest_matches'])
        self.assertFalse(codex['gates']['retained_evidence_verified'])
        self.assertEqual(report['accepted_arms'], ['opencode'])
        self.assertIn('edited after the run', ' '.join(codex['blockers']))
        self.assertIsNone(codex['cloud_tokens'])
        self.assertIsNone(codex['cloud_tokens_lower_bound'])
        self.assertEqual(report['metrics']['per_arm_completed_tasks']['codex'], 0)
        self.assertEqual(report['metrics']['ratio']['status'], 'undefined')
        self.assertIn('edited after the run', (self.out / 'REPORT.md').read_text('utf-8'))

    def test_a_missing_archived_rollout_blocks_acceptance_instead_of_falling_back(self):
        self.assertEqual(self.live()[0], 0)
        victim = sorted((self.out / 'arms' / 'codex' / 'rollouts').glob('*.jsonl'))[0]
        victim.unlink()
        self.assertEqual(self.cli(['report', str(self.out)])[0], 0)
        codex = self.report()['arms']['codex']
        self.assertFalse(codex['accepted'])
        self.assertFalse(codex['gates']['retained_evidence_verified'])
        self.assertIn(victim.name, ' '.join(codex['blockers']))
        self.assertIsNone(codex['cloud_tokens'])

    def test_the_copied_bundle_reports_offline_with_home_db_and_config_absent_and_deletes_nothing(self):
        self.assertEqual(self.live()[0], 0)
        original = self.report()
        self.assertEqual(original['accepted_arms'], ['codex', 'opencode'])
        bundle = self.raw / 'copied-to-another-mac'
        shutil.copytree(self.out, bundle)
        manifest = R.load_manifest(bundle)
        manifest.update({'codex_home': str(self.raw / 'gone-home'), 'opencode_db': str(self.raw / 'gone.db')})
        manifest['native_config']['path'] = str(self.raw / 'gone-config.json')
        R.save_manifest(bundle, manifest)
        (code, text) = self.cli(['report', str(bundle)])
        self.assertEqual(code, 0, text)
        offline = json.loads((bundle / 'report.json').read_text('utf-8'))
        self.assertEqual(offline['accepted_arms'], ['codex', 'opencode'])
        self.assertEqual(offline['native_config_integrity']['source'], 'retained at execution closeout')
        self.assertEqual(offline['native_config_integrity']['status'], 'unchanged')
        for arm in ('codex', 'opencode'):
            self.assertTrue(offline['arms'][arm]['evidence']['verified'], offline['arms'][arm]['blockers'])
            self.assertEqual(offline['arms'][arm]['cloud_tokens'], original['arms'][arm]['cloud_tokens'])
            self.assertEqual(offline['arms'][arm]['local_tokens'], original['arms'][arm]['local_tokens'])
        self.assertEqual(offline['metrics']['cloud_tokens_per_completed_task'], original['metrics']['cloud_tokens_per_completed_task'])
        self.assertEqual(offline['metrics']['ratio']['status'], original['metrics']['ratio']['status'])
        self.assertEqual((bundle / 'COMPARISON.md').exists(), False)
        tar = bundle / 'archives' / 'codex-repo.tar.gz'
        digest = A.sha256_file(tar)
        self.assertEqual({entry['status'] for entry in offline['cleanup']}, {'archived_and_removed'})
        (code, text) = self.cli(['report', str(bundle)])
        self.assertEqual(code, 0, text)
        again = json.loads((bundle / 'report.json').read_text('utf-8'))
        self.assertEqual({entry['arm']: entry['status'] for entry in again['cleanup']}, {'codex': 'archived_and_removed', 'opencode': 'archived_and_removed'})
        self.assertNotIn('already_removed', json.dumps(again['cleanup']))
        self.assertEqual(A.sha256_file(tar), digest)
        self.assertTrue(tar.exists() and (bundle / 'archives' / 'opencode.bundle').exists())
        (code, text) = self.cli(['compare', str(bundle), str(self.out), '--out-dir', str(self.raw / 'cmp')])
        self.assertEqual(code, 0, text)
        comparison = json.loads((self.raw / 'cmp' / 'comparison.json').read_text('utf-8'))
        self.assertEqual(comparison['blockers'], [])
        self.assertEqual(sorted({row['arm'] for row in comparison['rows']}), ['codex', 'opencode'])
        self.assertEqual(len(comparison['ratios']), 2)
        self.assertEqual({ratio['status'] for ratio in comparison['ratios'].values()}, {original['metrics']['ratio']['status']})
