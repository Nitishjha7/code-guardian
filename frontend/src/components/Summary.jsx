import { Icon } from './Icons'
import { CARD, band } from '../lib/ui'
import { relativeTime } from '../lib/history'

export function RiskDonut({ risk, size = 112 }) {
  const style = band(risk?.band)
  const complete = risk?.complete !== false
  const value = complete ? Math.max(0, Math.min(100, risk?.score ?? 0)) : 0

  const stroke = 9
  const r = (size - stroke) / 2
  const circumference = 2 * Math.PI * r

  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="#1C2540"
          strokeWidth={stroke}
        />
        {complete && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={style.ring}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={circumference * (1 - value / 100)}
            style={{ transition: 'stroke-dashoffset .6s ease' }}
          />
        )}
      </svg>
      <span className="absolute flex flex-col items-center leading-none">
        <span className="text-2xl font-semibold tabular-nums text-white">
          {complete ? value : '—'}
        </span>
        <span className="mt-0.5 text-[10px] text-slate-500">/100</span>
      </span>
    </div>
  )
}

/**
 * The review's own summary: score, what each auditor found, and how the run
 * went. Every number here comes from the response — nothing is estimated.
 */
export function FileAnalysis({ result, filename, onViewAll }) {
  if (!result) {
    // Before the first run the analysis panel has nothing to show, so it
    // explains the pipeline instead of sitting empty.
    const steps = [
      ['Supervisor', 'reads the code and picks which auditors it needs'],
      ['Auditors', 'security and performance run only if routed to'],
      ['Patch', 'rewrites the file; difflib computes the diff'],
      ['Guardrails', 'scans the output for credentials before it leaves'],
    ]
    return (
      <section className={CARD}>
        <div className="flex items-center gap-2 border-b border-ink-700 px-4 py-3">
          <Icon.sparkle width={15} height={15} className="text-brand-400" />
          <h2 className="text-sm font-medium text-white">How a review runs</h2>
        </div>
        <ol className="px-4 py-3.5">
          {steps.map(([name, what], i) => (
            <li key={name} className="relative flex gap-3 pb-4 last:pb-0">
              {i < steps.length - 1 && (
                <span className="absolute left-[11px] top-6 h-full w-px bg-ink-700" />
              )}
              <span className="relative grid h-6 w-6 shrink-0 place-items-center rounded-full border border-ink-600 bg-ink-800 text-[10px] font-semibold text-slate-400">
                {i + 1}
              </span>
              <span className="min-w-0 flex-1 pt-0.5">
                <span className="block text-xs font-medium text-slate-300">{name}</span>
                <span className="mt-0.5 block text-[11px] leading-relaxed text-slate-500">
                  {what}
                </span>
              </span>
            </li>
          ))}
        </ol>
      </section>
    )
  }

  const security = result.security_issues?.length || 0
  const performance = result.performance_issues?.length || 0
  const confirmed = (result.security_issues || []).filter((f) =>
    String(f.source || '').startsWith('llm+'),
  ).length
  const style = band(result.risk?.band)
  const incomplete = result.risk?.complete === false
  const routed = result.routed_to || []
  const failed = result.failed_audits || []

  return (
    <section className={CARD}>
      <div className="flex items-center gap-2 border-b border-ink-700 px-4 py-3">
        <Icon.sparkle width={15} height={15} className="text-brand-400" />
        <h2 className="text-sm font-medium text-white">File analysis</h2>
        <button
          onClick={onViewAll}
          className="ml-auto text-[11px] text-slate-500 transition hover:text-slate-300"
        >
          history
        </button>
      </div>

      <div className="flex items-center gap-4 px-4 py-4">
        <RiskDonut risk={result.risk} />
        <div className="min-w-0 flex-1">
          <p className={`text-sm font-semibold ${style.text}`}>
            {incomplete ? 'Score unavailable' : style.label}
          </p>
          {filename && (
            <p className="mt-1 truncate font-mono text-[11px] text-slate-500">{filename}</p>
          )}
          <p className="mt-2 text-xs leading-relaxed text-slate-500">
            {incomplete
              ? result.risk?.note
              : routed.length === 0
                ? 'The supervisor routed around both auditors.'
                : `Ran ${routed.map((r) => r.replace('_audit', '')).join(' and ')}.`}
          </p>
        </div>
      </div>

      <dl className="grid grid-cols-3 gap-px border-t border-ink-700 bg-ink-700 text-center">
        <Metric value={security} label="Security" tone="text-rose-300" />
        <Metric value={performance} label="Performance" tone="text-amber-300" />
        <Metric
          value={confirmed}
          label="Confirmed"
          tone={confirmed ? 'text-emerald-300' : 'text-slate-400'}
        />
      </dl>

      {failed.length > 0 && (
        <p className="flex items-start gap-2 border-t border-rose-900/40 bg-rose-500/5 px-4 py-3 text-[11px] leading-relaxed text-rose-300">
          <Icon.alert width={13} height={13} className="mt-px shrink-0" />
          <span>{failed.join(', ')} did not run. Treat this review as incomplete.</span>
        </p>
      )}
    </section>
  )
}

