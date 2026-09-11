import { useEffect, useState } from 'react'

export const PAGES = ['review', 'pulls', 'history', 'agents', 'settings']
const DEFAULT = 'review'

function read() {
  const id = window.location.hash.replace(/^#\/?/, '')
  return PAGES.includes(id) ? id : DEFAULT
}

/**
 * Page state in the URL hash, so a refresh keeps you where you were and the
 * back button works. Hash rather than history.pushState because the app is
 * served as static files behind nginx - real paths would 404 on reload unless
 * every route were rewritten to index.html.
 */
export function useHashPage() {
  const [page, setPage] = useState(read)

  useEffect(() => {
    const onChange = () => setPage(read())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  function navigate(id) {
    const next = PAGES.includes(id) ? id : DEFAULT
    if (next === read()) setPage(next)
    else window.location.hash = `/${next}`
  }

  return [page, navigate]
}
