import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT_ID = '0r000000000000000000000000000000000000000000000000000000000000001'
CHILD_ID = '0c000000000000000000000000000000000000000000000000000000000000002'
GRAND_ID = '0g000000000000000000000000000000000000000000000000000000000000003'
T0 = '2026-10-26T18:36:01.000000Z'
T1 = '2026-10-26T18:36:31.000000Z'

def usage(input_tokens=0, cached=0, output=0, reasoning=0):
    return {'total_tokens': input_tokens + output, 'input_tokens': input_tokens, 'cached_input_tokens': cached, 'output_tokens': output, 'reasoning_output_tokens': reasoning}

def catalog_entry(session_id, *, parent_id=None, model='gpt-6.1-sol', effort='medium', total=None, updates=1, cwd='/tmp/fixture', models=None, completion='complete', spawn_calls=None, repair_calls=0, spawned_ids=None, edit_calls=0, assistant=None, tool_calls=0):
    root = parent_id is None
    return {'path': f'/nonexistent/{session_id}.jsonl', 'session_id': session_id, 'cwd': cwd, 'parent_id': parent_id, 'models': models or [model], 'efforts': [effort] if effort else [], 'completion': completion, 'completion_markers': (['task_started', 'task_complete'] if completion == 'complete' else ['task_started']), 'spawn_calls': (1 if root else 0) if spawn_calls is None else spawn_calls, 'repair_calls': repair_calls, 'spawned_ids': [spawned_ids or CHILD_ID] if root else [], 'usage': total, 'usage_updates': updates, 'tool_calls': tool_calls, 'edit_calls': edit_calls, 'assistant_texts': [assistant] if assistant else [], 'first_event': T0, 'last_event': T1, 'malformed_lines': 0}

