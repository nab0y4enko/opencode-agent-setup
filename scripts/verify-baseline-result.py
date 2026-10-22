"""Independently enforce the Build-only baseline acceptance contract."""
import json
import math
import re
import sys

MODEL = 'openai/gpt-6.1-sol#high'


def test_run(text, count, success=True):
    """Require one real unittest summary, including the exact discovered count."""
    summaries = re.findall(r'^Ran (\d+) tests? in .+$', text or '', re.M)
    verdict = r'^OK\s*$' if success else r'^FAILED \(.*\)\s*$'
    return summaries == [str(count)] and bool(re.search(verdict, text or '', re.M))


def positive(value):
    return isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def verify(report):
    errors = []
    def require(condition, message):
        if not condition:
            errors.append(message)

    require(report.get('opencode_exit') == 0, 'OpenCode failed')
    require(report.get('independent_test_exit') == 0 and test_run(report.get('tests'), 4),
            'Independent four-test run missing or failed')
    commits = report.get('commits') or []
    require(len(commits) == 2, 'Expected exactly two completed stage commits')
    if len(commits) == 2:
        shas = [c.get('sha') for c in commits]
        require(all(isinstance(s, str) and re.fullmatch('[0-9a-f]{40}', s) for s in shas), 'Invalid stage commit SHA')
        require(shas[0] != shas[1], 'Stage commits are not distinct')
        require(sorted(commits[0].get('files', [])) == ['fixture.py'], 'Stage 1 committed unexpected files')
        require(sorted(commits[1].get('files', [])) == ['fixture.py', 'test_fixture.py'], 'Stage 2 committed unexpected files')
    require(report.get('status') == '', 'Worktree is dirty')
    require(report.get('children') == [], 'Child session/delegation check missing or children observed')

    checkpoints = report.get('checkpoints') or []
    require(len(checkpoints) == 2, 'Expected two independently replayed checkpoints')
    for i, checkpoint in enumerate(checkpoints[:2]):
        number, count, word = i + 1, i + 3, ('three', 'four')[i]
        require(checkpoint.get('independent_test_exit') == 0 and test_run(checkpoint.get('tests'), count),
                f'Stage {number} independent {word}-test checkpoint failed')
        require(i < len(commits) and checkpoint.get('sha') == commits[i].get('sha'), f'Stage {number} checkpoint commit mismatch')
        patch = checkpoint.get('patch', '')
        require(bool(patch.strip()) and patch.strip() == checkpoint.get('artifact_patch', '').strip(),
                f'Stage {number} patch evidence missing or differs from committed patch')
        require(test_run(checkpoint.get('artifact_tests'), count), f'Stage {number} passing test evidence missing')
        if i == 1:
            require(checkpoint.get('regression_exit') not in (None, 0) and test_run(checkpoint.get('regression_tests'), 4, False)
                    and 'ValueError not raised' in checkpoint.get('regression_tests', ''),
                    'Stage 2 regression did not fail against stage 1 implementation')
            require(test_run(checkpoint.get('artifact_red_tests'), 4, False)
                    and 'ValueError not raised' in checkpoint.get('artifact_red_tests', ''), 'Stage 2 red failure evidence missing')

    usage = report.get('usage')
    require(isinstance(usage, dict) and bool(usage), 'Usage report missing; token measurement did not run')
    if not isinstance(usage, dict) or not usage:
        return errors
    root = usage.get('root', {})
    require(bool(root.get('id')) and root.get('agent') == 'build' and root.get('model') == MODEL,
            'Root did not use the requested cloud Build route')
    sessions = usage.get('sessions', [])
    require(len(sessions) == 1 and sessions[0].get('id') == root.get('id') and not sessions[0].get('parentID'),
            'Usage shows child sessions/delegation or a missing measured root session')
    buckets = usage.get('breakdown', sessions)
    require(bool(buckets) and all(b.get('agent') == 'build' and b.get('class') == 'cloud' and b.get('model') == MODEL
                                 and b.get('sessionID', b.get('id')) == root.get('id') for b in buckets),
            'Actual message usage departed from the requested cloud Build route')
    require(usage.get('dispatches') == [], 'Usage delegation check missing or a dispatch was observed')
    totals = usage.get('totals', {})
    cloud = totals.get('cloud', {}).get('weighted')
    require(positive(cloud), 'No cloud tokens recorded')
    require(cloud == totals.get('all', {}).get('weighted') and totals.get('local', {}).get('weighted') == 0
            and totals.get('unknown', {}).get('weighted', 0) == 0, 'Token usage includes local or unknown model routes')
    agents = usage.get('byAgent', [])
    models = usage.get('byModel', [])
    require(len(agents) == 1 and agents[0].get('agent') == 'build' and agents[0].get('class') == 'cloud'
            and positive(agents[0].get('weighted')), 'Actual agent usage is not cloud Build')
    require(len(models) == 1 and models[0].get('model') == MODEL.split('#')[0] and models[0].get('class') == 'cloud'
            and positive(models[0].get('weighted')), 'Actual model usage is not OpenAI Sol high')
    events = report.get('events') or {}
    require(positive(events.get('count')) and events.get('parseErrors') == [], 'Event evidence missing or malformed')
    require(events.get('sessionIDs') == [root.get('id')], 'Event session does not match the measured root')
    require(events.get('delegationCalls') == [], 'Event tool calls show delegation or delegation check is missing')
    return errors


if __name__ == '__main__':
    with open(sys.argv[1]) as source:
        failures = verify(json.load(source))
    print(json.dumps({'passed': not failures, 'failures': failures}, indent=2))
    sys.exit(1 if failures else 0)
