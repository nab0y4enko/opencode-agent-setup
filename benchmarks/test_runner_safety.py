"""Regression coverage for runner input isolation and recoverable cleanup."""
import json
import sys
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import run as R
import test_runner as T


class LaunchIsolation(T.FakeCliHarness):
    def test_untracked_source_blocks_launch_before_any_client_runs(self):
        args = self.frozen()
        self.assertEqual(self.cli(['prepare'] + args)[0], 0)
        (self.out / 'arms' / 'opencode' / 'repo' / 'sitecustomize.py').write_text('raise RuntimeError("extra")\n')
        code, text = self.cli(['run'] + args + ['--live'])
        self.assertEqual(code, 2, text)
        self.assertEqual(list(self.home.rglob('*.jsonl')), [])
        self.assertEqual(self.hybrid_rows(), 0)

    def test_second_arm_is_revalidated_after_the_first_client_finishes(self):
        args = self.frozen()
        self.assertEqual(self.cli(['prepare'] + args)[0], 0)
        original = R.run_codex_arm

        def contaminate(*args, **kwargs):
            result = original(*args, **kwargs)
            path = self.out / 'arms' / 'opencode' / 'repo' / 'ttl_cache.py'
            path.write_text(path.read_text().replace('self._clock() > deadline', 'self._clock() >= deadline'))
            return result

        with mock.patch.object(R, 'run_codex_arm', side_effect=contaminate):
            code, text = self.cli(['run'] + args + ['--live'])
        self.assertEqual(code, 0, text)
        self.assertEqual(self.hybrid_rows(), 0, 'contaminated second arm must never bill a client')
        self.assertFalse(self.arm('opencode')['accepted'])
        self.assertTrue(any('pristine' in b for b in self.arm('opencode')['blockers']))


class RecoveryArchives(unittest.TestCase):
    setUp = T.OwnedCleanup.setUp
    tearDown = T.OwnedCleanup.tearDown
    git = T.OwnedCleanup.git
    manifest = T.OwnedCleanup.manifest

    def test_ignored_build_and_test_artifacts_survive_verified_cleanup(self):
        build = self.repo / '.bench-build' / 'DerivedData'
        build.mkdir(parents=True)
        (build / 'compile.log').write_bytes(b'needed build evidence\n')
        manifest = dict(self.manifest(self.repo), excluded=['.bench-build/'])
        result = R.archive_and_cleanup(self.out, manifest, 'codex')
        self.assertEqual(result['status'], 'archived_and_removed', result)
        with tarfile.open(self.out / 'archives' / 'codex-repo.tar.gz') as tar:
            self.assertIn('codex/.bench-build/DerivedData/compile.log', tar.getnames())
            self.assertEqual(tar.extractfile('codex/.bench-build/DerivedData/compile.log').read(), b'needed build evidence\n')


