"""Installer: merge, limits, sidecars and verification on temporary directories; no server or client call."""
import io
import json
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import install as I

PROFILE = I.load_json(I.PROFILE)
MODEL = 'qwen-test'
LIMITS = {'context': 262144, 'output': 32768}
INSTALLED = {
    'model': 'openai/gpt-6.1-sol#medium',
    'experimental': {'subagent_depth': 1},
    'providers': {'openai': {'name': 'OpenAI', 'settings': {'apiKey': 'sk-secret'}},
                  'omlx': {'models': {'old-model': {'name': 'old-model'}}}},
    'agents': {
        'build': {'model': 'openai/gpt-6.1-sol#medium'},
        'hybrid': {'model': 'openai/pinned', 'steps': 30,
                   'permissions': [{'action': 'shell', 'resource': '*', 'effect': 'deny'},
                                   {'action': 'shell', 'resource': 'git *', 'effect': 'allow'}]},
        'general': {'steps': 40,
                    'permissions': [{'action': 'shell', 'resource': '*', 'effect': 'allow'},
                                    {'action': 'skill', 'resource': '*', 'effect': 'deny'},
                                    {'action': 'edit', 'resource': '*/.git/*', 'effect': 'deny'}]},
    },
}


def listing(merged, model=MODEL):
    """What `opencode debug agents --standalone` prints for a merged config."""
    out = []
    for name, agent in merged['agents'].items():
        entry = {'id': name, 'steps': agent.get('steps'),
                 'permissions': [{'action': '*', 'resource': '*', 'effect': 'allow'}] + agent.get('permissions', [])}
        if agent.get('model') == I.LOCAL_MODEL:
            entry['model'] = {'providerID': 'omlx', 'id': model}
        out.append(entry)
    return out


class Merge(unittest.TestCase):
    def setUp(self):
        self.merged = I.merge(INSTALLED, PROFILE, MODEL, LIMITS)

    def test_keeps_what_the_profile_does_not_own(self):
        self.assertEqual(self.merged['model'], 'openai/gpt-6.1-sol#medium')
        self.assertEqual(self.merged['experimental'], {'subagent_depth': 1})
        self.assertEqual(self.merged['providers']['openai'], INSTALLED['providers']['openai'])
        self.assertEqual(self.merged['agents']['build'], INSTALLED['agents']['build'])
        self.assertIn('old-model', self.merged['providers']['omlx']['models'])
        self.assertEqual(self.merged['default_agent'], 'hybrid')

    def test_local_model_is_keyed_by_its_served_id_with_the_chosen_limits(self):
        models = self.merged['providers']['omlx']['models']
        self.assertNotIn(I.MODEL_REF, models)
        self.assertEqual(models[MODEL]['name'], MODEL)
        self.assertEqual(models[MODEL]['limit'], LIMITS)
        self.assertEqual(self.merged['providers']['omlx']['settings']['apiKey'], '{file:./omlx.key}')

    def test_profile_fields_replace_installed_ones(self):
        for name, wanted in PROFILE['agents'].items():
            for key, value in wanted.items():
                if key != 'permissions':
                    self.assertEqual(self.merged['agents'][name][key], value, (name, key))

    def test_compaction_overrides_stale_cloud_pin_and_is_verified_local(self):
        installed = dict(INSTALLED, agents=dict(INSTALLED['agents'],
                         compaction={'model': 'openai/stale#medium'}))
        merged = I.merge(installed, PROFILE, MODEL, LIMITS)
        self.assertEqual(merged['agents']['compaction']['model'], I.LOCAL_MODEL)
        agents = listing(merged)
        next(a for a in agents if a['id'] == 'compaction')['model'] = {'providerID': 'openai', 'id': 'stale'}
        self.assertTrue(any('compaction runs on' in p for p in I.check_agents(agents, PROFILE, MODEL)))
        self.assertEqual(merged['model'], installed['model'])
        self.assertEqual(merged['providers']['openai'], installed['providers']['openai'])

    def test_cloud_roles_never_keep_a_pinned_model(self):
        self.assertNotIn('model', self.merged['agents']['hybrid'])
        self.assertNotIn('model', self.merged['agents']['review'])

    def test_shell_restrictions_and_legacy_rules_go_custom_rules_stay_before_the_profile(self):
        hybrid = self.merged['agents']['hybrid']['permissions']
        self.assertNotIn({'action': 'shell', 'resource': '*', 'effect': 'deny'}, hybrid)
        self.assertEqual(hybrid[0], {'action': 'shell', 'resource': 'git *', 'effect': 'allow'})
        self.assertEqual(hybrid[1:], PROFILE['agents']['hybrid']['permissions'])
        general = self.merged['agents']['general']['permissions']
        self.assertNotIn({'action': 'skill', 'resource': '*', 'effect': 'deny'}, general)
        self.assertEqual(general[0], {'action': 'edit', 'resource': '*/.git/*', 'effect': 'deny'})
        self.assertEqual(general.count({'action': 'shell', 'resource': '*', 'effect': 'allow'}), 1)

    def test_merging_twice_changes_nothing(self):
        self.assertEqual(I.merge(self.merged, PROFILE, MODEL, LIMITS), self.merged)


