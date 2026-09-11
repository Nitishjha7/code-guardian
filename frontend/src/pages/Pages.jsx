import { useEffect, useState } from 'react'

import { Icon } from '../components/Icons'
import { RiskDonut } from '../components/Summary'
import { graphTopology } from '../api'
import { CARD, band } from '../lib/ui'
import { clear, relativeTime } from '../lib/history'

/* ------------------------------------------------------------------ Agents */

const AGENTS = [
  {
    name: 'Supervisor',
    file: 'agents/supervisor.py',
    kind: 'Router',
    tint: 'border-indigo-500/30 bg-indigo-500/10 text-indigo-300',
    icon: Icon.agents,
    what: 'An LLM bound to the specialists as tools. It decides at runtime which audits a submission needs — one, both, or neither.',
    criteria: [
      'Tool docstrings are the routing logic, written as criteria',
      'temperature 0 — routing is classification, not creative writing',
      'looks_high_stakes() forces both auditors on auth/DB/exec surfaces',
      'force_full_audit bypasses routing entirely',
    ],
  },
  {
    name: 'Security Agent',
    file: 'agents/security_agent.py',
    kind: 'Auditor',
    tint: 'border-rose-500/30 bg-rose-500/10 text-rose-300',
    icon: Icon.shield,
    what: 'OWASP Top 10, injection, hardcoded secrets, insecure deserialization, weak crypto — with Bandit fused in.',
    criteria: [
      'LLM findings merged with Bandit by line containment',
      'Agreement tags the finding llm+bandit:<rule> and escalates severity',
      'Bandit cannot hallucinate; the LLM catches what no rule encodes',
      'Bandit is Python-only — elsewhere the audit is the LLM alone',
    ],
  },
  {
    name: 'Performance Agent',
    file: 'agents/performance_agent.py',
    kind: 'Auditor',
    tint: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
    icon: Icon.gauge,
    what: 'Algorithmic complexity, N+1 queries, memory growth, unclosed resources, missing caching.',
    criteria: [
      'Reports Big-O before and after where it applies',
      'Explicitly told not to report security issues',
      'Routing recall here is 50% — the measured weak spot',
    ],
  },
  {
    name: 'Patch Generator',
    file: 'agents/patch_generator.py',
    kind: 'Synthesis',
    tint: 'border-sky-500/30 bg-sky-500/10 text-sky-300',
    icon: Icon.wrench,
    what: 'Rewrites the file to fix every finding it safely can, preserving business logic and public API.',
    criteria: [
      'The model returns the file; difflib computes the diff',
      'LLM-authored unified diffs routinely fail to apply',
      'Unfixable findings get a TODO(code-guardian) comment, not silence',
    ],
  },
  {
    name: 'Test Generator',
    file: 'agents/test_generator.py',
    kind: 'Synthesis',
    tint: 'border-violet-500/30 bg-violet-500/10 text-violet-300',
    icon: Icon.review,
    what: 'One regression test per Critical/High security finding, written to fail before the fix and pass after.',
    criteria: [
      'Generated, never executed — sandboxing is a separate project',
      'A node, not a tool: "are there findings?" is a boolean, not judgement',
      'Performance findings excluded — LLM-picked thresholds are flaky',
    ],
  },
  {
    name: 'Guardrails',
    file: 'guardrails_config/validators.py',
    kind: 'Safety',
    tint: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    icon: Icon.check,
    what: 'Scans every outbound diff, patch and comment for credentials, and checks the tone of automated review text.',
    criteria: [
      '11 secret patterns; secrets are redacted, not dropped',
      'Placeholder-aware — os.environ[...] is what a fix should look like',
      'Tone is flagged, never rewritten; silent edits hide prompt regressions',
      'Guardrails AI optional; engine is always named in the report',
    ],
  },
]

