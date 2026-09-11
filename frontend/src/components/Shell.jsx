import { Icon } from './Icons'

const NAV = [
  { id: 'dashboard', label: 'Dashboard', icon: Icon.home },
  { id: 'repository', label: 'Repository', icon: Icon.repo },
  { id: 'pulls', label: 'Pull Requests', icon: Icon.pr },
  { id: 'review', label: 'Code Review', icon: Icon.review },
  { id: 'analytics', label: 'Analytics', icon: Icon.chart },
  { id: 'agents', label: 'Agents', icon: Icon.agents },
  { id: 'settings', label: 'Settings', icon: Icon.settings },
]

export function Sidebar({ page, onNavigate }) {
  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-slate-800/80 bg-slate-950/60 lg:flex">
      <nav className="flex-1 space-y-1 p-3">
        {NAV.map(({ id, label, icon: Ico }) => {
          const active = page === id
          return (
            <button
              key={id}
              onClick={() => onNavigate(id)}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition ${
                active
                  ? 'border border-indigo-500/30 bg-indigo-500/10 text-indigo-200'
                  : 'border border-transparent text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
              }`}
            >
              <Ico />
              {label}
            </button>
          )
        })}
      </nav>

      <div className="m-3 rounded-xl border border-slate-800 bg-gradient-to-b from-indigo-500/10 to-slate-900/40 p-4">
        <Icon.bolt className="text-indigo-300" />
        <p className="mt-3 text-sm font-medium leading-snug text-slate-200">
          AI Agents
          <br />
          Working Together
          <br />
          for Better Code
        </p>
      </div>
    </aside>
  )
}

export function TopBar({ backend, onNewReview, onNavigate }) {
  const online = backend?.status === 'ok'
  const tokenReady = backend?.pr_bot?.github_token_configured

  return (
    <header className="flex items-center gap-4 border-b border-slate-800/80 bg-slate-950/80 px-5 py-3 backdrop-blur">
      <button
        onClick={() => onNavigate('dashboard')}
        className="flex items-center gap-3 text-left"
      >
        <span className="grid h-10 w-10 place-items-center rounded-xl border border-indigo-500/30 bg-indigo-500/15 text-indigo-300">
          <Icon.shield width={22} height={22} />
        </span>
        <span>
          <span className="block text-lg font-semibold leading-tight text-slate-50">
            Code <span className="text-indigo-400">Guardian</span>
          </span>
          <span className="block text-[11px] text-slate-500">
            Safer Code. Faster Fixes. Automated.
          </span>
        </span>
      </button>

      <div className="ml-auto flex items-center gap-3">
        <button
          onClick={() => onNavigate('settings')}
          title={
            tokenReady
              ? 'GITHUB_TOKEN is configured'
              : 'GITHUB_TOKEN is not set — pull requests cannot be read'
          }
          className="hidden items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-300 hover:bg-slate-800/60 sm:flex"
        >
          <Icon.github width={18} height={18} />
          {tokenReady ? 'GitHub connected' : 'Connect GitHub'}
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              tokenReady ? 'bg-emerald-400' : 'bg-slate-600'
            }`}
          />
        </button>

        <button
          onClick={onNewReview}
          className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-indigo-950/40 transition hover:bg-indigo-500"
        >
          <Icon.plus width={16} height={16} />
          New Review
        </button>

        <span
          title={online ? `Backend online · ${backend.model}` : 'Backend unreachable'}
          className={`grid h-10 w-10 place-items-center rounded-full border text-sm font-semibold ${
            online
              ? 'border-slate-700 bg-slate-800 text-slate-200'
              : 'border-rose-700/60 bg-rose-900/30 text-rose-300'
          }`}
        >
          N
        </span>
      </div>
    </header>
  )
}

export function MobileNav({ page, onNavigate }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-slate-800/80 bg-slate-950/60 px-3 py-2 lg:hidden">
      {NAV.map(({ id, label }) => (
        <button
          key={id}
          onClick={() => onNavigate(id)}
          className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-xs ${
            page === id
              ? 'bg-indigo-500/15 text-indigo-200'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