class CheckProcessSafety(unittest.TestCase):
    def test_timed_out_independent_check_terminates_its_descendants(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            marker = root / 'late-edit'
            child = 'import time; from pathlib import Path; time.sleep(2); Path(' + repr(str(marker)) + ').write_text("survived")'
            parent = 'import subprocess, sys, time; subprocess.Popen([sys.executable, "-c", ' + repr(child) + ']); time.sleep(30)'
            manifest = {'fixture': 'ttl-python', 'check': [sys.executable, '-c', parent], 'expected_tests': 12}
            result = R.run_check(root, root / 'evidence', 'final', 0.2, manifest, 'codex')
            self.assertFalse(result['ok'])
            time.sleep(2.2)
            self.assertFalse(marker.exists(), 'check descendant edited the fixture after timeout')


class RecordedWindows(unittest.TestCase):
    def test_recorded_window_honors_utc_offsets_and_rejects_reverse_time(self):
        window = {'first_event': '2026-11-01T01:59:50-04:00', 'last_event': '2026-11-01T01:00:10-05:00'}
        self.assertEqual(R.window_seconds(window), 20)
        self.assertIsNone(R.window_seconds({'first_event': window['last_event'], 'last_event': window['first_event']}))
        self.assertIsNone(R.window_seconds({'first_event': None, 'last_event': None}))

    def test_recorded_window_accepts_any_fraction_width_on_python_39(self):
        # Python 3.9 fromisoformat accepts only 3 or 6 fractional digits; real logs carry 0-9.
        window = {'first_event': '2026-10-28T17:25:16.5Z', 'last_event': '2026-10-28T17:26:16.037118123Z'}
        self.assertEqual(R.window_seconds(window), 59.5)
        self.assertEqual(R.window_seconds({'first_event': '2026-10-28T17:25:16Z',
                                           'last_event': '2026-10-28T17:25:36.03711+00:00'}), 20.0)
        self.assertIsNone(R.window_seconds({'first_event': '2026-10-28T17:25:16.5',
                                            'last_event': '2026-10-28T17:26:16Z'}))

class RetainedEvidence(unittest.TestCase):
    def test_an_empty_or_partial_seal_cannot_verify_unsealed_decision_artifacts(self):
        with tempfile.TemporaryDirectory() as raw:
            evidence = Path(raw)
            (evidence / 'complete.patch').write_bytes(b'patch')
            (evidence / 'result.json').write_text('{}')
            for entries in ({}, {'complete.patch': R.A.sha256_file(evidence / 'complete.patch')}):
                (evidence / 'evidence-sha256.json').write_text(json.dumps({'files': entries}))
                result = R.verify_retained_evidence(evidence)
                self.assertFalse(result['verified'], result)
                self.assertTrue(any('result.json' in p for p in result['problems']))

class DuplicateRolloutRecovery(unittest.TestCase):
    def test_all_duplicate_session_sources_are_retained_before_offline_accounting(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            first, second = root / 'first.jsonl', root / 'second.jsonl'
            first.write_text('first evidence\n')
            second.write_text('second evidence\n')
            receipt = R.archive_rollouts({'session': {'path': str(second), 'rollout_paths': [str(first), str(second)]}}, ['session'], root / 'evidence')
            files = list((root / 'evidence' / 'rollouts').glob('*.jsonl'))
            self.assertEqual({path.read_text() for path in files}, {'first evidence\n', 'second evidence\n'})
            self.assertEqual(len(receipt['sha256']), 2)

class CloseoutIntegrity(unittest.TestCase):
    def test_resolved_non_secret_sidecar_change_invalidates_config_integrity(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            config = root / 'config.json'
            sidecar = root / 'local-model.txt'
            sidecar.write_text('first')
            config.write_text(json.dumps({'model': '{file:./local-model.txt}'}))
            snapshot = R.A.config_snapshot(config, {})
            manifest = {'native_config': snapshot}
            self.assertFalse(R.config_integrity(manifest)['changed'])
            sidecar.write_text('second')
            self.assertTrue(R.config_integrity(manifest)['changed'])

    def test_blocked_simulator_delete_retains_ownership_for_retry(self):
        with tempfile.TemporaryDirectory() as raw:
            manifest = {'completed_arms': [], 'simulators': {'codex': {'name': 'bench-codex', 'udid': 'owned'}}}
            with mock.patch.object(R, 'simulator_delete', return_value={'name': 'bench-codex', 'udid': 'owned', 'status': 'blocked_simctl_failed'}):
                R.closeout(Path(raw), manifest)
            self.assertEqual(manifest['simulators']['codex']['udid'], 'owned')


class FinishRecovery(T.FakeCliHarness):
    prepare = T.DesktopAppImport.prepare
    app_session = T.DesktopAppImport.app_session

    def test_hybrid_exception_after_accepted_import_retains_failure_and_closes_out(self):
        manifest = self.prepare()
        self.app_session(manifest['arms']['codex']['repo'])
        with mock.patch.object(R, 'run_opencode_arm', side_effect=RuntimeError('synthetic crash')):
            code, text = self.cli(['finish', str(self.out), '--codex-thread', T.ROOT, '--live'])
        self.assertEqual(code, 0, text)
        self.assertFalse(self.arm('opencode')['accepted'])
        self.assertIsNone(self.arm('opencode')['accounting']['cloud_total'])
        for arm in ('codex', 'opencode'):
            self.assertFalse(Path(manifest['arms'][arm]['repo']).exists())

class ConservativeMetricTargets(unittest.TestCase):
    def arms(self, cloud, local, maintenance, codex=100):
        def result(planner, worker, gap):
            return {'accepted': True, 'accounting': {'usage_complete': True, 'seats': {'planner': {'total': planner}, 'worker': {'total': worker}}, 'unknown_maintenance_total': gap}}
        return {'codex': result(codex, 0, 0), 'opencode': result(cloud, local, maintenance)}

    def test_unknown_maintenance_crossing_targets_cannot_pass_from_point_estimate(self):
        metrics = R.seat_metrics(self.arms(30, 70, 60))
        self.assertAlmostEqual(metrics['hybrid_cloud_share']['value'], .3)
        self.assertFalse(metrics['targets']['hybrid_cloud_share_at_most_0.35'])
        self.assertFalse(metrics['targets']['hybrid_cloud_at_most_half_of_codex'])
        self.assertAlmostEqual(metrics['hybrid_cloud_share']['lower_bound'], 30 / 160)
        self.assertAlmostEqual(metrics['hybrid_cloud_share']['upper_bound'], 90 / 160)
        self.assertAlmostEqual(metrics['cloud_vs_codex']['upper_bound'], .9)

    def test_targets_pass_when_the_entire_maintenance_interval_meets_them(self):
        metrics = R.seat_metrics(self.arms(10, 90, 5))
        self.assertTrue(all(metrics['targets'].values()), metrics)
        self.assertAlmostEqual(metrics['hybrid_cloud_share']['lower_bound'], 10 / 105)
        self.assertAlmostEqual(metrics['hybrid_cloud_share']['upper_bound'], 15 / 105)
        self.assertFalse(metrics['hybrid_cloud_share']['exact'])

    def test_ratio_block_uses_the_shared_cloud_target(self):
        self.assertEqual(R.ratio_block({})['threshold'], R.TARGETS['cloud_vs_codex'])

class HardwareComparison(T.FakeCliHarness):
    def test_compare_lists_safe_hardware_details_as_intended_machine_differences(self):
        self.assertEqual(self.cli(['prepare'] + self.frozen())[0], 0)
        first = R.load_manifest(self.out)
        second_out = self.raw / 'second-run'
        second_out.mkdir()
        first['machine'].update({'cpu_count': 8, 'hardware': {'chip': 'sample-a'}})
        R.save_manifest(self.out, first)
        second = json.loads(json.dumps(first))
        second['machine'].update({'cpu_count': 16, 'hardware': {'chip': 'sample-b'}})
        R.save_manifest(second_out, second)
        blockers, differences = R.compare_runs([self.out, second_out])
        self.assertEqual(blockers, [])
        self.assertEqual(differences['hardware'][str(self.out)]['cpu_count'], 8)
        self.assertEqual(differences['hardware'][str(second_out)]['hardware'], {'chip': 'sample-b'})

class InterruptedRuns(T.FakeCliHarness):
    def test_interrupted_prepare_retains_inputs_and_releases_only_owned_simulator(self):
        args = self.frozen() + ['--fixture', 'swiftui-list']
        record = {'name': 'bench-codex', 'udid': 'owned-test-device'}
        def interrupt(repo, evidence, *unused):
            (evidence / 'baseline.check.log').write_text('partial baseline output\n')
            raise KeyboardInterrupt()
        with mock.patch.object(R, 'simulator_create', return_value=record), mock.patch.object(R, 'simulator_delete', return_value=dict(record, status='deleted')) as delete, mock.patch.object(R, 'run_check', side_effect=interrupt):
            try:
                code, text = self.cli(['prepare'] + args)
            except KeyboardInterrupt:
                self.fail('prepare interruption escaped without simulator closeout')
        self.assertEqual(code, 130, text)
        delete.assert_called_once_with(record)
        manifest = R.load_manifest(self.out)
        self.assertEqual(manifest['simulators'], {})
        self.assertTrue(any('interrupted' in b for b in manifest['preparation_blockers']))
        self.assertTrue((self.out / 'preparation-interruption.json').exists())
        for arm in ('codex', 'opencode'):
            self.assertTrue(Path(manifest['arms'][arm]['repo']).exists())
        self.assertEqual((self.out / 'arms' / 'codex' / 'baseline.check.log').read_text(), 'partial baseline output\n')

    def test_interrupted_live_arm_never_launches_second_arm_and_archives_checkouts(self):
        args = self.frozen()
        self.assertEqual(self.cli(['prepare'] + args)[0], 0)
        with mock.patch.object(R, 'run_codex_arm', side_effect=KeyboardInterrupt()), mock.patch.object(R, 'run_opencode_arm') as hybrid:
            try:
                code, text = self.cli(['run'] + args + ['--live'])
            except KeyboardInterrupt:
                self.fail('live interruption escaped without arm closeout')
        self.assertEqual(code, 130, text)
        hybrid.assert_not_called()
        self.assertFalse(self.arm('codex')['accepted'])
        self.assertIsNone(self.arm('codex')['accounting']['cloud_total'])
        manifest = R.load_manifest(self.out)
        for arm in ('codex', 'opencode'):
            self.assertFalse(Path(manifest['arms'][arm]['repo']).exists())
            self.assertTrue((self.out / 'archives' / (arm + '.bundle')).exists())

class InterruptedLaunch(unittest.TestCase):
    def test_interruption_terminates_owned_client_and_retains_execution_receipt(self):
        import os
        import subprocess
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original_wait = subprocess.Popen.wait
            processes = []
            def interrupt_once(proc, *args, **kwargs):
                if not processes:
                    processes.append(proc)
                    raise KeyboardInterrupt()
                return original_wait(proc, *args, **kwargs)
            try:
                with mock.patch.object(subprocess.Popen, 'wait', interrupt_once):
                    with self.assertRaises(KeyboardInterrupt):
                        R.launch([sys.executable, '-c', 'import time; time.sleep(30)'], root, root, 60, 'arm')
                receipt = root / 'arm.execution.json'
                self.assertTrue(receipt.exists(), 'interrupted launch lost its process ownership receipt')
                self.assertTrue(json.loads(receipt.read_text())['interrupted'])
                with self.assertRaises(ProcessLookupError):
                    os.kill(processes[0].pid, 0)
            finally:
                for proc in processes:
                    if proc.poll() is None:
                        R.terminate_group(proc.pid, grace=0.1)
                    proc.wait()

class FinishInterruption(T.FakeCliHarness):
    prepare = T.DesktopAppImport.prepare
    app_session = T.DesktopAppImport.app_session

    def test_interrupted_paid_hybrid_after_app_import_records_receipt_and_closes_out(self):
        manifest = self.prepare()
        self.app_session(manifest['arms']['codex']['repo'])
        receipt = {'interrupted': True, 'exit_code': -15, 'process_group_still_alive': False, 'surviving_children': []}
        def interrupt(out, manifest):
            (out / 'arms' / 'opencode' / 'arm.execution.json').write_text(json.dumps(receipt))
            raise KeyboardInterrupt()
        with mock.patch.object(R, 'run_opencode_arm', side_effect=interrupt):
            try:
                code, text = self.cli(['finish', str(self.out), '--codex-thread', T.ROOT, '--live'])
            except KeyboardInterrupt:
                self.fail('Hybrid interruption escaped App closeout')
        self.assertEqual(code, 130, text)
        result = self.arm('opencode')
        self.assertFalse(result['accepted'])
        self.assertTrue(result['execution']['interrupted'])
        self.assertIsNone(result['accounting']['cloud_total'])
        for arm in manifest['arms']:
            self.assertFalse(Path(manifest['arms'][arm]['repo']).exists())


class SimulatorCreationInterruption(T.FakeCliHarness):
    def test_pending_interrupt_waits_for_durable_baseline_ownership_and_is_inherited_by_native_child(self):
        import os
        import signal
        import subprocess
        record = {'name': 'bench-codex', 'udid': 'owned-test-device'}
        observed = []
        def create(name):
            child = subprocess.run([sys.executable, '-c', 'import signal; print(int(signal.SIGINT in signal.pthread_sigmask(signal.SIG_BLOCK, [])))'], capture_output=True, text=True, check=True)
            observed.append(child.stdout.strip())
            os.kill(os.getpid(), signal.SIGINT)
            return record
        def delete(owned):
            self.assertEqual(R.load_manifest(self.out)['simulators']['codex'], record)
            return dict(owned, status='deleted')
        with mock.patch.object(R, 'simulator_create', side_effect=create), mock.patch.object(R, 'simulator_delete', side_effect=delete) as deletion, mock.patch.object(R, 'run_check') as baseline:
            code, text = self.cli(['prepare'] + self.frozen() + ['--fixture', 'swiftui-list'])
        self.assertEqual(code, 130, text)
        self.assertEqual(observed, ['1'])
        deletion.assert_called_once_with(record)
        baseline.assert_not_called()
        self.assertEqual(R.load_manifest(self.out)['simulators'], {})

    def test_pending_interrupt_during_live_creation_keeps_owned_record_before_boot(self):
        import os
        import signal
        self.out.mkdir()
        manifest = {'fixture': 'swiftui-list', 'simulators': {}}
        record = {'name': 'bench-codex', 'udid': 'owned-test-device'}
        def create(name):
            os.kill(os.getpid(), signal.SIGINT)
            return record
        with mock.patch.object(R, 'simulator_create', side_effect=create), mock.patch.object(R, 'simctl') as boot:
            with self.assertRaises(KeyboardInterrupt):
                R.start_arm_simulator(self.out, manifest, 'codex')
        self.assertEqual(R.load_manifest(self.out)['simulators']['codex'], record)
        boot.assert_not_called()
