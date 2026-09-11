import { Icon } from './Icons'

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

      <button
        onClick={onNewReview}
        className="ml-auto rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 transition hover:bg-slate-700"
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