/** The nodes the graph actually ran, newest first, with their timings. */
export function ReviewTimeline({ result }) {
  if (!result?.logs?.length) return null

  const steps = (result.logs || [])
    .filter((l) => !l.startsWith('Review started'))
    .map((line) => {
      const [head, ...rest] = line.split(':')
      return { head: head.trim(), detail: rest.join(':').trim() }
    })

  if (steps.length === 0) return null

  return (
    <section className={CARD}>
      <div className="flex items-center gap-2 border-b border-ink-700 px-4 py-3">
        <Icon.clock width={15} height={15} className="text-slate-500" />
        <h2 className="text-sm font-medium text-white">Review timeline</h2>
      </div>
      <ol className="space-y-0 px-4 py-3">
        {steps.map((s, i) => (
          <li key={i} className="relative flex gap-3 pb-3.5 last:pb-0">
            {i < steps.length - 1 && (
              <span className="absolute left-[7px] top-4 h-full w-px bg-ink-700" />
            )}
            <span className="relative mt-1 grid h-3.5 w-3.5 shrink-0 place-items-center rounded-full border-2 border-brand-500 bg-ink-850" />
            <span className="min-w-0 flex-1">
              <span className="block text-xs font-medium text-slate-300">{s.head}</span>
              {s.detail && (
                <span className="mt-0.5 block text-[11px] leading-relaxed text-slate-500">
                  {s.detail}
                </span>
              )}
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
}

export function RecentActivity({ entries, onSeeAll }) {
  return (
    <section className={CARD}>
      <div className="flex items-center gap-2 border-b border-ink-700 px-4 py-3">
        <Icon.chart width={15} height={15} className="text-slate-500" />
        <h2 className="text-sm font-medium text-white">Recent</h2>
        {entries.length > 0 && (
          <button
            onClick={onSeeAll}
            className="ml-auto text-[11px] text-slate-500 transition hover:text-slate-300"
          >
            all {entries.length}
          </button>
        )}
      </div>

      {entries.length === 0 ? (
        <p className="px-4 py-3.5 text-xs leading-relaxed text-slate-500">
          Reviews run in this browser appear here.
        </p>
      ) : (
        <ul className="divide-y divide-ink-700/70">
          {entries.slice(0, 6).map((e) => {
            const style = band(e.band)
            return (
              <li key={e.id} className="flex items-center gap-3 px-4 py-2.5">
                <span
                  className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg border text-[11px] font-semibold tabular-nums ${style.chip}`}
                >
                  {e.complete && e.score !== null ? e.score : '—'}
                </span>
                <span className="min-w-0 flex-1 truncate text-xs text-slate-400">
                  {e.label}
                </span>
                <span className="shrink-0 font-mono text-[10px] text-slate-600">
                  {relativeTime(e.at)}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

/* ------------------------------------------------------------------ bits -- */

function Metric({ value, label, tone = 'text-slate-200' }) {
  return (
    <div className="bg-ink-850 px-2 py-3">
      <dd className={`text-lg font-semibold tabular-nums ${tone}`}>{value}</dd>
      <dt className="mt-0.5 text-[10px] text-slate-500">{label}</dt>
    </div>
  )
}
