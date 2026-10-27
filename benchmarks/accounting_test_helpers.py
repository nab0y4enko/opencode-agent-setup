"""Offline fixtures for benchmarks/test_accounting.py: no CLI, no network, no paid calls."""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT, CHILD, REVIEW = 'r0', 'c0', 'g0'
SHA = 'a' * 64
T0, T1 = '2026-10-26T18:36:01Z', '2026-10-26T18:36:31Z'
REPO = '/repo/fixture'
SOL, LUNA = 'gpt-6.1-sol', 'gpt-5.1-luna'
CLOUD, CLOUD_MODEL = 'openai', 'gpt-6.1-sol'
LOCAL, LOCAL_MODEL = 'omlx', 'qwen-3.8-nf-splash'
LOCAL_QUALIFIED = f'{LOCAL}/{LOCAL_MODEL}'
OC_KW = {'expected_cloud_provider': CLOUD, 'expected_cloud_model': CLOUD_MODEL,
         'expected_local_provider': LOCAL, 'expected_local_model': LOCAL_QUALIFIED}
ALIAS = {'root': ROOT, 'worker': CHILD, 'review': REVIEW, 'maintenance': ROOT}
DEFAULT = object()


def usage(inp=0, cached=0, out=0, reasoning=0):
    return {'input_tokens': inp, 'cached_input_tokens': cached, 'output_tokens': out,
            'reasoning_output_tokens': reasoning, 'total_tokens': inp + out}


def entry(sid, *, parent=None, model=SOL, effort='medium', models=None, total=None, updates=1,
          completion='complete', spawn_ids=(), repair_calls=0, edits=0, tools=0, assistant=None):
    root = parent is None
    return {'path': f'/nonexistent/{sid}.jsonl', 'session_id': sid, 'cwd': REPO, 'parent_id': parent,
            'models': [model] if models is None else list(models), 'efforts': [effort] if effort else [],
            'usage': total, 'usage_updates': updates, 'tool_calls': tools, 'edit_calls': edits,
            'assistant_texts': [assistant] if assistant else [], 'first_event': T0, 'last_event': T1,
            'malformed_lines': 0, 'completion': completion,
            'completion_markers': ['task_started'] + (['task_complete'] if completion == 'complete' else []),
            'spawn_calls': len(spawn_ids) if root else 0, 'repair_calls': repair_calls,
            'spawned_ids': list(spawn_ids) if root else []}


def codex_catalog(*, root_usage=None, child_usage=DEFAULT, child_model=LUNA, child_effort='medium',
                  child_completion='complete', child_models=None, spawn_ids=(CHILD,), **child_kw):
    return {ROOT: entry(ROOT, total=root_usage if root_usage is not None else usage(1000, 400, 300, 60),
                        spawn_ids=spawn_ids, assistant='VERDICT: PASS ' + SHA),
            CHILD: entry(CHILD, parent=ROOT, model=child_model, effort=child_effort, models=child_models,
                         total=usage(300, 100, 100, 20) if child_usage is DEFAULT else child_usage,
                         completion=child_completion, **child_kw)}


CODEX_KW = {'root_thread_id': ROOT, 'expected_root_model': SOL, 'expected_child_model': LUNA,
            'expected_effort': 'medium'}


def write_rollout(path, sid, *, cwd=REPO, parent=None, model=SOL, effort='medium', total=None,
                  completion='complete', spawn_ids=(), edits=0, assistant=None, malformed=0,
                  source=DEFAULT):
    if source is DEFAULT:
        source = {'subagent': {'thread_spawn': {'parent_thread_id': parent}}} if parent else 'cli'
    events = [{'timestamp': T0, 'type': 'session_meta',
               'payload': {'id': sid, 'cwd': cwd, 'source': source}},
              {'timestamp': T0, 'type': 'turn_context', 'payload': {'model': model, 'effort': effort}},
              {'timestamp': T0, 'type': 'event_msg', 'payload': {'type': 'task_started'}}]
    for spawned in spawn_ids:
        events.append({'timestamp': T0, 'type': 'response_item',
                       'payload': {'type': 'function_call', 'name': 'spawn_agent'}})
        events.append({'timestamp': T0, 'type': 'response_item',
                       'payload': {'type': 'function_call_output', 'output': json.dumps({'thread_id': spawned})}})
    if edits:
        events.append({'timestamp': T0, 'type': 'response_item',
                       'payload': {'type': 'function_call', 'name': 'apply_patch'}})
    if total is not None:
        events.append({'timestamp': T0, 'type': 'event_msg',
                       'payload': {'type': 'token_count', 'info': {'total_token_usage': total}}})
    if assistant:
        events.append({'timestamp': T1, 'type': 'event_msg', 'payload': {'type': 'agent_message', 'message': assistant}})
    marker = {'complete': 'task_complete', 'aborted': 'turn_aborted'}.get(completion)
    if marker:
        events.append({'timestamp': T1, 'type': 'event_msg', 'payload': {'type': marker}})
    lines = [json.dumps(event) for event in events] + ['not json {'] * malformed
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path