def write_rollout(path, session_id, cwd, *, parent_id=None, model='gpt-6.1-sol', effort='medium', usage_total=None, updates=1, assistant=None, edit=False, completion='complete', spawn_ids=(), followups=0):
    events = [{'timestamp': T0, 'type': 'session_meta', 'payload': {'id': session_id, 'cwd': cwd, 'source': {'subagent': {'thread_spawn': {'parent_thread_id': parent_id}}} if parent_id else {}}}, {'timestamp': T0, 'type': 'turn_context', 'payload': {'model': model, 'effort': effort}}, {'timestamp': T0, 'type': 'event_msg', 'payload': {'type': 'task_started'}}]
    for spawned in spawn_ids:
        events.append({'timestamp': T0, 'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'spawn_agent'}})
        events.append({'timestamp': T0, 'type': 'response_item', 'payload': {'type': 'function_call_output', 'output': json.dumps({'thread_id': spawned})}})
    for _ in range(followups):
        events.append({'timestamp': T0, 'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'send_input'}})
    if edit:
        events.append({'timestamp': T0, 'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'apply_patch'}})
    running = {'total_tokens': 0, 'input_tokens': 0, 'cached_input_tokens': 0, 'output_tokens': 0, 'reasoning_output_tokens': 0}
    for _ in range(max(updates, 1)):
        running = usage_total or running
        events.append({'timestamp': T0, 'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {'total_token_usage': running}}})
    if assistant:
        events.append({'timestamp': T1, 'type': 'event_msg', 'payload': {'type': 'agent_message', 'message': assistant}})
    marker = {'complete': 'task_complete', 'aborted': 'turn_aborted', 'active': None}.get(completion, 'task_complete')
    if marker:
        events.append({'timestamp': T1, 'type': 'event_msg', 'payload': {'type': marker}})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join((json.dumps(event) + '\n' for event in events)), encoding='utf-8')
    return path

def assistant_data(provider, model_id, *, tokens=None, agent=None, text='', finish='stop', tools=(), variant='medium'):
    content = [{'type': 'text', 'text': text}] if text else []
    content += [{'type': 'tool', 'tool': tool} for tool in tools]
    return json.dumps({'tokens': tokens or {}, 'model': {'providerID': provider, 'modelID': model_id, 'variant': variant}, 'agent': agent, 'finish': finish, 'content': content})

def make_db(path, sessions):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript('create table session_v2 (id text primary key, parent_id text, agent text, model text, directory text, title text, time_created int, time_idle int, tokens_input int, tokens_output int, tokens_reasoning int, tokens_cache_read int, tokens_cache_write int, idle_outcome text);create table session_message (id text primary key, session_id text, seq int, type text, data text, time_created int);')
    for (index, session) in enumerate(sessions):
        tokens = session.get('tokens', {})
        conn.execute('insert into session_v2 values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (session['id'], session.get('parent_id'), session.get('agent'), json.dumps(session.get('model', {})), session.get('directory'), session.get('title', ''), 1 + index, 2 + index, tokens.get('input', 0), tokens.get('output', 0), tokens.get('reasoning', 0), tokens.get('cache_read', 0), tokens.get('cache_write', 0), session.get('idle_outcome', 'ready')))
        for (seq, (kind, data)) in enumerate(session.get('messages', [])):
            conn.execute('insert into session_message values (?,?,?,?,?,?)', (f"{session['id']}:{seq}", session['id'], seq, kind, data, 10 + seq))
    conn.commit()
    conn.close()
    return path

def hybrid_snapshot(root_id, repo, *, verdict_text, review_finish='stop', dispatches=2, local_model_id='qwen-3.8-nf-splash', root_edit=False, maintenance_extra=200, review_model_id='gpt-6.1-sol', idle='ready', time_idle=2, cloud_variant='medium', include_review=True, root_answer_model=True):
    """Native Hybrid records that really finished: every session went idle with a valid outcome,
    ends on an assistant answer, and the answering model/reasoning variant are the recorded ones.
    Negative knobs only remove evidence a real native session would have written."""
    user = json.dumps({'role': 'user'})
    root_payload = json.loads(assistant_data('openai', 'gpt-6.1-sol', agent='hybrid', tokens={'input': 900, 'output': 300, 'reasoning': 100, 'cache': {'read': 400}}, text='coordinator plan', variant=cloud_variant, tools=['edit'] if root_edit else []))
    if not root_answer_model:
        root_payload['model'] = {}
    worker = [('user', user), ('assistant', assistant_data('omlx', local_model_id, agent='general', tokens={'input': 500, 'output': 200}, text='implemented'))]
    for _ in range(max(dispatches - 1, 0)):
        worker += [('user', user), ('assistant', assistant_data('omlx', local_model_id, agent='general', tokens={'input': 0, 'output': 0}, text='repaired'))]
    sessions = [{'id': root_id, 'agent': 'hybrid', 'directory': repo, 'model': {'providerID': 'openai', 'modelID': 'gpt-6.1-sol'}, 'tokens': {'input': 1000 + maintenance_extra, 'output': 300, 'cache_read': 400}, 'messages': [('user', user), ('assistant', json.dumps(root_payload))]}, {'id': CHILD_ID, 'parent_id': root_id, 'agent': 'general', 'directory': repo, 'model': {'providerID': 'omlx', 'modelID': local_model_id}, 'tokens': {'input': 500, 'output': 200}, 'messages': worker}]
    if include_review:
        sessions.append({'id': GRAND_ID, 'parent_id': root_id, 'agent': 'review', 'directory': repo, 'model': {'providerID': 'openai', 'modelID': review_model_id}, 'tokens': {'input': 200, 'output': 100}, 'messages': [('assistant', assistant_data('openai', review_model_id, agent='review', tokens={'input': 200, 'output': 100}, text=verdict_text, finish=review_finish, variant=cloud_variant))]})
    records = []
    for session in sessions:
        row = {**session, 'model': json.dumps(session['model']), 'tokens_input': session['tokens'].get('input', 0), 'tokens_output': session['tokens'].get('output', 0), 'tokens_reasoning': session['tokens'].get('reasoning', 0), 'tokens_cache_read': session['tokens'].get('cache_read', 0), 'tokens_cache_write': session['tokens'].get('cache_write', 0), 'time_created': 1, 'time_idle': time_idle, 'idle_outcome': idle, 'title': '', 'parent_id': session.get('parent_id')}
        messages = [{'id': f"{session['id']}:{seq}", 'session_id': session['id'], 'seq': seq, 'type': kind, 'data': data, 'time_created': 10} for (seq, (kind, data)) in enumerate(session.get('messages', []))]
        records.append({'session': row, 'messages': messages})
    return {'records': records, 'database': None}
FAKE_CODEX = r'''
import hashlib, json, subprocess, sys, time
from pathlib import Path
cfg = json.loads(Path(sys.argv[0] + '.cfg').read_text())
args = sys.argv[1:]
if '--version' in args:
    print('codex-cli 0.0.0-fake-offline')
    sys.exit(0)
repo = Path(args[args.index('-C') + 1])
if cfg.get('apply_fix', True):
    path = repo / 'ttl_cache.py'
    path.write_text(path.read_text().replace('self._clock() > deadline', 'self._clock() >= deadline'))
diff = subprocess.run(['git', '-C', str(repo), 'diff', '--binary', 'HEAD'], capture_output=True).stdout
digest = hashlib.sha256(diff).hexdigest()
style = cfg.get('verdict_style', 'pass')
text = {'pass': 'Reviewed the complete diff and ran the suite.\nVERDICT: PASS ' + digest + '\n',
        'fenced': '```\nVERDICT: PASS ' + digest + '\n```\n',
        'quoted': 'The reviewer wrote: "VERDICT: PASS ' + digest + '" only.\n',
        'fail': 'The diff does not hold up.\nVERDICT: FAIL ' + digest + '\n',
        'stale': 'Reviewed an older patch.\nVERDICT: PASS ' + 'b' * 64 + '\n',
        'none': 'Tests are green, I am done here.\n'}[style]
if cfg.get('extra_file'):
    (repo / cfg['extra_file']).write_text('untracked helper\n', encoding='utf-8')
if cfg.get('empty_commit'):
    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=fake', '-c', 'user.email=fake@invalid', 'commit', '-q', '--allow-empty', '-m', 'fake moved HEAD'], capture_output=True)
(root, child) = (cfg['root_id'], cfg['child_id'])
session_dir = Path(cfg['codex_home']) / 'sessions' / '2026-10-26'
session_dir.mkdir(parents=True, exist_ok=True)

def lines(sid, parent, model, total, assistant, spawned=None):
    out = [json.dumps({'timestamp': '2026-10-26T18:36:01.000000Z', 'type': 'session_meta', 'payload': {'id': sid, 'cwd': str(repo), 'source': {'subagent': {'thread_spawn': {'parent_thread_id': parent}}} if parent else {}}}), json.dumps({'timestamp': '2026-10-26T18:36:01.000000Z', 'type': 'turn_context', 'payload': {'model': model, 'effort': 'medium'}}), json.dumps({'timestamp': '2026-10-26T18:36:01.000000Z', 'type': 'event_msg', 'payload': {'type': 'task_started'}})]
    event = json.loads(out[1])
    event['payload']['effort'] = cfg.get('child_effort', cfg.get('effort', 'medium')) if parent else cfg.get('effort', 'medium')
    out[1] = json.dumps(event)
    for _ in range(0 if parent else cfg.get('root_edits', 0)):
        out.append(json.dumps({'timestamp': '2026-10-26T18:36:02.000000Z', 'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'apply_patch'}}))
    if spawned:
        out.append(json.dumps({'timestamp': '2026-10-26T18:36:02.000000Z', 'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'spawn_agent'}}))
        out.append(json.dumps({'timestamp': '2026-10-26T18:36:02.000000Z', 'type': 'response_item', 'payload': {'type': 'function_call_output', 'output': json.dumps({'thread_id': spawned})}}))
    if total is not None:
        out.append(json.dumps({'timestamp': '2026-10-26T18:36:20.000000Z', 'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {'total_token_usage': total}}}))
    if assistant:
        out.append(json.dumps({'timestamp': '2026-10-26T18:36:31.000000Z', 'type': 'event_msg', 'payload': {'type': 'agent_message', 'message': assistant}}))
    if not cfg.get('root_active'):
        out.append(json.dumps({'timestamp': '2026-10-26T18:36:32.000000Z', 'type': 'event_msg', 'payload': {'type': 'task_complete'}}))
    return ''.join((line + '\n' for line in out))
(session_dir / (root + '.jsonl')).write_text(lines(root, None, cfg.get('root_model', 'gpt-6.1-sol'), {'total_tokens': cfg['root_total'], 'input_tokens': cfg['root_input'], 'cached_input_tokens': cfg['root_cached'], 'output_tokens': cfg['root_output'], 'reasoning_output_tokens': cfg['root_reasoning']}, text, spawned=child))
(session_dir / (child + '.jsonl')).write_text(lines(child, root, cfg.get('child_model', 'gpt-6-luna'), {'total_tokens': cfg['child_total'], 'input_tokens': cfg['child_input'], 'cached_input_tokens': cfg['child_cached'], 'output_tokens': cfg['child_output'], 'reasoning_output_tokens': cfg['child_reasoning']} if cfg.get('child_usage', True) else None, cfg.get('child_text')))
if cfg.get('no_child'):
    (session_dir / (child + '.jsonl')).unlink()
if cfg.get('child_active'):
    kept = [line for line in (session_dir / (child + '.jsonl')).read_text().splitlines(True) if 'task_complete' not in line]
    (session_dir / (child + '.jsonl')).write_text(''.join(kept), encoding='utf-8')
print(json.dumps({'type': 'thread.started', 'thread_id': root}), flush=True)
print(json.dumps({'type': 'turn.completed'}), flush=True)
if cfg.get('linger'):
    # A helper left behind in the arm's own process group, still running after the client exits.
    lingering = subprocess.Popen(['sleep', '120'])
    Path(cfg['linger']).write_text(str(lingering.pid))
if cfg.get('sleep'):
    time.sleep(cfg['sleep'])
sys.exit(cfg.get('exit_code', 0))
'''
FAKE_OPENCODE = r'''
import hashlib, json, sqlite3, subprocess, sys
from pathlib import Path
cfg = json.loads(Path(sys.argv[0] + '.cfg').read_text())
args = sys.argv[1:]
with open(sys.argv[0] + '.calls', 'a') as calls:
    calls.write(json.dumps(args) + '\n')
if '--version' in args:
    print('opencode 0.0.0-fake-offline')
    sys.exit(0)
if args[:2] == ['debug', 'agents']:
    # Effective rules as OpenCode lists them: defaults first, the last matching rule wins.
    open_rules = [{'action': '*', 'resource': '*', 'effect': 'allow'}]
    agents = cfg.get('effective_agents') or [{'id': role, 'permissions': open_rules} for role in ('hybrid', 'general', 'explore', 'review')]
    print(json.dumps(agents))
    sys.exit(cfg.get('debug_exit', 0))
if '--agent' in args and args[args.index('--agent') + 1] in ('general', 'review'):
    role = args[args.index('--agent') + 1]
    command = {'command': 'git status --short | tee probe.log'}
    state = ({'status': 'error', 'input': command, 'error': 'Permission denied: shell'} if role in cfg.get('probe_denied', [])
             else {'status': 'completed', 'input': command, 'output': ''})
    print(json.dumps({'type': 'tool_use', 'part': {'type': 'tool', 'tool': 'shell', 'state': state}}))
    print(json.dumps({'type': 'text', 'part': {'type': 'text', 'text': 'DONE'}}))
    sys.exit(cfg.get('probe_exit', 0))
repo = Path.cwd()
if cfg.get('apply_fix', True):
    path = repo / 'ttl_cache.py'
    path.write_text(path.read_text().replace('self._clock() > deadline', 'self._clock() >= deadline'))
diff = subprocess.run(['git', '-C', str(repo), 'diff', '--binary', 'HEAD'], capture_output=True).stdout
digest = hashlib.sha256(diff).hexdigest()
style = cfg.get('verdict_style', 'pass')
if style == 'pass':
    text = 'Verified the digest and evidence.\nVERDICT: PASS ' + digest + '\n'
elif style == 'fenced':
    text = '~~~\nVERDICT: PASS ' + digest + '\n~~~\n'
else:
    text = 'Tests pass.\n'

def data(provider, model_id, agent, tokens, text='', finish='stop', variant='medium'):
    filled = {**{'input': 0, 'output': 0, 'reasoning': 0}, **(tokens or {})}
    filled['cache'] = {**{'read': 0, 'write': 0}, **(filled.get('cache') or {})}
    return json.dumps({'tokens': filled, 'model': {'providerID': provider, 'modelID': model_id, 'variant': variant}, 'agent': agent, 'finish': finish, 'content': [{'type': 'text', 'text': text}] if text else []})
(root, child, review) = (cfg['root_id'], cfg['child_id'], cfg['review_id'])
db = Path(cfg['db'])
db.parent.mkdir(parents=True, exist_ok=True)
conn = sqlite3.connect(db)
conn.executescript('create table if not exists session_v2 (id text primary key, parent_id text, agent text, model text, directory text, title text, time_created int, time_idle int, tokens_input int, tokens_output int, tokens_reasoning int, tokens_cache_read int, tokens_cache_write int, idle_outcome text);create table if not exists session_message (id text primary key, session_id text, seq int, type text, data text, time_created int);')
rows = [(root, None, 'hybrid', {'providerID': 'openai', 'modelID': 'gpt-6.1-sol'}, {'input': 1200, 'output': 300, 'cache_read': 400}, [('user', json.dumps({'role': 'user'})), ('assistant', data('openai', 'gpt-6.1-sol', 'hybrid', {'input': 900, 'output': 300, 'reasoning': 100, 'cache': {'read': 400}}, 'coordinator plan'))]), (child, root, 'general', {'providerID': 'omlx', 'modelID': cfg['local_model_id']}, {'input': 500, 'output': 200}, [('user', json.dumps({'role': 'user'})), ('assistant', data('omlx', cfg['local_model_id'], 'general', {'input': 500, 'output': 200}, 'implemented')), ('user', json.dumps({'role': 'user'})), ('assistant', data('omlx', cfg['local_model_id'], 'general', {'input': 0, 'output': 0}, 'repaired'))]), (review, root, 'review', {'providerID': 'openai', 'modelID': 'gpt-6.1-sol'}, {'input': 200, 'output': 100}, [('assistant', data('openai', 'gpt-6.1-sol', 'review', {'input': 200, 'output': 100}, text, finish=cfg.get('review_finish', 'stop')))])]
for (index, (sid, parent, agent, model, tokens, messages)) in enumerate(rows):
    conn.execute('insert or replace into session_v2 values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (sid, parent, agent, json.dumps(model), str(repo), '', index, index + 1, tokens.get('input', 0), tokens.get('output', 0), tokens.get('reasoning', 0), tokens.get('cache_read', 0), tokens.get('cache_write', 0), 'ready'))
    for (seq, (kind, payload)) in enumerate(messages):
        conn.execute('insert or replace into session_message values (?,?,?,?,?,?)', (f'{sid}:{seq}', sid, seq, kind, payload, seq))
conn.commit()
conn.close()
print(json.dumps({'type': 'session.created', 'sessionID': root}), flush=True)
sys.exit(cfg.get('exit_code', 0))
'''

def write_fake(directory, name, body, cfg):
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / name
    script.write_text(f'#!{sys.executable}\n{body}', encoding='utf-8')
    script.chmod(493)
    (directory / f'{name}.cfg').write_text(json.dumps(cfg), encoding='utf-8')
    return str(script)

def native_config(directory, local_model):
    directory.mkdir(parents=True, exist_ok=True)
    config = {'$schema': 'https://opencode.ai/config.json', 'providers': {'omlx': {'settings': {'baseURL': 'http://127.0.0.1:9/v1', 'apiKey': '{file:./omlx.key}'}}}, 'agents': {'general': {'model': local_model, 'mode': 'subagent'}, 'explore': {'model': local_model}, 'hybrid': {'mode': 'primary'}, 'review': {'mode': 'subagent'}}, 'default_agent': 'hybrid', 'experimental': {'subagent_depth': 1}}
    path = directory / 'opencode.json'
    path.write_text(json.dumps(config, indent=2), encoding='utf-8')
    (directory / 'omlx.key').write_text('SECRET-DO-NOT-COPY\n', encoding='utf-8')
    return str(path)
