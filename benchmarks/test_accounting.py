"""Offline, focused checks for the accounting/evidence module. No CLI, no network."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import accounting as A
import accounting_test_helpers as H


def codex(**over):
    return A.account_codex(H.codex_catalog(**over), [H.ROOT, H.CHILD], **H.CODEX_KW)


def blockers_have(result, phrase):
    return any(phrase in b for b in result['blockers'])


class CodexUsage(unittest.TestCase):
    def test_disjoint_subsets_add_up_to_the_recorded_total(self):
        parts = A.codex_disjoint({'input_tokens': 100, 'cached_input_tokens': 80,
                                  'output_tokens': 20, 'reasoning_output_tokens': 5,
                                  'total_tokens': 120})
        self.assertEqual((parts['uncached_input'], parts['cached_input']), (20, 80))
        self.assertEqual((parts['non_reasoning_output'], parts['reasoning_output']), (15, 5))
        self.assertEqual(parts['cloud_total'], 120)
        self.assertEqual(parts['cloud_total'], parts['raw_total'])

    def test_final_cumulative_usage_counted_once_per_root_and_descendant(self):
        result = codex()
        self.assertEqual(result['totals']['cloud_total'], 1700)
        self.assertEqual(result['totals']['cached_input'], 500)
        self.assertEqual(result['reasoning_output_total'], 80)
        self.assertEqual(result['cloud_total'], 1700)
        self.assertTrue(result['usage_complete'] and result['routing_ok'])
        self.assertEqual([s['role'] for s in result['sessions']], ['root', 'child'])
        self.assertEqual(result['root_final_text'], 'VERDICT: PASS ' + H.SHA)
        root_only = A.account_codex(H.codex_catalog(), [H.ROOT], **H.CODEX_KW)
        self.assertEqual(root_only['totals']['cloud_total'], 1300)
        self.assertEqual(root_only['known_lower_bound'], 1300)
        self.assertEqual(root_only['children'], 0)
        self.assertFalse(root_only['routing_ok'])

    def test_malformed_or_negative_counters_are_incomplete_never_zero(self):
        self.assertEqual((A.as_counter(12), A.as_counter(20.0), A.as_counter(0)), (12, 20, 0))
        for bad in ('30k', -5, 2.5, True, [5], {'n': 1}, None):
            self.assertIsNone(A.as_counter(bad), bad)
        parts = A.codex_disjoint({'input_tokens': 100, 'output_tokens': '30k', 'total_tokens': 130})
        self.assertFalse(parts['complete'])
        self.assertEqual(parts['missing_fields'], [])
        self.assertEqual(parts['invalid_fields'], ['output_tokens'])
        result = codex(child_usage={'input_tokens': 300, 'output_tokens': -100, 'total_tokens': 400})
        self.assertEqual(result['sessions'][1]['usage_status'], 'incomplete')
        self.assertFalse(result['usage_complete'])
        self.assertIsNone(result['cloud_total'])
        self.assertEqual(result['known_lower_bound'], 1300)
        self.assertTrue(blockers_have(result, 'malformed counter'))

    def test_repeated_token_count_updates_do_not_double_count(self):
        catalog = H.codex_catalog()
        catalog[H.CHILD]['usage_updates'] = 4
        self.assertEqual(A.account_codex(catalog, [H.ROOT, H.CHILD], **H.CODEX_KW)['cloud_total'], 1700)

    def test_missing_usage_field_is_unknown_not_zero(self):
        parts = A.codex_disjoint({'input_tokens': 100, 'output_tokens': 20})
        self.assertFalse(parts['complete'])
        self.assertEqual(parts['missing_fields'], ['total_tokens'])
        result = codex(child_usage={'input_tokens': 300, 'output_tokens': 100})
        self.assertFalse(result['usage_complete'])
        self.assertIsNone(result['cloud_total'])
        self.assertEqual(result['known_lower_bound'], 1300)
        self.assertEqual(result['sessions'][1]['usage_status'], 'incomplete')

    def test_inconsistent_counters_are_not_attributed(self):
        result = codex(child_usage={'input_tokens': 100, 'cached_input_tokens': 300,
                                    'output_tokens': 50, 'reasoning_output_tokens': 0,
                                    'total_tokens': 150})
        self.assertEqual(result['sessions'][1]['usage_status'], 'inconsistent')
        self.assertFalse(result['usage_complete'])
        self.assertTrue(blockers_have(result, 'inconsistent'))


    def test_cache_write_input_is_a_reported_subset_of_input_never_extra_spend(self):
        recorded = {'input_tokens': 100, 'cached_input_tokens': 60, 'cache_write_input_tokens': 30,
                    'output_tokens': 20, 'reasoning_output_tokens': 5, 'total_tokens': 120}
        parts = A.codex_disjoint(recorded)
        self.assertTrue(parts['complete'])
        self.assertEqual((parts['cache_write_input'], parts['cloud_total']), (30, 120))
        result = codex(root_usage=recorded)
        self.assertTrue(result['usage_complete'], result['blockers'])
        self.assertEqual(result['cache_write_input_total'], 30)
        self.assertEqual(result['cloud_total'], 120 + 400)
        oversized = codex(root_usage=dict(recorded, cache_write_input_tokens=101))
        self.assertFalse(oversized['usage_complete'])
        self.assertEqual(oversized['sessions'][0]['usage_status'], 'inconsistent')
        malformed = A.codex_disjoint(dict(recorded, cache_write_input_tokens='30k'))
        self.assertEqual(malformed['invalid_fields'], ['cache_write_input_tokens'])
        self.assertFalse(malformed['complete'])


class CodexFailClosed(unittest.TestCase):
    def test_worker_turns_beyond_one_repair_fail_closed_whatever_tool_dispatched_them(self):
        # Real Codex multi-agent roots dispatch follow-ups with send_message/followup_task; the
        # worker's own task_started markers are the authoritative count of turns it actually ran.
        def worker_turns(turns, **kwargs):
            catalog = H.codex_catalog()
            catalog[H.CHILD]['completion_markers'] = ['task_started', 'task_complete'] * turns
            return A.account_codex(catalog, [H.ROOT, H.CHILD], **H.CODEX_KW, **kwargs)
        three = worker_turns(3)
        self.assertEqual(three['sessions'][1]['turns'], 3)
        self.assertEqual(three['root_dispatch_calls']['followup'], 0)
        self.assertFalse(three['routing_ok'])
        self.assertTrue(blockers_have(three, f'worker {H.CHILD} ran 3 turn(s)'))
        repaired = worker_turns(2)
        self.assertTrue(repaired['routing_ok'], repaired['blockers'])
        self.assertFalse(worker_turns(2, max_worker_turns=1)['routing_ok'])

    def test_up_to_four_parallel_luna_workers_each_routed_and_finished(self):
        def children(count, **child):
            catalog = H.codex_catalog()
            ids = [H.ROOT]
            for index in range(count):
                sid = f'w{index}'
                catalog[sid] = H.entry(sid, parent=H.ROOT, total=H.usage(100, 50, 10, 2), **dict({'model': H.LUNA}, **child))
                ids.append(sid)
            del catalog[H.CHILD]
            catalog[H.ROOT]['spawn_calls'] = count
            return A.account_codex(catalog, ids, **H.CODEX_KW)
        four = children(4)
        self.assertTrue(four['routing_ok'], four['blockers'])
        self.assertEqual(four['children'], 4)
        self.assertEqual(four['seats']['worker']['total'], 4 * 110)
        five = children(5)
        self.assertFalse(five['routing_ok'])
        self.assertTrue(blockers_have(five, 'at most 4'))
        wrong = children(2, model='gpt-6.1-sol')
        self.assertFalse(wrong['routing_ok'])
        self.assertEqual(wrong['seats']['worker']['total'], 0)

    def test_seats_split_sol_planner_and_luna_worker_and_sum_to_the_total(self):
        result = codex()
        planner, worker = result['seats']['planner'], result['seats']['worker']
        self.assertEqual((planner['model'], worker['model']), (H.SOL, H.LUNA))
        self.assertEqual((planner['uncached_input'], planner['cached_input'], planner['output'], planner['reasoning']), (600, 400, 300, 60))
        self.assertEqual(planner['total'] + worker['total'] + result['seats']['unknown']['total'], result['cloud_total'])
        self.assertEqual(result['by_model'][H.LUNA]['total'], worker['total'])

    def test_missing_child_model_is_never_assumed(self):
        result = codex(child_models=[])
        self.assertEqual(result['unexpected_models'], [f'{H.CHILD}:child:missing-model'])
        self.assertFalse(result['routing_ok'])
        self.assertTrue(blockers_have(result, 'recorded no model'))

    def test_missing_reasoning_effort_is_never_assumed(self):
        result = codex(child_effort=None)
        self.assertEqual(result['effort_mismatch'], [f'{H.CHILD}:child:missing-effort'])
        self.assertFalse(result['routing_ok'])
        self.assertTrue(blockers_have(result, 'no reasoning effort'))

    def test_wrong_reasoning_effort_is_recorded_not_accepted(self):
        result = codex(child_effort='high')
        self.assertEqual(result['effort_mismatch'], [f'{H.CHILD}:child:high'])
        self.assertFalse(result['routing_ok'])
        self.assertTrue(blockers_have(result, 'instead of'))

    def test_missing_completion_evidence_is_not_an_accepted_arm(self):
        for state in ('active', 'aborted', 'unknown'):
            result = codex(child_completion=state)
            self.assertEqual(result['incomplete_sessions'], [f'{H.CHILD}:child:{state}'])
            self.assertFalse(result['routing_ok'])
            self.assertTrue(blockers_have(result, 'no task_complete marker'), state)

    def test_observed_descendant_without_rollout(self):
        result = A.account_codex(H.codex_catalog(), [H.ROOT, H.CHILD, 'ghost'], **H.CODEX_KW)
        self.assertEqual(result['missing_rollouts'], ['ghost'])
        self.assertFalse(result['routing_ok'])
        self.assertTrue(blockers_have(result, 'no rollout file'))

    def test_missing_rollout_can_never_leave_an_exact_total(self):
        result = A.account_codex(H.codex_catalog(), [H.ROOT, H.CHILD, 'ghost'], **H.CODEX_KW)
        self.assertFalse(result['usage_complete'])
        self.assertIsNone(result['cloud_total'])
        self.assertEqual(result['known_lower_bound'], 1700)
        self.assertEqual(result['totals']['cloud_total'], 1700)

    def test_duplicate_session_ids_are_counted_once(self):
        result = A.account_codex(H.codex_catalog(), [H.ROOT, H.CHILD, H.CHILD], **H.CODEX_KW)
        self.assertEqual(result['duplicate_session_ids'], [H.CHILD])
        self.assertEqual(result['session_count'], 2)
        self.assertEqual(result['totals']['cloud_total'], 1700)
        self.assertEqual(result['known_lower_bound'], 1700)
        self.assertFalse(result['routing_ok'])
        self.assertTrue(blockers_have(result, 'counted once, never twice'))

    def test_missing_child_usage_keeps_only_a_lower_bound(self):
        result = codex(child_usage=None)
        self.assertFalse(result['usage_complete'])
        self.assertIsNone(result['cloud_total'])
        self.assertEqual(result['known_lower_bound'], 1300)
        self.assertTrue(blockers_have(result, 'no usage record'))

    def test_routing_errors_block_the_arm(self):
        catalog = H.codex_catalog()
        catalog['c2'] = H.entry('c2', parent=H.ROOT, model=H.LUNA, total=H.usage(10, 0, 10, 0))
        catalog[H.ROOT]['spawn_calls'] = 2
        two_children = A.account_codex(catalog, [H.ROOT, H.CHILD, 'c2'], **H.CODEX_KW)
        self.assertEqual(two_children['children'], 2)
        self.assertTrue(two_children['routing_ok'], two_children['blockers'])
        self.assertFalse(A.account_codex(catalog, [H.ROOT, H.CHILD, 'c2'], max_workers=1, **H.CODEX_KW)['routing_ok'])
        editing_catalog = H.codex_catalog()
        editing_catalog[H.ROOT]['edit_calls'] = 3
        editing = A.account_codex(editing_catalog, [H.ROOT, H.CHILD], **H.CODEX_KW)
        self.assertFalse(editing['routing_ok'])
        self.assertTrue(blockers_have(editing, 'root must plan and review only'))
        unowned = codex(spawn_ids=(H.CHILD, 'ghost'))
        self.assertFalse(unowned['routing_ok'])
        self.assertTrue(blockers_have(unowned, 'unrollowned spawn'))


class CodexRolloutFiles(unittest.TestCase):
    def test_session_meta_source_may_be_a_string_or_an_object(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / 'sessions' / '2026-10-26'
            root = H.write_rollout(home / f'{H.ROOT}.jsonl', H.ROOT, total=H.usage(300, 100, 50, 10),
                                   spawn_ids=(H.CHILD,), source='cli')
            child = H.write_rollout(home / f'{H.CHILD}.jsonl', H.CHILD, parent=H.ROOT, model=H.LUNA,
                                    total=H.usage(100, 0, 20, 0))
            root_rec, child_rec = A.scan_codex_rollout(root), A.scan_codex_rollout(child)
            self.assertEqual((root_rec['session_id'], root_rec['parent_id']), (H.ROOT, None))
            self.assertEqual((child_rec['session_id'], child_rec['parent_id']), (H.CHILD, H.ROOT))
            for odd in ('worker', 7, None, [], {'subagent': 'plain'}, {'subagent': {'thread_spawn': 5}}):
                odd_path = Path(raw) / f'odd-{type(odd).__name__}.jsonl'
                H.write_rollout(odd_path, 'odd', source=odd)
                self.assertEqual(A.scan_codex_rollout(odd_path)['session_id'], 'odd', odd)

    def test_real_multi_agent_rollout_shapes_keep_the_root_verdict_its_own(self):
        # Shapes observed in Codex 0.163/0.164 rollouts: spawn_agent returns only a task name,
        # lineage lives in session_meta, and a worker's message to the root is a response_item
        # agent_message authored by the worker.  That message must never become the root verdict.
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / 'sessions' / '2026-10-26'
            root = H.write_rollout(home / f'{H.ROOT}.jsonl', H.ROOT, total=H.usage(300, 100, 50, 10))
            events = [json.loads(line) for line in root.read_text().splitlines()]
            events[3:3] = [
                {'timestamp': H.T0, 'type': 'response_item',
                 'payload': {'type': 'function_call', 'name': 'spawn_agent', 'call_id': 'c1'}},
                {'timestamp': H.T0, 'type': 'response_item',
                 'payload': {'type': 'function_call_output', 'call_id': 'c1',
                             'output': json.dumps({'task_name': '/root/worker'})}},
                {'timestamp': H.T0, 'type': 'response_item',
                 'payload': {'type': 'message', 'role': 'assistant',
                             'content': [{'type': 'output_text', 'text': 'Root reviewed it.\nVERDICT: FAIL ' + H.SHA}]}},
                {'timestamp': H.T1, 'type': 'response_item',
                 'payload': {'type': 'agent_message', 'author': '/root/worker', 'recipient': '/root',
                             'message': 'VERDICT: PASS ' + H.SHA,
                             'content': [{'type': 'input_text', 'text': 'VERDICT: PASS ' + H.SHA}]}}]
            root.write_text(''.join(json.dumps(event) + '\n' for event in events))
            H.write_rollout(home / f'{H.CHILD}.jsonl', H.CHILD, parent=H.ROOT, model=H.LUNA,
                            total=H.usage(100, 0, 20, 0))
            catalog = A.scan_codex_rollouts(Path(raw) / 'sessions')
            self.assertEqual(catalog[H.ROOT]['spawned_ids'], [])
            self.assertEqual(A.codex_tree(catalog, H.ROOT), sorted([H.ROOT, H.CHILD]))
            result = A.account_codex(catalog, A.codex_tree(catalog, H.ROOT), **H.CODEX_KW)
            self.assertEqual(result['root_final_text'], 'Root reviewed it.\nVERDICT: FAIL ' + H.SHA)
            self.assertEqual(A.semantic_verdict(result['root_final_text'], H.SHA)['status'], 'not_pass')

    def test_malformed_rollout_lines_prevent_complete_evidence(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / 'sessions' / '2026-10-26'
            H.write_rollout(home / f'{H.ROOT}.jsonl', H.ROOT, total=H.usage(300, 100, 50, 10),
                            spawn_ids=(H.CHILD,), assistant='VERDICT: PASS ' + H.SHA)
            H.write_rollout(home / f'{H.CHILD}.jsonl', H.CHILD, parent=H.ROOT, model=H.LUNA,
                            total=H.usage(100, 0, 20, 0))
            catalog = A.scan_codex_rollouts(Path(raw) / 'sessions')
            clean = A.account_codex(catalog, A.codex_tree(catalog, H.ROOT), **H.CODEX_KW)
            self.assertTrue(clean['usage_complete'])
            self.assertEqual(clean['cloud_total'], 470)
            H.write_rollout(home / f'{H.CHILD}.jsonl', H.CHILD, parent=H.ROOT, model=H.LUNA,
                            total=H.usage(100, 0, 20, 0), malformed=3)
            catalog = A.scan_codex_rollouts(Path(raw) / 'sessions')
            self.assertEqual(catalog[H.CHILD]['malformed_lines'], 3)
            torn = A.account_codex(catalog, A.codex_tree(catalog, H.ROOT), **H.CODEX_KW)
            self.assertEqual(torn['malformed_rollouts'], [f'{H.CHILD}:3'])
            self.assertFalse(torn['usage_complete'])
            self.assertIsNone(torn['cloud_total'])
            self.assertEqual(torn['known_lower_bound'], 470)
            self.assertTrue(blockers_have(torn, 'malformed line'))

    def test_rollouts_are_parsed_from_disk(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / 'sessions' / '2026-10-26'
            H.write_rollout(home / f'{H.ROOT}.jsonl', H.ROOT, total=H.usage(300, 100, 50, 10),
                            spawn_ids=(H.CHILD,), assistant='VERDICT: PASS ' + H.SHA)
            H.write_rollout(home / f'{H.CHILD}.jsonl', H.CHILD, parent=H.ROOT, model=H.LUNA,
                            total=H.usage(100, 0, 20, 0), completion='aborted', malformed=2)
            catalog = A.scan_codex_rollouts(Path(raw) / 'sessions')
            self.assertEqual(sorted(catalog), sorted([H.ROOT, H.CHILD]))
            self.assertEqual(catalog[H.CHILD]['parent_id'], H.ROOT)
            self.assertEqual(catalog[H.ROOT]['spawned_ids'], [H.CHILD])
            self.assertEqual(catalog[H.CHILD]['completion'], 'aborted')
            self.assertEqual(catalog[H.CHILD]['malformed_lines'], 2)
            self.assertEqual(catalog[H.ROOT]['usage'], H.usage(300, 100, 50, 10))
            self.assertEqual(A.codex_tree(catalog, H.ROOT), sorted([H.ROOT, H.CHILD]))
            result = A.account_codex(catalog, A.codex_tree(catalog, H.ROOT), **H.CODEX_KW)
            self.assertEqual(result['incomplete_sessions'], [f'{H.CHILD}:child:aborted'])
            self.assertFalse(result['routing_ok'])

    def test_unknown_root_thread_fails_preflight(self):
        with self.assertRaises(A.PreflightBlocker):
            A.codex_tree({}, H.ROOT)


class VerdictSemantics(unittest.TestCase):
    def test_only_a_plain_digest_bound_verdict_counts(self):
        fence = '`' * 3
        shapes = [(fence + 'VERDICT: PASS ' + H.SHA + fence, 'absent'),
                  (fence + '\nVERDICT: PASS ' + H.SHA + '\n' + fence, 'forged'),
                  ('said "VERDICT: PASS ' + H.SHA + '"', 'absent'),
                  ('> VERDICT: PASS ' + H.SHA, 'forged'),
                  ('**VERDICT: PASS ' + H.SHA + '**', 'pass')]
        for shape, expected in shapes:
            verdict = A.semantic_verdict(shape, H.SHA)
            self.assertEqual(verdict['status'], expected, shape)
            if expected == 'forged':
                self.assertTrue(verdict['rejected_non_plain'], shape)
                self.assertFalse(verdict['digest_matches'], shape)
        good = A.semantic_verdict('VERDICT: PASS ' + H.SHA, H.SHA)
        self.assertEqual((good['status'], good['digest_matches']), ('pass', True))
        self.assertFalse(A.semantic_verdict('VERDICT: PASS ' + H.SHA, 'b' * 64)['digest_matches'])
        self.assertEqual(A.semantic_verdict('VERDICT: PASS', H.SHA)['status'], 'missing_digest')
        self.assertEqual(A.semantic_verdict('tests green', H.SHA)['status'], 'absent')
        self.assertEqual(A.semantic_verdict('VERDICT: FAIL ' + H.SHA, H.SHA)['status'], 'not_pass')


class NativeConfig(unittest.TestCase):
    def test_secrets_are_dropped_and_refs_resolved(self):
        with tempfile.TemporaryDirectory() as raw:
            path = H.native_config(Path(raw) / 'native.json')
            snap = A.config_snapshot(path, {'GW_HOST': ' gw.example ', 'LOCAL_ID': 'qwen-3.8-nf-splash'})
            dump = json.dumps(snap['snapshot'])
            self.assertNotIn('super-secret-value', dump)
            self.assertNotIn('Authorization', dump)
            self.assertEqual(snap['stats']['redacted_fields'], 2)
            self.assertEqual(snap['snapshot']['base_url'], 'https://gw.example/gw.example')
            self.assertEqual(snap['snapshot']['worker']['model_ref'], 'qwen-3.8-nf-splash')
            self.assertEqual(snap['snapshot']['missing'], '<missing-file:nope.json>')
            self.assertEqual(snap['snapshot']['x_trace'], '<unset-env:ABSENT_REGION>')
            self.assertEqual(snap['snapshot']['x_route'], '<redacted-unresolved-credential-ref>')
            self.assertEqual(snap['snapshot']['headers'], {})
            self.assertEqual(snap['snapshot']['creds'], '<redacted-unresolved-credential-ref>')
            self.assertEqual(snap['raw_sha256'], A.sha256_bytes(path.read_bytes()))
            blockers, observed = A.validate_native_profile(snap, H.LOCAL_MODEL)
            self.assertEqual(blockers, [])
            self.assertEqual((observed['default_agent'], observed['subagent_depth']), ('hybrid', 2))

    def test_profile_pinning_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            path = H.native_config(Path(raw) / 'native.json',
                                   agents={'general': {'model': 'other'}, 'hybrid': {'model': 'gpt-6.1-sol'},
                                           'review': {'model': 'gpt-6.1-sol'}})
            snap = A.config_snapshot(path)
            blockers, observed = A.validate_native_profile(snap, H.LOCAL_MODEL)
            self.assertEqual(len(blockers), 3)
            self.assertTrue(any('pins model' in b for b in blockers))
            self.assertTrue(any('--local-model' in b for b in blockers))
            self.assertTrue(observed['hybrid_has_model'] and observed['review_has_model'])

    def test_missing_or_jsonc_config_fails_preflight(self):
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(A.PreflightBlocker):
                A.config_snapshot(Path(raw) / 'absent.json')
            jsonc = Path(raw) / 'jsonc.json'
            jsonc.write_text('{ "agents": {} } // comment', encoding='utf-8')
            with self.assertRaisesRegex(A.PreflightBlocker, 'strict JSON'):
                A.config_snapshot(jsonc)


class OpenCodeAccounting(unittest.TestCase):
    def test_gap_free_arm_is_exact_and_counted_once_per_message(self):
        result = H.hybrid_arm()
        self.assertEqual(result['cloud_total'], 2000)
        self.assertEqual(result['known_lower_bound'], 2000)
        self.assertEqual(result['local_total'], 700)
        self.assertEqual(result['unknown_maintenance_total'], 0)
        self.assertEqual(result['cloud_cost_range']['status'], 'exact')
        self.assertTrue(result['usage_complete'] and result['routing_ok'])
        self.assertEqual(result['local_dispatches'], 1)

    def test_session_aggregate_gap_stays_unknown_maintenance(self):
        result = H.hybrid_arm(maintenance=lambda rec: H.set_native(rec, input=1100))
        self.assertEqual(result['unknown_maintenance_total'], 200)
        self.assertIsNone(result['cloud_total'])
        self.assertEqual(result['cloud_cost_range']['status'], 'cloud_exact_unknown')
        self.assertEqual(result['cloud_cost_range']['upper_bound'], 2200)
        self.assertEqual(result['known_lower_bound'], 2000)

    def test_failed_and_unfinished_records_are_counted_but_fail_closed(self):
        result = H.hybrid_arm(review=lambda rec: rec['messages'].__setitem__(
            0, dict(rec['messages'][0], data=H.assistant_msg({'input': 200, 'output': 100},
                                                             agent='review', finish='error'))))
        self.assertEqual(result['known_lower_bound'], 2000)
        self.assertEqual(result['invalid_completion'], [f'{H.REVIEW}:{H.REVIEW}:0:finish=error'])
        self.assertFalse(result['usage_complete'])
        self.assertIsNone(result['cloud_total'])
        self.assertTrue(blockers_have(result, 'unfinished assistant records'))
        pending = H.hybrid_arm(review=lambda rec: rec['messages'].__setitem__(
            0, dict(rec['messages'][0], data=H.assistant_msg({'input': 200, 'output': 100},
                                                             agent='review', finish=None))))
        self.assertEqual(pending['pending_assistant_messages'], [f'{H.REVIEW}:{H.REVIEW}:0'])
        self.assertFalse(pending['usage_complete'])

    def test_missing_or_unknown_token_fields_are_unknown_not_zero(self):
        blank = H.hybrid_arm(worker=lambda rec: rec['messages'].__setitem__(
            1, dict(rec['messages'][1], data=H.assistant_msg(None, provider=H.LOCAL,
                                                             model=H.LOCAL_MODEL, agent='general'))))
        self.assertTrue(any(':input,output' in m for m in blank['missing_usage_fields']))
        self.assertFalse(blank['usage_complete'])
        self.assertEqual(blank['local_total'], 0)
        extra = H.hybrid_arm(review=lambda rec: rec['messages'].__setitem__(
            0, dict(rec['messages'][0], data=H.assistant_msg({'input': 200, 'output': 100,
                                                              'mystery': 5}, agent='review'))))
        self.assertTrue(any('mystery' in u for u in extra['unaccounted_usage_fields']))
        self.assertFalse(extra['usage_complete'])
        self.assertIsNone(extra['cloud_total'])

    def test_unrouted_provider_never_becomes_cloud(self):
        recs = H.arm_records()
        rec = H.by_id(recs)[H.CHILD]
        rec['messages'][1] = dict(rec['messages'][1], data=H.assistant_msg(
            {'input': 700, 'output': 100}, provider='gateway', model='router-1', agent='general'))
        H.set_native(rec, input=700, output=100)
        result = H.hybrid_arm(recs)
        self.assertEqual(result['unknown_usage_total'], 800)
        self.assertEqual(result['cloud_total'], None)
        self.assertEqual(result['totals']['local']['total'], 0)
        self.assertEqual(result['cloud_cost_range']['upper_bound'], 2800)

    def test_wrong_routing_on_cloud_or_local_side_is_rejected(self):
        wrong_review = H.hybrid_arm(review=lambda rec: rec['messages'].__setitem__(
            0, dict(rec['messages'][0], data=H.assistant_msg({'input': 200, 'output': 100},
                                                             agent='review', model='gpt-4o-mini'))))
        self.assertFalse(wrong_review['routing_ok'])
        self.assertTrue(any('wrong routing' in b for b in wrong_review['blockers']))
        local_root = H.hybrid_arm(root=lambda rec: rec['messages'].__setitem__(
            1, dict(rec['messages'][1], data=H.assistant_msg({'input': 900, 'output': 300,
                                                              'reasoning': 100, 'cache': {'read': 400}},
                                                             provider=H.LOCAL, model=H.LOCAL_MODEL,
                                                             agent='hybrid'))))
        self.assertFalse(local_root['routing_ok'])
        self.assertEqual(local_root['totals']['cloud']['total'], 300)
        self.assertEqual(local_root['cloud_total'], 300)
        self.assertTrue(any('wrong routing' in b for b in local_root['blockers']))

    def test_reasoning_variant_is_read_from_the_record_not_assumed(self):
        result = H.hybrid_arm(review=lambda rec: rec['messages'].__setitem__(
            0, dict(rec['messages'][0], data=H.assistant_msg({'input': 200, 'output': 100},
                                                             agent='review', variant='none'))))
        self.assertTrue(any('reasoning variant' in b for b in result['blockers']))
        self.assertEqual(result['variant_mismatch'], [f'{H.REVIEW}:none'])
        self.assertFalse(result['routing_ok'])

    def test_frozen_shape_of_the_arm_is_enforced(self):
        extra = H.hybrid_arm(worker=lambda rec: rec['session'].__setitem__('agent', 'explore'))
        self.assertTrue(any('at least one general local worker' in b for b in extra['blockers']))
        cloud_explore = H.hybrid_arm(worker=lambda rec: rec['session'].__setitem__('agent', 'explore'))
        self.assertFalse(cloud_explore['routing_ok'])
        stranger = H.hybrid_arm(worker=lambda rec: rec['session'].__setitem__('agent', 'build'))
        self.assertTrue(any('unexpected native session' in b for b in stranger['blockers']))
        no_review = [r for r in H.arm_records() if r['session']['id'] != H.REVIEW]
        self.assertTrue(blockers_have(H.hybrid_arm(no_review), 'no review subagent session'))
        editing = H.hybrid_arm(root=lambda rec: rec['messages'].__setitem__(
            1, dict(rec['messages'][1], data=H.assistant_msg({'input': 900, 'output': 300,
                                                              'reasoning': 100, 'cache': {'read': 400}},
                                                             agent='hybrid', tools=['edit']))))
        self.assertTrue(blockers_have(editing, 'must not implement'))
        dispatches = H.hybrid_arm(worker=lambda rec: rec['messages'].extend(
            [dict(rec['messages'][0], id=f'{H.CHILD}:{9 + i}', seq=9 + i) for i in range(2)]))
        self.assertEqual(dispatches['local_dispatches'], 3)
        self.assertTrue(blockers_have(dispatches, 'dispatches'))

    def test_real_opencode_2_1_tool_parts_are_named_tools_and_root_edits_are_caught(self):
        # OpenCode 2.1.4 stores a tool call as {"type": "tool", "name": ...} inside content.
        def real_tool_message(rec):
            data = json.loads(rec['messages'][1]['data'])
            data['content'] = [{'type': 'text', 'text': 'plan'},
                               {'type': 'tool', 'id': 'call_1', 'name': 'shell', 'state': {'status': 'completed'}},
                               {'type': 'tool', 'id': 'call_2', 'name': 'edit', 'state': {'status': 'completed'}},
                               {'type': 'reasoning', 'text': 'name: edit'}]
            rec['messages'][1] = dict(rec['messages'][1], data=json.dumps(data))
        editing = H.hybrid_arm(root=real_tool_message)
        root = next(s for s in editing['sessions'] if s['agent'] == 'hybrid')
        self.assertEqual(root['tools'], {'edit': 1, 'shell': 1})
        self.assertEqual(root['edit_calls'], 1)
        self.assertTrue(blockers_have(editing, 'must not implement'))

    def test_parallel_local_workers_and_explore_sessions_have_bounds(self):
        def local(sid, agent, turns=1, provider=H.LOCAL, model=H.LOCAL_MODEL, finish='stop'):
            messages = []
            for _ in range(turns):
                messages += [('user', H.user_msg()),
                             ('assistant', H.assistant_msg({'input': 100, 'output': 10}, provider=provider,
                                                           model=model, agent=agent, finish=finish))]
            return H.record(sid, agent, {'providerID': provider, 'modelID': model},
                            {'input': 100 * turns, 'output': 10 * turns}, messages, parent=H.ROOT)

        def arm(workers=1, explores=0, **worker):
            records = [r for r in H.arm_records() if r['session']['id'] != H.CHILD]
            records += [local(f'w{i}', 'general', **worker) for i in range(workers)]
            records += [local(f'e{i}', 'explore') for i in range(explores)]
            return H.hybrid_arm(records)
        best = arm(workers=4, explores=2)
        self.assertTrue(best['routing_ok'], best['blockers'])
        self.assertEqual(best['seats']['worker']['total'], 6 * 110)
        self.assertEqual(best['by_role']['explore']['total'], 2 * 110)
        self.assertTrue(blockers_have(arm(workers=5), 'at most 4'))
        self.assertTrue(blockers_have(arm(explores=3), 'at most 2 explore'))
        self.assertFalse(arm(workers=2, turns=2)['blockers'], 'one repair per worker is allowed')
        self.assertTrue(blockers_have(arm(turns=3), 'dispatches'))
        self.assertFalse(arm(provider=H.CLOUD, model=H.CLOUD_MODEL)['routing_ok'])
        self.assertTrue(blockers_have(arm(finish=''), 'unfinished'))

    def test_seats_follow_the_recorded_model_of_each_request(self):
        result = H.hybrid_arm()
        planner, worker = result['seats']['planner'], result['seats']['worker']
        self.assertEqual((planner['model'], worker['model']), (f'{H.CLOUD}/{H.CLOUD_MODEL}', H.LOCAL_QUALIFIED))
        self.assertEqual((planner['uncached_input'], planner['cached_input'], planner['output'], planner['reasoning']), (1100, 400, 400, 100))
        self.assertEqual(planner['total'], result['known_lower_bound'])
        self.assertEqual(worker['total'], result['local_total'])
        self.assertEqual(result['by_role']['review']['total'], 300)

        def switched(rec):
            rec['messages'].append({'id': f'{H.REVIEW}:9', 'session_id': H.REVIEW, 'seq': 9, 'type': 'assistant',
                                    'data': H.assistant_msg({'input': 50, 'output': 5}, provider=H.LOCAL,
                                                            model=H.LOCAL_MODEL, agent='review'), 'time_created': 11})
        mixed = H.hybrid_arm(review=switched)
        self.assertEqual(mixed['seats']['worker']['total'], worker['total'] + 55)
        self.assertEqual(mixed['by_role']['review']['total'], 355)
        self.assertFalse(mixed['routing_ok'])

    def test_every_assistant_request_is_recorded_on_a_clean_arm(self):
        result = H.hybrid_arm()
        self.assertEqual([(r['session'], r['tier'], r['total']) for r in result['requests']],
                         [(H.ROOT, 'cloud', 1700), (H.CHILD, 'local', 700), (H.REVIEW, 'cloud', 300)])
        self.assertEqual(sum(r['total'] for r in result['requests'] if r['tier'] == 'cloud'),
                         result['known_lower_bound'])
        self.assertEqual([r['model'] for r in result['requests']],
                         [H.CLOUD_MODEL, H.LOCAL_MODEL, H.CLOUD_MODEL])

    def test_local_worker_without_assistant_routing_fails_closed(self):
        recs = H.arm_records()
        rec = H.by_id(recs)[H.CHILD]
        rec['messages'] = [m for m in rec['messages'] if m['type'] != 'assistant']
        H.set_native(rec, input=0, output=0)
        result = H.hybrid_arm(recs)
        self.assertFalse(result['routing_ok'])
        self.assertEqual(result['unexpected_models'], [f'{H.CHILD}:no-assistant-model'])
        self.assertTrue(blockers_have(result, 'never assumed from the session configuration'))
        self.assertEqual(result['local_worker_sessions'], [H.CHILD])

    def test_local_worker_with_wrong_actual_route_is_rejected(self):
        recs = H.arm_records()
        rec = H.by_id(recs)[H.CHILD]
        rec['messages'][1] = dict(rec['messages'][1], data=H.assistant_msg(
            {'input': 500, 'output': 200}, provider=H.CLOUD, model=H.CLOUD_MODEL, agent='general'))
        result = H.hybrid_arm(recs)
        self.assertFalse(result['routing_ok'])
        self.assertIn(f'{H.CHILD}:{H.CLOUD}/{H.CLOUD_MODEL}', result['unexpected_models'])
        self.assertEqual(result['local_total'], 0)
        self.assertEqual(result['totals']['cloud']['total'], 2700)
        self.assertTrue(blockers_have(result, 'wrong routing'))

    def test_assistant_routing_is_not_inherited_from_the_session_config(self):
        recs = H.arm_records()
        rec = H.by_id(recs)[H.REVIEW]
        data = json.loads(rec['messages'][0]['data'])
        data.pop('model')
        rec['messages'][0] = dict(rec['messages'][0], data=json.dumps(data))
        result = H.hybrid_arm(recs)
        self.assertFalse(result['routing_ok'])
        self.assertEqual(result['assistant_messages_without_model'], [f'{H.REVIEW}:{H.REVIEW}:0'])
        self.assertEqual(result['unexpected_models'], [f'{H.REVIEW}:no-assistant-model'])
        self.assertTrue(blockers_have(result, 'never inherited from the session configuration'))

    def test_unfinished_turn_on_any_required_role_fails_closed(self):
        roles = [(H.ROOT, 1, {'input': 900, 'output': 300, 'reasoning': 100, 'cache': {'read': 400}},
                  H.CLOUD, H.CLOUD_MODEL, 'hybrid'),
                 (H.CHILD, 1, {'input': 500, 'output': 200}, H.LOCAL, H.LOCAL_MODEL, 'general'),
                 (H.REVIEW, 0, {'input': 200, 'output': 100}, H.CLOUD, H.CLOUD_MODEL, 'review')]
        for sid, index, tokens, provider, model, agent in roles:
            recs = H.arm_records()
            rec = H.by_id(recs)[sid]
            rec['messages'][index] = dict(rec['messages'][index], data=H.assistant_msg(
                tokens, provider=provider, model=model, agent=agent, finish=None))
            result = H.hybrid_arm(recs)
            self.assertEqual(result['pending_assistant_messages'], [f'{sid}:{sid}:{index}'], sid)
            self.assertFalse(result['usage_complete'], sid)
            self.assertIsNone(result['cloud_total'], sid)
            self.assertIsNone(result['cloud_cost_range']['upper_bound'], sid)
            self.assertTrue(blockers_have(result, 'unfinished assistant records'), sid)

    def test_malformed_token_counters_are_never_an_exact_total(self):
        for tokens in ({'input': '300', 'output': 100}, {'input': -5, 'output': 100},
                       {'input': 200.5, 'output': 100}):
            recs = H.arm_records()
            rec = H.by_id(recs)[H.REVIEW]
            rec['messages'][0] = dict(rec['messages'][0], data=H.assistant_msg(
                tokens, agent='review', text='VERDICT: PASS ' + H.SHA))
            result = H.hybrid_arm(recs)
            self.assertEqual(result['invalid_usage_fields'], [f'{H.REVIEW}:{H.REVIEW}:0:input'], tokens)
            self.assertFalse(result['usage_complete'], tokens)
            self.assertIsNone(result['cloud_total'], tokens)
            self.assertEqual(result['cloud_cost_range']['status'], 'unknown', tokens)
            self.assertIsNone(result['cloud_cost_range']['upper_bound'], tokens)

    def test_malformed_native_aggregate_counter_fails_closed(self):
        recs = H.arm_records()
        H.set_native(H.by_id(recs)[H.ROOT], input='many')
        result = H.hybrid_arm(recs)
        self.assertTrue(blockers_have(result, 'malformed counter'))
        self.assertTrue(blockers_have(result, 'inconsistent'))
        self.assertFalse(result['usage_complete'])
        self.assertIsNone(result['cloud_total'])
        self.assertEqual(result['sessions'][0]['native_total'], 800)

    def test_duplicate_sessions_and_messages_are_counted_once(self):
        recs = H.arm_records()
        recs[2]['messages'].append(dict(recs[2]['messages'][0]))
        result = H.hybrid_arm(recs + [recs[0]])
        self.assertEqual(result['known_lower_bound'], 2000)
        self.assertEqual(result['totals']['cloud']['total'], 2000)
        self.assertEqual(result['local_total'], 700)
        self.assertEqual(len(result['sessions']), 3)
        self.assertEqual(result['duplicate_records'], [f'{H.REVIEW}:{H.REVIEW}:0', f'{H.ROOT}:session'])
        self.assertFalse(result['usage_complete'])
        self.assertIsNone(result['cloud_total'])
        self.assertIsNone(result['cloud_cost_range']['upper_bound'])
        self.assertTrue(blockers_have(result, 'counted once, never twice'))

    def test_inconsistent_native_aggregate_and_invalid_idle_outcome(self):
        result = H.hybrid_arm(worker=lambda rec: H.set_native(rec, input=10, output=0))
        self.assertTrue(blockers_have(result, 'inconsistent'))
        self.assertFalse(result['usage_complete'])
        idle = H.hybrid_arm(review=lambda rec: rec['session'].__setitem__('idle_outcome', 'error'))
        self.assertTrue(any('idle_outcome=error' in c for c in idle['invalid_completion']))
        self.assertFalse(idle['usage_complete'])

    def test_usage_without_actual_model_is_unknown_never_cloud_lower_bound(self):
        for sid, index, unattributed, cloud in ((H.REVIEW, 0, 300, 1700), (H.CHILD, 1, 700, 2000)):
            recs = H.arm_records()
            rec = H.by_id(recs)[sid]
            data = json.loads(rec['messages'][index]['data'])
            data.pop('model')
            rec['messages'][index] = dict(rec['messages'][index], data=json.dumps(data))
            result = H.hybrid_arm(recs)
            self.assertEqual(result['assistant_messages_without_model'],
                             [f"{sid}:{rec['messages'][index]['id']}"], sid)
            self.assertEqual(result['unknown_usage_total'], unattributed, sid)
            self.assertEqual(result['known_lower_bound'], cloud, sid)
            self.assertEqual(result['cloud_cost_range']['status'], 'unknown', sid)
            self.assertIsNone(result['cloud_total'], sid)
            self.assertIsNone(result['cloud_cost_range']['upper_bound'], sid)
            self.assertFalse(result['routing_ok'], sid)

    def test_missing_completion_evidence_fails_closed_for_every_role(self):
        def waiting(rec):
            rec['messages'].append({'id': f"{rec['session']['id']}:w", 'seq': 99,
                                    'session_id': rec['session']['id'], 'type': 'user',
                                    'data': H.user_msg()})
        mutations = [('idle_outcome=None', lambda r: r['session'].__setitem__('idle_outcome', None)),
                     ('idle_outcome=error', lambda r: r['session'].__setitem__('idle_outcome', 'error')),
                     ('time_idle=None', lambda r: r['session'].__setitem__('time_idle', None)),
                     ('awaiting_answer', waiting)]
        for sid in (H.ROOT, H.CHILD, H.REVIEW):
            for label, mutate in mutations:
                recs = H.arm_records()
                mutate(H.by_id(recs)[sid])
                case, result = f'{sid}/{label}', H.hybrid_arm(recs)
                self.assertTrue(result['incomplete_sessions'], case)
                self.assertTrue(blockers_have(result, 'completion evidence'), case)
                self.assertEqual((result['usage_complete'], result['routing_ok']), (False, False), case)
                self.assertEqual((result['cloud_cost_range']['status'], result['cloud_total']),
                                 ('unknown', None), case)
                self.assertIsNone(result['cloud_cost_range']['upper_bound'], case)
                self.assertEqual((result['known_lower_bound'], result['local_total']), (2000, 700), case)

    def test_complete_arm_records_completion_evidence_for_every_role(self):
        result = H.hybrid_arm()
        self.assertEqual([(s['id'], s['idle_outcome'], s['time_idle'], s['incomplete_evidence'])
                          for s in result['sessions']],
                         [(sid, 'ready', 2, []) for sid in (H.ROOT, H.CHILD, H.REVIEW)])
        self.assertEqual((result['incomplete_sessions'], result['cloud_cost_range']['status']), ([], 'exact'))
        self.assertTrue(result['usage_complete'] and result['routing_ok'])
        self.assertEqual((result['cloud_total'], result['cloud_cost_range']['upper_bound']), (2000, 2000))

    def test_agent_is_recovered_from_the_assistant_payload(self):
        recs = H.arm_records()
        H.by_id(recs)[H.REVIEW]['session']['agent'] = None
        result = H.hybrid_arm(recs)
        self.assertEqual(result['review_sessions'], [H.REVIEW])
        self.assertTrue(result['routing_ok'])


class OpenCodeDatabase(unittest.TestCase):
    def test_snapshot_scopes_by_directory_and_follows_children(self):
        with tempfile.TemporaryDirectory() as raw:
            db = H.write_db(Path(raw) / 'native.db', H.arm_records() + [
                H.record('elsewhere', 'hybrid', {'providerID': H.CLOUD, 'modelID': H.CLOUD_MODEL},
                         {}, [('user', H.user_msg())], directory='/other/repo')])
            snap = A.snapshot_opencode(db, [H.REPO])
            self.assertEqual(sorted(r['session']['id'] for r in snap['records']),
                             sorted([H.ROOT, H.CHILD, H.REVIEW]))
            self.assertEqual(snap['scope_directories'], [H.REPO])
            root_rec = [r for r in snap['records'] if r['session']['id'] == H.ROOT][0]
            self.assertEqual(len(root_rec['messages']), 2)
            result = A.account_opencode(snap, root_session_ids=[H.ROOT], **H.OC_KW)
            self.assertEqual(result['known_lower_bound'], 2000)
            seeded = A.snapshot_opencode(db, [], ['elsewhere'])
            self.assertEqual([r['session']['id'] for r in seeded['records']], ['elsewhere'])

    def test_missing_database_or_schema_fails_preflight(self):
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(A.PreflightBlocker):
                A.snapshot_opencode(Path(raw) / 'absent.db', [H.REPO])
            wrong = Path(raw) / 'wrong.db'
            conn = __import__('sqlite3').connect(str(wrong))
            conn.execute('create table session (id text)')
            conn.commit()
            conn.close()
            with self.assertRaisesRegex(A.PreflightBlocker, 'session_v2'):
                A.snapshot_opencode(wrong, [H.REPO])


if __name__ == '__main__':
    unittest.main()
