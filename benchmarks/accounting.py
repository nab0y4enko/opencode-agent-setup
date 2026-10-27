"""Accounting and evidence checks for the portable cross-Mac benchmark (offline only).

Codex: the final cumulative ``total_token_usage`` of each rollout is counted once for the root
and once per descendant; cached input is a subset of input and reasoning output a subset of
output, so the reported parts stay disjoint and still add up to the recorded total. OpenCode:
usage is already disjoint per assistant message, so every assistant record is summed once,
failures and unfinished records included; the difference between a native session aggregate and
its assistant sum is unknown maintenance and stays its own number, never folded into a tier.
Unknown is never zero and routing is never assumed: a missing model, reasoning effort,
completion marker, descendant rollout or usage field fails the arm closed, leaving only a known
lower bound and no accepted verdict.
- A counter that is negative, fractional or not a number at all is malformed, never a zero: the arm
  keeps its known lower bound, withholds the exact total and the upper bound of the cloud range.
  Duplicated session or message identifiers are counted once and reported, and routing is validated
  against the assistant records that actually ran, never against the installed session configuration.
"""
import hashlib
import json
import re
import sqlite3
from pathlib import Path

PROTOCOL = 'portable-cross-mac-1'
OPENCODE_TOKEN_FIELDS = ('input', 'output', 'reasoning')
OPENCODE_CACHE_FIELDS = ('read', 'write')
OPENCODE_REQUIRED_FIELDS = ('input', 'output')
CODEX_USAGE_FIELDS = ('input_tokens', 'output_tokens', 'total_tokens')
CODEX_COUNTER_FIELDS = ('input_tokens', 'cached_input_tokens', 'output_tokens',
                        'reasoning_output_tokens', 'total_tokens')
ERROR_FINISHES = ('error', 'cancelled', 'canceled', 'aborted', 'failed')
VALID_IDLE_OUTCOMES = ('ready', 'succeeded')
EXPECTED_REASONING_VARIANT = 'medium'
CODEX_COMPLETION_MARKERS = {'task_started': 'active', 'task_complete': 'complete', 'turn_aborted': 'aborted'}
CODEX_SPAWN_TOOL = 'spawn_agent'
CODEX_REPAIR_TOOLS = ('send_input', 'followup_task')
CODEX_TOOL_CALL_TYPES = {'function_call', 'local_shell_call', 'custom_tool_call', 'web_search_call', 'mcp_tool_call'}
CODEX_EDIT_TOOLS = {'apply_patch', 'edit', 'write', 'patch', 'notebook_edit'}
EDIT_TOOLS = {'edit', 'write', 'apply_patch', 'patch', 'multiedit', 'notebook_edit', 'str_replace_editor'}
SECRET_FIELD_HINTS = ('apikey', 'api_key', 'token', 'password', 'secret', 'auth', 'credential', 'bearer', 'accesskey')
SECRET_REF_HINTS = ('key', 'secret', 'token', 'password', 'credential', '.env')
REF_PATTERN = re.compile(r'\{(file|env):([^{}]+)\}')


class PreflightBlocker(Exception):
    """A concrete blocker that must stop an arm before any model is launched."""


def as_int(value):
    """Tolerant integer coercion for event counts only; token counters use ``as_counter``."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def as_counter(value):
    """Strict non-negative integer token counter; anything else stays unknown (never zero).

    ``as_int`` remains for tolerant display of values that were already validated, but no usage
    total may be called complete while a counter is malformed, negative or fractional.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value >= 0 and value.is_integer():
        return int(value)
    return None


def counter_problems(node, names):
    """Counters that are present but unusable: malformed, negative or fractional."""
    node = node if isinstance(node, dict) else {}
    return [name for name in names
            if node.get(name) is not None and as_counter(node.get(name)) is None]


def _dig(node, *keys):
    """Walk nested JSON that may arrive as a string, a scalar or an object without crashing."""
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


# ------------------------------------------------------------------ verdict text
_FENCE = re.compile(r'^\s*(```|~~~)')
_VERDICT = re.compile(r'^VERDICT:\s*(PASS|FAIL|CHANGES_REQUIRED)\b[ \t]*(.*)$', re.I)
_SHA = re.compile(r'^([0-9a-f]{64})$')


def find_verdicts(text):
    """Verdict lines tagged plain/quoted/fenced so decoration cannot forge one."""
    found, fenced = [], False
    for raw in (text or '').splitlines():
        if _FENCE.match(raw):
            fenced = not fenced
            continue
        line = raw.strip()
        bare = line.replace('*', '').strip()
        stripped = bare.lstrip('># \t')
        match = _VERDICT.match(stripped)
        if not match:
            continue
        rest = match.group(2).strip().strip('`*"\' ')
        first = rest.split()[0] if rest.split() else ''
        sha_match = _SHA.match(first)
        quoted = bare != stripped or bare[:1] in '"\'`' or bare[-1:] in '"\'`' or '`' in line
        found.append({'verdict': match.group(1).upper(), 'line': line[:400],
                      'state': 'fenced' if fenced else 'quoted' if quoted else 'plain',
                      'sha': sha_match.group(1) if sha_match else first[:80],
                      'full_sha_present': bool(sha_match)})
    return found


