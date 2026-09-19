import { Icon } from './Icons'

const REPO_URL = 'https://github.com/Nitishjha7/code-guardian'

const NAV = [
  { id: 'review', label: 'Review', icon: Icon.review },
  { id: 'pulls', label: 'Pull Requests', icon: Icon.pr },
  { id: 'agents', label: 'Agents', icon: Icon.agents },
  { id: 'history', label: 'History', icon: Icon.clock },
  { id: 'settings', label: 'Settings', icon: Icon.settings },
]

export function Sidebar({ page, onNavigate, backend }) {
  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-ink-700 bg-ink-900 lg:flex">
      <button
        onClick={() => onNavigate('review')}
        className="flex items-center gap-3 px-5 py-5 text-left"
      >
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-600 text-white">
          <Icon.shield width={19} height={19} />
        </span>
        <span className="min-w-0">
          <span className="block text-[15px] font-semibold leading-tight text-white">
            Code Guardian
          </span>
          <span className="block text-[11px] leading-tight text-slate-500">
            Multi-agent code review
          </span>
        </span>
      </button>

      <nav className="flex-1 space-y-1 px-3">
        {NAV.map(({ id, label, icon: Ico }) => {
          const active = page === id
          return (
            <button
              key={id}
              onClick={() => onNavigate(id)}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition ${
                active
                  ? 'bg-brand-600 font-medium text-white'
                  : 'text-slate-400 hover:bg-ink-800 hover:text-slate-200'
              }`}
            >
              <Ico width={17} height={17} />
              {label}
            </button>
          )
        })}
      </nav>

      <div className="p-3">
        <a
          href={REPO_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-3 rounded-xl border border-ink-700 bg-ink-850 p-3.5 transition hover:border-ink-600"
        >
          <Icon.github width={18} height={18} className="shrink-0 text-slate-400" />
          <span className="min-w-0">
            <span className="block text-xs font-medium text-slate-200">Source on GitHub</span>
            <span className="block truncate text-[11px] text-slate-500">
              {backend?.version ? `v${backend.version}` : 'open source'}
            </span>
          </span>
        </a>
      </div>
    </aside>
  )
}

export function TopBar({ backend, onNewReview, onNavigate, filename, language }) {
  const online = backend?.status === 'ok'
  const keyReady = backend?.groq_key_configured

  const state = !online
    ? { dot: 'bg-rose-500', text: 'backend unreachable', tone: 'text-rose-300' }
    : !keyReady
      ? { dot: 'bg-amber-500', text: 'no API key', tone: 'text-amber-300' }
      : { dot: 'bg-emerald-500', text: backend.model, tone: 'text-slate-400' }

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-ink-700 bg-ink-900 px-4">
      <button
        onClick={() => onNavigate('review')}
        className="flex items-center gap-2 text-sm font-semibold text-white lg:hidden"
      >
        <Icon.shield width={18} height={18} className="text-brand-400" />
        Code Guardian
      </button>

      {filename && (
        <span className="hidden items-center gap-2 rounded-lg border border-ink-700 bg-ink-850 px-3 py-1.5 lg:flex">
          <Icon.file width={14} height={14} className="text-slate-500" />
          <span className="font-mono text-xs text-slate-300">{filename}</span>
          {language && (
            <span className="rounded bg-ink-700 px-1.5 py-0.5 font-mono text-[10px] uppercase text-slate-400">
              {language}
            </span>
          )}
        </span>
      )}

      <span
        className={`ml-auto flex items-center gap-2 rounded-lg border border-ink-700 bg-ink-850 px-3 py-1.5 font-mono text-[11px] ${state.tone}`}
        title={online ? 'Backend healthy' : 'Backend unreachable'}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${state.dot}`} />
        {state.text}
      </span>

      <a
        href={REPO_URL}
        target="_blank"
        rel="noopener noreferrer"
        title="Source on GitHub"
        className="grid h-9 w-9 place-items-center rounded-lg border border-ink-700 bg-ink-850 text-slate-400 transition hover:border-ink-600 hover:text-slate-200"
      >
        <Icon.github width={15} height={15} />
      </a>

      <button
        onClick={onNewReview}
        className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3.5 py-2 text-sm font-medium text-white transition hover:bg-brand-500"
      >
        <Icon.sparkle width={15} height={15} />
        <span className="hidden sm:inline">New review</span>
      </button>
    </header>
  )
}

export function MobileNav({ page, onNavigate }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-ink-700 bg-ink-900 px-3 py-2 lg:hidden">
      {NAV.map(({ id, label, icon: Ico }) => (
        <button
          key={id}
          onClick={() => onNavigate(id)}
          className={`flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-xs transition ${
            page === id
              ? 'bg-brand-600 font-medium text-white'
              : 'text-slate-400 hover:bg-ink-800'
          }`}
        >
          <Ico width={14} height={14} />
          {label}
        </button>
      ))}
    </div>
  )
}
