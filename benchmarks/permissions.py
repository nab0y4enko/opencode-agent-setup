"""Permission gate: can each installed Hybrid role run what a round needs, before any token is spent?

OpenCode lists an agent's effective rules in order (its defaults first, then the installed config);
the last rule whose action and resource both match decides. A shell command is checked one
pipeline or chain part at a time, so a `| tee` or `cd … &&` wrapper needs its own allowance.
"""
import json
import re

ROLES = ('hybrid', 'general', 'review')
PROBE_ROLES = ('general', 'review')
# Wrappers a local model adds unasked; each part must be allowed or the arm stops at a denial.
PROBE_COMMAND = "git status --short && git diff --binary HEAD | shasum -a 256 2>&1 | tee probe.log; printf 'probe\\n'"
PROBE_PROMPT = ('Permission probe. Use the shell tool exactly once to run this command unchanged, then reply DONE: '
                + PROBE_COMMAND)
FIX = ('the benchmark needs unrestricted shell for hybrid, general and review: remove the restricting rule from '
       'that agent in the installed config (see AGENTS.md); never reword prompts around it')

_SPLIT = re.compile(r'&&|\|\||[;|\n]')


def _matches(pattern, value):
    regex = ''.join('.*' if ch == '*' else '.' if ch == '?' else re.escape(ch) for ch in str(pattern))
    return re.fullmatch(regex, str(value), re.S) is not None


def decide(rules, action, resource):
    """The effect of the last matching rule and that rule; no match is 'unknown', never allow."""
    decided = None
    for rule in rules or []:
        if isinstance(rule, dict) and _matches(rule.get('action', ''), action) \
                and _matches(rule.get('resource', ''), resource):
            decided = rule
    return (decided.get('effect') or 'unknown', decided) if decided else ('unknown', None)


def command_parts(command):
    return [part.strip() for part in _SPLIT.split(command) if part.strip()]


def required_actions(check, repo, allowed_changed):
    """What each role does in a round, including the wrappers the local model adds."""
    files = ' '.join(allowed_changed)
    inspect = ['git status --short', 'git diff --stat', 'git diff HEAD',
               'git ls-files --others --exclude-standard', 'git diff --binary HEAD | shasum -a 256']
    wrappers = [f"printf '--- files ---\\n'; cat {files}", 'echo "exit=$?"']
    return {
        'hybrid': [('shell', command) for command in [check] + inspect]
                  + [('subagent', name) for name in ('general', 'explore', 'review')],
        'general': [('shell', command) for command in
                    [check, f'PYTHONDONTWRITEBYTECODE=1 {check}', f'cat {files}',
                     f'cd {repo} && {check} 2>&1 | tee {repo}/.bench-check.log'] + wrappers]
                   + [('edit', f'{repo}/{path}') for path in allowed_changed],
        'review': [('shell', command) for command in inspect + [f'cat {files}'] + wrappers],
    }


def gate(agents, *, check, repo, allowed_changed):
    """Blockers (one per role) and every decision taken, from `opencode debug agents` output."""
    by_id = {agent.get('id'): agent for agent in agents if isinstance(agent, dict)} if isinstance(agents, list) else {}
    blockers, decisions = [], []
    for role, actions in required_actions(check, str(repo), list(allowed_changed)).items():
        agent = by_id.get(role)
        if agent is None:
            blockers.append(f'OpenCode lists no effective {role} agent, so its permissions are unverified')
            continue
        rules = agent.get('permissions') or agent.get('permission') or []
        refused = []
        for action, resource in actions:
            for part in (command_parts(resource) if action == 'shell' else [resource]):
                effect, rule = decide(rules, action, part)
                decisions.append({'agent': role, 'action': action, 'resource': part, 'effect': effect, 'rule': rule})
                if effect != 'allow':
                    shown = f"{rule['action']} {rule['resource']!r} {rule['effect']}" if rule else 'no matching rule'
                    entry = f'{effect} {action} `{part}` ({shown})'
                    if entry not in refused:
                        refused.append(entry)
        if refused:
            blockers.append(f'installed OpenCode {role} agent would ' + '; '.join(refused[:6])
                            + (f'; and {len(refused) - 6} more' if len(refused) > 6 else '') + f' — {FIX}')
    return blockers, decisions


def _denied(state):
    error = state.get('error')
    if isinstance(error, dict):
        return error.get('type') == 'permission.rejected'
    return isinstance(error, str) and error.startswith('Permission denied')


def probe_result(stdout_text):
    """Tool calls, denials and client errors in an `opencode run --format json` stream."""
    result = {'tool_calls': 0, 'denied': [], 'errors': []}
    for line in (stdout_text or '').splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get('type') == 'error':
            error = event.get('error')
            result['errors'].append(str(error.get('message') if isinstance(error, dict) else error)[:300])
        part = event.get('part') if isinstance(event.get('part'), dict) else {}
        state = part.get('state') if isinstance(part.get('state'), dict) else {}
        if part.get('type') != 'tool' or state.get('status') not in ('completed', 'error'):
            continue
        result['tool_calls'] += 1
        if state.get('status') == 'error' and _denied(state):
            result['denied'].append(str((state.get('input') or {}).get('command') or part.get('tool'))[:300])
    return result
