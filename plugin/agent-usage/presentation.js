// Facts for the read-only TUI. No I/O, model requests or quality grading.
// Recorded spans can include tool/delegation waits; they are not billed compute.
import {analyze, modelRef, money} from '../../src/usage-analysis.js';

const running = value => (value?.type ?? value) === 'running';
const endOf = message => Math.max(message.created || 0, message.completed || 0);
const identity = row => `${row.sessionID}:${row.agent}:${typeof row.model === 'string' ? row.model : modelRef(row.model)}`;

export function duration(seconds) {
  if (!Number.isFinite(seconds)) return '—';
  const s = Math.max(0, Math.floor(seconds));
  if (s >= 3600) return `${Math.floor(s / 3600)}h ${Math.floor(s % 3600 / 60)}m`;
  return s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`;
}

function unionSeconds(intervals) {
  const sorted = intervals.filter(([a, b]) => a > 0 && b >= a).sort((a, b) => a[0] - b[0]);
  let total = 0, start = null, end = null;
  for (const [a, b] of sorted) {
    if (start === null) { start = a; end = b; }
    else if (a <= end) end = Math.max(end, b);
    else { total += end - start; start = a; end = b; }
  }
  return Math.round((total + (start === null ? 0 : end - start)) / 1000);
}

function completeRate(message, pricing) {
  const rate = pricing[modelRef(message.model).split('#')[0]];
  if (!rate) return false;
  const rates = {reasoning: rate.output, cacheWrite: rate.input, cacheRead: rate.input, ...rate};
  return Object.entries(message.tokens).every(([key, count]) => !count || (Number.isFinite(rates[key]) && rates[key] >= 0));
}

function costFor(messages, aggregate, pricing) {
  const recordedValue = messages.reduce((n, m) => n + (m.cost > 0 ? m.cost : 0), 0);
  const missing = messages.filter(m => !(m.cost > 0));
  const unpricedTurns = aggregate.cost === null ? missing.filter(m => !completeRate(m, pricing)).length : 0;
  const facts = {recordedValue, unpricedTurns};
  if (!messages.length) return {...facts, kind: 'none', value: null, label: 'No usage'};
  if (aggregate.cost === null) return {...facts, kind: 'unavailable', value: null, label: 'Unavailable'};
  if (messages.every(m => m.class === 'local') && missing.length) {
    return {...facts, kind: 'local', value: null, label: 'Operating cost unmeasured'};
  }
  const kind = missing.length ? (missing.length < messages.length ? 'mixed' : 'estimated') : 'recorded';
  const basis = kind === 'mixed' ? 'recorded + estimated' : kind;
  return {...facts, kind, value: aggregate.cost, label: `${money(aggregate.cost)} ${basis}`};
}

function reviewFor(messages, rootID, statuses, isRunning) {
  const newestFirst = [...messages].sort((a, b) => endOf(b) - endOf(a) || b.created - a.created);
  const cloud = newestFirst.filter(m => m.class === 'cloud');
  const coordinator = cloud.find(m => m.reviewVerdict && m.sessionID === rootID && ['orchestrator', 'build', 'plan'].includes(m.agent));
  const independentActivity = cloud.find(m => m.sessionID !== rootID && m.agent === 'cloud-reviewer');
  const independent = cloud.find(m => m.reviewVerdict && m.sessionID !== rootID && m.agent === 'cloud-reviewer');
  const reviewer = coordinator ?? independent;
  const previous = !!reviewer && (isRunning || messages.some(m => endOf(m) > endOf(reviewer)));
  return {
    verdict: reviewer?.reviewVerdict ?? null,
    kind: !reviewer ? 'No explicit review verdict' : reviewer === independent ? 'Independent review' : reviewer.agent === 'orchestrator' ? 'Coordinator review' : 'Primary agent review',
    agent: reviewer?.agent ?? null,
    model: reviewer ? modelRef(reviewer.model) : null,
    sourceSessionID: reviewer?.sessionID ?? null,
    sourceMessageID: reviewer?.id ?? null,
    previous,
    conflict: !!coordinator && !!independent && coordinator.reviewVerdict !== independent.reviewVerdict,
    independent: !!independentActivity,
    independentStatus: !independentActivity ? 'not-observed' : running(statuses[independentActivity.sessionID]) ? 'running' : independent ? 'reported' : 'no-verdict',
    independentVerdict: independent?.reviewVerdict ?? null,
    independentSourceSessionID: independent?.sessionID ?? independentActivity?.sessionID ?? null,
    independentSourceMessageID: independent?.id ?? null,
    independentModel: independentActivity ? modelRef(independentActivity.model) : null,
    independentPrevious: !!independent && (!!independentActivity && endOf(independentActivity) > endOf(independent) || running(statuses[independent.sessionID])),
  };
}

export function dashboard(tree, {statuses = {}, selected = null, now = Date.now(), pricing = {}} = {}) {
  const report = analyze(tree, {pricing});
  const byIdentity = new Map(report.breakdown.map(b => [identity(b), b]));
  const messages = tree.messages.map(m => {
    const agent = m.agent ?? (m.compaction ? 'compaction' : 'unknown');
    return {...m, agent, class: byIdentity.get(identity({...m, agent}))?.class ?? 'unknown'};
  });
  const latest = new Map();
  for (const m of messages) if (!latest.has(m.sessionID) || m.created >= latest.get(m.sessionID).created) latest.set(m.sessionID, m);
  const active = tree.sessions.filter(s => running(statuses[s.id])).map(s => {
    const m = latest.get(s.id);
    const observed = !!m && (m.pending || modelRef(m.model) === modelRef(s.model));
    return {sessionID: s.id, agent: m?.agent ?? s.agent ?? 'unknown', model: observed ? modelRef(m.model) : 'unknown', class: observed ? m.class : 'unknown', state: observed ? 'observed' : 'awaiting-model', started: m?.created || s.created || null};
  });
  const isRunning = active.length > 0;
  const starts = [tree.root.created, ...messages.map(m => m.created)].filter(v => Number.isFinite(v) && v > 0);
  const first = starts.length ? Math.min(...starts) : null;
  const last = Math.max(0, ...messages.map(endOf), tree.root.idle ?? 0);
  const elapsedSeconds = first === null ? 0 : Math.max(0, Math.round(((isRunning ? now : last) - first) / 1000));
  const used = new Map();
  for (const m of [...messages].sort((a, b) => endOf(b) - endOf(a))) {
    if (used.has(identity(m))) continue;
    used.set(identity(m), {
      sessionID: m.sessionID, agent: m.agent, model: modelRef(m.model), class: m.class,
      lastUsed: endOf(m), active: active.some(a => a.sessionID === m.sessionID && a.model === modelRef(m.model) && a.agent === m.agent),
      cost: costFor(messages.filter(row => identity(row) === identity(m)), byIdentity.get(identity(m)), pricing),
    });
  }
  const group = name => {
    const rows = messages.filter(m => m.class === name), bucket = report.totals[name];
    const intervals = rows.map(m => [m.created, m.pending && running(statuses[m.sessionID]) && latest.get(m.sessionID) === m ? now : endOf(m)]);
    return {tokens: bucket.raw, turns: bucket.turns, sessions: bucket.sessions, elapsedSeconds: unionSeconds(intervals), cost: costFor(rows, bucket, pricing)};
  };
  return {
    report,
    status: isRunning ? 'running' : ['succeeded', 'failed', 'interrupted'].includes(tree.root.outcome) ? tree.root.outcome : 'idle',
    elapsedSeconds, cloud: group('cloud'), local: group('local'), unknown: group('unknown'),
    active, history: [...used.values()],
    selected: selected?.model ? {agent: selected.agent ?? 'unknown', model: typeof selected.model === 'string' ? selected.model : modelRef(selected.model)} : null,
    review: reviewFor(messages, tree.root.id, statuses, isRunning),
  };
}
