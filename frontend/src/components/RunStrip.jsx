import { CARD, band } from '../lib/ui'

const STAGES = [
  { id: 'route', label: 'Route' },
  { id: 'security', label: 'Security' },
  { id: 'performance', label: 'Performance' },
  { id: 'patch', label: 'Patch' },
  { id: 'tests', label: 'Tests' },
  { id: 'guard', label: 'Guardrails' },
]

/**
 * What the last run actually did, stage by stage. This is the demo centrepiece:
 * on a CSS file both auditors read "skipped", on vulnerable Python they read
 * "ran" - the routing decision made visible instead of described.
 */
// Maps a graph node name (from the SSE stream) to the strip's own stage id.
// "tools" runs whichever auditor(s) the supervisor routed to, so one node can
// light up either or both of two stages — everything else is one-to-one.
const NODE_TO_STAGES = {
  supervisor: ['route'],
  tools: ['security', 'performance'],
  collect: ['route', 'security', 'performance'],
  patch: ['patch'],
  tests: ['tests'],
  guardrail: ['guard'],
}

export default function RunStrip({ result, loading, completedNodes }) {
  if (loading) return <Skeleton completedNodes={completedNodes} />
  if (!result) return null

  const routed = result.routed_to || []
  const failed = result.failed_audits || []
  const guard = result.guardrail_report || {}
  const risk = result.risk || {}
  const style = band(risk.band)

  const state = {
    route: routed.length
      ? { tone: 'ok', text: routed.length === 2 ? 'both' : routed[0].split('_')[0] }
      : { tone: 'skip', text: 'none needed' },
    security: stageOf('security_audit', routed, failed, result.security_issues),
    performance: stageOf('performance_audit', routed, failed, result.performance_issues),
    patch: result.diff
      ? { tone: 'ok', text: `${result.diff.split('\n').length} lines` }
      : { tone: 'skip', text: 'not needed' },
    tests: result.generated_tests
      ? { tone: 'ok', text: `${result.generated_tests.split('\n').length} lines` }
      : { tone: 'skip', text: 'not needed' },
    guard:
      guard.passed === false
        ? { tone: 'warn', text: `${guard.redactions || 0} redacted` }
        : { tone: 'ok', text: 'clean' },
  }

  return (
    <section className={`${CARD} flex flex-wrap items-stretch divide-x divide-slate-800`}>
      <div className="flex min-w-[170px] items-center gap-3 px-4 py-3">
        <span
          className={`grid h-11 w-11 shrink-0 place-items-center rounded-lg border text-base font-semibold tabular-nums ${style.chip}`}
        >
          {risk.complete === false ? '—' : (risk.score ?? 0)}
        </span>
        <span className="min-w-0">
          <span className={`block truncate text-sm font-medium ${style.text}`}>
            {risk.complete === false ? 'Unavailable' : style.label}
          </span>
          <span className="block text-[11px] text-slate-500">risk score</span>
        </span>
      </div>

      {STAGES.map(({ id, label }) => (
        <div key={id} className="flex min-w-[116px] flex-1 flex-col justify-center px-4 py-3">
          <span className="text-[10px] uppercase tracking-wide text-slate-600">
            {label}
          </span>
          <span className={`mt-0.5 text-sm ${TONE[state[id].tone]}`}>
            {state[id].text}
          </span>
        </div>
      ))}
    </section>
  )
}

const TONE = {
  ok: 'text-slate-200',
  skip: 'text-slate-600',
  warn: 'text-amber-300',
  fail: 'text-rose-300',
}

function stageOf(name, routed, failed, findings) {
  if (failed.includes(name)) return { tone: 'fail', text: 'failed' }
  if (!routed.includes(name)) return { tone: 'skip', text: 'skipped' }
  const n = findings?.length || 0
  return { tone: n ? 'ok' : 'skip', text: n ? `${n} found` : 'clean' }
}

/**
 * The skeleton doubles as the live progress view: once a node in the stream
 * has completed, its stage(s) lose the pulse and show the node's own label
 * instead of a placeholder bar. Stages the graph hasn't reached yet — and, on
 * a CSS-only run, ones it will never reach — stay pulsing, which is itself
 * informative: a stage still pulsing after `done` would mean this mapping is
 * out of sync with the graph, not that something hung.
 */
function Skeleton({ completedNodes }) {
  const reached = new Set(
    [...(completedNodes || [])].flatMap((node) => NODE_TO_STAGES[node] || []),
  )

  return (
    <section className={`${CARD} flex flex-wrap items-stretch divide-x divide-slate-800`}>
      {['risk', ...STAGES.map((s) => s.id)].map((id) => (
        <div key={id} className="min-w-[116px] flex-1 space-y-2 px-4 py-3.5">
          <div className="h-2 w-12 animate-pulse rounded bg-slate-800" />
          {reached.has(id) ? (
            <div className="text-sm text-slate-400">done</div>
          ) : (
            <div className="h-3 w-16 animate-pulse rounded bg-slate-800/70" />
          )}
        </div>
      ))}
    </section>
  )
}
