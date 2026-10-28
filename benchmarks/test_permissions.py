"""Permission gate: real `opencode debug agents` rule shapes, no client or model call."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import permissions as P

DEFAULTS = [{'action': '*', 'resource': '*', 'effect': 'allow'},
            {'action': 'read', 'resource': '*.env', 'effect': 'ask'},
            {'action': 'read', 'resource': '*.env.example', 'effect': 'allow'}]
OPEN = {'hybrid': DEFAULTS + [{'action': 'edit', 'resource': '*', 'effect': 'deny'},
                              {'action': 'subagent', 'resource': '*', 'effect': 'deny'},
                              {'action': 'subagent', 'resource': 'general', 'effect': 'allow'},
                              {'action': 'subagent', 'resource': 'explore', 'effect': 'allow'},
                              {'action': 'subagent', 'resource': 'review', 'effect': 'allow'}],
        'general': DEFAULTS + [{'action': 'subagent', 'resource': '*', 'effect': 'deny'},
                               {'action': 'edit', 'resource': '/Users/me/.config/opencode/*', 'effect': 'deny'},
                               {'action': 'edit', 'resource': '*/.git/*', 'effect': 'deny'}],
        'review': DEFAULTS + [{'action': 'edit', 'resource': '*', 'effect': 'deny'},
                              {'action': 'subagent', 'resource': '*', 'effect': 'deny'}]}
# The deny-by-default allowlist that rejected every M5 Max Hybrid arm on 2026-10-28.
ALLOWLIST = [{'action': 'shell', 'resource': '*', 'effect': 'deny'}] + [
    {'action': 'shell', 'resource': pattern, 'effect': 'allow'} for pattern in
    ('pwd', 'ls*', 'cat *', 'git status*', 'git diff*', 'git ls-files*', 'shasum *', 'python3 -m unittest*',
     './check.sh bench-*', 'PYTHONDONTWRITEBYTECODE=1 python3 -m unittest*')]
CHECK, REPO = './check.sh bench-opencode', '/runs/r1/arms/opencode/repo'
ALLOWED = ['ListApp/ContentView.swift', 'ListApp/ItemListModel.swift']


def agents(**overrides):
    rules = dict(OPEN, **overrides)
    return [{'id': role, 'permissions': rules[role]} for role in rules]


def gate(listing):
    return P.gate(listing, check=CHECK, repo=REPO, allowed_changed=ALLOWED)


class Decisions(unittest.TestCase):
    def test_last_matching_rule_wins_with_wildcards(self):
        explore = DEFAULTS + [{'action': '*', 'resource': '*', 'effect': 'deny'},
                              {'action': 'shell', 'resource': '*', 'effect': 'allow'}]
        self.assertEqual(P.decide(explore, 'shell', 'rm -rf x')[0], 'allow')
        self.assertEqual(P.decide(explore, 'edit', 'a.py')[0], 'deny')
        self.assertEqual(P.decide(DEFAULTS, 'read', 'prod.env')[0], 'ask')
        self.assertEqual(P.decide([], 'shell', 'ls')[0], 'unknown')

    def test_shell_commands_are_judged_one_pipeline_part_at_a_time(self):
        self.assertEqual(P.command_parts('cd r && ./check.sh x 2>&1 | tee r/l; printf a || echo b'),
                         ['cd r', './check.sh x 2>&1', 'tee r/l', 'printf a', 'echo b'])


class Gate(unittest.TestCase):
    def test_open_shell_passes_and_keeps_role_boundaries_out_of_scope(self):
        blockers, decisions = gate(agents())
        self.assertEqual(blockers, [])
        self.assertTrue(all(d['effect'] == 'allow' for d in decisions))
        self.assertIn({'agent': 'general', 'action': 'edit', 'resource': f'{REPO}/ListApp/ContentView.swift'},
                      [{k: d[k] for k in ('agent', 'action', 'resource')} for d in decisions])

    def test_the_m5_max_allowlist_is_refused_before_any_round(self):
        blockers, _ = gate(agents(general=OPEN['general'] + ALLOWLIST, review=OPEN['review'] + ALLOWLIST))
        self.assertEqual(len(blockers), 2)
        general = next(b for b in blockers if ' general ' in b)
        self.assertIn('deny shell `tee', general)
        self.assertIn('deny shell `cd', general)
        self.assertIn("shell '*' deny", general)
        self.assertIn('deny shell `printf', next(b for b in blockers if ' review ' in b))
        self.assertIn('never reword prompts', general)

    def test_ask_and_missing_roles_block_because_a_noninteractive_run_cannot_answer(self):
        blockers, _ = gate([a for a in agents(hybrid=OPEN['hybrid'] + [
            {'action': 'shell', 'resource': 'git diff*', 'effect': 'ask'}]) if a['id'] != 'review'])
        self.assertTrue(any('hybrid agent would ask shell `git diff' in b for b in blockers))
        self.assertTrue(any('no effective review agent' in b for b in blockers))

    def test_a_worker_that_cannot_edit_its_allowed_files_is_refused(self):
        blockers, _ = gate(agents(general=OPEN['general'] + [{'action': 'edit', 'resource': '*', 'effect': 'deny'}]))
        self.assertIn('deny edit', blockers[0])


class Probe(unittest.TestCase):
    def stream(self, *states):
        return '\n'.join(json.dumps({'type': 'tool_use', 'part': {'type': 'tool', 'tool': 'shell', 'state': state}})
                         for state in states)

    def test_stream_and_stored_denial_shapes_are_both_denials(self):
        result = P.probe_result(self.stream(
            {'status': 'completed', 'input': {'command': 'git status'}},
            {'status': 'error', 'input': {'command': 'x | tee l'}, 'error': 'Permission denied: shell'},
            {'status': 'error', 'input': {'command': 'printf a'}, 'error': {'type': 'permission.rejected'}},
            {'status': 'error', 'input': {'command': 'false'}, 'error': 'exit 1'}))
        self.assertEqual(result['tool_calls'], 4)
        self.assertEqual(result['denied'], ['x | tee l', 'printf a'])

    def test_model_text_and_client_errors_are_not_denials(self):
        text = json.dumps({'type': 'text', 'part': {'type': 'text', 'text': '"error": "Permission denied: shell"'}})
        error = json.dumps({'type': 'error', 'error': {'message': 'usage limit reached'}})
        result = P.probe_result(text + '\nnot json\n' + error)
        self.assertEqual((result['tool_calls'], result['denied']), (0, []))
        self.assertEqual(result['errors'], ['usage limit reached'])


if __name__ == '__main__':
    unittest.main()
