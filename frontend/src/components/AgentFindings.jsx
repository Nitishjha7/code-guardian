import { useState } from 'react'

import { Icon } from './Icons'
import { CARD, SEVERITY } from '../lib/ui'

export default function AgentFindings({ result, onOpenFinding }) {
  const [filter, setFilter] = useState('all')

  const security = result.security_issues || []
  const performance = result.performance_issues || []
  const total = security.length + performance.length

  const failed = result.failed_audits || []
  const routed = result.routed_to || []

  return (
    <section className={CARD}>
      <div className="flex flex-wrap items-center gap-3 border-b border-slate-800 px-5 py-4">
        <h2 className="text-base font-semibold text-slate-100">Agent Findings</h2>

        <div className="ml-auto flex gap-1 rounded-lg border border-slate-800 bg-slate-950/60 p-1">
          {[
            ['all', `All (${total})`],
            ['security', `Security (${security.length})`],
            ['performance', `Performance (${performance.length})`],
          ].map(([id, label]) => (
            <button
              key={id}
              onClick={() => setFilter(id)}
              className={`rounded-md px-3 py-1.5 text-xs transition ${
                filter === id
                  ? 'bg-slate-800 text-slate-100'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 p-5 lg:grid-cols-3">
        {filter !== 'performance' && (
          <AgentCard
            icon={<Icon.shield width={18} height={18} />}
            tint="border-rose-500/30 bg-rose-500/10 text-rose-300"
            name="Security Agent"
            findings={security}
            ran={routed.includes('security_audit')}
            failed={failed.includes('security_audit')}
            onOpenFinding={onOpenFinding}
          />
        )}

        {filter !== 'security' && (
          <AgentCard
            icon={<Icon.gauge width={18} height={18} />}
            tint="border-amber-500/30 bg-amber-500/10 text-amber-300"
            name="Performance Agent"
            findings={performance}
            ran={routed.includes('performance_audit')}
            failed={failed.includes('performance_audit')}
            onOpenFinding={onOpenFinding}
          />
        )}

        {filter === 'all' && <PatchCard result={result} />}
      </div>
    </section>
  )
}

function AgentCard({ icon, tint, name, findings, ran, failed, onOpenFinding }) {
  const badge = failed
    ? { text: 'failed', cls: 'border-rose-500/40 bg-rose-500/10 text-rose-300' }
    : !ran
      ? { text: 'not run', cls: 'border-slate-700 bg-slate-800 text-slate-400' }
      : {
          text: `${findings.length} finding${findings.length === 1 ? '' : 's'}`,
          cls: 'border-slate-700 bg-slate-800 text-slate-300',
        }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
      <div className="flex items-center gap-3">
        <span className={`grid h-9 w-9 place-items-center rounded-lg border ${tint}`}>
          {icon}
        </span>
        <h3 className="text-sm font-medium text-slate-200">{name}</h3>
        <span className={`ml-auto rounded-md border px-2 py-0.5 text-[11px] ${badge.cls}`}>
          {badge.text}
        </span>
      </div>

      <div className="mt-4 space-y-2">
        {failed ? (
          <p className="rounded-md border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-xs text-rose-300">
            This audit failed to run. The code was <b>not</b> checked.
          </p>
        ) : !ran ? (
          <p className="rounded-md border border-dashed border-slate-800 px-3 py-2 text-xs text-slate-500">
            The supervisor routed around this auditor.
          </p>
        ) : findings.length === 0 ? (
          <p className="rounded-md border border-emerald-600/25 bg-emerald-500/5 px-3 py-2 text-xs text-emerald-300">
            No issues found.
          </p>
        ) : (
          <>
            {findings.slice(0, 3).map((f, i) => (
              <button
                key={i}
                onClick={() => onOpenFinding?.(f)}
                className="flex w-full items-center gap-2 rounded-md px-1 py-1 text-left hover:bg-slate-800/50"
              >
                <span
                  className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-medium ${
                    SEVERITY[f.severity] || SEVERITY.Medium
                  }`}
                >
                  {f.severity}
                </span>
                <span className="min-w-0 flex-1 truncate text-xs text-slate-300">
                  {f.title}
                </span>
                {String(f.source || '').startsWith('llm+') && (
                  <span
                    title={`Confirmed independently by ${f.source.slice(4)}`}
                    className="shrink-0 rounded border border-emerald-600/40 bg-emerald-500/10 px-1 text-[9px] text-emerald-300"
                  >
                    ✓
                  </span>
                )}
              </button>
            ))}
            {findings.length > 3 && (
              <p className="pt-1 text-[11px] text-slate-500">
                + {findings.length - 3} more finding
                {findings.length - 3 === 1 ? '' : 's'}
              </p>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function PatchCard({ result }) {
  const diff = result.diff || ''
  const tests = result.generated_tests || ''
  const added = diff.split('\n').filter((l) => l.startsWith('+') && !l.startsWith('+++'))
  const removed = diff
    .split('\n')
    .filter((l) => l.startsWith('-') && !l.startsWith('---'))

  const guard = result.guardrail_report || {}

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
      <div className="flex items-center gap-3">
        <span className="grid h-9 w-9 place-items-center rounded-lg border border-sky-500/30 bg-sky-500/10 text-sky-300">
          <Icon.wrench width={18} height={18} />
        </span>
        <h3 className="text-sm font-medium text-slate-200">Patch Generator</h3>
        <span className="ml-auto rounded-md border border-slate-700 bg-slate-800 px-2 py-0.5 text-[11px] text-slate-300">
          {diff ? '1 patch' : 'no patch'}
        </span>
      </div>

      <div className="mt-4 space-y-2 text-xs">
        {diff ? (
          <>
            <Line ok text={`${added.length} lines added, ${removed.length} removed`} />
            {tests && (
              <Line ok text={`${tests.split('\n').length} lines of regression tests`} />
            )}
            <Line
              ok={guard.passed !== false}
              text={
                guard.passed === false
                  ? `Guardrails: ${guard.redactions || 0} redaction(s), ${
                      guard.tone_flags?.length || 0
                    } tone flag(s)`
                  : 'Guardrails passed — no secrets in output'
              }
            />
            <Line ok text="Diff computed with difflib, not the model" />
          </>
        ) : (
          <p className="rounded-md border border-dashed border-slate-800 px-3 py-2 text-slate-500">
            Nothing to fix, so no patch was generated.
          </p>
        )}
      </div>
    </div>
  )
}

function Line({ ok, text }) {
  return (
    <div className="flex items-start gap-2">
      <span className={ok ? 'mt-0.5 text-emerald-400' : 'mt-0.5 text-amber-400'}>
        {ok ? <Icon.check width={13} height={13} /> : <Icon.alert width={13} height={13} />}
      </span>
      <span className="text-slate-300">{text}</span>
    </div>
  )
}
