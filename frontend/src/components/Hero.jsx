import { Icon } from './Icons'
import { CARD } from '../lib/ui'

const PIPELINE = [
  {
    icon: Icon.shield,
    name: 'Security Analysis',
    sub: 'OWASP + Bandit, fused',
    tint: 'text-emerald-300 border-emerald-500/30 bg-emerald-500/10',
  },
  {
    icon: Icon.gauge,
    name: 'Performance Review',
    sub: 'Big-O, N+1, leaks',
    tint: 'text-rose-300 border-rose-500/30 bg-rose-500/10',
  },
  {
    icon: Icon.wrench,
    name: 'Patch Generator',
    sub: 'Exact unified diff',
    tint: 'text-sky-300 border-sky-500/30 bg-sky-500/10',
  },
  {
    icon: Icon.check,
    name: 'Guardrails',
    sub: 'Secrets + tone',
    tint: 'text-violet-300 border-violet-500/30 bg-violet-500/10',
  },
  {
    icon: Icon.github,
    name: 'GitHub PR Bot',
    sub: 'HMAC webhook',
    tint: 'text-slate-300 border-slate-600 bg-slate-800/60',
  },
]

export default function Hero() {
  return (
    <section
      className={`${CARD} relative overflow-hidden bg-gradient-to-br from-indigo-950/50 via-slate-900/60 to-slate-900/40 p-6`}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute -right-20 -top-24 h-72 w-72 rounded-full bg-indigo-500/10 blur-3xl"
      />

      <div className="relative flex flex-wrap items-start gap-6">
        <div className="min-w-[260px] flex-1">
          <h1 className="text-2xl font-semibold tracking-tight text-slate-50 sm:text-3xl">
            Multi-Agent Autonomous Code Reviewer &amp; PR Bot
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-400">
            A supervisor LLM decides which specialist auditors a submission actually
            needs, then they review, score and fix it — automatically.
          </p>
        </div>

        <blockquote className="hidden rounded-lg border border-slate-700/60 bg-slate-900/50 px-5 py-3 text-right xl:block">
          <p className="text-sm italic text-slate-300">“Better Code</p>
          <p className="text-sm italic text-slate-300">A Safer Tomorrow”</p>
        </blockquote>
      </div>

      <div className="relative mt-5 grid gap-3 border-t border-slate-800/80 pt-5 sm:grid-cols-2 lg:grid-cols-5">
        {PIPELINE.map(({ icon: Ico, name, sub, tint }) => (
          <div key={name} className="flex items-center gap-3">
            <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg border ${tint}`}>
              <Ico width={17} height={17} />
            </span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-slate-200">
                {name}
              </span>
              <span className="block truncate text-[11px] text-slate-500">{sub}</span>
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}