def semantic_verdict(text, expected_sha):
    """Only a plain verdict bound to the expected digest is a substantive review."""
    candidates = find_verdicts(text)
    plain = [c for c in candidates if c['state'] == 'plain']
    rejected = [c for c in candidates if c['state'] != 'plain']
    if not plain:
        return {'status': 'forged' if rejected else 'absent', 'digest_matches': False,
                'candidate': None, 'rejected_non_plain': rejected}
    last = plain[-1]
    if not last['full_sha_present']:
        return {'status': 'missing_digest', 'digest_matches': False, 'candidate': last,
                'rejected_non_plain': rejected}
    return {'status': 'pass' if last['verdict'] == 'PASS' else 'not_pass',
            'digest_matches': last['sha'] == expected_sha, 'candidate': last,
            'rejected_non_plain': rejected}


# --------------------------------------------------------------- native config
def _secret_field(name):
    low = re.sub('[^a-z0-9]', '', str(name).lower())
    return any(h in low for h in SECRET_FIELD_HINTS)


def _secret_ref(target):
    return any(h in Path(str(target)).name.lower() for h in SECRET_REF_HINTS)


def _resolve_ref(value, config_dir, env):
    """Resolve {file:}/{env:} refs; a credential-looking target is never read or echoed."""
    def replace(match):
        kind, target = match.group(1), match.group(2)
        if _secret_ref(target):
            return '<redacted-unresolved-credential-ref>'
        if kind == 'env':
            raw = env.get(target)
            return raw.strip()[:200] if raw is not None else f'<unset-env:{target}>'
        try:
            return (config_dir / target).resolve().read_text(encoding='utf-8').strip()[:200]
        except OSError:
            return f'<missing-file:{target}>'
    return REF_PATTERN.sub(replace, value)


def _redact(node, config_dir, env, stats):
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if _secret_field(key):
                stats['redacted_fields'] += 1
                continue
            resolved = _resolve_ref(key, config_dir, env) if isinstance(key, str) else key
            if _secret_field(resolved):
                stats['redacted_fields'] += 1
                continue
            stats['resolved_keys'] += resolved != key
            out[resolved] = _redact(value, config_dir, env, stats)
        return out
    if isinstance(node, list):
        return [_redact(item, config_dir, env, stats) for item in node]
    if isinstance(node, str):
        resolved = _resolve_ref(node, config_dir, env)
        stats['resolved_refs'] += resolved != node
        return resolved
    return node


def config_snapshot(config_path, env=None):
    """Strict-JSON native config, credential fields dropped, refs resolved safely."""
    env, path = dict(env or {}), Path(config_path)
    if not path.exists():
        raise PreflightBlocker(f'native config missing: {path}')
    raw = path.read_text(encoding='utf-8')
    try:
        config = json.loads(raw)
    except ValueError as exc:
        raise PreflightBlocker(f'native config {path} is not strict JSON (JSONC unsupported): {exc}') from exc
    stats = {'redacted_fields': 0, 'resolved_refs': 0, 'resolved_keys': 0}
    return {'path': str(path), 'snapshot': _redact(config, path.resolve().parent, env, stats),
            'stats': stats, 'raw_sha256': sha256_bytes(raw.encode('utf-8'))}


def validate_native_profile(snapshot, local_model):
    """Frozen profile: Hybrid and review inherit the caller cloud model, only the local
    worker model is pinned and it must match the requested one."""
    root = snapshot.get('snapshot') or {}
    agents = root.get('agents') or {}
    hybrid, review, general = agents.get('hybrid'), agents.get('review') or {}, agents.get('general') or {}
    blockers = [] if isinstance(hybrid, dict) else ['installed native config has no hybrid agent']
    for name, agent in (('hybrid', hybrid), ('review', review)):
        if isinstance(agent, dict) and agent.get('model'):
            blockers.append(f'agent {name} pins model {agent["model"]!r}; Hybrid and review must '
                            'inherit the caller cloud model')
    observed = {'general_model': general.get('model'),
                'hybrid_has_model': bool(isinstance(hybrid, dict) and hybrid.get('model')),
                'review_has_model': bool(isinstance(review, dict) and review.get('model')),
                'default_agent': root.get('default_agent'),
                'subagent_depth': (root.get('experimental') or {}).get('subagent_depth')}
    if observed['general_model'] != local_model:
        blockers.append(f"installed general worker model {observed['general_model']!r} does not match "
                        f'--local-model {local_model!r}')
    return blockers, observed


# --------------------------------------------------------------- Codex rollouts
def _assistant_text(payload):
    if payload.get('type') == 'agent_message':
        return str(payload.get('message') or '')
    if payload.get('type') == 'message' and payload.get('role') == 'assistant':
        return '\n'.join(p.get('text', '') for p in (payload.get('content') or [])
                         if isinstance(p, dict) and p.get('type') in ('output_text', 'text') and p.get('text'))
    return None


def _spawned_id(output):
    node = output if isinstance(output, dict) else None
    if node is None:
        try:
            node = json.loads(str(output or ''))
        except ValueError:
            return None
    if not isinstance(node, dict):
        return None
    for key in ('thread_id', 'agent_id'):
        if isinstance(node.get(key), str) and node[key]:
            return node[key]
    return None


