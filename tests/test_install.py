"""Offline tests for install.py and the profile: no Homebrew, Splash, OpenCode or network calls."""
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import install  # noqa: E402


class ProfileTest(unittest.TestCase):
    def setUp(self):
        self.profile = install.load_profile()

    def test_roles_route_to_the_intended_models(self):
        self.assertEqual(install.expected_routes(self.profile), {
            'build': ('openai', 'gpt-6.2-sol', 'high'),
            'implementer': ('splash', 'worker', 'lite-1k'),
            'validator': ('splash', 'worker', 'lite-512'),
        })

    def test_workers_cannot_ask_the_user_or_start_subagents(self):
        for name in ('implementer', 'validator'):
            rules = {(r['action'], r['resource'], r['effect']) for r in self.profile['agents'][name]['permissions']}
            self.assertIn(('subagent', '*', 'deny'), rules, name)
            self.assertIn(('question', '*', 'deny'), rules, name)

    def test_orchestrator_cannot_use_the_generic_subagents(self):
        rules = {(r['resource'], r['effect']) for r in self.profile['agents']['build']['permissions']
                 if r['action'] == 'subagent'}
        self.assertEqual(rules, {('general', 'deny'), ('explore', 'deny')})

    def test_worker_variants_cap_thinking(self):
        model_id, body = install.thinking_cap(self.profile)
        self.assertTrue(model_id)
        self.assertEqual(body, {'reasoning_effort': 'low', 'thinking_token_budget': 1024})

    def test_worker_model_is_served_locally(self):
        url, model_id = install.worker_model(self.profile)
        self.assertEqual(url, 'http://127.0.0.1:8000/v1')
        self.assertIn(':', model_id)

    def test_profile_has_no_machine_paths_or_secrets(self):
        for path in (install.PROFILE, install.RULES):
            text = path.read_text(encoding='utf-8')
            self.assertNotRegex(text, r'/Users/|/home/', path.name)
            self.assertNotRegex(text, r'sk-[A-Za-z0-9-]{8,}', path.name)
            self.assertNotRegex(text, re.compile(r'"api_?key"\s*:', re.I), path.name)

    def test_validator_can_finish_a_full_check_matrix(self):
        # A 40-step validator stopped twice before writing its report on a four-platform check set.
        self.assertGreaterEqual(self.profile['agents']['validator']['steps'], 80)
        self.assertIn('report file first', self.profile['agents']['validator']['system'])

    def test_rules_ask_for_one_pass_validation(self):
        rules = install.RULES.read_text(encoding='utf-8')
        self.assertIn('every failure in one pass', rules)
        self.assertIn('resume it to finish', rules)

    def test_worker_prompts_point_at_the_rules_file(self):
        rules = install.RULES.read_text(encoding='utf-8')
        for heading in ('## Workers', '## Report format'):
            self.assertIn(heading, rules)
        for name in ('implementer', 'validator'):
            self.assertIn('AGENTS.md', self.profile['agents'][name]['system'])


class ParseTest(unittest.TestCase):
    def test_jsonc_comments_are_removed_but_not_inside_strings(self):
        text = '{\n  // note\n  "url": "http://x//y", /* block */ "n": 1\n}'
        self.assertEqual(install.parse_jsonc(text), {'url': 'http://x//y', 'n': 1})

    def test_escaped_quotes_stay_inside_strings(self):
        self.assertEqual(install.parse_jsonc('{"a": "say \\"hi\\" // not a comment"}'),
                         {'a': 'say "hi" // not a comment'})

    def test_bad_jsonc_is_a_setup_error(self):
        with self.assertRaises(install.SetupError):
            install.parse_jsonc('{"a": /* open')

    def test_model_refs(self):
        self.assertEqual(install.parse_model_ref('openai/gpt-6.2-sol#high'), ('openai', 'gpt-6.2-sol', 'high'))
        self.assertEqual(install.parse_model_ref('splash/worker'), ('splash', 'worker', None))
        with self.assertRaises(install.SetupError):
            install.parse_model_ref('worker')


class BrewPlanTest(unittest.TestCase):
    def test_fresh_mac_gets_every_tap_and_package(self):
        self.assertEqual(install.brew_plan([], [], []), [
            ['brew', 'tap', 'anomalyco/tap'], ['brew', 'tap', 'incoai/tap'],
            ['brew', 'install', 'anomalyco/tap/opencode-v2'], ['brew', 'install', 'incoai/tap/splash'],
            ['brew', 'install', '--cask', 'incoai/tap/splash-app']])

    def test_installed_mac_needs_nothing(self):
        self.assertEqual(install.brew_plan(['anomalyco/tap', 'incoai/tap'], ['opencode-v2', 'splash'],
                                           ['splash-app']), [])


class FilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.src = root / 'src'
        self.src.mkdir()
        (self.src / 'p.jsonc').write_text('{"new": true}')
        (self.src / 'rules.md').write_text('# new rules\n')
        self.sources = {self.src / 'p.jsonc': 'opencode.jsonc', self.src / 'rules.md': 'AGENTS.md'}
        self.dest = root / 'config'

    def tearDown(self):
        self.tmp.cleanup()

    def install_once(self, stamp):
        move, write = install.plan_files(self.dest, self.sources)
        install.apply_files(self.dest, move, write, stamp)
        return move, write

    def test_empty_directory_gets_both_files_and_no_backup(self):
        move, write = self.install_once('t1')
        self.assertEqual(move, [])
        self.assertEqual(sorted(p.name for p, _ in write), ['AGENTS.md', 'opencode.jsonc'])
        self.assertEqual((self.dest / 'opencode.jsonc').read_text(), '{"new": true}')
        self.assertFalse(any(self.dest.glob('backup-*')))

    def test_differing_files_and_a_plain_json_config_are_backed_up(self):
        self.dest.mkdir()
        (self.dest / 'opencode.json').write_text('{"old": 1}')
        (self.dest / 'AGENTS.md').write_text('# old\n')
        (self.dest / 'service.json').write_text('{}')
        self.install_once('t2')
        backup = self.dest / 'backup-t2'
        self.assertEqual(sorted(p.name for p in backup.iterdir()), ['AGENTS.md', 'opencode.json'])
        self.assertEqual((backup / 'AGENTS.md').read_text(), '# old\n')
        self.assertFalse((self.dest / 'opencode.json').exists())
        self.assertTrue((self.dest / 'service.json').exists(), 'unrelated files stay')
        self.assertEqual((self.dest / 'AGENTS.md').read_text(), '# new rules\n')

    def test_second_run_changes_nothing(self):
        self.install_once('t3')
        self.assertEqual(install.plan_files(self.dest, self.sources), ([], []))

    def test_local_top_level_keys_survive_install(self):
        # A rerun moved a locally added MCP server (machine paths, so never in the profile) to the backup.
        (self.src / 'p.jsonc').write_text('{\n  // profile\n  "new": true\n}\n')
        self.dest.mkdir()
        mcp = {'servers': {'browse': {'type': 'local', 'command': ['/opt/browse', 'mcp']}}}
        (self.dest / 'opencode.jsonc').write_text(
            '{"theme": "dark", "new": false, "mcp": ' + install.json.dumps(mcp) + '}')
        self.install_once('t4')
        written = (self.dest / 'opencode.jsonc').read_text()
        self.assertEqual(install.parse_jsonc(written), {'new': True, 'theme': 'dark', 'mcp': mcp})
        self.assertIn('// profile', written)
        self.assertEqual(install.plan_files(self.dest, self.sources), ([], []))


class ChecksTest(unittest.TestCase):
    ROUTES = {'build': ('openai', 'gpt-6.2-sol', 'high'), 'implementer': ('splash', 'worker', 'lite-1k')}

    def test_matching_listing_has_no_problems(self):
        listing = [{'name': 'Build', 'model': {'providerID': 'openai', 'id': 'gpt-6.2-sol', 'variant': 'high'}},
                   {'name': 'implementer', 'model': {'providerID': 'splash', 'id': 'worker', 'variant': 'lite-1k'}}]
        self.assertEqual(install.route_problems(listing, self.ROUTES), [])

    def test_wrong_variant_and_missing_agent_are_reported(self):
        listing = [{'name': 'Build', 'model': {'providerID': 'openai', 'id': 'gpt-6.2-sol', 'variant': 'medium'}}]
        problems = install.route_problems(listing, self.ROUTES)
        self.assertEqual(len(problems), 2)
        self.assertIn('build', problems[0])
        self.assertIn('implementer: missing', problems[1])

    def test_login_detection(self):
        self.assertTrue(install.has_login('OpenAI  OpenAI                      stored\n'))
        self.assertFalse(install.has_login('Anthropic  Anthropic  stored\n'))
        self.assertFalse(install.has_login(''))


if __name__ == '__main__':
    unittest.main()
