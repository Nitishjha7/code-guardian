/**
 * The seams that actually broke while building this.
 *
 * Every case corresponds to a real defect: "New review" leaving the editor
 * populated, a failed audit being rendered as a clean pass, and the Pull
 * Requests page opening on the code editor instead of the PR input.
 *
 * Queries use getAllBy where the app renders a label more than once on
 * purpose - the sidebar and the mobile nav both exist in the tree, and a
 * failed audit is reported in three places deliberately.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App'

const HEALTH = {
  status: 'ok',
  version: '0.1.0',
  model: 'openai/gpt-oss-120b',
  fallback_models: [],
  groq_key_configured: true,
  guardrails: { guardrails_ai_installed: false, secret_patterns: 13, tone_patterns: 3 },
  pr_bot: { github_token_configured: true, webhook_secret_configured: true },
}

function reviewResult(overrides = {}) {
  return {
    language: 'python',
    routed_to: ['security_audit'],
    risk: { score: 63, band: 'high', complete: true, size_modifier: 1, drivers: [], note: '' },
    failed_audits: [],
    audit_errors: [],
    security_issues: [
      {
        title: 'SQL injection in get_user',
        severity: 'Critical',
        line_hint: 'cursor.execute(...)',
        explanation: 'User input is concatenated into the query.',
        recommendation: 'Use a parameterised query.',
        source: 'llm+bandit:B608',
        complexity_before: 'n/a',
        complexity_after: 'n/a',
        memory_note: '',
      },
    ],
    performance_issues: [],
    fixed_code: 'patched',
    diff: '--- a\n+++ b\n-bad\n+good',
    summary_report: '## Code Guardian Review',
    generated_tests: '',
    tests_note: '',
    guardrail_report: { passed: true, engine: 'local', secrets_found: [], redactions: 0, tone_flags: [] },
    logs: ['Supervisor: routed.', 'Review finished in 2.10s.'],
    token_usage: {},
    ...overrides,
  }
}

/** Serialise a result the way /api/review/stream does. */
function sseBody(result) {
  return (
    'event: progress\ndata: {"node":"supervisor","label":"Routing","elapsed_ms":10}\n\n' +
    'event: done\ndata: ' + JSON.stringify(result) + '\n\n'
  )
}

function mockFetch(result = reviewResult()) {
  return vi.fn(async (url) => {
    const u = String(url)
    if (u.endsWith('/health')) {
      return { ok: true, status: 200, json: async () => HEALTH }
    }
    if (u.includes('/review/stream')) {
      const bytes = new TextEncoder().encode(sseBody(result))
      let sent = false
      return {
        ok: true,
        status: 200,
        body: {
          getReader: () => ({
            read: async () => {
              if (sent) return { done: true, value: undefined }
              sent = true
              return { done: false, value: bytes }
            },
            releaseLock: () => {},
          }),
        },
      }
    }
    if (u.includes('/graph')) {
      return { ok: true, status: 200, json: async () => ({ mermaid: 'graph TD;' }) }
    }
    return { ok: true, status: 200, json: async () => ({}) }
  })
}

/** The sidebar and the mobile nav both render; click the first. */
async function navigate(user, name) {
  const buttons = await screen.findAllByRole('button', { name })
  await user.click(buttons[0])
}

beforeEach(() => {
  localStorage.clear()
  window.scrollTo = vi.fn()
  // The page lives in the URL hash, and jsdom keeps one window across the
  // file - without this, a test that navigated away leaves the next one
  // starting on that page instead of Review.
  window.location.hash = ""
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Review page', () => {
  it('loads a sample into the editor on first paint', async () => {
    global.fetch = mockFetch()
    render(<App />)
    const editor = await screen.findByTestId('code-editor')
    expect(editor.value).toContain('sqlite3')
  })

  it('runs a review and shows the finding with its severity and corroboration', async () => {
    global.fetch = mockFetch()
    const user = userEvent.setup()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: /run review/i }))

    expect(await screen.findByText(/SQL injection in get_user/i)).toBeInTheDocument()
    expect(screen.getAllByText('Critical').length).toBeGreaterThan(0)
    // llm+bandit means two engines agreed; the badge is how a reader sees that.
    expect(screen.getAllByText(/confirmed/i).length).toBeGreaterThan(0)
  })

  it('"New review" clears the editor, not just the results', async () => {
    // The original bug: it reset the result panels and left the same code
    // loaded, so on the Review page the button looked like it did nothing.
    global.fetch = mockFetch()
    const user = userEvent.setup()
    render(<App />)

    const editor = await screen.findByTestId('code-editor')
    expect(editor.value.length).toBeGreaterThan(0)

    await navigate(user, /new review/i)
    await waitFor(() => expect(screen.getByTestId('code-editor').value).toBe(''))
  })

  it('disables Run while the editor is empty', async () => {
    global.fetch = mockFetch()
    const user = userEvent.setup()
    render(<App />)

    await screen.findByTestId('code-editor')
    await navigate(user, /new review/i)

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /run review/i })).toBeDisabled(),
    )
  })
})

describe('Failed audits', () => {
  it('never renders a failed audit as a clean pass', async () => {
    // The defect this whole project guards against: an audit that raised must
    // not read as "no issues found".
    global.fetch = mockFetch(
      reviewResult({
        routed_to: ['security_audit'],
        failed_audits: ['security_audit'],
        audit_errors: ['security_audit: RateLimitError'],
        security_issues: [],
        risk: {
          score: 0,
          band: 'unknown',
          complete: false,
          size_modifier: 1,
          drivers: [],
          note: 'security_audit did not run',
        },
      }),
    )
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /run review/i }))

    await waitFor(() =>
      expect(screen.getAllByText(/did not run|failed/i).length).toBeGreaterThan(0),
    )
    expect(screen.queryByText(/^No issues found$/i)).not.toBeInTheDocument()
  })
})

describe('Navigation', () => {
  it('the Pull Requests page opens on the PR input, not the code editor', async () => {
    global.fetch = mockFetch()
    const user = userEvent.setup()
    render(<App />)

    await screen.findByTestId('code-editor')
    await navigate(user, /^pull requests$/i)

    expect(
      await screen.findByPlaceholderText(/github\.com\/owner\/repo\/pull/i),
    ).toBeInTheDocument()
  })

  it('shows the compiled graph on the Agents page', async () => {
    global.fetch = mockFetch()
    const user = userEvent.setup()
    render(<App />)

    await screen.findByTestId('code-editor')
    await navigate(user, /^agents$/i)

    expect((await screen.findAllByText(/compiled graph/i)).length).toBeGreaterThan(0)
  })
})