def scan_codex_rollout(path):
    """One rollout: lineage, models, effort, final cumulative usage, completion, dispatches."""
    record = {'path': str(path), 'session_id': None, 'cwd': None, 'parent_id': None, 'models': [],
              'efforts': [], 'usage': None, 'usage_updates': 0, 'tool_calls': 0, 'edit_calls': 0,
              'assistant_texts': [], 'first_event': None, 'last_event': None, 'malformed_lines': 0,
              'completion': 'unknown', 'completion_markers': [], 'spawn_calls': 0, 'repair_calls': 0,
              'spawned_ids': []}
    try:
        handle = Path(path).open('r', encoding='utf-8', errors='replace')
    except OSError:
        return None
    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                event = None
            if not isinstance(event, dict):
                record['malformed_lines'] += 1
                continue
            payload = event.get('payload')
            payload = payload if isinstance(payload, dict) else {}
            stamp = event.get('timestamp')
            record['first_event'] = record['first_event'] or stamp
            record['last_event'] = stamp or record['last_event']
            if record['session_id'] is None and 'id' in payload:
                record['session_id'] = payload.get('id')
                record['cwd'] = payload.get('cwd')
                # session_meta source is a bare string ('cli') on a root rollout and a nested
                # object on a subagent rollout; either shape must scan without crashing.
                spawn = _dig(payload.get('source'), 'subagent', 'thread_spawn')
                if isinstance(spawn, dict):
                    record['parent_id'] = spawn.get('parent_thread_id')
            if event.get('type') == 'turn_context' or ('model' in payload and 'effort' in payload):
                if payload.get('model'):
                    record['models'].append(payload['model'])
                    record['efforts'].append(payload.get('effort') or payload.get('reasoning_effort'))
            info = payload.get('info')
            if payload.get('type') == 'token_count' and isinstance(info, dict) \
                    and isinstance(info.get('total_token_usage'), dict):
                record['usage'] = info['total_token_usage']
                record['usage_updates'] += 1
            ptype, name = str(payload.get('type') or ''), str(payload.get('name') or '').lower()
            if ptype in CODEX_TOOL_CALL_TYPES:
                record['tool_calls'] += 1
                record['edit_calls'] += name in CODEX_EDIT_TOOLS
                if name == CODEX_SPAWN_TOOL:
                    record['spawn_calls'] += 1
                elif name in CODEX_REPAIR_TOOLS:
                    record['repair_calls'] += 1
            if ptype in CODEX_COMPLETION_MARKERS:
                record['completion_markers'].append(ptype)
                record['completion'] = CODEX_COMPLETION_MARKERS[ptype]
            elif ptype in ('function_call_output', 'custom_tool_call_output'):
                spawned = _spawned_id(payload.get('output'))
                if spawned and spawned not in record['spawned_ids']:
                    record['spawned_ids'].append(spawned)
            text = _assistant_text(payload)
            if text:
                record['assistant_texts'].append(text)
    record['models'] = list(dict.fromkeys(record['models']))
    record['efforts'] = list(dict.fromkeys(e for e in record['efforts'] if e))
    return record if record['session_id'] else None


def scan_codex_rollouts(sessions_dir):
    catalog = {}
    if not Path(sessions_dir).exists():
        return catalog
    for path in sorted(Path(sessions_dir).glob('**/*.jsonl')):
        record = scan_codex_rollout(path)
        if record:
            catalog[record['session_id']] = record
    return catalog


def codex_tree(catalog, root_thread_id):
    """Root, every descendant rollout, and every id the root claims it spawned."""
    if root_thread_id not in catalog:
        raise PreflightBlocker(f'no Codex rollout found for root thread {root_thread_id}')
    ids = {root_thread_id}
    while True:
        grown = ids | {sid for sid, rec in catalog.items() if rec.get('parent_id') in ids and sid not in ids}
        if grown == ids:
            break
        ids = grown
    observed = set(ids)
    for sid in ids:
        observed.update((catalog.get(sid) or {}).get('spawned_ids') or [])
    return sorted(observed)


def codex_disjoint(usage):
    """Split cumulative Codex usage into disjoint parts; missing fields stay unknown."""
    usage = usage if isinstance(usage, dict) else {}
    present = {name: usage.get(name) for name in CODEX_COUNTER_FIELDS}
    clean = {name: (as_counter(value) or 0) for name, value in present.items()}
    cached, raw_input = clean['cached_input_tokens'], clean['input_tokens']
    reasoning, output = clean['reasoning_output_tokens'], clean['output_tokens']
    uncached = max(raw_input - cached, 0)
    missing = [n for n in CODEX_USAGE_FIELDS if usage.get(n) is None]
    invalid = counter_problems(usage, CODEX_COUNTER_FIELDS)
    return {'uncached_input': uncached, 'cached_input': cached,
            'non_reasoning_output': max(output - reasoning, 0), 'reasoning_output': reasoning,
            'raw_input': raw_input, 'raw_output': output, 'raw_total': clean['total_tokens'],
            'cloud_total': uncached + cached + output,
            'missing_fields': missing, 'invalid_fields': invalid,
            'complete': not missing and not invalid}


