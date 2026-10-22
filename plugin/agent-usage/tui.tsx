// OpenCode 2.1.2 TUI plugin: live agents -> models -> session instances with token usage.
// Opens with /usage (or the command palette), adds a compact block to the session sidebar, and shows a routing
// toast when a root session finishes. Reads only the TUI's own session/message data; no model requests.
// Native discovery/rendering smoke: OPENCODE_PLUGIN_TESTS=1 node --test test/plugin-runtime.test.js.
// Natural delivery/toast smoke: OPENCODE_COMPLETION_TESTS=1 node --test test/plugin-completion.test.js (local inference).
import {Plugin} from "@opencode/plugin/tui"
import {createEffect, createMemo, createSignal, For, Show} from "solid-js"
import {analyze, hierarchy, num, pct, summaryLine, treeFrom} from "../../src/usage-analysis.js"
import {createUsageNavigation, latestRoot} from "./navigation.js"

type Context = Plugin.Context
type Report = ReturnType<typeof analyze>

function familyOf(context: Context, rootID: string) {
  const ids = new Set<string>([rootID, ...(context.data.session.family(rootID) ?? [])])
  for (const s of context.data.session.list()) if (context.data.session.root(s.id) === rootID) ids.add(s.id)
  return [...ids]
}

/** Live report for a root session. Reading list()/message.list() inside the memo keeps it reactive. */
function useReport(context: Context, rootID: () => string | undefined) {
  const synced = new Set<string>()
  createEffect(() => {
    const id = rootID()
    if (!id) return
    for (const sid of familyOf(context, id)) {
      if (synced.has(sid)) continue
      synced.add(sid)
      void context.data.session.message.sync(sid).catch(() => synced.delete(sid))
    }
  })
  return createMemo<Report | undefined>(() => {
    const id = rootID()
    if (!id) return undefined
    const sessions = context.data.session.list()
    familyOf(context, id) // subscribe to membership changes
    const tree = treeFrom(sessions, (sid) => context.data.session.message.list(sid), id)
    return tree ? analyze(tree) : undefined
  })
}

