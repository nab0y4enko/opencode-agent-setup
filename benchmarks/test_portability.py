"""Offline two-arm runner portability regressions: no network, no model, no paid call.  A copied run
directory must still prove its round from sealed retained evidence alone: report and compare never
probe the live config, trust a cached report.json or fall back to a live CODEX_HOME; the frozen launch
contract refuses an unverifiable model, effort or budget before anything launches; the seal binds the
recorded result and captured logs; an absent client binary is a readable blocker.  Fake CLIs come from
the sibling test_runner_helpers module; no machine-specific imports are needed.
"""
import contextlib, io, json, shutil, sqlite3, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent))
import accounting as A
import run as R
import test_runner_helpers as H
(SOL, LUNA, LOCAL) = ('gpt-6.1-sol', 'gpt-6-luna', 'omlx/test-local')
ARMS = ('codex', 'opencode')

def tree(root):
    return {str(p.relative_to(root)): A.sha256_file(p) for p in sorted(root.rglob('*')) if p.is_file()}

class Harness(unittest.TestCase):
    """Real CLI against fake CLIs; declares no tests of its own."""
    timeout = 60
    def setUp(self):
        self.raw = Path(tempfile.mkdtemp())
        self.home = self.raw / 'codexhome'
        self.home.mkdir()
        self.db = H.make_db(self.raw / 'opencode.db', [])
        self.config = H.native_config(self.raw / 'native', LOCAL)
        self.out = self.raw / 'run'
        self.opencode = H.write_fake(self.raw / 'bin', 'opencode', H.FAKE_OPENCODE, {'db': str(self.db), 'root_id': 'ses_root', 'child_id': 'ses_local', 'review_id': 'ses_review', 'local_model_id': 'test-local'})
    def tearDown(self):
        shutil.rmtree(self.raw, ignore_errors=True)
    def codex(self):
        cfg = {'codex_home': str(self.home), 'root_id': '0' * 31 + '1', 'child_id': '0' * 31 + '2', 'root_input': 100, 'root_cached': 80, 'root_output': 20, 'root_reasoning': 5, 'root_total': 120, 'child_input': 50, 'child_cached': 40, 'child_output': 10, 'child_reasoning': 2, 'child_total': 60}
        return H.write_fake(self.raw / 'bin', 'codex', H.FAKE_CODEX, cfg)
    def frozen(self):
        return ['--out', str(self.out), '--local-model', LOCAL, '--codex-bin', self.codex(), '--opencode-bin', self.opencode, '--codex-home', str(self.home), '--opencode-db', str(self.db), '--opencode-config', self.config, '--timeout', str(self.timeout)]
    def cli(self, argv):
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            return (R.main(argv), captured.getvalue())
    def live(self):
        self.assertEqual(self.cli(['run'] + self.frozen() + ['--live'])[0], 0)
        self.assertEqual(self.report()['accepted_arms'], list(ARMS))
    def report(self):
        return json.loads((self.out / 'report.json').read_text('utf-8'))
    def nothing_launched(self):
        self.assertEqual(list(self.home.rglob('*.jsonl')), [])
        self.assertEqual(sqlite3.connect(str(self.db)).execute('select count(*) from session_v2').fetchone()[0], 0)
    def refused_both(self, report, phrase):
        self.assertEqual(report['accepted_arms'], [])
        for arm in ARMS:
            self.assertFalse(report['arms'][arm]['accepted'])
            self.assertFalse(report['arms'][arm]['gates']['installed_native_config_unchanged'])
            self.assertTrue(any((phrase in b) for b in report['arms'][arm]['blockers']), arm)
    def compare(self, other):
        (code, text) = self.cli(['compare', str(self.out), str(other), '--out-dir', str(self.raw / 'cmp')])
        self.assertEqual(code, 0, text)
        return json.loads((self.raw / 'cmp' / 'comparison.json').read_text('utf-8'))
    def rows(self, comparison, run_name):
        return {row['arm']: row for row in comparison['rows'] if row['run'] == run_name}
    def ratio(self, comparison, run_name):
        return {Path(label).name: block['status'] for (label, block) in comparison['ratios'].items()}[run_name]

