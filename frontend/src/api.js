const BASE = import.meta.env.VITE_API_URL || '/api'

async function request(path, options) {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = body.detail
    } catch {
      // response had no JSON body; the status line is all we have
    }
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  return res.json()
}

function post(path, body) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function health() {
  return request('/health')
}

export function graphTopology() {
  return request('/graph')
}

export function review({ sourceCode, language, forceFullAudit }) {
  return post('/review', {
    source_code: sourceCode,
    language,
    force_full_audit: forceFullAudit,
  })
}

export function reviewPR(url) {
  return post('/review-pr', { url })
}
