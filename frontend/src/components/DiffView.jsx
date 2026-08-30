function lineClass(line) {
  if (line.startsWith('+++') || line.startsWith('---')) return 'text-slate-500'
  if (line.startsWith('@@')) return 'text-cyan-400'
  if (line.startsWith('+')) return 'bg-emerald-500/10 text-emerald-300'
  if (line.startsWith('-')) return 'bg-red-500/10 text-red-300'
  return 'text-slate-400'
}

export default function DiffView({ diff }) {
  if (!diff) {
    return (
      <p className="rounded-lg border border-slate-700/70 bg-slate-900/60 px-4 py-6 text-center text-sm text-slate-500">
        No patch generated.
      </p>
    )
  }

  return (
    <pre className="overflow-x-auto rounded-lg border border-slate-700/70 bg-black/50 p-4 text-xs leading-relaxed">
      {diff.split('\n').map((line, i) => (
        <div key={i} className={lineClass(line)}>
          {line || ' '}
        </div>
      ))}
    </pre>
  )
}
