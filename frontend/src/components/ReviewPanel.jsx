import { useRef, useState } from 'react'
import Editor from '@monaco-editor/react'

import { Icon } from './Icons'
import { SAMPLES } from '../samples'
import { CARD, LANGUAGES } from '../lib/ui'

const TABS = [
  { id: 'paste', label: 'Paste Code' },
  { id: 'pr', label: 'GitHub PR' },
  { id: 'upload', label: 'Upload File' },
]

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

  const lineCount = code ? code.split('\n').length : 0

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
      <div className="flex flex-wrap items-center gap-3 border-b border-slate-800 px-5 py-4">
        <h2 className="text-base font-semibold text-slate-100">Review Code</h2>

        <div className="ml-auto flex items-center gap-2">
          <label className="text-xs text-slate-500">Language</label>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 outline-none focus:border-indigo-500"
          >
            {LANGUAGES.map((l) => (
              <option key={l} value={l}>
                {l.charAt(0).toUpperCase() + l.slice(1)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex gap-1 border-b border-slate-800 px-4">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => (id === 'upload' ? fileInput.current?.click() : setTab(id))}
            className={`px-4 py-2.5 text-sm transition ${
              tab === id
                ? 'border-b-2 border-indigo-500 text-slate-100'
                : 'border-b-2 border-transparent text-slate-500 hover:text-slate-300'
            }`}
          >
            {label}
          </button>
        ))}
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
          className="my-auto ml-auto rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-300 outline-none"
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
      </div>

      <div className="grid gap-5 p-5 xl:grid-cols-[1.45fr_1fr]">
        {/* ---------------------------------------------------- editor ---- */}
        <div>
          <div className="overflow-hidden rounded-lg border border-slate-800 bg-[#0d1117]">
            <Editor
              height="240px"
              theme="vs-dark"
              language={language}
              value={code}
              onChange={(v) => setCode(v ?? '')}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                lineNumbers: 'on',
                scrollBeyondLastLine: false,
                automaticLayout: true,
                padding: { top: 12, bottom: 12 },
                renderLineHighlight: 'none',
              }}
            />
            <div className="flex items-center gap-2 border-t border-slate-800 px-3 py-2 text-xs text-slate-500">
              <Icon.file width={14} height={14} />
              <input
                value={filename}
                onChange={(e) => setFilename(e.target.value)}
                className="w-40 bg-transparent text-slate-400 outline-none focus:text-slate-200"
              />
              <span className="ml-auto">{lineCount} lines</span>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <label
              className="flex items-center gap-2 text-xs text-slate-400"
              title="Bypass the supervisor's routing and run every auditor. For high-stakes paths where a false negative is unacceptable."
            >
              <input
                type="checkbox"
                checked={forceFullAudit}
                onChange={(e) => setForceFullAudit(e.target.checked)}
                className="accent-indigo-500"
              />
              Force full audit
            </label>

            <button
              onClick={onRun}
              disabled={loading || !code.trim()}
              className="ml-auto flex items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white shadow-lg shadow-indigo-950/40 transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {loading ? 'Reviewing…' : 'Run AI Review'}
              {!loading && <Icon.arrow width={16} height={16} />}
            </button>
          </div>
        </div>

        {/* -------------------------------------------------------- PR ---- */}
        <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-5">
          <div className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-lg border border-slate-700 bg-slate-800 text-slate-300">
              <Icon.github width={18} height={18} />
            </span>
            <p className="text-sm font-medium text-slate-200">
              Or analyze a GitHub Pull Request
            </p>
          </div>

          <input
            value={prUrl}
            onChange={(e) => setPrUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && prUrl.trim() && onRunPR(prUrl)}
            placeholder="https://github.com/owner/repo/pull/42"
            className="mt-4 w-full rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2.5 text-sm text-slate-200 outline-none placeholder:text-slate-600 focus:border-indigo-500"
          />

          <button
            onClick={() => onRunPR(prUrl)}
            disabled={prLoading || !prUrl.trim() || !tokenReady}
            className="mt-3 w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {prLoading ? 'Analyzing PR…' : 'Analyze PR'}
          </button>

          <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
            {tokenReady ? (
              <>
                Reads the lines the PR <b className="text-slate-400">adds</b> and returns
                the review. It does <b className="text-slate-400">not</b> post a comment —
                only the webhook does that.
              </>
            ) : (
              <>
                Needs <code className="text-slate-400">GITHUB_TOKEN</code> in
                <code className="text-slate-400"> backend/.env</code>. Without it the
                backend cannot read pull requests.
              </>
            )}
          </p>
        </div>
      </div>
    </section>
  )
}