class RetainedEvidenceIsAllAReportReads(Harness):
    def test_config_edited_after_the_run_cannot_rewrite_history(self):
        self.live()
        Path(self.config).write_text('{"agents": {"general": {"model": "omlx/other"}}}', encoding='utf-8')
        with mock.patch.object(R, 'config_integrity', side_effect=AssertionError('a report must not probe live config')):
            report = R.build_report(self.out, R.load_manifest(self.out))
        self.assertEqual(report['native_config_integrity']['status'], 'unchanged')
        self.assertEqual(report['accepted_arms'], list(ARMS))
    def test_changed_or_unrecorded_closeout_receipt_refuses_every_arm(self):
        self.live()
        frozen = R.load_manifest(self.out)['native_config']
        changed = {'status': 'changed', 'path': frozen['path'], 'frozen_sha256': frozen['raw_sha256'], 'current_sha256': 'b' * 64, 'changed': True}
        for (receipt, status, phrase) in ((changed, 'changed', 'global configuration edit invalidates'), (None, 'unrecorded', 'never captured unchanged')):
            with self.subTest(receipt=status):
                manifest = R.load_manifest(self.out)
                if receipt is None:
                    del manifest['config_integrity_final']
                else:
                    manifest['config_integrity_final'] = receipt
                R.save_manifest(self.out, manifest)
                Path(self.config).unlink(missing_ok=True)
                self.assertEqual(self.cli(['report', str(self.out)])[0], 0)
                self.assertEqual(self.report()['native_config_integrity']['status'], status)
                self.refused_both(self.report(), phrase)

class CompareRebuildsEveryReport(Harness):
    def test_compare_rebuilds_from_evidence_and_ignores_any_cached_report(self):
        self.live()
        shutil.copytree(self.out, self.raw / 'copied')
        patch = self.out / 'arms' / 'codex' / 'complete.patch'
        patch.write_bytes(patch.read_bytes() + b'\n+forged\n')
        stale = self.report()
        stale['arms']['codex']['accepted'] = True
        for cached in (None, stale):
            with self.subTest(cached_report=bool(cached)):
                (self.out / 'report.json').unlink(missing_ok=True)
                if cached is not None:
                    (self.out / 'report.json').write_text(json.dumps(cached), encoding='utf-8')
                comparison = self.compare(self.raw / 'copied')
                self.assertFalse(self.rows(comparison, 'run')['codex']['accepted'])
                self.assertEqual(self.ratio(comparison, 'run'), 'undefined')
                self.assertTrue(self.rows(comparison, 'copied')['codex']['accepted'])

class FrozenLaunchContract(Harness):
    def test_medium_one_cloud_model_with_configurable_child_is_accepted(self):
        (code, text) = self.cli(['run'] + self.frozen() + ['--child-model', 'gpt-5-mini-worker', '--effort', 'medium', '--opencode-cloud-model', 'openai/' + SOL + '#medium'])
        self.assertEqual(code, 0, text)
        self.assertTrue(all((('gpt-5-mini-worker at medium effort' in (self.out / 'prompts' / (n + '.txt')).read_text('utf-8')) and (LUNA not in (self.out / 'prompts' / (n + '.txt')).read_text('utf-8')) for n in ('codex', 'codex-app'))))
        manifest = R.load_manifest(self.out)
        self.assertEqual((manifest['models']['codex_child'], manifest['models']['effort']), ('gpt-5-mini-worker', 'medium'))
        plan = json.loads((self.out / 'dry-run-plan.json').read_text('utf-8'))
        self.assertEqual(plan['blockers'], [])
        self.assertIn('agents.default_subagent_model="gpt-5-mini-worker"', ' '.join(plan['planned_argv']['codex']))
        self.assertEqual(R.permission_blockers(plan['planned_argv']['codex']), [])
    def test_unmatched_model_effort_or_budget_is_refused_before_launch(self):
        cases = ((['--opencode-cloud-model', 'openai/' + SOL], 'explicit #effort'),
                 (['--opencode-cloud-model', 'openai/gpt-5-hera#medium'], 'same cloud model'),
                 (['--effort', 'high', '--opencode-cloud-model', 'openai/' + SOL + '#high'], 'reasoning effort'),
                 (['--timeout', '0'], 'positive number of seconds'))
        for (index, (extra, phrase)) in enumerate(cases):
            with self.subTest(case=index):
                self.out = self.raw / ('gate-' + str(index))
                (code, text) = self.cli(['run'] + self.frozen() + extra + ['--live'])
                self.assertEqual(code, 2, text)
                self.assertIn(phrase, text)
                self.assertFalse(self.out.exists())
                self.nothing_launched()

