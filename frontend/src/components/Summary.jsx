import { Icon } from './Icons'
import { CARD, band } from '../lib/ui'
import { relativeTime } from '../lib/history'

export function RiskDonut({ risk, size = 110 }) {
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
            style={{ transition: 'stroke-dashoffset .6s ease' }}
          />
        )}
      </svg>
      <div className="absolute text-center">
        <div className="text-2xl font-semibold tabular-nums text-slate-50">
          {complete ? value : '—'}
        </div>
        <div className="text-[10px] uppercase tracking-wide text-slate-500">
          Risk Score
        </div>
      </div>
    </div>
  )
}

export function LastReviewSummary({ result, onViewAll }) {
  if (!result) {
    return (
      <section className={CARD}>
        <Header title="Last Review Summary" />
        <p className="px-5 pb-6 pt-2 text-sm text-slate-500">
          No review yet. Paste code and hit <b className="text-slate-400">Run AI Review</b>.
        </p>
      </section>
    )
  }

  const security = result.security_issues?.length || 0
  const performance = result.performance_issues?.length || 0
  const style = band(result.risk?.band)
  const seconds = secondsFrom(result.logs)
  const testLines = result.generated_tests
    ? result.generated_tests.split('\n').length
    : 0
  const patchLines = result.diff ? result.diff.split('\n').length : 0

  return (
    <section className={CARD}>
      <Header title="Last Review Summary" action="View All" onAction={onViewAll} />

      <div className="flex items-center gap-5 px-5 pb-4">
        <div className="text-center">
          <RiskDonut risk={result.risk} />
          <span
            className={`mt-2 inline-block rounded-md border px-2 py-0.5 text-[11px] ${style.chip}`}
          >
            {result.risk?.complete === false ? 'Unavailable' : style.label}
          </span>
        </div>

        <div className="flex-1 space-y-2.5">
          <p className="text-xs text-slate-500">Findings</p>
          <Stat
            icon={<Icon.shield width={14} height={14} />}
            tone="text-rose-300"
            value={security}
            label="Security"
          />
          <Stat
            icon={<Icon.alert width={14} height={14} />}
            tone="text-amber-300"
            value={performance}
            label="Performance"
          />
          <Stat
            icon={<Icon.check width={14} height={14} />}
            tone="text-sky-300"
            value={security + performance}
            label="Total Issues"
          />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 border-t border-slate-800 px-5 py-4 text-center">
        <Metric value={patchLines || '—'} label="Lines of Fix" />
        <Metric value={testLines || '—'} label="Test Lines" />
        <Metric value={seconds ? `~${seconds}s` : '—'} label="Processing Time" />
      </div>

      {result.risk?.complete === false && (
        <p className="border-t border-rose-900/40 bg-rose-500/5 px-5 py-3 text-[11px] text-rose-300">
          {result.risk.note}
        </p>
      )}
    </section>
  )
}

export function SystemStatus({ backend, onViewGraph }) {
  const online = backend?.status === 'ok'
  const keyReady = backend?.groq_key_configured

  const tone = !online
    ? 'border-rose-700/50 bg-rose-950/30'
    : keyReady
      ? 'border-emerald-700/40 bg-emerald-950/20'
      : 'border-amber-700/40 bg-amber-950/20'

  return (
    <section className={`rounded-xl border ${tone} p-4`}>
      <div className="flex items-center gap-3">
        <span
          className={`grid h-9 w-9 place-items-center rounded-full border ${
            online && keyReady
              ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300'
              : 'border-amber-500/40 bg-amber-500/15 text-amber-300'
          }`}
        >
          {online && keyReady ? (
            <Icon.check width={17} height={17} />
          ) : (
            <Icon.alert width={17} height={17} />
          )}
        </span>

        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-slate-100">
            {!online
              ? 'Backend unreachable'
              : keyReady
                ? 'System Online'
                : 'No API key configured'}
          </p>
          <p className="truncate text-[11px] text-slate-500">
            {online ? backend.model : 'Is the backend container running?'}
          </p>
        </div>

        {online && (
          <button
            onClick={onViewGraph}
            className="flex shrink-0 items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
          >
            View Graph
            <Icon.arrow width={13} height={13} />
          </button>
        )}
      </div>
    </section>
  )
}

export function RecentActivity({ entries, onSeeAll }) {
  return (
    <section className={CARD}>
      <Header title="Recent Activity" action="See All" onAction={onSeeAll} />

      {entries.length === 0 ? (
        <p className="px-5 pb-6 pt-2 text-sm text-slate-500">
          Nothing yet. Reviews you run in this browser show up here.
        </p>
      ) : (
        <ul className="space-y-1 px-3 pb-4">
          {entries.slice(0, 5).map((e) => {
            const style = band(e.band)
            return (
              <li
                key={e.id}
                className="flex items-start gap-3 rounded-lg px-2 py-2 hover:bg-slate-800/40"
              >
                <span
                  className={`mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg border ${style.chip}`}
                >
                  {e.failed?.length ? (
                    <Icon.alert width={14} height={14} />
                  ) : (
                    <Icon.check width={14} height={14} />
                  )}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-slate-200">
                    {e.kind === 'pr' ? 'PR analyzed' : 'Review completed'}
                    {e.score !== null && (
                      <span className={`ml-2 text-xs ${style.text}`}>{e.score}/100</span>
                    )}
                  </p>
                  <p className="truncate text-[11px] text-slate-500">{e.label}</p>
                </div>
                <span className="shrink-0 text-[11px] text-slate-600">
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

function Header({ title, action, onAction }) {
  return (
    <div className="flex items-center px-5 py-4">
      <h2 className="text-base font-semibold text-slate-100">{title}</h2>
      {action && (
        <button
          onClick={onAction}
          className="ml-auto text-xs text-indigo-400 hover:text-indigo-300"
        >
          {action}
        </button>
      )}
    </div>
  )
}

function Stat({ icon, tone, value, label }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className={tone}>{icon}</span>
      <span className="font-semibold tabular-nums text-slate-100">{value}</span>
      <span className="text-slate-400">{label}</span>
    </div>
  )
}

function Metric({ value, label }) {
  return (
    <div>
      <div className="text-lg font-semibold tabular-nums text-slate-100">{value}</div>
      <div className="text-[10px] text-slate-500">{label}</div>
    </div>
  )
}

function secondsFrom(logs) {
  const line = (logs || []).find((l) => l.includes('Review finished in'))
  const match = line?.match(/([\d.]+)s/)
  return match ? Number(match[1]).toFixed(1) : null
}
