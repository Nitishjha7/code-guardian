import { useRef, useState } from 'react'
import Editor from '@monaco-editor/react'

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
}) {
  const [tab, setTab] = useState('paste')
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
    <section className={CARD}>
      <div className="flex flex-wrap items-center gap-1 border-b border-slate-800 px-2">
        <Tab active={tab === 'paste'} onClick={() => setTab('paste')}>
          Code
        </Tab>
        <Tab active={tab === 'pr'} onClick={() => setTab('pr')}>
          Pull request
        </Tab>
        <button
          onClick={() => fileInput.current?.click()}
          className="px-3 py-2 text-sm text-slate-500 hover:text-slate-300"
        >
          Upload
        </button>
        <input
          ref={fileInput}
          type="file"
          accept=".py,.js,.jsx,.ts,.tsx,.java,.go,.sql,.css,.html,.json,.txt"
          onChange={handleFile}
          className="hidden"
        />

        <select
          onChange={(e) => loadSample(e.target.value)}
          value=""
          className="ml-auto my-1 rounded border border-slate-800 bg-slate-900 px-2 py-1 text-xs text-slate-400 outline-none"
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

      {tab === 'paste' ? (
        <>
          <div className="overflow-hidden border-b border-slate-800 bg-[#0d1117]">
            <Editor
              height="260px"
              theme="vs-dark"
              language={language}
              value={code}
              onChange={(v) => setCode(v ?? '')}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                scrollBeyondLastLine: false,
                automaticLayout: true,
                padding: { top: 10, bottom: 10 },
                renderLineHighlight: 'none',
                overviewRulerLanes: 0,
              }}
            />
          </div>

          <div className="flex flex-wrap items-center gap-3 px-3 py-2.5">
            <input
              value={filename}
              onChange={(e) => setFilename(e.target.value)}
              className="w-32 bg-transparent font-mono text-xs text-slate-400 outline-none focus:text-slate-200"
            />
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="rounded border border-slate-800 bg-slate-900 px-2 py-1 font-mono text-xs text-slate-400 outline-none"
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
              className="flex items-center gap-1.5 text-xs text-slate-500"
              title="Bypass routing and run every auditor. For paths where a false negative is unacceptable."
            >
              <input
                type="checkbox"
                checked={forceFullAudit}
                onChange={(e) => setForceFullAudit(e.target.checked)}
                className="accent-indigo-500"
              />
              force full audit
            </label>

            <button
              onClick={onRun}
              disabled={loading || !code.trim()}
              className="ml-auto rounded bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {loading ? 'Reviewing…' : 'Review'}
            </button>
          </div>
        </>
      ) : (
        <div className="space-y-2.5 p-3">
          <div className="flex gap-2">
            <input
              value={prUrl}
              onChange={(e) => setPrUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && prUrl.trim() && onRunPR(prUrl)}
              placeholder="https://github.com/owner/repo/pull/42"
              className="min-w-0 flex-1 rounded border border-slate-800 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-200 outline-none placeholder:text-slate-700 focus:border-indigo-600"
            />
            <button
              onClick={() => onRunPR(prUrl)}
              disabled={prLoading || !prUrl.trim() || !tokenReady}
              className="shrink-0 rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {prLoading ? 'Reading…' : 'Analyze'}
            </button>
          </div>
          <p className="text-xs text-slate-600">
            {tokenReady
              ? 'Reviews the lines the PR adds. Posts nothing — the comment is returned for preview.'
              : 'Needs GITHUB_TOKEN in backend/.env.'}{' '}
            Accepts <code className="text-slate-500">owner/repo#42</code> too.
          </p>
        </div>
      )}
    </section>
  )
}

function Tab({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-2 text-sm transition ${
        active
          ? 'border-b-2 border-indigo-500 text-slate-100'
          : 'border-b-2 border-transparent text-slate-500 hover:text-slate-300'
      }`}
    >
      {children}
    </button>
  )
}