export function AgentsPage() {
  const [mermaid, setMermaid] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    graphTopology()
      .then((d) => setMermaid(d.mermaid))
      .catch((e) => setError(e.message))
  }, [])

  return (
    <div className="space-y-5">
      <PageHead
        title="Agents"
        subtitle="Six pieces. The supervisor is the only one the model itself controls."
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {AGENTS.map((a) => (
          <div key={a.name} className={`${CARD} p-5`}>
            <div className="flex items-center gap-3">
              <span className={`grid h-10 w-10 place-items-center rounded-lg border ${a.tint}`}>
                <a.icon width={19} height={19} />
              </span>
              <div className="min-w-0">
                <h3 className="truncate text-sm font-medium text-slate-100">{a.name}</h3>
                <code className="text-[10px] text-slate-500">{a.file}</code>
              </div>
              <span className="ml-auto rounded-md border border-slate-700 bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400">
                {a.kind}
              </span>
            </div>

            <p className="mt-3 text-xs leading-relaxed text-slate-400">{a.what}</p>

            <ul className="mt-3 space-y-1.5 border-t border-slate-800 pt-3">
              {a.criteria.map((c) => (
                <li key={c} className="flex gap-2 text-[11px] leading-relaxed text-slate-500">
                  <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-slate-600" />
                  {c}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className={`${CARD} p-5`}>
        <h3 className="text-sm font-medium text-slate-100">Compiled graph</h3>
        <p className="mt-1 text-xs text-slate-500">
          Straight from <code>/api/graph</code> — this is the topology the backend is
          actually running, not a drawing of it.
        </p>
        {error ? (
          <p className="mt-3 text-xs text-rose-300">{error}</p>
        ) : (
          <pre className="mt-3 overflow-x-auto rounded-lg border border-slate-800 bg-[#0d1117] p-4 text-[11px] leading-relaxed text-slate-400">
            {mermaid || 'Loading…'}
          </pre>
        )}
      </div>
    </div>
  )
}

/* --------------------------------------------------------------- Analytics */

export function AnalyticsPage({ entries, onChanged }) {
  if (entries.length === 0) {
    return (
      <div className="space-y-5">
        <PageHead title="Analytics" subtitle="Built from reviews run in this browser." />
        <EmptyCard
          icon={Icon.chart}
          title="No reviews yet"
          text="Run a review and the numbers here fill in. Nothing is fabricated — every figure comes from a review that actually ran."
        />
      </div>
    )
  }

  const scored = entries.filter((e) => e.complete && e.score !== null)
  const avg = scored.length
    ? Math.round(scored.reduce((n, e) => n + e.score, 0) / scored.length)
    : null
  const security = entries.reduce((n, e) => n + e.security, 0)
  const performance = entries.reduce((n, e) => n + e.performance, 0)
  const confirmed = entries.reduce((n, e) => n + (e.confirmed || 0), 0)
  const incomplete = entries.filter((e) => !e.complete).length

  const timed = entries.filter((e) => e.seconds)
  const avgTime = timed.length
    ? (timed.reduce((n, e) => n + e.seconds, 0) / timed.length).toFixed(1)
    : null

  const bands = {}
  for (const e of entries) bands[e.band] = (bands[e.band] || 0) + 1

  const routing = { security_audit: 0, performance_audit: 0, none: 0 }
  for (const e of entries) {
    if (e.kind !== 'review') continue
    if (!e.routed?.length) routing.none += 1
    for (const r of e.routed || []) if (r in routing) routing[r] += 1
  }

  return (
    <div className="space-y-5">
      <PageHead
        title="Analytics"
        subtitle={`${entries.length} review${entries.length === 1 ? '' : 's'} run in this browser.`}
        action={
          <button
            onClick={() => onChanged(clear())}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-400 hover:bg-slate-800"
          >
            <Icon.trash width={13} height={13} />
            Clear history
          </button>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Tile label="Average risk score" value={avg ?? '—'} suffix="/100" />
        <Tile label="Security findings" value={security} />
        <Tile label="Performance findings" value={performance} />
        <Tile label="Average duration" value={avgTime ?? '—'} suffix="s" />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className={`${CARD} p-5`}>
          <h3 className="text-sm font-medium text-slate-100">Risk bands</h3>
          <div className="mt-4 space-y-2.5">
            {Object.entries(bands)
              .sort((a, b) => b[1] - a[1])
              .map(([name, count]) => {
                const style = band(name)
                const pct = Math.round((count / entries.length) * 100)
                return (
                  <div key={name}>
                    <div className="flex justify-between text-xs">
                      <span className={style.text}>{style.label}</span>
                      <span className="tabular-nums text-slate-500">{count}</span>
                    </div>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-800">
                      <div
                        className="h-full rounded-full"
                        style={{ width: `${pct}%`, background: style.ring }}
                      />
                    </div>
                  </div>
                )
              })}
          </div>
        </div>

        <div className={`${CARD} p-5`}>
          <h3 className="text-sm font-medium text-slate-100">Router decisions</h3>
          <p className="mt-1 text-[11px] text-slate-500">
            How often each auditor was actually chosen.
          </p>
          <div className="mt-4 space-y-3 text-xs">
            <Row label="Security audit run" value={routing.security_audit} />
            <Row label="Performance audit run" value={routing.performance_audit} />
            <Row label="No auditor needed" value={routing.none} />
          </div>
        </div>

        <div className={`${CARD} p-5`}>
          <h3 className="text-sm font-medium text-slate-100">Quality signals</h3>
          <div className="mt-4 space-y-3 text-xs">
            <Row label="Confirmed by both engines" value={confirmed} tone="text-emerald-300" />
            <Row
              label="Incomplete reviews"
              value={incomplete}
              tone={incomplete ? 'text-rose-300' : 'text-slate-300'}
            />
          </div>
          <p className="mt-4 border-t border-slate-800 pt-3 text-[11px] leading-relaxed text-slate-500">
            Cost per review is deliberately absent: it has not been measured, and this
            project does not display numbers it has not measured.
          </p>
        </div>
      </div>

      <div className={CARD}>
        <h3 className="px-5 py-4 text-sm font-medium text-slate-100">All reviews</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-y border-slate-800 text-slate-500">
              <tr>
                <Th>When</Th>
                <Th>Target</Th>
                <Th>Lang</Th>
                <Th>Risk</Th>
                <Th>Sec</Th>
                <Th>Perf</Th>
                <Th>Time</Th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => {
                const style = band(e.band)
                return (
                  <tr key={e.id} className="border-b border-slate-800/60 hover:bg-slate-800/30">
                    <Td className="text-slate-500">{relativeTime(e.at)}</Td>
                    <Td className="max-w-[16rem] truncate text-slate-300">{e.label}</Td>
                    <Td className="text-slate-500">{e.language}</Td>
                    <Td>
                      <span className={style.text}>
                        {e.complete && e.score !== null ? e.score : '—'}
                      </span>
                    </Td>
                    <Td className="tabular-nums text-slate-400">{e.security}</Td>
                    <Td className="tabular-nums text-slate-400">{e.performance}</Td>
                    <Td className="tabular-nums text-slate-500">
                      {e.seconds ? `${e.seconds}s` : '—'}
                    </Td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------- Settings */

export function SettingsPage({ backend }) {
  const g = backend?.guardrails || {}
  const bot = backend?.pr_bot || {}

  return (
    <div className="space-y-5">
      <PageHead
        title="Settings"
        subtitle="Live backend configuration. Everything here is read from /api/health."
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <div className={`${CARD} p-5`}>
          <h3 className="text-sm font-medium text-slate-100">Engine</h3>
          <dl className="mt-4 space-y-3 text-xs">
            <Field label="Model" value={backend?.model || '—'} />
            <Field
              label="GROQ_API_KEY"
              value={backend?.groq_key_configured ? 'configured' : 'not set'}
              ok={backend?.groq_key_configured}
            />
            <Field label="Version" value={backend?.version || '—'} />
          </dl>
          <p className="mt-4 border-t border-slate-800 pt-3 text-[11px] leading-relaxed text-slate-500">
            Groq retires model ids. If audits start failing, check which models your key
            can see before assuming the code broke.
          </p>
        </div>

        <div className={`${CARD} p-5`}>
          <h3 className="text-sm font-medium text-slate-100">Guardrails</h3>
          <dl className="mt-4 space-y-3 text-xs">
            <Field
              label="Guardrails AI installed"
              value={g.guardrails_ai_installed ? 'yes' : 'no (using local scanner)'}
              ok={true}
            />
            <Field label="Secret patterns" value={g.secret_patterns ?? '—'} />
            <Field label="Tone patterns" value={g.tone_patterns ?? '—'} />
          </dl>
          <p className="mt-4 border-t border-slate-800 pt-3 text-[11px] leading-relaxed text-slate-500">
            The local scanner is the default because some Guardrails AI validators pull a
            full torch install. The report always names which engine ran.
          </p>
        </div>

        <div className={`${CARD} p-5 lg:col-span-2`}>
          <h3 className="text-sm font-medium text-slate-100">GitHub PR bot</h3>
          <dl className="mt-4 grid gap-3 text-xs sm:grid-cols-2">
            <Field
              label="GITHUB_TOKEN"
              value={bot.github_token_configured ? 'configured' : 'not set'}
              ok={bot.github_token_configured}
            />
            <Field
              label="GITHUB_WEBHOOK_SECRET"
              value={bot.webhook_secret_configured ? 'configured' : 'not set'}
              ok={bot.webhook_secret_configured}
            />
          </dl>
          <p className="mt-4 border-t border-slate-800 pt-3 text-[11px] leading-relaxed text-slate-500">
            Both are set in <code className="text-slate-400">backend/.env</code>. The
            webhook <b className="text-slate-400">fails closed</b>: with no secret it
            returns 503 and processes nothing, because a public URL that runs LLM calls
            and writes comments is a denial-of-wallet vector.
          </p>
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------- Repository / Pull reqs */

export function TokenGatedPage({ title, subtitle, icon, blurb, tokenReady, children }) {
  if (!tokenReady) {
    return (
      <div className="space-y-5">
        <PageHead title={title} subtitle={subtitle} />
        <EmptyCard
          icon={icon}
          title="GITHUB_TOKEN is not set"
          text={blurb}
          code={`# backend/.env
GITHUB_TOKEN=ghp_...`}
        />
      </div>
    )
  }
  return (
    <div className="space-y-5">
      <PageHead title={title} subtitle={subtitle} />
      {children}
    </div>
  )
}

/* ------------------------------------------------------------------ bits -- */

export function PageHead({ title, subtitle, action }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div>
        <h1 className="text-xl font-semibold text-slate-50">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {action && <div className="ml-auto">{action}</div>}
    </div>
  )
}

export function EmptyCard({ icon: Ico, title, text, code }) {
  return (
    <div className={`${CARD} px-6 py-14 text-center`}>
      <span className="mx-auto grid h-12 w-12 place-items-center rounded-xl border border-slate-800 bg-slate-900 text-slate-600">
        <Ico width={22} height={22} />
      </span>
      <h3 className="mt-4 text-sm font-medium text-slate-200">{title}</h3>
      <p className="mx-auto mt-2 max-w-md text-xs leading-relaxed text-slate-500">{text}</p>
      {code && (
        <pre className="mx-auto mt-4 w-fit rounded-lg border border-slate-800 bg-[#0d1117] px-4 py-3 text-left text-[11px] text-slate-400">
          {code}
        </pre>
      )}
    </div>
  )
}

function Tile({ label, value, suffix }) {
  return (
    <div className={`${CARD} p-5`}>
      <div className="text-2xl font-semibold tabular-nums text-slate-50">
        {value}
        {suffix && value !== '—' && (
          <span className="text-sm text-slate-500">{suffix}</span>
        )}
      </div>
      <div className="mt-1 text-xs text-slate-500">{label}</div>
    </div>
  )
}

function Row({ label, value, tone = 'text-slate-300' }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-500">{label}</span>
      <span className={`font-semibold tabular-nums ${tone}`}>{value}</span>
    </div>
  )
}

function Field({ label, value, ok }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-slate-500">{label}</dt>
      <dd
        className={`truncate font-mono ${
          ok === undefined ? 'text-slate-300' : ok ? 'text-emerald-300' : 'text-amber-300'
        }`}
      >
        {value}
      </dd>
    </div>
  )
}

function Th({ children }) {
  return <th className="px-5 py-2.5 font-medium">{children}</th>
}

function Td({ children, className = '' }) {
  return <td className={`px-5 py-2.5 ${className}`}>{children}</td>
}

export { RiskDonut }
