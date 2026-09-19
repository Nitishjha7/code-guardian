import { Icon } from './Icons'

const REPO_URL = 'https://github.com/Nitishjha7/code-guardian'

const NAV = [
  { id: 'review', label: 'Review', icon: Icon.review },
  { id: 'pulls', label: 'Pull Requests', icon: Icon.pr },
  { id: 'history', label: 'History', icon: Icon.chart },
  { id: 'agents', label: 'Agents', icon: Icon.agents },
  { id: 'settings', label: 'Settings', icon: Icon.settings },
]

export function Sidebar({ page, onNavigate }) {
  return (
    <aside className="hidden w-52 shrink-0 border-r border-slate-800 lg:block">
      <nav className="sticky top-0 space-y-0.5 p-2">
        {NAV.map(({ id, label, icon: Ico }) => {
          const active = page === id
          return (
            <button
              key={id}
              onClick={() => onNavigate(id)}
              className={`flex w-full items-center gap-2.5 rounded px-3 py-2 text-sm transition ${
                active
                  ? 'bg-slate-800 text-slate-100'
                  : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
              }`}
            >
              <Ico width={16} height={16} />
              {label}
            </button>
          )
        })}
      </nav>
    </aside>
  )
}

export function TopBar({ backend, onNewReview, onNavigate }) {
  const online = backend?.status === 'ok'
  const keyReady = backend?.groq_key_configured
  const tokenReady = backend?.pr_bot?.github_token_configured

  const state = !online
    ? { dot: 'bg-rose-500', text: 'backend unreachable' }
    : !keyReady
      ? { dot: 'bg-amber-500', text: 'no API key' }
      : { dot: 'bg-emerald-500', text: backend.model }

  return (
    <header className="flex items-center gap-4 border-b border-slate-800 px-4 py-2.5">
      <button
        onClick={() => onNavigate('review')}
        className="flex items-center gap-2 text-sm font-semibold text-slate-100"
      >
        <Icon.shield width={18} height={18} className="text-indigo-400" />
        Code Guardian
      </button>

      <span
        className="flex items-center gap-2 rounded border border-slate-800 bg-slate-900 px-2.5 py-1 font-mono text-[11px] text-slate-400"
        title={online ? 'Backend healthy' : 'Backend unreachable'}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${state.dot}`} />
        {state.text}
      </span>

      {online && !tokenReady && (
        <button
          onClick={() => onNavigate('settings')}
          className="hidden rounded border border-slate-800 bg-slate-900 px-2.5 py-1 font-mono text-[11px] text-slate-500 hover:text-slate-300 sm:block"
          title="GITHUB_TOKEN is not set — pull requests cannot be read"
        >
          no github token
        </button>
      )}

      <a
        href={REPO_URL}
        target="_blank"
        rel="noopener noreferrer"
        title="Source on GitHub"
        className="ml-auto flex items-center gap-1.5 rounded border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-400 transition hover:border-slate-700 hover:text-slate-200"
      >
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
          <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.4 7.4 0 0 1 2-.27c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
        </svg>
        <span className="hidden sm:inline">GitHub</span>
      </a>

      <button
        onClick={onNewReview}
        className="rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 transition hover:bg-slate-700"
      >
        New review
      </button>
    </header>
  )
}

export function MobileNav({ page, onNavigate }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-slate-800 px-2 py-1.5 lg:hidden">
      {NAV.map(({ id, label }) => (
        <button
          key={id}
          onClick={() => onNavigate(id)}
          className={`whitespace-nowrap rounded px-2.5 py-1 text-xs ${
            page === id ? 'bg-slate-800 text-slate-100' : 'text-slate-400'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
