/**
 * Review history, kept in this browser only.
 *
 * The backend is stateless by design (see docs/ROADMAP.md - persistence is
 * Phase 4), so "Recent Activity" and the Analytics page are built from what
 * this browser has actually run. That keeps them real: every row below is a
 * review that happened, not a placeholder.
 *
 * Consequences worth knowing rather than hiding: clearing site data wipes it,
 * and it does not follow you to another machine.
 */

const KEY = 'code-guardian:history:v1'
const LIMIT = 50

function read() {
  try {
    const raw = localStorage.getItem(KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    // Private windows and blocked site data both land here.
    return []
  }
}

function write(entries) {
  try {
    localStorage.setItem(KEY, JSON.stringify(entries.slice(0, LIMIT)))
  } catch {
    // Storage full or unavailable - the app must keep working regardless.
  }
}

export function load() {
  return read()
}

export function record(entry) {
  const entries = [{ id: crypto.randomUUID(), at: Date.now(), ...entry }, ...read()]
  write(entries)
  return entries.slice(0, LIMIT)
}

export function clear() {
  try {
    localStorage.removeItem(KEY)
  } catch {
    /* nothing to do */
  }
  return []
}

/** Summarise a /api/review response into a history row. */
export function fromReview(result, { label, language }) {
  const security = result.security_issues?.length || 0
  const performance = result.performance_issues?.length || 0
  return {
    kind: 'review',
    label,
    language,
    score: result.risk?.complete ? result.risk.score : null,
    band: result.risk?.band || 'none',
    complete: result.risk?.complete !== false,
    security,
    performance,
    confirmed: (result.security_issues || []).filter((f) =>
      String(f.source || '').startsWith('llm+'),
    ).length,
    routed: result.routed_to || [],
    failed: result.failed_audits || [],
    patchLines: result.diff ? result.diff.split('\n').length : 0,
    testLines: result.generated_tests ? result.generated_tests.split('\n').length : 0,
    seconds: extractSeconds(result.logs),
  }
}

/** Summarise a /api/review-pr response into a history row. */
export function fromPR(result) {
  const files = result.files || []
  const scored = files.filter((f) => f.risk?.complete)
  const worst = scored.reduce(
    (acc, f) => (acc === null || f.risk.score > acc.risk.score ? f : acc),
    null,
  )
  return {
    kind: 'pr',
    label: `${result.repository}#${result.number}`,
    language: 'mixed',
    score: worst ? worst.risk.score : null,
    band: worst ? worst.risk.band : 'unknown',
    complete: scored.length === files.length,
    security: files.reduce((n, f) => n + (f.security_issues?.length || 0), 0),
    performance: files.reduce((n, f) => n + (f.performance_issues?.length || 0), 0),
    confirmed: files.reduce(
      (n, f) =>
        n +
        (f.security_issues || []).filter((x) =>
          String(x.source || '').startsWith('llm+'),
        ).length,
      0,
    ),
    files: files.length,
    routed: [],
    failed: files.flatMap((f) => f.failed_audits || []),
    patchLines: 0,
    testLines: 0,
    seconds: null,
  }
}

function extractSeconds(logs) {
  const line = (logs || []).find((l) => l.includes('Review finished in'))
  if (!line) return null
  const match = line.match(/([\d.]+)s/)
  return match ? Number(match[1]) : null
}

export function relativeTime(ts) {
  const seconds = Math.max(1, Math.round((Date.now() - ts) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}
