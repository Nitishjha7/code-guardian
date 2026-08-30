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
    throw new Error(detail)
  }
  return res.json()
}

export function health() {
  return request('/health')
}

export function review({ sourceCode, language, forceFullAudit }) {
  return request('/review', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source_code: sourceCode,
      language,
      force_full_audit: forceFullAudit,
    }),
  })
}