class Choices(unittest.TestCase):
    def test_limits_follow_the_served_length_unless_given(self):
        profile_limit = {'context': 131072, 'output': 32768}
        self.assertEqual(I.choose_limits(None, None, 262144, profile_limit), {'context': 262144, 'output': 32768})
        self.assertEqual(I.choose_limits(None, None, 32768, profile_limit), {'context': 32768, 'output': 8192})
        self.assertEqual(I.choose_limits(None, None, None, profile_limit), {'context': 131072, 'output': 32768})
        self.assertEqual(I.choose_limits(65536, 4096, 262144, profile_limit), {'context': 65536, 'output': 4096})
        with self.assertRaises(I.SetupError):
            I.choose_limits(8192, 8192, None, profile_limit)

    def test_model_must_be_served_and_unambiguous(self):
        self.assertEqual(I.choose_model(None, None, {'only': 1}), 'only')
        self.assertEqual(I.choose_model(None, 'b', {'a': 1, 'b': 2}), 'b')
        self.assertEqual(I.choose_model('a', 'b', {}), 'a')
        with self.assertRaises(I.SetupError):
            I.choose_model(None, None, {'a': 1, 'b': 2})
        with self.assertRaises(I.SetupError):
            I.choose_model('c', None, {'a': 1})


class Verify(unittest.TestCase):
    def setUp(self):
        self.merged = I.merge(INSTALLED, PROFILE, MODEL, LIMITS)

    def test_installed_profile_passes(self):
        self.assertEqual(I.check_agents(listing(self.merged), PROFILE, MODEL), [])

    def test_wrong_local_model_steps_pins_and_shell_denials_are_problems(self):
        broken = listing(self.merged, model='other')
        for agent in broken:
            if agent['id'] == 'review':
                agent['model'] = {'providerID': 'openai', 'id': 'pinned'}
            if agent['id'] == 'hybrid':
                agent['steps'] = 30
                agent['permissions'].append({'action': 'shell', 'resource': 'tee *', 'effect': 'ask'})
        problems = '\n'.join(I.check_agents(broken, PROFILE, MODEL))
        for phrase in ('general runs on', 'explore runs on', 'review pins', 'hybrid has 30 steps', 'hybrid would ask'):
            self.assertIn(phrase, problems)
        self.assertEqual(I.check_agents({}, PROFILE, MODEL), ['OpenCode did not list its agents'])


class Install(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / 'opencode.json').write_text(json.dumps(INSTALLED, indent=2), encoding='utf-8')
        (self.dir / 'omlx.key').write_text('local-key\n', encoding='utf-8')

    def run_install(self, *extra, served=None, agents=None):
        served = {MODEL: 262144} if served is None else served
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(I, 'served_models', return_value=served), \
                mock.patch.object(I.shutil, 'which', return_value='/bin/opencode'), \
                mock.patch.object(I, 'effective_agents', side_effect=lambda _: agents(self.read())), \
                mock.patch.dict(I.os.environ, {}, clear=False), redirect_stdout(out), redirect_stderr(err):
            I.os.environ.pop('OMLX_API_KEY', None)
            code = I.main(['--config-dir', str(self.dir), *extra])
        return code, out.getvalue(), err.getvalue()

    def read(self):
        return json.loads((self.dir / 'opencode.json').read_text(encoding='utf-8'))

    def test_installs_sidecars_backs_up_and_verifies(self):
        code, out, err = self.run_install(agents=listing)
        self.assertEqual(code, 0, err)
        self.assertEqual((self.dir / 'local-model.txt').read_text(), MODEL + '\n')
        self.assertEqual((self.dir / 'omlx-url.txt').read_text(), I.DEFAULT_URL + '\n')
        self.assertEqual(stat.S_IMODE((self.dir / 'omlx.key').stat().st_mode), 0o600)
        self.assertEqual(len(list(self.dir.glob('opencode.json.bak-*'))), 1)
        self.assertEqual(self.read()['agents']['general']['steps'], PROFILE['agents']['general']['steps'])
        self.assertNotIn('local-key', out + err)

    def test_dry_run_writes_nothing_and_hides_secrets(self):
        (self.dir / 'opencode.json').write_text(json.dumps(INSTALLED, indent=2), encoding='utf-8')
        before = (self.dir / 'opencode.json').read_text()
        code, out, _ = self.run_install('--dry-run')
        self.assertEqual(code, 0)
        self.assertEqual((self.dir / 'opencode.json').read_text(), before)
        self.assertFalse((self.dir / 'local-model.txt').exists())
        self.assertIn('"steps": 200', out)
        self.assertNotIn('sk-secret', out)

    def test_failed_verification_exits_nonzero(self):
        def pinned(config):
            agents = listing(config)
            agents[[a['id'] for a in agents].index('review')]['model'] = {'providerID': 'openai', 'id': 'x'}
            return agents
        code, _, err = self.run_install(agents=pinned)
        self.assertEqual(code, 1)
        self.assertIn('review pins', err)

    def test_missing_key_or_unreachable_server_stops_before_writing(self):
        (self.dir / 'omlx.key').unlink()
        before = (self.dir / 'opencode.json').read_text()
        code, _, err = self.run_install()
        self.assertEqual(code, 1)
        self.assertIn('no oMLX key', err)
        (self.dir / 'omlx.key').write_text('k\n', encoding='utf-8')
        with mock.patch.object(I, 'served_models', side_effect=I.SetupError('cannot list models')), \
                redirect_stderr(io.StringIO()) as err:
            self.assertEqual(I.main(['--config-dir', str(self.dir), '--skip-verify']), 1)
        self.assertIn('pass --model and --context', err.getvalue())
        self.assertEqual((self.dir / 'opencode.json').read_text(), before)


if __name__ == '__main__':
    unittest.main()
