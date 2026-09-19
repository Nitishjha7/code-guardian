import { useRef, useState } from 'react'
import Editor from '@monaco-editor/react'

import { Icon } from './Icons'
import { SAMPLES } from '../samples'
import { CARD, LANGUAGES } from '../lib/ui'

const EXT_LANGUAGE = {
  py: 'python',
  js: 'javascript',
  jsx: 'javascript',
  ts: 'typescript',
  tsx: 'typescript',
  java: 'java',
  go: 'go',
  sql: 'sql',
  css: 'css',
  html: 'html',
  json: 'json',
}

export default function ReviewPanel({
  code,
  setCode,
  language,
  setLanguage,
  filename,
  setFilename,
  forceFullAudit,
  setForceFullAudit,
  onRun,
  onRunPR,
  loading,
  prLoading,
  tokenReady,
  // Which tab to open on. The Pull Requests page passes "pr" so the panel lands
  // on the PR input instead of the code editor.
  initialTab = 'paste',
}) {
  const [tab, setTab] = useState(initialTab)
  const [prUrl, setPrUrl] = useState('')
  const fileInput = useRef(null)

  function loadSample(id) {
    const sample = SAMPLES.find((s) => s.id === id)
    if (!sample) return
    setCode(sample.code)
    setLanguage(sample.language)
    setFilename(sample.filename)
    setTab('paste')
  }

  async function handleFile(event) {
    const file = event.target.files?.[0]
    if (!file) return
    const text = await file.text()
    setCode(text)
    setFilename(file.name)
    const ext = file.name.split('.').pop()?.toLowerCase()
    if (EXT_LANGUAGE[ext]) setLanguage(EXT_LANGUAGE[ext])
    setTab('paste')
    event.target.value = ''
  }

  return (
    <section className={`${CARD} overflow-hidden`}>
      <div className="flex flex-wrap items-center gap-1 border-b border-ink-700 bg-ink-900/60 px-3">
        <Tab active={tab === 'paste'} onClick={() => setTab('paste')} icon={Icon.code}>
          Code
        </Tab>
        <Tab active={tab === 'pr'} onClick={() => setTab('pr')} icon={Icon.pr}>
          Pull Request
        </Tab>

        <input
          ref={fileInput}
          type="file"
          accept=".py,.js,.jsx,.ts,.tsx,.java,.go,.sql,.css,.html,.json,.txt"
          onChange={handleFile}
          className="hidden"
        />

        <div className="ml-auto flex items-center gap-2 py-2">
          {tab === 'paste' && (
            <button
              onClick={() => fileInput.current?.click()}
              title="Load a file into the editor"
              className="inline-flex items-center gap-1.5 rounded-lg border border-ink-700 bg-ink-800 px-2.5 py-1.5 text-xs text-slate-400 transition hover:border-ink-600 hover:text-slate-200"
            >
              <Icon.upload width={13} height={13} />
              Open file…
            </button>
          )}

          <select
            onChange={(e) => loadSample(e.target.value)}
            value=""
            className="rounded-lg border border-ink-700 bg-ink-800 px-2.5 py-1.5 text-xs text-slate-400 outline-none transition hover:border-ink-600 focus:border-brand-600"
          >
            <option value="" disabled>
              sample…
            </option>
            {SAMPLES.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {tab === 'paste' ? (
        <>
          <div className="overflow-hidden border-b border-ink-700 bg-[#0a0e1a]">
            <Editor
              height="320px"
              theme="vs-dark"
              language={language}
              value={code}
              onChange={(v) => setCode(v ?? '')}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                fontFamily: 'JetBrains Mono, ui-monospace, monospace',
                scrollBeyondLastLine: false,
                automaticLayout: true,
                padding: { top: 14, bottom: 14 },
                renderLineHighlight: 'none',
                overviewRulerLanes: 0,
              }}
            />
          </div>

          <div className="flex flex-wrap items-center gap-3 bg-ink-900/40 px-4 py-3">
            <input
              value={filename}
              onChange={(e) => setFilename(e.target.value)}
              placeholder="filename"
              className="w-36 rounded-lg border border-transparent bg-transparent px-2 py-1 font-mono text-xs text-slate-400 outline-none transition placeholder:text-slate-600 hover:border-ink-700 focus:border-brand-600 focus:text-slate-200"
            />
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="rounded-lg border border-ink-700 bg-ink-800 px-2.5 py-1.5 font-mono text-xs text-slate-400 outline-none focus:border-brand-600"
            >
              {LANGUAGES.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
            <span className="font-mono text-xs text-slate-600">
              {code ? code.split('\n').length : 0} lines
            </span>

            <label
              className="flex cursor-pointer items-center gap-2 text-xs text-slate-500 transition hover:text-slate-300"
              title="Bypass routing and run every auditor. For paths where a false negative is unacceptable."
            >
              <input
                type="checkbox"
                checked={forceFullAudit}
                onChange={(e) => setForceFullAudit(e.target.checked)}
                className="h-3.5 w-3.5 accent-brand-500"
              />
              force full audit
            </label>

            <button
              // Called with no argument on purpose — onRun falls back to the
              // editor's current state. Passing the click event through would
              // land it in the submission parameter.
              onClick={() => onRun()}
              disabled={loading || !code.trim()}
              className="ml-auto inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white transition hover:bg-brand-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {loading ? (
                <>
                  <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                  Reviewing…
                </>
              ) : (
                <>
                  <Icon.sparkle width={15} height={15} />
                  Run review
                </>
              )}
            </button>
          </div>
        </>
      ) : (
        <div className="space-y-3 p-4">
          <div className="flex gap-2">
            <div className="relative min-w-0 flex-1">
              <Icon.github
                width={15}
                height={15}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-600"
              />
              <input
                value={prUrl}
                onChange={(e) => setPrUrl(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && prUrl.trim() && onRunPR(prUrl)}
                placeholder="https://github.com/owner/repo/pull/42"
                className="w-full rounded-lg border border-ink-700 bg-ink-900 py-2.5 pl-9 pr-3 font-mono text-sm text-slate-200 outline-none transition placeholder:text-slate-600 focus:border-brand-600"
              />
            </div>
            <button
              onClick={() => onRunPR(prUrl)}
              disabled={prLoading || !prUrl.trim() || !tokenReady}
              className="shrink-0 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-brand-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {prLoading ? 'Reading…' : 'Analyze'}
            </button>
          </div>
          <p className="text-xs leading-relaxed text-slate-500">
            {tokenReady
              ? 'Any public GitHub PR. Reviews only the lines it adds, and posts nothing — the comment is returned here for preview.'
              : 'Needs GITHUB_TOKEN in backend/.env.'}{' '}
            Accepts <code className="text-slate-400">owner/repo#42</code> too.
          </p>
        </div>
      )}
    </section>
  )
}

function Tab({ active, onClick, children, icon: Ico }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 border-b-2 px-3 py-3 text-sm transition ${
        active
          ? 'border-brand-500 text-white'
          : 'border-transparent text-slate-500 hover:text-slate-300'
      }`}
    >
      {Ico && <Ico width={15} height={15} />}
      {children}
    </button>
  )
}
