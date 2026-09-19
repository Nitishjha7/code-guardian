import { useState } from 'react'

import { Icon } from './Icons'
import { CARD, SEVERITY } from '../lib/ui'

const ORDER = { Critical: 0, High: 1, Medium: 2, Low: 3 }

export default function AgentFindings({ result, onOpenFinding }) {
  const [filter, setFilter] = useState('all')

  const security = (result.security_issues || []).map((f) => ({ ...f, kind: 'security' }))
  const performance = (result.performance_issues || []).map((f) => ({
    ...f,
    kind: 'performance',
  }))
  const total = security.length + performance.length

  const failed = result.failed_audits || []
  const routed = result.routed_to || []

  const shown = (
    filter === 'security' ? security : filter === 'performance' ? performance : [...security, ...performance]
  ).sort((a, b) => (ORDER[a.severity] ?? 2) - (ORDER[b.severity] ?? 2))

  return (
    <section className={CARD}>
      <div className="flex flex-wrap items-center gap-3 border-b border-ink-700 px-4 py-3">
        <h2 className="text-sm font-medium text-white">Findings</h2>

        <div className="ml-auto flex gap-1 rounded-lg border border-ink-700 bg-ink-900 p-1">
          {[
            ['all', 'All', total],
            ['security', 'Security', security.length],
            ['performance', 'Performance', performance.length],
          ].map(([id, label, count]) => (
            <button
              key={id}
              onClick={() => setFilter(id)}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs transition ${
                filter === id
                  ? 'bg-brand-600 font-medium text-white'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {label}
              <span
                className={`rounded px-1 text-[10px] tabular-nums ${
                  filter === id ? 'bg-white/20' : 'bg-ink-700'
                }`}
              >
                {count}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* One row per auditor, so "did not run" and "found nothing" stay
          distinguishable even when the list below is empty. */}
      <div className="grid gap-px border-b border-ink-700 bg-ink-700 sm:grid-cols-2">
        <AuditorStatus
          icon={Icon.shield}
          tint="text-rose-300 border-rose-500/30 bg-rose-500/10"
          name="Security"
          count={security.length}
          ran={routed.includes('security_audit')}
          failed={failed.includes('security_audit')}
        />
        <AuditorStatus
          icon={Icon.gauge}
          tint="text-amber-300 border-amber-500/30 bg-amber-500/10"
          name="Performance"
          count={performance.length}
          ran={routed.includes('performance_audit')}
          failed={failed.includes('performance_audit')}
        />
      </div>
      {shown.length === 0 ? (
        <div className="px-4 py-8 text-center">
          {/* A failed audit must never render as a green tick: the list is
              empty because nothing looked, not because nothing was found. */}
          <span
            className={`mx-auto grid h-12 w-12 place-items-center rounded-full border ${
              failed.length
                ? 'border-rose-600/30 bg-rose-500/10 text-rose-300'
                : 'border-emerald-600/30 bg-emerald-500/10 text-emerald-300'
            }`}
          >
            {failed.length ? (
              <Icon.alert width={20} height={20} />
            ) : (
              <Icon.check width={20} height={20} />
            )}
          </span>
          <p className="mt-3 text-sm font-medium text-slate-200">
            {failed.length
              ? 'This review is incomplete'
              : routed.length === 0
                ? 'No audit was needed'
                : 'No issues found'}
          </p>
          <p className="mx-auto mt-1 max-w-[42ch] text-xs leading-relaxed text-slate-500">
            {failed.length
              ? `${failed.join(', ')} did not run, so this code was not checked. Do not read the empty list as a pass.`
              : routed.length === 0
                ? 'The supervisor read the submission and routed around both auditors.'
                : 'Every auditor that ran came back clean.'}
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-ink-700/60">
          {shown.map((f, i) => (
            <li key={i}>
              <button
                onClick={() => onOpenFinding?.(f)}
                className="flex w-full items-start gap-3 px-4 py-3 text-left transition hover:bg-ink-800/60"
              >
                <span
                  className={`mt-0.5 shrink-0 rounded-md border px-2 py-0.5 text-[10px] font-medium ${
                    SEVERITY[f.severity] || SEVERITY.Medium
                  }`}
                >
                  {f.severity}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate text-sm text-slate-200">{f.title}</span>
                    {String(f.source || '').startsWith('llm+') && (
                      <span
                        title={`Confirmed independently by ${f.source.slice(4)}`}
                        className="shrink-0 rounded border border-emerald-600/40 bg-emerald-500/10 px-1.5 text-[9px] text-emerald-300"
                      >
                        ✓ confirmed
                      </span>
                    )}
                  </span>
                  {f.explanation && (
                    <span className="mt-0.5 block truncate text-xs text-slate-500">
                      {f.explanation}
                    </span>
                  )}
                </span>
                {f.line_hint && (
                  <code className="mt-0.5 hidden shrink-0 rounded bg-ink-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-500 sm:block">
                    {String(f.line_hint).slice(0, 18)}
                  </code>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function AuditorStatus({ icon: Ico, tint, name, count, ran, failed }) {
  const state = failed
    ? { text: 'failed — code not checked', tone: 'text-rose-300' }
    : !ran
      ? { text: 'routed around', tone: 'text-slate-500' }
      : { text: `${count} finding${count === 1 ? '' : 's'}`, tone: 'text-slate-400' }

  return (
    <div className="flex items-center gap-3 bg-ink-850 px-4 py-3">
      <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg border ${tint}`}>
        <Ico width={16} height={16} />
      </span>
      <span className="min-w-0">
        <span className="block text-xs font-medium text-slate-200">{name} Agent</span>
        <span className={`block text-[11px] ${state.tone}`}>{state.text}</span>
      </span>
    </div>
  )
}
