import { useEffect, useRef, useState } from 'react'

import { health, review, reviewPR } from './api'
import { SAMPLES } from './samples'
import { CARD, band } from './lib/ui'
import { fromPR, fromReview, load, record, relativeTime } from './lib/history'

import { Icon } from './components/Icons'
import { MobileNav, Sidebar, TopBar } from './components/Shell'
import Hero from './components/Hero'
import ReviewPanel from './components/ReviewPanel'
import AgentFindings from './components/AgentFindings'
import PatchView from './components/PatchView'
import {
  LastReviewSummary,
  RecentActivity,
  SystemStatus,
} from './components/Summary'
import {
  AgentsPage,
  AnalyticsPage,
  EmptyCard,
  PageHead,
  SettingsPage,
  TokenGatedPage,
} from './pages/Pages'

export default function App() {
  const [page, setPage] = useState('dashboard')
  const [backend, setBackend] = useState(null)

  const [code, setCode] = useState(SAMPLES[0].code)
  const [language, setLanguage] = useState(SAMPLES[0].language)
  const [filename, setFilename] = useState(SAMPLES[0].filename)
  const [forceFullAudit, setForceFullAudit] = useState(false)

  const [result, setResult] = useState(null)
  const [reviewedSource, setReviewedSource] = useState('')
  const [prResult, setPrResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [prLoading, setPrLoading] = useState(false)
  const [error, setError] = useState(null)

  const [entries, setEntries] = useState(() => load())
  const [openFinding, setOpenFinding] = useState(null)
  const resultsRef = useRef(null)

  useEffect(() => {
    if (!openFinding) return
    const onKey = (e) => e.key === 'Escape' && setOpenFinding(null)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [openFinding])

  useEffect(() => {
    health()
      .then(setBackend)
      .catch(() => setBackend({ status: 'unreachable' }))
  }, [])

  const tokenReady = backend?.pr_bot?.github_token_configured

  async function runReview() {
    setLoading(true)
    setError(null)
    setPrResult(null)
    try {
      const data = await review({ sourceCode: code, language, forceFullAudit })
      setResult(data)
      setReviewedSource(code)
      setEntries(record(fromReview(data, { label: filename, language })))
      setPage('dashboard')
      requestAnimationFrame(() =>
        resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
      )
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function runPRReview(url) {
    setPrLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await reviewPR(url)
      setPrResult(data)
      setEntries(record(fromPR(data)))
      setPage('pulls')
    } catch (e) {
      setError(e.message)
      setPage('pulls')
    } finally {
      setPrLoading(false)
    }
  }

  function newReview() {
    setResult(null)
    setPrResult(null)
    setError(null)
    setPage('dashboard')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const panel = (
    <ReviewPanel
      code={code}
      setCode={setCode}
      language={language}
      setLanguage={setLanguage}
      filename={filename}
      setFilename={setFilename}
      forceFullAudit={forceFullAudit}
      setForceFullAudit={setForceFullAudit}
      onRun={runReview}
      onRunPR={runPRReview}
      loading={loading}
      prLoading={prLoading}
      tokenReady={tokenReady}
    />
  )

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      <TopBar backend={backend} onNewReview={newReview} onNavigate={setPage} />
      <MobileNav page={page} onNavigate={setPage} />

      <div className="flex">
        <Sidebar page={page} onNavigate={setPage} />

        <main className="min-w-0 flex-1 space-y-5 p-5">
          {error && (
            <div className="flex items-start gap-3 rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
              <Icon.alert className="mt-0.5 shrink-0" width={17} height={17} />
              <span className="flex-1">{error}</span>
              <button
                onClick={() => setError(null)}
                className="shrink-0 text-rose-400 hover:text-rose-200"
              >
                ✕
              </button>
            </div>
          )}

          {page === 'dashboard' && (
            <>
              <Hero />

              <div className="grid gap-5 xl:grid-cols-[1fr_340px]">
                <div className="space-y-5">
                  {panel}

                  <div ref={resultsRef} className="space-y-5">
                    {loading && <Working />}
                    {result && !loading && (
                      <>
                        <AgentFindings result={result} onOpenFinding={setOpenFinding} />
                        <PatchView result={result} original={reviewedSource} />
                      </>
                    )}
                  </div>
                </div>

                <aside className="space-y-5">
                  <SystemStatus backend={backend} onViewGraph={() => setPage('agents')} />
                  <LastReviewSummary
                    result={result}
                    onViewAll={() => setPage('analytics')}
                  />
                  <RecentActivity
                    entries={entries}
                    onSeeAll={() => setPage('analytics')}
                  />
                </aside>
              </div>
            </>
          )}

          {page === 'review' && (
            <div className="space-y-5">
              <PageHead
                title="Code Review"
                subtitle="The full report for the last review you ran."
              />
              {panel}
              {loading && <Working />}
              {result && !loading ? (
                <>
                  <AgentFindings result={result} onOpenFinding={setOpenFinding} />
                  <PatchView result={result} original={reviewedSource} />
                </>
              ) : (
                !loading && (
                  <EmptyCard
                    icon={Icon.review}
                    title="No review yet"
                    text="Run a review above and the full report — findings, patch, generated tests, markdown and the agent log — appears here."
                  />
                )
              )}
            </div>
          )}

          {page === 'pulls' && (
            <TokenGatedPage
              title="Pull Requests"
              subtitle="Review a PR on demand. Nothing is posted — only the webhook comments."
              icon={Icon.pr}
              tokenReady={tokenReady}
              blurb="Reading pull requests needs a GitHub token with repo scope. Add it and restart the backend; the webhook additionally needs GITHUB_WEBHOOK_SECRET."
            >
              {panel}
              {prLoading && <Working label="Reading the PR and reviewing added lines…" />}
              {prResult && !prLoading && <PRResult data={prResult} />}
              {!prResult && !prLoading && (
                <EmptyCard
                  icon={Icon.pr}
                  title="No pull request analyzed yet"
                  text="Paste a github.com PR link above. Only the lines the PR adds are reviewed — flagging untouched code is noise the author cannot act on."
                />
              )}
            </TokenGatedPage>
          )}

          {page === 'repository' && (
            <TokenGatedPage
              title="Repository"
              subtitle="Repository-wide review is not built."
              icon={Icon.repo}
              tokenReady={false}
              blurb="Reviewing a whole repository needs repo ingestion and multi-file context — a separate project, deliberately deferred (see docs/ROADMAP.md). Today the system reviews a submission or the lines a PR adds."
            />
          )}

          {page === 'analytics' && (
            <AnalyticsPage entries={entries} onChanged={setEntries} />
          )}

          {page === 'agents' && <AgentsPage />}

          {page === 'settings' && <SettingsPage backend={backend} />}
        </main>
      </div>

      {openFinding && (
        <FindingDetail finding={openFinding} onClose={() => setOpenFinding(null)} />
      )}
    </div>
  )
}

function FindingDetail({ finding, onClose }) {
  const source = String(finding.source || 'llm')
  const confirmed = source.startsWith('llm+')

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-slate-950/80 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className={`${CARD} max-h-[85vh] w-full max-w-2xl overflow-auto bg-slate-900`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3 border-b border-slate-800 px-5 py-4">
          <span
            className={`shrink-0 rounded border px-2 py-0.5 text-[11px] font-medium ${
              band(finding.severity?.toLowerCase()).chip
            }`}
          >
            {finding.severity}
          </span>
          <h3 className="flex-1 text-sm font-medium text-slate-100">{finding.title}</h3>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-200">
            ✕
          </button>
        </div>

        <div className="space-y-4 px-5 py-4 text-sm">
          {finding.line_hint && (
            <pre className="overflow-x-auto rounded-lg border border-slate-800 bg-[#0d1117] px-3 py-2 text-xs text-slate-300">
              {finding.line_hint}
            </pre>
          )}

          {finding.explanation && (
            <Block label="Why this matters" text={finding.explanation} />
          )}

          {finding.complexity_before && finding.complexity_before !== 'n/a' && (
            <div>
              <p className="text-xs font-medium text-slate-400">Complexity</p>
              <p className="mt-1 text-sm">
                <code className="text-amber-300">{finding.complexity_before}</code>
                <span className="mx-2 text-slate-600">→</span>
                <code className="text-emerald-300">{finding.complexity_after}</code>
              </p>
            </div>
          )}

          {finding.recommendation && (
            <Block label="Recommended fix" text={finding.recommendation} />
          )}

          <div className="border-t border-slate-800 pt-3 text-[11px] text-slate-500">
            Found by{' '}
            <b className={confirmed ? 'text-emerald-300' : 'text-slate-400'}>
              {confirmed
                ? `the LLM and ${source.slice(4)} independently`
                : source === 'llm'
                  ? 'the LLM auditor'
                  : `static analysis (${source})`}
            </b>
            {confirmed && ' — corroborated findings are the ones to read first.'}
          </div>
        </div>
      </div>
    </div>
  )
}

function Block({ label, text }) {
  return (
    <div>
      <p className="text-xs font-medium text-slate-400">{label}</p>
      <p className="mt-1 leading-relaxed text-slate-300">{text}</p>
    </div>
  )
}

function Working({ label = 'Supervisor is routing the submission…' }) {
  return (
    <div className={`${CARD} flex items-center gap-4 px-5 py-8`}>
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-slate-700 border-t-indigo-400" />
      <div>
        <p className="text-sm text-slate-300">{label}</p>
        <p className="mt-0.5 text-xs text-slate-500">
          Routing, then the chosen auditors, patch, tests and guardrails.
        </p>
      </div>
    </div>
  )
}

function PRResult({ data }) {
  const scored = data.files.filter((f) => f.risk?.complete)
  const worst = scored.reduce(
    (acc, f) => (acc === null || f.risk.score > acc.risk.score ? f : acc),
    null,
  )
  const style = band(worst?.risk?.band)

  return (
    <div className="space-y-5">
      <div className={`${CARD} p-5`}>
        <div className="flex flex-wrap items-center gap-4">
          <div>
            <h2 className="text-base font-semibold text-slate-100">
              {data.repository}
              <span className="text-slate-500">#{data.number}</span>
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              {data.files.length} file{data.files.length === 1 ? '' : 's'} reviewed ·
              highest-risk file shown, not an average
            </p>
          </div>
          {worst && (
            <span
              className={`ml-auto rounded-lg border px-3 py-1.5 text-sm font-medium ${style.chip}`}
            >
              {worst.risk.score}/100 · {style.label}
            </span>
          )}
        </div>
      </div>

      {data.files.map((f) => (
        <div key={f.filename} className={`${CARD} p-5`}>
          <div className="flex flex-wrap items-center gap-3">
            <Icon.file width={15} height={15} className="text-slate-500" />
            <code className="text-sm text-slate-200">{f.filename}</code>
            <span className="rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">
              {f.language}
            </span>
            <span className="text-[11px] text-slate-600">+{f.additions}</span>
            <span
              className={`ml-auto rounded-md border px-2 py-0.5 text-[11px] ${
                band(f.risk?.band).chip
              }`}
            >
              {f.risk?.complete ? `${f.risk.score}/100` : 'unavailable'}
            </span>
          </div>

          {f.failed_audits?.length > 0 && (
            <p className="mt-3 rounded-md border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-xs text-rose-300">
              {f.failed_audits.join(', ')} did not run — this file was not fully checked.
            </p>
          )}

          <ul className="mt-3 space-y-1.5">
            {[...f.security_issues, ...f.performance_issues].map((x, i) => (
              <li key={i} className="flex items-start gap-2 text-xs">
                <span
                  className={`mt-0.5 shrink-0 rounded border px-1.5 py-0.5 text-[10px] ${
                    band(x.severity?.toLowerCase()).chip
                  }`}
                >
                  {x.severity}
                </span>
                <span className="text-slate-300">{x.title}</span>
              </li>
            ))}
            {f.security_issues.length + f.performance_issues.length === 0 &&
              !f.failed_audits?.length && (
                <li className="text-xs text-emerald-300">No issues in the added lines.</li>
              )}
          </ul>
        </div>
      ))}

      <details className={`${CARD} p-5`}>
        <summary className="cursor-pointer text-sm text-slate-300">
          The comment the webhook would post
        </summary>
        <pre className="mt-4 max-h-96 overflow-auto whitespace-pre-wrap rounded-lg border border-slate-800 bg-[#0d1117] p-4 text-xs text-slate-400">
          {data.comment_markdown}
        </pre>
      </details>
    </div>
  )
}

export { relativeTime }
