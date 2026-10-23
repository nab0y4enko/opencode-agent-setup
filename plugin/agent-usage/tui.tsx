// Read-only usage dashboard. No model requests, billing guesses or quality scores.
import {Plugin} from "@opencode/plugin/tui"
import {createEffect, createMemo, createSignal, For, Show, onCleanup} from "solid-js"
import {analyze, num, pct, summaryLine, treeFrom} from "../../src/usage-analysis.js"
import {dashboard, duration} from "./presentation.js"
import {createUsageNavigation, latestRoot} from "./navigation.js"

type Context = Plugin.Context
type View = ReturnType<typeof dashboard>
type Tone = Context["theme"]["text"]["base"]
const short = (model: string) => model.replace(/^[^/]+\//, "")
const activeStatus = (status: unknown) => status === "running" || (status as {type?: string})?.type === "running"
const tones = (context: Context) => ({cloud: context.theme.hue.cyan[context.themeMode === "light" ? 700 : 300], local: context.theme.hue.green[context.themeMode === "light" ? 700 : 300], unknown: context.theme.text.feedback.warning.base})
const countLabel = (count: number, label: string, plural = `${label}s`) => `${num(count)} ${count === 1 ? label : plural}`
const statusText = (status: string) => ({running: "RUNNING", succeeded: "COMPLETED", failed: "FAILED", interrupted: "STOPPED", idle: "IDLE"}[status] ?? status)
const verdictTone = (context: Context, verdict: string | null) => verdict === "PASS" ? context.theme.text.feedback.success.base : verdict ? context.theme.text.feedback.error.base : context.theme.text.feedback.warning.base

function familyOf(context: Context, rootID: string) {
  const ids = new Set<string>([rootID, ...(context.data.session.family(rootID) ?? [])])
  for (const s of context.data.session.list()) if (context.data.session.root(s.id) === rootID) ids.add(s.id)
  return [...ids]
}

function useView(context: Context, rootID: () => string | undefined) {
  const synced = new Set<string>()
  const [now, setNow] = createSignal(Date.now())
  createEffect(() => {
    const id = rootID()
    if (!id) return
    const ids = familyOf(context, id)
    for (const sid of ids) {
      if (synced.has(sid)) continue
      synced.add(sid)
      void context.data.session.message.sync(sid).catch(() => synced.delete(sid))
    }
    if (!ids.some(sid => activeStatus(context.data.session.status(sid)))) return
    setNow(Date.now())
    const timer = setInterval(() => setNow(Date.now()), 1000)
    onCleanup(() => clearInterval(timer))
  })
  return createMemo<View | undefined>(() => {
    const id = rootID()
    if (!id) return undefined
    const sessions = context.data.session.list()
    const ids = familyOf(context, id)
    const tree = treeFrom(sessions, sid => context.data.session.message.list(sid), id)
    if (!tree) return undefined
    const model = context.ui.model.current()
    return dashboard(tree, {statuses: Object.fromEntries(ids.map(sid => [sid, context.data.session.status(sid)])), selected: model ? {model} : null, now: now()})
  })
}

function Metric(props: {context: Context; label: string; value: string; color?: Tone}) {
  return <box flexDirection="row" justifyContent="space-between" gap={2}>
    <text fg={props.context.theme.text.muted}>{props.label}</text>
    <text fg={props.color ?? props.context.theme.text.base}>{props.value}</text>
  </box>
}

function UsageCard(props: {context: Context; title: string; color: Tone; stats: View["cloud"]}) {
  const theme = props.context.theme
  return <box flexGrow={1} flexBasis={0} minWidth={38} border borderStyle="rounded" borderColor={props.color} backgroundColor={theme.background.raised.base} paddingLeft={2} paddingRight={2} paddingTop={1} paddingBottom={1}>
    <box flexDirection="row" justifyContent="space-between">
      <text fg={props.color}><b>{props.title}</b></text>
      <text fg={theme.text.muted}>{countLabel(props.stats.turns, "turn")} · {countLabel(props.stats.sessions, "session")}</text>
    </box>
    <Metric context={props.context} label="Input tokens" value={num(props.stats.tokens.input)} />
    <Metric context={props.context} label="Output tokens" value={num(props.stats.tokens.output)} />
    <Metric context={props.context} label="Reasoning tokens" value={num(props.stats.tokens.reasoning)} />
    <Metric context={props.context} label="Cache read / write" value={`${num(props.stats.tokens.cacheRead)} / ${num(props.stats.tokens.cacheWrite)}`} />
    <Metric context={props.context} label="Recorded turn span" value={duration(props.stats.elapsedSeconds)} />
    <Metric context={props.context} label={props.title === "LOCAL" ? "Local cost" : "API cost"} value={props.stats.cost.label} color={props.stats.cost.value === null ? theme.text.feedback.warning.base : props.color} />
    <Show when={props.stats.cost.unpricedTurns && props.stats.cost.recordedValue > 0}>
      <text fg={theme.text.feedback.warning.base}>${props.stats.cost.recordedValue.toFixed(4)} recorded; {props.stats.cost.unpricedTurns} unpriced turns</text>
    </Show>
  </box>
}

function UsagePage(props: {context: Context; rootID: string | undefined; onClose: () => void}) {
  const context = props.context, theme = context.theme, colors = tones(context)
  const [rootID, setRootID] = createSignal(props.rootID)
  const view = useView(context, rootID)
  const [advanced, setAdvanced] = createSignal(false)
  const [configured, setConfigured] = createSignal(false)
  const roles = createMemo(() => (context.data.location.agent.list() ?? []).filter(agent => ["orchestrator", "general", "explore", "plan", "build", "cloud-reviewer", "summary", "compaction", "title"].includes(agent.id)))
  const openReview = () => {
    const id = view()?.review.sourceSessionID
    if (id) context.ui.router.navigate({type: "session", sessionID: id})
  }
  const openIndependent = () => {const id = view()?.review.independentSourceSessionID; if (id) context.ui.router.navigate({type: "session", sessionID: id})}
  context.keymap.layer(() => ({commands: [
    {bind: "escape", title: "back", run: props.onClose},
    {bind: "r", title: "resync", run: () => {const id = rootID(); if (id) for (const sid of familyOf(context, id)) {context.data.session.message.invalidate(sid); void context.data.session.message.sync(sid)}}},
    {bind: "n", title: "newest session", run: () => setRootID(latestRoot(context))},
    {bind: "v", title: "review source", run: openReview},
    {bind: "i", title: "independent review source", run: openIndependent},
    {bind: "c", title: "configured roles", run: () => setConfigured(!configured())},
    {bind: "w", title: "weighted detail", run: () => setAdvanced(!advanced())},
  ]}))
  return <box width="100%" height="100%" backgroundColor={theme.background.base} paddingLeft={2} paddingRight={2} paddingTop={1}>
    <Show when={view()} fallback={<text fg={theme.text.muted}>No session data yet. Start a session, then open /usage.</text>}>
      {v => <>
        <box flexDirection="row" justifyContent="space-between" paddingBottom={1} height={4} flexShrink={0} gap={2}>
          <box>
            <text fg={theme.text.base}><b>Agent usage</b>  {v().report.root.title || "Untitled session"}</text>
            <text fg={theme.text.muted}>{v().report.root.id}</text>
          </box>
          <box alignItems="flex-end" flexShrink={0}>
            <text fg={v().status === "failed" ? theme.text.feedback.error.base : v().status === "running" ? colors.cloud : theme.text.feedback.success.base}><b>{statusText(v().status)}</b>  ·  {duration(v().elapsedSeconds)} elapsed</text>
            <text fg={theme.text.muted}>{countLabel(v().report.sessions.length, "session")} · {countLabel(v().report.dispatches.length, "dispatch", "dispatches")}</text>
          </box>
        </box>
        <scrollbox flexGrow={1}>
          <text fg={theme.text.muted}>Routing: {v().report.routing.label} · raw per-turn token records</text>
          <box flexDirection="row" flexWrap="wrap" gap={2} width="100%">
            <UsageCard context={context} title="CLOUD" color={colors.cloud} stats={v().cloud} />
            <UsageCard context={context} title="LOCAL" color={colors.local} stats={v().local} />
          </box>
          <Show when={v().unknown.turns}>
            <UsageCard context={context} title="UNKNOWN PROVIDER" color={colors.unknown} stats={v().unknown} />
          </Show>
          <text fg={theme.text.muted}>Token categories are separate. Spans include tool / delegation waits and overlap across cloud and local; they are not billed compute time.</text>
          <box paddingTop={1} paddingBottom={1}>
            <text fg={theme.text.base}><b>NOW</b></text>
            <Show when={v().active.length} fallback={<text fg={theme.text.muted}>No model running</text>}>
              <For each={v().active}>{model => <text fg={colors[model.class] ?? colors.unknown}>● {model.agent} · {model.state === "awaiting-model" ? "Awaiting model record" : model.model}</text>}</For>
            </Show>
            <text fg={theme.text.muted}>Selected in UI: {v().selected?.model ?? "Not available"} · selection is separate from usage history</text>
          </box>
          <box border borderStyle="rounded" borderColor={v().review.conflict ? colors.unknown : verdictTone(context, v().review.verdict)} backgroundColor={theme.background.raised.base} paddingLeft={2} paddingRight={2} paddingTop={1} paddingBottom={1}>
            <text fg={theme.text.base}><b>REVIEW</b>  <span fg={verdictTone(context, v().review.verdict)}>{v().review.previous ? "Previous reported verdict: " : "Reported verdict: "}{v().review.verdict ?? "Not reported"}</span></text>
            <text fg={theme.text.base}>{v().review.kind}{v().review.model ? ` · ${v().review.model}` : ""}</text>
            <text fg={v().review.independentVerdict ? verdictTone(context, v().review.independentVerdict) : theme.text.muted} onMouseUp={openIndependent}>Independent review: {v().review.independent ? `${v().review.independentStatus} · ${v().review.independentModel}${v().review.independentVerdict ? ` · ${v().review.independentPrevious ? "previous " : ""}${v().review.independentVerdict}` : ""}` : "Not observed"}</text>
            <Show when={v().review.independentSourceMessageID}><text fg={theme.text.action.base} onMouseUp={openIndependent}>i Open independent review · message {v().review.independentSourceMessageID}</text></Show>
            <Show when={v().review.conflict}><text fg={colors.unknown}>Different coordinator and independent verdicts were reported. Press i to inspect the independent review.</text></Show>
            <text fg={theme.text.muted}>Explicit model statement, not an independent verification of correctness. Worker self-checks do not count as final review.</text>
            <Show when={v().review.sourceSessionID}><text fg={theme.text.action.base} onMouseUp={openReview}>v Open review session · message {v().review.sourceMessageID ?? "ID unavailable"}</text></Show>
          </box>
          <box paddingTop={1}>
            <text fg={theme.text.base}><b>MODELS USED</b>  <span fg={theme.text.muted}>Most recent first · actual message identities</span></text>
            <For each={v().history}>{entry => {
              const usage = () => v().report.breakdown.find(b => b.sessionID === entry.sessionID && b.agent === entry.agent && b.model === entry.model)
              return <box border={['left']} borderColor={colors[entry.class] ?? colors.unknown} paddingLeft={2} marginTop={1}>
                <text fg={colors[entry.class] ?? colors.unknown}><b>{entry.agent}</b> · {entry.model} · {entry.active ? "RUNNING" : "USED"}</text>
                <text fg={theme.text.muted}>{usage()?.turns ?? 0} turns · in {num(usage()?.tokens.input)} · out {num(usage()?.tokens.output)} · reason {num(usage()?.tokens.reasoning)} · cache R {num(usage()?.tokens.cacheRead)} / W {num(usage()?.tokens.cacheWrite)} · {duration(usage()?.elapsedSeconds ?? 0)} identity span</text>
                <text fg={theme.text.action.base} onMouseUp={() => context.ui.router.navigate({type: "session", sessionID: entry.sessionID})}>{entry.sessionID} · Cost: {entry.cost.label}</text>
              </box>
            }}</For>
          </box>
          <Show when={configured()}>
            <box paddingTop={1}>
              <text fg={theme.text.base}><b>CONFIGURED ROLES</b>  <span fg={theme.text.muted}>Current defaults; explicit UI choices can override them</span></text>
              <For each={roles()}>{agent => <text fg={theme.text.muted}>{agent.id} · {agent.model ? `${agent.model.providerID}/${agent.model.id}${agent.model.variant ? `#${agent.model.variant}` : ""}` : "Native / inherited model"}</text>}</For>
            </box>
          </Show>
          <box paddingTop={1}>
            <text fg={theme.text.base}><b>ATTENTION</b></text>
            <Show when={v().report.findings.length} fallback={<text fg={theme.text.muted}>No recorded usage warnings</text>}>
              <For each={v().report.findings.slice(0, 6)}>{finding => <text fg={finding.severity === "high" ? theme.text.feedback.error.base : finding.severity === "info" ? theme.text.muted : colors.unknown}>• {finding.title} · {finding.suggestion}</text>}</For>
            </Show>
          </box>
          <Show when={advanced()}>
            <box paddingTop={1}>
              <text fg={theme.text.muted}>Weighted heuristic: cloud {num(v().report.totals.cloud.weighted)} ({pct(v().report.shares.cloudWeighted)}) · local {num(v().report.totals.local.weighted)} ({pct(v().report.shares.localWeighted)})</text>
              <text fg={theme.text.muted}>Input + output + reasoning + cache write + 10% cache read. This is not billing or an efficiency score.</text>
            </box>
          </Show>
          <text fg={theme.text.muted}> </text>
        </scrollbox>
        <text fg={theme.text.muted} flexShrink={0}>esc back · r refresh · v review · i independent · c configured roles · w weighted detail · n newest</text>
      </>}
    </Show>
  </box>
}

function SidebarUsage(props: {context: Context; sessionID: string}) {
  const context = props.context, theme = context.theme, colors = tones(context)
  const view = useView(context, () => context.data.session.root(props.sessionID))
  return <Show when={view()}>{v => <box paddingLeft={1} paddingRight={1} gap={0}>
    <box flexDirection="row" justifyContent="space-between">
      <text fg={theme.text.base}><b>Usage</b></text>
      <text fg={v().status === "failed" ? theme.text.feedback.error.base : colors.cloud}>{statusText(v().status)} · {duration(v().elapsedSeconds)}</text>
    </box>
    <For each={(["cloud", "local", ...(v().unknown.turns ? ["unknown"] : [])] as const)}>{kind => <box marginTop={1}>
      <text fg={colors[kind]}><b>{kind.toUpperCase()}</b> · {v()[kind].turns} turns · {duration(v()[kind].elapsedSeconds)} span</text>
      <text fg={theme.text.base}>In {num(v()[kind].tokens.input)} · Out {num(v()[kind].tokens.output)}</text>
      <text fg={theme.text.muted}>Reason {num(v()[kind].tokens.reasoning)}</text>
      <text fg={theme.text.muted}>Cache R {num(v()[kind].tokens.cacheRead)} · W {num(v()[kind].tokens.cacheWrite)}</text>
      <text fg={v()[kind].cost.value === null ? colors.unknown : colors[kind]}>Cost: {kind === "local" && v()[kind].cost.kind === "local" ? "Not measured" : v()[kind].cost.label}</text>
    </box>}</For>
    <box marginTop={1}>
      <text fg={theme.text.base}><b>NOW</b></text>
      <Show when={v().active.length} fallback={<text fg={theme.text.muted}>No model running</text>}>
        <For each={v().active.slice(0, 3)}>{model => <text fg={colors[model.class] ?? colors.unknown}>● {model.agent} · {model.state === "awaiting-model" ? "Awaiting model record" : short(model.model)}</text>}</For>
      </Show>
      <text fg={theme.text.muted}>Next: {v().selected ? short(v().selected.model) : "Not available"}</text>
    </box>
    <box marginTop={1}>
      <text fg={theme.text.base}><b>USED</b></text>
      <For each={v().history.slice(0, 3)}>{entry => <box>
        <text fg={colors[entry.class] ?? colors.unknown}>{entry.agent}</text>
        <text fg={theme.text.muted}>{short(entry.model)}</text>
      </box>}</For>
      <Show when={v().history.length > 3}><text fg={theme.text.muted}>+{v().history.length - 3} more in /usage</text></Show>
    </box>
    <box marginTop={1}>
      <text fg={theme.text.base}><b>REVIEW</b> · <span fg={verdictTone(context, v().review.verdict)}>{v().review.previous ? "Previous " : ""}{v().review.verdict ?? "Not reported"}</span></text>
      <text fg={theme.text.muted}>{v().review.kind}</text>
      <text fg={theme.text.muted}>Independent: {v().review.independent ? v().review.independentVerdict ?? v().review.independentStatus : "Not observed"}</text>
    </box>
    <text fg={theme.text.action.base} onMouseUp={() => context.keymap.dispatch("agent-usage.open")}>/usage  details &amp; review source</text>
  </box>}</Show>
}
export default Plugin.define({
  id: "agent-usage",
  setup(context) {
    const navigation = createUsageNavigation(context)
    context.ui.router.register({
      name: "agent-usage",
      render: ({data}) => <UsagePage context={context} rootID={navigation.initialRoot(data)} onClose={navigation.close} />,
    })
    context.ui.slot({
      append: "sidebar.content",
      render: (props) => <SidebarUsage context={context} sessionID={props.sessionID} />,
    })
    context.ui.slot({
      append: "app",
      render() {
        context.keymap.layer(() => ({
          mode: "global",
          commands: [
            {
              id: "agent-usage.open",
              title: "Agent usage: tokens by agent, model and session",
              group: "System",
              slash: { name: "usage" },
              palette: true,
              run: navigation.open,
            },
          ],
        }))
        return null
      },
    })
    const onDone = (event: { data?: { sessionID?: string }; properties?: { sessionID?: string } }) => {
      const sessionID = event.data?.sessionID ?? event.properties?.sessionID
      if (!sessionID || context.data.session.root(sessionID) !== sessionID) return
      const tree = treeFrom(context.data.session.list(), (sid) => context.data.session.message.list(sid), sessionID)
      if (!tree) return
      const report = analyze(tree)
      context.ui.toast.show({ title: "Agent usage", message: summaryLine(report) + " Open /usage for the breakdown.", variant: "info", duration: 8000, sessionID })
    }
    const offs = (["session.execution.succeeded", "session.execution.failed", "session.execution.interrupted"] as const).map((type) =>
      context.data.on(type as never, onDone as never),
    )
    return () => offs.forEach((off) => off())
  },
})
