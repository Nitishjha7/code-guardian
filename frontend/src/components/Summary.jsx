import { CARD, band } from '../lib/ui'
import { relativeTime } from '../lib/history'

export function RiskDonut({ risk, size = 88 }) {
  const style = band(risk?.band)
  const complete = risk?.complete !== false
  const value = complete ? Math.max(0, Math.min(100, risk?.score ?? 0)) : 0

  const stroke = 7
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
          stroke="#1e293b"
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
            style={{ transition: 'stroke-dashoffset .5s ease' }}
          />
        )}
      </svg>
      <span className="absolute text-xl font-semibold tabular-nums text-slate-50">
        {complete ? value : '—'}
      </span>
    </div>
  )
}

export function LastReviewSummary({ result, onViewAll }) {
  if (!result) {
    return (
      <section className={`${CARD} px-4 py-3`}>
        <h2 className="text-xs font-medium uppercase tracking-wide text-slate-500">
          Last review
        </h2>
        <p className="mt-2 text-sm text-slate-500">None yet.</p>
      </section>
    )
  }

  const security = result.security_issues?.length || 0
  const performance = result.performance_issues?.length || 0
  const confirmed = (result.security_issues || []).filter((f) =>
    String(f.source || '').startsWith('llm+'),
  ).length
  const style = band(result.risk?.band)
  const seconds = secondsFrom(result.logs)
  const incomplete = result.risk?.complete === false

  return (
    <section className={CARD}>
      <div className="flex items-center border-b border-slate-800 px-4 py-2.5">
        <h2 className="text-xs font-medium uppercase tracking-wide text-slate-500">
          Last review
        </h2>
        <button
          onClick={onViewAll}
          className="ml-auto text-[11px] text-slate-500 hover:text-slate-300"
        >
          history
        </button>
      </div>

      <div className="flex items-center gap-4 px-4 py-3">
        <RiskDonut risk={result.risk} />
        <div className="min-w-0 flex-1 space-y-1 text-sm">
          <p className={`font-medium ${style.text}`}>
            {incomplete ? 'Score unavailable' : style.label}
          </p>
          <Row label="security" value={security} />
          <Row label="performance" value={performance} />
          {confirmed > 0 && (
            <Row label="confirmed" value={confirmed} tone="text-emerald-400" />
          )}
        </div>
      </div>

      <dl className="grid grid-cols-3 gap-px border-t border-slate-800 bg-slate-800 text-center">
        <Metric value={lineCount(result.diff)} label="patch" />
        <Metric value={lineCount(result.generated_tests)} label="tests" />
        <Metric value={seconds ? `${seconds}s` : '—'} label="took" />
      </dl>

      {incomplete && (
        <p className="border-t border-rose-900/40 bg-rose-500/5 px-4 py-2.5 text-[11px] text-rose-300">
          {result.risk.note}
        </p>
      )}
    </section>
  )
}

export function RecentActivity({ entries, onSeeAll }) {
  return (
    <section className={CARD}>
      <div className="flex items-center border-b border-slate-800 px-4 py-2.5">
        <h2 className="text-xs font-medium uppercase tracking-wide text-slate-500">
          Recent
        </h2>
        {entries.length > 0 && (
          <button
            onClick={onSeeAll}
            className="ml-auto text-[11px] text-slate-500 hover:text-slate-300"
          >
            all {entries.length}
          </button>
        )}
      </div>

      {entries.length === 0 ? (
        <p className="px-4 py-3 text-sm text-slate-500">
          Reviews run in this browser appear here.
        </p>
      ) : (
        <ul className="divide-y divide-slate-800/70">
          {entries.slice(0, 6).map((e) => {
            const style = band(e.band)
            return (
              <li key={e.id} className="flex items-baseline gap-2.5 px-4 py-2">
                <span className={`w-9 shrink-0 font-mono text-xs ${style.text}`}>
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

function Row({ label, value, tone = 'text-slate-300' }) {
  return (
    <p className="flex items-baseline gap-2 text-xs">
      <span className={`font-mono font-semibold tabular-nums ${tone}`}>{value}</span>
      <span className="text-slate-500">{label}</span>
    </p>
  )
}

function Metric({ value, label }) {
  return (
    <div className="bg-slate-900/40 px-2 py-2.5">
      <dd className="font-mono text-sm tabular-nums text-slate-200">{value}</dd>
      <dt className="text-[10px] text-slate-600">{label}</dt>
    </div>
  )
}

function lineCount(text) {
  return text ? text.split('\n').length : '—'
}

function secondsFrom(logs) {
  const line = (logs || []).find((l) => l.includes('Review finished in'))
  const match = line?.match(/([\d.]+)s/)
  return match ? Number(match[1]).toFixed(1) : null
}