const short = (model: string) => model.replace(/^[^/]+\//, "")

function UsagePage(props: { context: Context; rootID: string | undefined; onClose: () => void }) {
  const context = props.context
  const theme = context.theme
  const [rootID, setRootID] = createSignal(props.rootID)
  const report = useReport(context, rootID)
  const tree = createMemo(() => (report() ? hierarchy(report()!) : []))
  const [refresh, setRefresh] = createSignal(0)

  context.keymap.layer(() => ({
    commands: [
      { bind: "escape", title: "back", run: props.onClose },
      {
        bind: "r",
        title: "resync",
        run: () => {
          const id = rootID()
          if (!id) return
          for (const sid of familyOf(context, id)) {
            context.data.session.message.invalidate(sid)
            void context.data.session.message.sync(sid)
          }
          setRefresh(refresh() + 1)
        },
      },
      {
        bind: "n",
        title: "newest session",
        run: () => setRootID(latestRoot(context)),
      },
    ],
  }))

  return (
    <box width="100%" height="100%" backgroundColor={theme.background.base} paddingLeft={2} paddingRight={2} paddingTop={1}>
      <Show when={report()} fallback={<text fg={theme.text.muted}>No session data yet. Start a session, then open /usage.</text>}>
        {(r) => (
          <scrollbox flexGrow={1}>
            <box flexDirection="row" justifyContent="space-between">
              <text fg={theme.text.base}>
                <b>Agent usage</b> {r().root.title || r().root.id}
              </text>
              <text fg={theme.text.muted}>{r().root.id}</text>
            </box>
            <text fg={theme.text.base}>
              Routing: {r().routing.label}
            </text>
            <text fg={theme.text.muted}>
              cloud {num(r().totals.cloud.weighted)} ({pct(r().shares.cloudWeighted)}) · local {num(r().totals.local.weighted)} ({pct(r().shares.localWeighted)}) weighted
              · unknown {num(r().totals.unknown.weighted)} ({pct(r().shares.unknownWeighted)})
              · {r().totals.all.turns} turns · {r().sessions.length} sessions · {r().dispatches.length} dispatches
            </text>
            <text fg={theme.text.muted}> </text>
            <For each={tree()}>
              {(agent) => (
                <box>
                  <text fg={theme.text.base}>
                    <b>{agent.agent}</b> [{agent.class}] {num(agent.weighted)} weighted · {agent.turns} turns · {agent.sessions} session(s)
                    {agent.cost === null ? "" : ` · $${agent.cost.toFixed(4)}`}
                  </text>
                  <For each={agent.models}>
                    {(model) => (
                      <box paddingLeft={2}>
                        <text fg={theme.text.muted}>
                          {model.model} · {num(model.weighted)} weighted
                        </text>
                        <For each={model.instances}>
                          {(instance) => (
                            <box paddingLeft={2} flexDirection="row" gap={1}>
                              <text fg={context.data.session.status(instance.id) === "running" ? theme.text.base : theme.text.muted}>
                                {context.data.session.status(instance.id) === "running" ? "▶" : "·"}
                              </text>
                              <text fg={theme.text.muted}>
                                {instance.title || instance.id} · {instance.turns} turns · in {num(instance.tokens.input)} out {num(instance.tokens.output)} reason{" "}
                                {num(instance.tokens.reasoning)} cache-rd {num(instance.tokens.cacheRead)} cache-wr {num(instance.tokens.cacheWrite)}
                                {instance.errors ? ` · ${instance.errors} error(s)` : ""}
                              </text>
                            </box>
                          )}
                        </For>
                      </box>
                    )}
                  </For>
                </box>
              )}
            </For>
            <text fg={theme.text.muted}> </text>
            <text fg={theme.text.base}>
              <b>Findings</b>
            </text>
            <Show when={r().findings.length} fallback={<text fg={theme.text.muted}>none</text>}>
              <For each={r().findings.slice(0, 6)}>
                {(f) => (
                  <box paddingLeft={2}>
                    <text fg={f.severity === "high" ? theme.text.feedback.error.base : theme.text.base}>
                      [{f.severity}] {f.title}
                    </text>
                    <text fg={theme.text.muted}>{f.suggestion}</text>
                  </box>
                )}
              </For>
            </Show>
            <text fg={theme.text.muted}> </text>
            <text fg={theme.text.muted}>esc back · r resync · n newest root · full report: opencode-agent-setup usage --session {r().root.id}</text>
          </scrollbox>
        )}
      </Show>
    </box>
  )
}

function SidebarUsage(props: { context: Context; sessionID: string }) {
  const context = props.context
  const theme = context.theme
  const rootID = () => context.data.session.root(props.sessionID)
  const report = useReport(context, rootID)
  const tree = createMemo(() => (report() ? hierarchy(report()!) : []))
  return (
    <Show when={report()}>
      {(r) => (
        <box paddingLeft={1} paddingRight={1} gap={0}>
          <text fg={theme.text.base}>
            <b>Usage</b> {r().routing.label}
          </text>
          <text fg={theme.text.muted}>
            Weighted: cloud {pct(r().shares.cloudWeighted)} · local {pct(r().shares.localWeighted)}
          </text>
          <For each={tree().slice(0, 6)}>
            {(agent) => (
              <box>
                <text fg={theme.text.base}>
                  {agent.agent} · {num(agent.weighted)} weighted
                  {agent.models[0]?.instances.some((i) => context.data.session.status(i.id) === "running") ? " ▶" : ""}
                </text>
                <text fg={theme.text.muted}>{short(agent.models[0]?.model ?? "")}</text>
              </box>
            )}
          </For>
          <text fg={theme.text.muted} onMouseUp={() => context.keymap.dispatch("agent-usage.open")}>
            /usage for details
          </text>
        </box>
      )}
    </Show>
  )
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