def account_codex(catalog, ids, *, root_thread_id, expected_root_model, expected_child_model,
                  expected_effort='medium', client='codex-cli'):
    """Final cumulative usage per native session, counted once, failing closed."""
    totals = dict.fromkeys(('uncached_input', 'cached_input', 'non_reasoning_output',
                            'reasoning_output', 'cloud_total', 'raw_total'), 0)
    sessions, blockers, unexpected_models = [], [], []
    unknown_sessions, attribution_bad = [], []
    missing_rollouts, effort_mismatch, incomplete_sessions = [], [], []
    requested = [sid for sid in ids if sid]
    ids = list(dict.fromkeys(requested))
    duplicate_ids = [sid for sid in dict.fromkeys(requested) if requested.count(sid) > 1]
    if duplicate_ids:
        blockers.append(f'session id(s) {", ".join(duplicate_ids)} listed more than once; every rollout '
                        'is counted once, never twice')
    malformed_rollouts = []
    descendants = max(len(ids) - 1, 0)
    root_calls, root_edit_calls, children, expected_children = None, 0, 0, 0
    for sid in ids:
        rec = catalog.get(sid)
        if rec is None:
            missing_rollouts.append(sid)
            unknown_sessions.append(sid)
            blockers.append(f'session {sid} has no rollout file; usage is unknown, never zero, and the '
                            'required child is unaccounted')
            continue
        reported = rec.get('malformed_lines')
        if (reported is not None and as_counter(reported) is None) or as_int(reported) > 0:
            malformed_rollouts.append(f'{sid}:{reported}')
            blockers.append(f"session {sid} rollout has {rec['malformed_lines']} malformed line(s); the "
                            'record is only partly readable, so complete usage evidence and any exact '
                            'total are withheld')
        role = 'root' if sid == root_thread_id else 'child'
        expected = expected_root_model if role == 'root' else expected_child_model
        models, efforts = list(rec['models']), list(rec['efforts'])
        if not models:
            unexpected_models.append(f'{sid}:{role}:missing-model')
            blockers.append(f'session {sid} ({role}) recorded no model; required {expected!r} routing is '
                            'unverified, never assumed')
        if not efforts:
            effort_mismatch.append(f'{sid}:{role}:missing-effort')
            blockers.append(f'session {sid} ({role}) recorded no reasoning effort; required '
                            f'{expected_effort!r} effort is unverified, never assumed')
        bad_effort = [e for e in efforts if e != expected_effort]
        if bad_effort:
            effort_mismatch.append(f"{sid}:{role}:{','.join(bad_effort)}")
            blockers.append(f'session {sid} ({role}) recorded effort(s) {bad_effort} instead of '
                            f'{expected_effort!r}; effort is read from the rollout, never assumed')
        completion = str(rec.get('completion') or 'unknown')
        if completion != 'complete':
            incomplete_sessions.append(f'{sid}:{role}:{completion}')
            blockers.append(f'session {sid} ({role}) has no task_complete marker (state {completion!r}); '
                            'an active, aborted or unknown turn is never an accepted arm')
        usage, tokens, status = rec.get('usage'), None, 'unknown'
        if usage is None:
            unknown_sessions.append(sid)
            blockers.append(f'session {sid} ({role}) has no usage record; the arm total is a lower bound '
                            'and is never reported as zero')
        else:
            tokens = codex_disjoint(usage)
            parts = (tokens['uncached_input'] + tokens['cached_input'] + tokens['non_reasoning_output']
                     + tokens['reasoning_output'])
            subsets_ok = (tokens['cached_input'] <= tokens['raw_input']
                          and tokens['reasoning_output'] <= tokens['raw_output'])
            if not tokens['complete']:
                status = 'incomplete'
                reason = (f"missing field(s) {', '.join(tokens['missing_fields'])}"
                          if tokens['missing_fields'] else
                          f"malformed counter(s) {', '.join(tokens['invalid_fields'])}")
                unknown_sessions.append(sid)
                attribution_bad.append(sid)
            elif len(set(models)) > 1:
                status, reason = 'mixed', f'model changed within the session ({", ".join(models)})'
                attribution_bad.append(sid)
            elif tokens['raw_total'] != parts or not subsets_ok:
                status, reason = 'inconsistent', 'cumulative counters do not match their disjoint parts'
                attribution_bad.append(sid)
            else:
                status, reason = 'complete', ''
                for key in totals:
                    totals[key] += tokens[key]
            if reason:
                blockers.append(f'session {sid} ({role}) usage is {status} ({reason}); the arm total '
                                'stays a lower bound and is never reported as zero')
            for model in [m for m in models if m != expected]:
                unexpected_models.append(f'{sid}:{role}:{model}')
        if role == 'root':
            root_edit_calls = as_int(rec.get('edit_calls'))
            if root_edit_calls:
                blockers.append(f'Codex root made {root_edit_calls} edit call(s); the root must plan and '
                                'review only')
            spawns, repairs = as_int(rec.get('spawn_calls')), as_int(rec.get('repair_calls'))
            root_calls = {'spawn_agent': spawns, 'followup': repairs,
                          'observed_child_ids': list(rec.get('spawned_ids') or [])}
            if spawns > 1:
                blockers.append(f'Codex root recorded {spawns} spawn_agent calls; exactly ONE initial '
                                'worker is allowed')
            if spawns + repairs > 2:
                blockers.append(f'Codex root recorded {spawns + repairs} worker dispatches; the frozen '
                                'budget is one initial plus at most one repair')
            if spawns and spawns > descendants:
                blockers.append(f'Codex root observed {spawns} spawn(s) but only {descendants} '
                                'descendant session(s) exist; an unrollowned spawn is never accepted')
        else:
            children += 1
            if models == [expected_child_model] and efforts == [expected_effort] and completion == 'complete':
                expected_children += 1
        sessions.append({'session_id': sid, 'parent_id': rec['parent_id'], 'role': role, 'models': models,
                         'efforts': efforts, 'expected_model': expected, 'expected_effort': expected_effort,
                         'completion': completion, 'completion_markers': list(rec.get('completion_markers') or []),
                         'spawn_calls': as_int(rec.get('spawn_calls')), 'repair_calls': as_int(rec.get('repair_calls')),
                         'usage_status': status, 'tokens': tokens, 'usage_updates': rec['usage_updates'],
                         'tool_calls': rec['tool_calls'], 'edit_calls': rec['edit_calls'], 'cwd': rec['cwd'],
                         'path': rec['path'], 'sha256': sha256_file(rec['path']) if Path(rec['path']).exists() else None,
                         'first_event': rec['first_event'], 'last_event': rec['last_event'],
                         'malformed_lines': rec['malformed_lines']})
    if root_thread_id not in catalog:
        blockers.append(f'no Codex rollout was recorded for the root thread {root_thread_id}')
    if children == 0:
        blockers.append('no Luna child session was spawned; the required Sol+Luna routing did not happen')
    elif children > 1:
        blockers.append(f'expected exactly one Luna child session, found {children}')
    elif expected_children == 0:
        blockers.append(f'no child ran the expected {expected_child_model} {expected_effort} routing')
    dispatch_ok = not root_calls or (root_calls['spawn_agent'] <= 1
                                     and root_calls['spawn_agent'] + root_calls['followup'] <= 2
                                     and root_calls['spawn_agent'] <= descendants)
    routing_ok = (root_thread_id in catalog and not unexpected_models and not missing_rollouts
                  and not duplicate_ids and not effort_mismatch and not incomplete_sessions
                  and not root_edit_calls and dispatch_ok and children == 1 and expected_children > 0)
    usage_complete = not (unknown_sessions or attribution_bad or missing_rollouts or malformed_rollouts)
    final_texts = (catalog.get(root_thread_id) or {}).get('assistant_texts') or []
    return {'client': client, 'protocol': PROTOCOL, 'root_thread_id': root_thread_id, 'sessions': sessions,
            'session_count': len(sessions), 'children': children, 'expected_child_sessions': expected_children,
            'totals': totals, 'cloud_total': totals['cloud_total'] if usage_complete else None,
            'known_lower_bound': totals['cloud_total'], 'cached_input_total': totals['cached_input'],
            'reasoning_output_total': totals['reasoning_output'], 'usage_complete': usage_complete,
            'unexpected_models': unexpected_models, 'routing_ok': routing_ok, 'blockers': blockers,
            'missing_rollouts': missing_rollouts, 'effort_mismatch': effort_mismatch,
            'malformed_rollouts': malformed_rollouts, 'duplicate_session_ids': duplicate_ids,
            'incomplete_sessions': incomplete_sessions, 'root_dispatch_calls': root_calls,
            'tool_calls': sum(s['tool_calls'] for s in sessions), 'model_calls': sum(len(s['models']) for s in sessions),
            'counting': ('final cumulative input+output counted once per native session; cached input is a '
                         'subset of input and reasoning output a subset of output, reported as disjoint parts'),
            'recorded_window': {'first_event': min([s['first_event'] for s in sessions if s['first_event']], default=None),
                                'last_event': max([s['last_event'] for s in sessions if s['last_event']], default=None)},
            'root_final_text': final_texts[-1] if final_texts else '',
            'root_final_text_source': f'last assistant message of root session {root_thread_id}'}


