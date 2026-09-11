import { useState } from 'react'

import { Icon } from './Icons'
import { CARD } from '../lib/ui'

const TABS = [
  ['diff', 'Diff'],
  ['full', 'Full Code'],
  ['tests', 'Tests'],
  ['report', 'Markdown'],
  ['log', 'Agent Log'],
]

export default function PatchView({ result, original }) {
  const [tab, setTab] = useState('diff')
  const [copied, setCopied] = useState('')

  const tabs = TABS.filter(([id]) => id !== 'tests' || result.generated_tests)

  async function copy(text, what) {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(what)
      setTimeout(() => setCopied(''), 1600)
    } catch {
      // Clipboard blocked (insecure origin, or permission denied). The panels
      // are selectable, so this is a convenience, not the only way out.
      setCopied('blocked')
      setTimeout(() => setCopied(''), 1600)
    }
  }

  const payload =
    tab === 'full'
      ? result.fixed_code
      : tab === 'tests'
        ? result.generated_tests
        : tab === 'report'
          ? result.summary_report
          : tab === 'log'
            ? (result.logs || []).join('\n')
            : result.diff

  return (
    <section className={CARD}>
      <div className="flex flex-wrap items-center gap-3 border-b border-slate-800 px-5 py-4">
        <h2 className="text-base font-semibold text-slate-100">Generated Patch</h2>

        <div className="flex gap-1 rounded-lg border border-slate-800 bg-slate-950/60 p-1">
          {tabs.map(([id, label]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`rounded-md px-3 py-1.5 text-xs transition ${
                tab === id
                  ? 'bg-slate-800 text-slate-100'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <button
          onClick={() => copy(payload || '', tab)}
          disabled={!payload}
          className="ml-auto rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-1.5 text-xs text-slate-300 transition hover:bg-slate-800 disabled:opacity-40"
        >
          {copied === tab ? 'Copied' : copied === 'blocked' ? 'Blocked' : 'Copy'}
        </button>
      </div>

      <div className="p-5">
        {tab === 'diff' &&
          (result.diff ? (
            <SideBySide original={original} patched={result.fixed_code} diff={result.diff} />
          ) : (
            <Empty text="No patch generated — nothing needed fixing." />
          ))}

        {tab === 'full' &&
          (result.fixed_code ? (
            <Code text={result.fixed_code} />
          ) : (
            <Empty text="No patched code." />
          ))}

        {tab === 'tests' && (
          <>
            <p className="mb-3 rounded-lg border border-amber-600/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-300">
              <b>Generated, not executed.</b> Running LLM-authored tests safely needs a
              sandbox — read these before you trust them.
            </p>
            <Code text={result.generated_tests} />
          </>
        )}

        {tab === 'report' && <Code text={result.summary_report} wrap />}

        {tab === 'log' && (
          <ol className="space-y-1 rounded-lg border border-slate-800 bg-[#0d1117] p-4 font-mono text-xs">
            {(result.logs || []).map((line, i) => (
              <li key={i} className="flex gap-3">
                <span className="shrink-0 text-slate-600">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span
                  className={
                    /FAILED|failed/.test(line) ? 'text-rose-300' : 'text-slate-400'
                  }
                >
                  {line}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  )
}

function SideBySide({ original, patched, diff }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Pane
        title="Original"
        tone="border-rose-900/40 bg-rose-950/10"
        head="border-rose-900/40 text-rose-300"
        text={original}
        marker="-"
      />
      <Pane
        title="Patched"
        tone="border-emerald-900/40 bg-emerald-950/10"
        head="border-emerald-900/40 text-emerald-300"
        text={patched}
        marker="+"
      />

      <details className="lg:col-span-2">
        <summary className="cursor-pointer text-xs text-slate-500 hover:text-slate-300">
          Show unified diff
        </summary>
        <pre className="mt-3 overflow-x-auto rounded-lg border border-slate-800 bg-[#0d1117] p-4 text-xs leading-relaxed">
          {diff.split('\n').map((line, i) => (
            <div key={i} className={diffClass(line)}>
              {line || ' '}
            </div>
          ))}
        </pre>
      </details>
    </div>
  )
}

function Pane({ title, tone, head, text, marker }) {
  const lines = (text || '').split('\n')
  return (
    <div className={`overflow-hidden rounded-lg border ${tone}`}>
      <div className={`border-b px-3 py-2 text-xs font-medium ${head}`}>
        {marker} {title}
      </div>
      <pre className="max-h-80 overflow-auto p-3 text-xs leading-relaxed">
        {lines.map((line, i) => (
          <div key={i} className="flex gap-3">
            <span className="w-6 shrink-0 select-none text-right text-slate-700">
              {i + 1}
            </span>
            <span className="text-slate-300">{line || ' '}</span>
          </div>
        ))}
      </pre>
    </div>
  )
}

function Code({ text, wrap }) {
  return (
    <pre
      className={`max-h-[28rem] overflow-auto rounded-lg border border-slate-800 bg-[#0d1117] p-4 text-xs leading-relaxed text-slate-300 ${
        wrap ? 'whitespace-pre-wrap' : ''
      }`}
    >
      {text || ''}
    </pre>
  )
}

function Empty({ text }) {
  return (
    <p className="rounded-lg border border-dashed border-slate-800 px-4 py-10 text-center text-sm text-slate-500">
      <Icon.file className="mx-auto mb-2 text-slate-700" width={22} height={22} />
      {text}
    </p>
  )
}

function diffClass(line) {
  if (line.startsWith('+++') || line.startsWith('---')) return 'text-slate-600'
  if (line.startsWith('@@')) return 'text-cyan-400'
  if (line.startsWith('+')) return 'bg-emerald-500/10 text-emerald-300'
  if (line.startsWith('-')) return 'bg-rose-500/10 text-rose-300'
  return 'text-slate-500'
}