def user_msg():
    return json.dumps({'role': 'user'})


def assistant_msg(tokens=None, *, provider=CLOUD, model=CLOUD_MODEL, agent='hybrid', finish='stop',
                  tools=(), variant='medium', text='ok'):
    model_id = model if variant is None else f'{model}'
    data = {'tokens': tokens, 'model': {'providerID': provider, 'modelID': model_id},
            'agent': agent, 'finish': finish,
            'content': [{'type': 'text', 'text': text}] + [{'type': 'tool', 'tool': t} for t in tools]}
    if variant is not None:
        data['model']['variant'] = variant
    return json.dumps(data)


def record(sid, agent, model, native, messages, *, parent=None, directory=REPO, idle='ready'):
    row = {'id': sid, 'parent_id': parent, 'agent': agent, 'model': json.dumps(model),
           'directory': directory, 'title': '', 'time_created': 1, 'time_idle': 2, 'idle_outcome': idle}
    for field in ('input', 'output', 'reasoning', 'cache_read', 'cache_write'):
        row['tokens_' + field] = native.get(field, 0)
    messages = [{'id': f'{sid}:{i}', 'session_id': sid, 'seq': i, 'type': kind, 'data': data,
                 'time_created': 10} for i, (kind, data) in enumerate(messages)]
    return {'session': row, 'messages': messages}


def arm_records(**over):
    """Clean frozen arm: Hybrid root (cloud), one general local worker, one review (cloud)."""
    recs = [
        record(ROOT, 'hybrid', {'providerID': CLOUD, 'modelID': CLOUD_MODEL},
               {'input': 900, 'output': 300, 'reasoning': 100, 'cache_read': 400},
               [('user', user_msg()),
                ('assistant', assistant_msg({'input': 900, 'output': 300, 'reasoning': 100,
                                             'cache': {'read': 400}}, agent='hybrid'))]),
        record(CHILD, 'general', {'providerID': LOCAL, 'modelID': LOCAL_MODEL},
               {'input': 500, 'output': 200},
               [('user', user_msg()),
                ('assistant', assistant_msg({'input': 500, 'output': 200}, provider=LOCAL,
                                            model=LOCAL_MODEL, agent='general'))], parent=ROOT),
        record(REVIEW, 'review', {'providerID': CLOUD, 'modelID': CLOUD_MODEL},
               {'input': 200, 'output': 100},
               [('assistant', assistant_msg({'input': 200, 'output': 100}, agent='review',
                                            text='VERDICT: PASS ' + SHA))], parent=ROOT)]
    by_id = {r['session']['id']: r for r in recs}
    for key, value in over.items():
        value(by_id[ALIAS[key]])
    return recs


def hybrid_arm(records=None, **over):
    import accounting
    return accounting.account_opencode({'records': records if records is not None else arm_records(**over)},
                                       root_session_ids=[ROOT], **OC_KW)


def by_id(records):
    return {r['session']['id']: r for r in records}


def set_native(rec, **native):
    for field, value in native.items():
        rec['session']['tokens_' + field] = value
    return rec


def write_db(path, records):
    conn = sqlite3.connect(str(path))
    conn.executescript(
        "create table session_v2 (id text primary key, parent_id text, agent text, model text, "
        "directory text, title text, time_created int, time_idle int, tokens_input int, "
        "tokens_output int, tokens_reasoning int, tokens_cache_read int, tokens_cache_write int, "
        "idle_outcome text); create table session_message (id text primary key, session_id text, "
        "seq int, type text, data text, time_created int);")
    cols = ('id', 'parent_id', 'agent', 'model', 'directory', 'title', 'time_created', 'time_idle',
            'tokens_input', 'tokens_output', 'tokens_reasoning', 'tokens_cache_read',
            'tokens_cache_write', 'idle_outcome')
    for rec in records:
        conn.execute('insert into session_v2 values (%s)' % ','.join('?' * len(cols)),
                     [rec['session'].get(c) for c in cols])
        for msg in rec['messages']:
            conn.execute('insert into session_message values (?,?,?,?,?,?)',
                         (msg['id'], msg['session_id'], msg['seq'], msg['type'], msg['data'], 10))
    conn.commit()
    conn.close()
    return path


def native_config(path, **extra):
    config = {'agents': {'general': {'model': LOCAL_MODEL}, 'hybrid': {}, 'review': {}},
              'default_agent': 'hybrid', 'experimental': {'subagent_depth': 2},
              'apiKey': 'super-secret-value', 'headers': {'Authorization': 'Bearer {env:ABSENT_TOKEN}'},
              'base_url': 'https://gw.example/{env:GW_HOST}', 'worker': {'model_ref': '{env:LOCAL_ID}'},
              'x_trace': '{env:ABSENT_REGION}',
              'x_route': '{env:OPENAI_API_KEY}',
              'creds': '{file:secrets/api.key}', 'missing': '{file:nope.json}'}
    config.update(extra)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config), encoding='utf-8')
    return path