class SealedEvidenceCannotBeEdited(Harness):
    def test_seal_binds_claims_and_logs_and_refuses_edits(self):
        self.live()
        evidence = tree(self.out / 'arms')
        seals = {arm: json.loads((self.out / 'arms' / arm / 'evidence-sha256.json').read_text('utf-8'))['files'] for arm in ARMS}
        for name in ('result.json', 'complete.patch', 'arm.stdout.log', 'arm.execution.json', 'final.check.log'):
            self.assertIn(name, seals['codex'])
        for name in ('result.json', 'native-records.json'):
            self.assertIn(name, seals['opencode'])
        self.assertTrue(all(R.verify_retained_evidence(self.out / 'arms' / arm)['verified'] for arm in ARMS))
        path = self.out / 'arms' / 'codex' / 'result.json'
        original = path.read_bytes()
        for (label, key, field, forged) in (('returncode', 'check', 'returncode', 3), ('duration', 'execution', 'total_seconds', 0.4), ('scope', 'scope', 'changed', ['README.md'])):
            with self.subTest(claim=label):
                record = json.loads(original)
                record[key][field] = forged
                path.write_text(json.dumps(record), encoding='utf-8')
                self.assertEqual(self.cli(['report', str(self.out)])[0], 0)
                report = self.report()
                codex = report['arms']['codex']
                self.assertFalse(codex['accepted'])
                self.assertFalse(codex['gates']['retained_evidence_verified'])
                self.assertIn('no longer hashes', ' '.join(codex['blockers']))
                self.assertEqual(report['accepted_arms'], ['opencode'])
                self.assertEqual(report['metrics']['ratio']['status'], 'undefined')
            path.write_bytes(original)
        self.assertEqual(self.cli(['report', str(self.out)])[0], 0)
        self.assertEqual(self.report()['accepted_arms'], list(ARMS))
        self.assertEqual(tree(self.out / 'arms'), evidence)
        shutil.rmtree(self.out / 'arms' / 'codex' / 'rollouts')
        self.assertEqual(self.cli(['report', str(self.out)])[0], 0)
        codex = self.report()['arms']['codex']
        self.assertIn('cannot be re-accounted', ' '.join(codex['blockers']))
        self.assertNotIn('codexhome', json.dumps(codex['reaccount_source']))

class MissingClientBinaryDegradesReadably(Harness):
    def test_absent_executable_is_unavailable_and_never_tracebacks(self):
        missing = str(self.raw / 'not-installed-cli')
        for absent in (None, '', missing, str(self.raw)):
            self.assertEqual(R.tool_version(absent), 'unavailable')
        (code, text) = self.cli(['prepare'] + self.frozen() + ['--codex-bin', missing])
        self.assertEqual(code, 0, text)
        self.assertEqual(R.load_manifest(self.out)['machine']['codex'], 'unavailable')
        (code, text) = self.cli(['run'] + self.frozen() + ['--codex-bin', missing, '--live'])
        self.assertEqual(code, 2, text)
        self.assertIn('codex binary is not runnable', text)
        self.assertNotIn('Traceback', text)
        self.nothing_launched()
