import { useEffect, useState } from 'react'
import Editor from '@monaco-editor/react'

import { health, review } from './api'
import { SAMPLES } from './samples'
import FindingCard from './components/FindingCard'
import DiffView from './components/DiffView'

const LANGUAGES = ['python', 'javascript', 'typescript', 'java', 'go', 'sql', 'css']

export default function App() {
  const [code, setCode] = useState(SAMPLES[0].code)
  const [language, setLanguage] = useState(SAMPLES[0].language)
  const [forceFullAudit, setForceFullAudit] = useState(false)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('findings')
  const [backend, setBackend] = useState(null)

  useEffect(() => {
    health().then(setBackend).catch(() => setBackend({ status: 'unreachable' }))
  }, [])

  async function runReview() {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await review({ sourceCode: code, language, forceFullAudit })
      setResult(data)
      setTab('findings')
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function loadSample(id) {
    const sample = SAMPLES.find((s) => s.id === id)
    if (!sample) return
    setCode(sample.code)
    setLanguage(sample.language)
    setResult(null)
    setError(null)
  }

  const total =
    (result?.security_issues.length || 0) + (result?.performance_issues.length || 0)

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      <header className="border-b border-slate-800 px-6 py-4">
        <div className="mx-auto flex max-w-[1600px] items-center gap-4">
          <h1 className="text-lg font-semibold text-slate-50">Code Guardian</h1>
          <span className="text-xs text-slate-500">
            Multi-agent autonomous code reviewer
          </span>
          <span className="ml-auto text-xs text-slate-500">
            {backend?.status === 'ok' ? (
              <>
                <span className="text-emerald-400">●</span> {backend.model}
                {!backend.groq_key_configured && (
                  <span className="ml-2 text-amber-400">no API key configured</span>
                )}
              </>
            ) : backend ? (
              <span className="text-red-400">● backend unreachable</span>
            ) : null}
          </span>
        </div>
      </header>

      <main className="mx-auto grid max-w-[1600px] gap-6 p-6 lg:grid-cols-2">
        {/* ------------------------------- input ------------------------------ */}
        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="rounded border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm"
            >
              {LANGUAGES.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>

            <select
              onChange={(e) => loadSample(e.target.value)}
              defaultValue=""
              className="rounded border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm"
            >
              <option value="" disabled>
                Load a sample…
              </option>
              {SAMPLES.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>

            <label
              className="flex items-center gap-2 text-xs text-slate-400"
              title="Bypass the supervisor's routing and run every auditor. Use on high-stakes paths where a false negative is unacceptable."
            >
              <input
                type="checkbox"
                checked={forceFullAudit}
                onChange={(e) => setForceFullAudit(e.target.checked)}
                className="accent-emerald-500"
              />
              Force full audit
            </label>

            <button
              onClick={runReview}
              disabled={loading || !code.trim()}
              className="ml-auto rounded bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40"
            >
              {loading ? 'Reviewing…' : 'Review'}
            </button>
          </div>

          <div className="overflow-hidden rounded-lg border border-slate-800">
            <Editor
              height="70vh"
              theme="vs-dark"
              language={language}
              value={code}
              onChange={(v) => setCode(v ?? '')}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                scrollBeyondLastLine: false,
                automaticLayout: true,
              }}
            />
          </div>
        </section>

        {/* ------------------------------ results ----------------------------- */}
        <section className="flex flex-col gap-3">
          {error && (
            <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {error}
            </div>
          )}

          {loading && (
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-8 text-center text-sm text-slate-400">
              Supervisor is routing the submission…
            </div>
          )}

          {!result && !loading && !error && (
            <div className="rounded-lg border border-dashed border-slate-800 px-4 py-16 text-center text-sm text-slate-500">
              Paste code and hit Review.
            </div>
          )}

          {result && (
            <>
              {result.failed_audits.length > 0 && (
                <div className="rounded-lg border border-red-500/50 bg-red-500/10 px-4 py-3 text-sm text-red-200">
                  <b>This review is incomplete.</b>{' '}
                  {result.failed_audits
                    .map((a) => a.replace('_', ' '))
                    .join(', ')}{' '}
                  failed to run — the sections below are not a clean bill of health.
                  <ul className="mt-2 space-y-1 font-mono text-[11px] text-red-300/90">
                    {result.audit_errors.map((e, i) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                </div>
              )}

              {result.risk && <RiskBanner risk={result.risk} />}

              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="rounded border border-slate-700 bg-slate-900 px-2 py-1">
                  Routed to:{' '}
                  <b className="text-slate-100">
                    {result.routed_to.length
                      ? result.routed_to.map((r) => r.replace('_', ' ')).join(', ')
                      : 'no auditor'}
                  </b>
                </span>
                <span className="rounded border border-slate-700 bg-slate-900 px-2 py-1">
                  {total} finding{total === 1 ? '' : 's'}
                </span>
                <span
                  className={`rounded border px-2 py-1 ${
                    result.guardrail_report?.passed
                      ? 'border-emerald-600/50 bg-emerald-500/10 text-emerald-300'
                      : 'border-amber-600/50 bg-amber-500/10 text-amber-300'
                  }`}
                  title={`engine: ${result.guardrail_report?.engine || 'unknown'}`}
                >
                  Guardrails{' '}
                  {result.guardrail_report?.passed
                    ? 'passed'
                    : `flagged ${result.guardrail_report?.redactions ?? 0} redaction(s)`}
                </span>
              </div>

              <nav className="flex gap-1 border-b border-slate-800 text-sm">
                {[
                  ['findings', `Findings (${total})`],
                  ['patch', 'Patch'],
                  ['report', 'Markdown'],
                  ['logs', 'Agent log'],
                ].map(([key, label]) => (
                  <button
                    key={key}
                    onClick={() => setTab(key)}
                    className={`px-3 py-2 ${
                      tab === key
                        ? 'border-b-2 border-emerald-500 text-slate-50'
                        : 'text-slate-500 hover:text-slate-300'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </nav>

              <div className="space-y-4">
                {tab === 'findings' && (
                  <>
                    <Group
                      title="Security"
                      findings={result.security_issues}
                      ran={result.routed_to.includes("security_audit")}
                      failed={result.failed_audits.includes("security_audit")}
                    />
                    <Group
                      title="Performance"
                      findings={result.performance_issues}
                      ran={result.routed_to.includes("performance_audit")}
                      failed={result.failed_audits.includes("performance_audit")}
                    />
                  </>
                )}

                {tab === 'patch' && <DiffView diff={result.diff} />}

                {tab === 'report' && (
                  <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg border border-slate-800 bg-black/50 p-4 text-xs text-slate-300">
                    {result.summary_report}
                  </pre>
                )}

                {tab === 'logs' && (
                  <ol className="space-y-1 rounded-lg border border-slate-800 bg-black/50 p-4 font-mono text-xs text-slate-400">
                    {result.logs.map((line, i) => (
                      <li key={i}>
                        <span className="text-slate-600">{String(i + 1).padStart(2, '0')} </span>
                        {line}
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </>
          )}
        </section>
      </main>
    </div>
  )
}

const BAND_STYLES = {
  critical: 'border-red-500/50 bg-red-500/10 text-red-300',
  high: 'border-orange-500/50 bg-orange-500/10 text-orange-300',
  medium: 'border-amber-500/50 bg-amber-500/10 text-amber-300',
  low: 'border-sky-500/50 bg-sky-500/10 text-sky-300',
  none: 'border-emerald-600/50 bg-emerald-500/10 text-emerald-300',
  unknown: 'border-slate-600 bg-slate-800/60 text-slate-400',
}

function RiskBanner({ risk }) {
  const style = BAND_STYLES[risk.band] || BAND_STYLES.unknown

  return (
    <div className={`rounded-lg border px-4 py-3 ${style}`}>
      <div className="flex items-baseline gap-3">
        <span className="text-2xl font-semibold tabular-nums">
          {risk.complete ? risk.score : '—'}
        </span>
        <span className="text-xs uppercase tracking-wide opacity-80">
          / 100 · {risk.band}
        </span>
      </div>
      <p className="mt-1 text-xs opacity-90">{risk.note}</p>
      {risk.drivers?.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-[11px] opacity-80">
          {risk.drivers.map((d, i) => (
            <li key={i}>· {d}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Group({ title, findings, ran, failed }) {
  return (
    <div className="space-y-2">
      <h2 className="text-sm font-semibold text-slate-100">
        {title}{' '}
        <span
          className={`font-normal ${failed ? 'text-red-400' : 'text-slate-500'}`}
        >
          {failed ? '· failed' : ran ? `· ${findings.length}` : '· not run'}
        </span>
      </h2>
      {failed ? (
        <p className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-xs text-red-300">
          This audit failed to run. The code was <b>not</b> checked for{' '}
          {title.toLowerCase()} issues.
        </p>
      ) : !ran ? (
        <p className="rounded-lg border border-dashed border-slate-800 px-4 py-3 text-xs text-slate-500">
          The supervisor decided this submission did not need a {title.toLowerCase()}{' '}
          audit.
        </p>
      ) : findings.length === 0 ? (
        <p className="rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-3 text-xs text-emerald-400">
          No issues found.
        </p>
      ) : (
        findings.map((f, i) => <FindingCard key={i} finding={f} />)
      )}
    </div>
  )
}