# ------------------------------------------------------------- OpenCode native
def _table(conn, candidates):
    names = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
    for name in candidates:
        if name in names:
            return name
    raise PreflightBlocker(f'OpenCode database has none of {list(candidates)}')


def snapshot_opencode(db_path, repo_dirs, seed_ids=()):
    """Read-only native database snapshot: frozen repo sessions plus their descendants."""
    path = Path(db_path)
    if not path.exists():
        raise PreflightBlocker(f'OpenCode database missing: {path}')
    conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    try:
        sessions_table, found = _table(conn, ('session_v2',)), {}
        messages_table = _table(conn, ('session_message', 'session_message_v2'))
        directories = [str(d) for d in repo_dirs]
        if directories:
            marks = ','.join('?' * len(directories))
            rows = conn.execute(f'select * from {sessions_table} where directory in ({marks}) order by time_created', directories)
            found.update({row['id']: dict(row) for row in rows})
        for seed in [s for s in seed_ids if s]:
            row = conn.execute(f'select * from {sessions_table} where id=?', (seed,)).fetchone()
            if row is not None:
                found.setdefault(row['id'], dict(row))
        frontier = list(found)
        while frontier:
            for child in conn.execute(f'select * from {sessions_table} where parent_id=?', (frontier.pop(),)):
                if child['id'] not in found:
                    found[child['id']] = dict(child)
                    frontier.append(child['id'])
        rows_for = lambda sid: conn.execute(f'select * from {messages_table} where session_id=? order by seq', (sid,))
        return {'database': str(path), 'scope_directories': directories,
                'records': [{'session': s, 'messages': [dict(m) for m in rows_for(s['id'])]} for s in found.values()]}
    finally:
        conn.close()


