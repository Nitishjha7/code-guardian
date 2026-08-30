import { useState } from 'react'

const SEVERITY_STYLES = {
  Critical: 'bg-red-500/15 text-red-300 border-red-500/40',
  High: 'bg-orange-500/15 text-orange-300 border-orange-500/40',
  Medium: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
  Low: 'bg-sky-500/15 text-sky-300 border-sky-500/40',
}

export default function FindingCard({ finding }) {
  const [open, setOpen] = useState(finding.severity === 'Critical')
  const badge = SEVERITY_STYLES[finding.severity] || SEVERITY_STYLES.Medium
  const hasComplexity =
    finding.complexity_before && finding.complexity_before !== 'n/a'

  return (
    <div className="rounded-lg border border-slate-700/70 bg-slate-900/60">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <span
          className={`shrink-0 rounded border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${badge}`}
        >
          {finding.severity}
        </span>
        <span className="flex-1 text-sm font-medium text-slate-100">
          {finding.title}
        </span>
        <span className="text-slate-500">{open ? '−' : '+'}</span>
      </button>

      {open && (
        <div className="space-y-3 border-t border-slate-700/70 px-4 py-3 text-sm">
          {finding.line_hint && (
            <pre className="overflow-x-auto rounded bg-black/40 px-3 py-2 text-xs text-slate-300">
              {finding.line_hint}
            </pre>
          )}
          {finding.explanation && (
            <p className="text-slate-300">
              <span className="font-semibold text-slate-100">Why: </span>
              {finding.explanation}
            </p>
          )}
          {hasComplexity && (
            <p className="text-slate-300">
              <span className="font-semibold text-slate-100">Complexity: </span>
              <code className="text-amber-300">{finding.complexity_before}</code>
              {' → '}
              <code className="text-emerald-300">{finding.complexity_after}</code>
            </p>
          )}
          {finding.recommendation && (
            <p className="text-slate-300">
              <span className="font-semibold text-slate-100">Fix: </span>
              {finding.recommendation}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
