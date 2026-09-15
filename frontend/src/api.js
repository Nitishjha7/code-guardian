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

/**
 * Same review as `review()`, consumed as Server-Sent Events.
 *
 * `fetch` + `ReadableStream`, not `EventSource` — `EventSource` is GET-only,
 * and the payload (arbitrary source code, up to 200KB) has to go in a POST
 * body. `onProgress` fires once per graph node as it completes; the returned
 * promise resolves with the same shape `review()` returns, once the `done`
 * event lands — so a caller that doesn't care about progress can `await` this
 * exactly like the non-streaming call.
 */
export async function reviewStream({ sourceCode, language, forceFullAudit }, onProgress) {
  const res = await fetch(`${BASE}/review/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source_code: sourceCode,
      language,
      force_full_audit: forceFullAudit,
    }),
  })
  if (!res.ok || !res.body) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = body.detail
    } catch {
      // no JSON body — the status line is all there is
    }
    const err = new Error(detail)
    err.status = res.status
    throw err
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE frames are separated by a blank line; a frame may still be
    // incomplete at the end of the buffer if it arrived split across two
    // reads, so only fully-terminated frames are consumed here.
    let sep
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)

      const eventLine = frame.split('\n').find((l) => l.startsWith('event: '))
      const dataLine = frame.split('\n').find((l) => l.startsWith('data: '))
      if (!eventLine || !dataLine) continue

      const kind = eventLine.slice('event: '.length)
      const payload = JSON.parse(dataLine.slice('data: '.length))

      if (kind === 'progress') onProgress?.(payload)
      else if (kind === 'error') throw new Error(payload.detail || 'Review failed')
      else if (kind === 'done') return payload
    }
  }
  throw new Error('Stream ended before a result arrived')
}

export function reviewPR(url) {
  return post('/review-pr', { url })
}