def _model_fields(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {'providerID': None, 'modelID': value}
    if not isinstance(value, dict):
        return {}
    out = dict(value)
    if not out.get('modelID') and isinstance(out.get('id'), str):
        out['modelID'] = out['id']
    if isinstance(out.get('modelID'), str) and '#' in out['modelID']:
        out['modelID'], _, variant = out['modelID'].partition('#')
        out.setdefault('variant', variant)
    return out


def _agent_from_assistants(messages):
    for message in messages:
        if message.get('type') == 'assistant':
            try:
                agent = json.loads(message.get('data') or '{}').get('agent')
            except ValueError:
                continue
            if agent:
                return str(agent)
    return None


def _tool_names(node, acc):
    if isinstance(node, dict):
        for key in ('tool', 'toolName', 'toolname'):
            if isinstance(node.get(key), str):
                acc.append(node[key].lower())
        for key in ('content', 'tools', 'parts'):
            if key in node:
                _tool_names(node[key], acc)
    elif isinstance(node, list):
        for item in node:
            _tool_names(item, acc)


def account_opencode(snapshot, *, root_session_ids, expected_cloud_provider, expected_cloud_model,
                     expected_local_provider, expected_local_model, expected_local_agent='general',
                     expected_review_agent='review', max_local_dispatches=2, client='opencode-cli'):
    """Disjoint assistant-message usage summed once per message, failures and gaps included."""
    fields = ('input', 'output', 'reasoning', 'cache_read', 'cache_write')
    totals = {t: dict.fromkeys(fields + ('total',), 0) for t in ('cloud', 'local', 'unknown')}
    sessions_out, requests, blockers = [], [], []
    unexpected_models, missing_usage, invalid_completion = [], [], []
    pending, variant_mismatch, unknown_fields = [], [], []
    invalid_usage, duplicate_records, unattributed = [], [], []
    assistant_models, assistant_variants, local_sessions, review_sessions = {}, {}, [], []
    incomplete_sessions = []
    seen_sessions, seen_messages = set(), {}
    maintenance = 0
    for rec in snapshot.get('records', []):
        session, sid = rec['session'], rec['session']['id']
        if sid in seen_sessions:
            duplicate_records.append(f'{sid}:session')
            continue
        seen_sessions.add(sid)
        message_ids = seen_messages.setdefault(sid, set())
        agent = session.get('agent') or _agent_from_assistants(rec['messages'])
        session_model = _model_fields(session.get('model'))
        if agent == expected_local_agent:
            local_sessions.append(sid)
        elif agent == expected_review_agent:
            review_sessions.append(sid)
        known = user_turns = edit_calls = model_calls = 0
        tool_counts, session_pending = {}, []
        for message in rec['messages']:
            mid = message.get('id')
            if mid is not None:
                if mid in message_ids:
                    duplicate_records.append(f'{sid}:{mid}')
                    continue
                message_ids.add(mid)
            try:
                data = json.loads(message.get('data') or '{}')
            except ValueError:
                blockers.append(f"session {sid} message {mid} has undecodable data")
                continue
            if not isinstance(data, dict):
                blockers.append(f'session {sid} message {mid} has undecodable data (not an object)')
                continue
            if message.get('type') == 'user':
                user_turns += 1
                continue
            if message.get('type') != 'assistant':
                continue
            tokens = data.get('tokens') if isinstance(data.get('tokens'), dict) else {}
            absent = [f for f in OPENCODE_REQUIRED_FIELDS if tokens.get(f) is None]
            if absent:
                missing_usage.append(f'{sid}:{mid}:{",".join(absent)}')
            own = _model_fields(data.get('model'))
            provider, model_id = own.get('providerID'), own.get('modelID')
            attributed = bool(provider and model_id)
            tier = ('cloud' if attributed and provider == expected_cloud_provider
                    else 'local' if attributed and provider == expected_local_provider else 'unknown')
            variant = str(own.get('variant') or '').strip().lower() or None
            if tier == 'cloud':
                assistant_variants.setdefault(sid, set()).add(variant)
            cache = tokens.get('cache') if isinstance(tokens.get('cache'), dict) else {}
            bad = counter_problems(tokens, OPENCODE_TOKEN_FIELDS) + counter_problems(cache, OPENCODE_CACHE_FIELDS)
            if bad:
                invalid_usage.append(f'{sid}:{mid}:{",".join(sorted(bad))}')
            counts = {f: (as_counter(tokens.get(f)) or 0) for f in OPENCODE_TOKEN_FIELDS}
            counts['cache_read'], counts['cache_write'] = (as_counter(cache.get('read')) or 0,
                                                           as_counter(cache.get('write')) or 0)
            extra = sorted(set(tokens) - set(OPENCODE_TOKEN_FIELDS) - {'cache'}) + sorted(set(cache) - set(OPENCODE_CACHE_FIELDS))
            if extra:
                unknown_fields.append(f'{sid}:{mid}:{",".join(extra)}')
            total = sum(counts.values())
            known += total
            for key, value in counts.items():
                totals[tier][key] += value
            totals[tier]['total'] += total
            tools = []
            _tool_names(data, tools)
            edit_calls += sum(1 for t in tools if t in EDIT_TOOLS)
            for tool in tools:
                tool_counts[tool] = tool_counts.get(tool, 0) + 1
            finish = data.get('finish')
            if not finish or str(finish).lower() in ERROR_FINISHES:
                session_pending.append(mid)
                (pending if not finish else invalid_completion).append(
                    f'{sid}:{mid}' if not finish else f'{sid}:{mid}:finish={finish}')
            if attributed:
                assistant_models.setdefault(sid, set()).add(f"{own['providerID']}/{own['modelID']}")
                model_calls += 1
            else:
                unattributed.append(f'{sid}:{mid}')
                blockers.append(f"session {sid} assistant message {mid} recorded no provider/model of its "
                                'own; actual routing is read from the request, never inherited from the '
                                'session configuration')
            if tier == 'cloud' and model_id and model_id != expected_cloud_model:
                unexpected_models.append(f'{sid}:{agent}:{provider}/{model_id}')
            if (tier == 'local' and agent == expected_local_agent and model_id
                    and f'{provider}/{model_id}' != expected_local_model):
                unexpected_models.append(f'{sid}:{agent}:{provider}/{model_id}')
            requests.append({'session': sid, 'message': mid, 'seq': message.get('seq'),
                             'agent': data.get('agent') or agent, 'provider': provider, 'model': model_id,
                             'variant': variant, 'tier': tier, 'finish': finish, **counts, 'total': total})
        native_bad = counter_problems(session, ['tokens_' + f for f in fields])
        native_total = sum(as_counter(session.get('tokens_' + f)) or 0 for f in fields)
        if native_bad:
            blockers.append(f'session {sid} native aggregate has malformed counter(s) '
                            f"{', '.join(name[len('tokens_'):] for name in native_bad)}; accounting is "
                            'inconsistent and no exact total is claimed')
        gap = native_total - known
        maintenance += max(gap, 0)
        idle = str(session.get('idle_outcome') or '').strip().lower()
        if idle and idle not in VALID_IDLE_OUTCOMES:
            invalid_completion.append(f'{sid}:idle_outcome={idle}')
        evidence = []
        if idle not in VALID_IDLE_OUTCOMES:
            evidence.append(f"idle_outcome={session.get('idle_outcome') or 'missing'}")
        time_idle = session.get('time_idle')
        if isinstance(time_idle, bool) or not isinstance(time_idle, (int, float)):
            evidence.append(f'time_idle={time_idle!r}')
        if rec['messages'] and rec['messages'][-1].get('type') == 'user':
            evidence.append('trailing user message awaiting a response')
        incomplete_sessions += [f'{sid}:{reason}' for reason in evidence]
        if gap < 0:
            blockers.append(f'session {sid} native aggregate {native_total} is below the summed assistant '
                            f'usage {known}; accounting is inconsistent')
        sessions_out.append({'id': sid, 'parent_id': session.get('parent_id'), 'agent': agent,
                             'model': session_model, 'directory': session.get('directory'),
                             'native_total': native_total, 'assistant_total': known, 'maintenance_gap': gap,
                             'user_turns': user_turns, 'edit_calls': edit_calls, 'model_calls': model_calls,
                             'tool_calls': sum(tool_counts.values()), 'tools': dict(sorted(tool_counts.items())),
                             'pending_assistant_messages': session_pending, 'time_created': session.get('time_created'),
                             'time_idle': session.get('time_idle'), 'idle_outcome': session.get('idle_outcome'),
                             'incomplete_evidence': evidence})
    root_ids = [r for r in root_session_ids if r]
    roots = [s for s in sessions_out if s['id'] in root_ids] or [s for s in sessions_out if not s['parent_id']]
    if not roots:
        blockers.append('no root OpenCode session was found for the frozen repo directory or recorded ids')
    for root in roots:
        if root['agent'] != 'hybrid':
            blockers.append(f"root session {root['id']} agent is {root['agent']!r}, expected 'hybrid'")
        if root['edit_calls']:
            blockers.append(f"Hybrid root made {root['edit_calls']} edit call(s); the root must not implement")
    if len(local_sessions) != 1:
        blockers.append(f'expected exactly one general local worker session, found {len(local_sessions)}')
    dispatches = sum(s['user_turns'] for s in sessions_out if s['id'] in local_sessions)
    for session in sessions_out:
        model = session['model']
        if session['id'] in local_sessions and model and \
                f"{model.get('providerID')}/{model.get('modelID')}" != expected_local_model:
            blockers.append(f"local worker session {session['id']} ran {model} instead of {expected_local_model}")
    if dispatches > max_local_dispatches:
        blockers.append(f'local worker received {dispatches} dispatches (maximum {max_local_dispatches}: '
                        'one initial plus one repair)')
    if not review_sessions:
        blockers.append('no review subagent session was recorded; the native semantic review is missing')
    elif len(review_sessions) > 1:
        blockers.append(f'expected exactly one review session, found {len(review_sessions)}')
    extra_agents = [f"{s['id']}:{s['agent']}" for s in sessions_out
                    if s['agent'] not in ('hybrid', expected_local_agent, expected_review_agent)]
    if extra_agents:
        blockers.append(f"unexpected native session(s) {', '.join(extra_agents)}: the frozen arm is one "
                        f'Hybrid root, one {expected_local_agent} worker and one {expected_review_agent} review')
    cloud_expected = f'{expected_cloud_provider}/{expected_cloud_model}'
    by_id = {s['id']: s for s in sessions_out}
    required_roles = [('root Hybrid', [r['id'] for r in roots], cloud_expected, True),
                      (f'{expected_local_agent} worker', local_sessions, expected_local_model, False),
                      ('Sol reviewer', review_sessions, cloud_expected, True)]
    for label, tier_ids, expected_routing, check_variant in required_roles:
        for sid in tier_ids:
            seen = sorted(assistant_models.get(sid) or ())
            if not seen:
                unexpected_models.append(f'{sid}:no-assistant-model')
                blockers.append(f'{label} session {sid} recorded no assistant model; {expected_routing} '
                                'routing is unknown here, never assumed from the session configuration')
                continue
            wrong = [m for m in seen if m != expected_routing]
            if wrong:
                unexpected_models.append(f"{sid}:{'+'.join(wrong)}")
                blockers.append(f"{label} session {sid} used {', '.join(wrong)} instead of "
                                f'{expected_routing}; recorded assistant routing that misses its tier is '
                                'wrong routing, never a cheap success')
            if check_variant:
                variants = sorted(v or 'missing' for v in (assistant_variants.get(sid) or set()))
                if variants != [EXPECTED_REASONING_VARIANT]:
                    variant_mismatch.append(f'{sid}:{"+".join(variants)}')
                    blockers.append(f'{label} session {sid} recorded cloud reasoning variant(s) {variants} '
                                    f"instead of exactly ['{EXPECTED_REASONING_VARIANT}']; effort is read "
                                    'from recorded requests, never assumed')
            unfinished = (by_id.get(sid) or {}).get('pending_assistant_messages') or []
            if unfinished:
                blockers.append(f"{label} session {sid} has unfinished assistant records "
                                f"({', '.join(str(m) for m in unfinished)}); an incomplete turn is never "
                                'an accepted arm')
    if duplicate_records:
        blockers.append(f"duplicate native record(s) {', '.join(duplicate_records[:8])} were ignored; every "
                        'session and message is counted once, never twice')
    for entry in incomplete_sessions:
        blockers.append(f'native session {entry} lacks completion evidence; its counted usage is retained, '
                        'but a session that never went idle or still awaits an answer cannot pass the arm')
    usage_complete = not (pending or unknown_fields or missing_usage or invalid_completion
                          or invalid_usage or duplicate_records or incomplete_sessions
                          or [b for b in blockers if 'inconsistent' in b or 'undecodable' in b])
    cloud_known = totals['cloud']['total']
    status = ('unknown' if not usage_complete or unattributed else
              'exact' if maintenance == 0 and totals['unknown']['total'] == 0 else 'cloud_exact_unknown')
    upper_bound = (None if status == 'unknown'
                   else cloud_known + maintenance + totals['unknown']['total'])
    return {'client': client, 'protocol': PROTOCOL, 'sessions': sessions_out, 'requests': requests,
            'root_session_ids': root_ids, 'local_worker_sessions': local_sessions,
            'local_dispatches': dispatches, 'review_sessions': review_sessions, 'totals': totals,
            'cloud_total': cloud_known if status == 'exact' else None, 'known_lower_bound': cloud_known,
            'local_total': totals['local']['total'], 'unknown_maintenance_total': maintenance,
            'unknown_usage_total': totals['unknown']['total'], 'usage_complete': usage_complete,
            'cloud_cost_range': {'lower_bound': cloud_known,
                                 'upper_bound': upper_bound,
                                 'status': status, 'note': 'unknown maintenance stays its own number; the '
                                 'exact cloud total and every upper bound are withheld while usage evidence '
                                 'or routing coverage is incomplete'},
            'pending_assistant_messages': pending, 'missing_usage_fields': missing_usage,
            'incomplete_sessions': incomplete_sessions,
            'invalid_usage_fields': invalid_usage, 'duplicate_records': duplicate_records,
            'assistant_messages_without_model': unattributed,
            'invalid_completion': invalid_completion, 'unaccounted_usage_fields': unknown_fields,
            'variant_mismatch': variant_mismatch, 'unexpected_models': unexpected_models,
            'routing_ok': not blockers and not unexpected_models, 'blockers': blockers,
            'counting': 'per assistant message fields summed once; the session-aggregate difference stays '
                        'unknown maintenance, never a tier'}
