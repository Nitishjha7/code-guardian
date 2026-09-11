"""Held-out routing cases — written to be scored, never to be tuned against.

The dev set in :mod:`evals.routing_cases` was used to improve the tool
docstrings (performance recall moved 33% -> 50% that way), which makes its
numbers optimistic. This set exists so there is one honest number.

**The rule for this file: if a case fails, the case does not change and neither
does the prompt it failed on.** A held-out set that gets edited after you see
the score is just a slower dev set. Fixing a genuine mislabel is the only
allowed edit, and it should be obvious enough that you would have made it
before running anything.

These cases are deliberately harder than the dev set in three ways:

* **Different languages.** Go, Java, SQL, TypeScript, shell - not just the
  Python and JS the docstrings were written against.
* **Adversarial surface words.** Several no-audit cases contain words like
  "token", "auth" or "query" in harmless positions, because the routing
  backstop keys off exactly those. They test whether the *model* is reading
  the code or pattern-matching vocabulary.
* **Split cases.** Code that needs one auditor while loudly resembling the
  other - a security fix inside a hot loop, a cache with no security surface.
"""

from __future__ import annotations

from .routing_cases import RoutingCase

HOLDOUT_CASES: list[RoutingCase] = [
    # ---------------------------------------------------- security, non-Python
    RoutingCase(
        id="go-command-injection",
        language="go",
        needs_security=True,
        needs_performance=False,
        code='''func Backup(name string) error {
	cmd := exec.Command("sh", "-c", "tar -czf /backups/"+name+".tar.gz /data")
	return cmd.Run()
}
''',
    ),
    RoutingCase(
        id="java-xxe",
        language="java",
        needs_security=True,
        needs_performance=False,
        code='''public Document parse(InputStream xml) throws Exception {
    DocumentBuilderFactory f = DocumentBuilderFactory.newInstance();
    return f.newDocumentBuilder().parse(xml);
}
''',
    ),
    RoutingCase(
        id="sql-grant-all",
        language="sql",
        needs_security=True,
        needs_performance=False,
        code='''CREATE USER reporting WITH PASSWORD 'reporting123';
GRANT ALL PRIVILEGES ON DATABASE production TO reporting;
GRANT ALL ON SCHEMA public TO PUBLIC;
''',
    ),
    RoutingCase(
        id="ts-open-redirect",
        language="typescript",
        needs_security=True,
        needs_performance=False,
        code='''export function handleLogin(req: Request, res: Response) {
  const next = req.query.next as string
  res.redirect(next ?? '/dashboard')
}
''',
    ),
    RoutingCase(
        id="shell-curl-pipe-sh",
        language="bash",
        needs_security=True,
        needs_performance=False,
        code='''#!/bin/bash
VERSION=$(cat ./version)
curl -sL "https://updates.example.com/$VERSION/install.sh" | sh
''',
    ),
    RoutingCase(
        id="ts-jwt-in-localstorage",
        language="typescript",
        needs_security=True,
        needs_performance=False,
        note="XSS-exfiltratable token storage",
        code='''export function persistSession(token: string) {
  localStorage.setItem('access_token', token)
  document.cookie = `session=${token}; path=/`
}
''',
    ),
    RoutingCase(
        id="python-ssrf-fetch",
        language="python",
        needs_security=True,
        needs_performance=False,
        code='''def fetch_preview(url):
    resp = requests.get(url, timeout=5)
    return resp.text[:2000]
''',
    ),
    # ------------------------------------------------- performance, non-Python
    RoutingCase(
        id="go-string-concat-loop",
        language="go",
        needs_security=False,
        needs_performance=True,
        code='''func Join(parts []string) string {
	out := ""
	for _, p := range parts {
		out += p + ","
	}
	return out
}
''',
    ),
    RoutingCase(
        id="java-boxing-in-loop",
        language="java",
        needs_security=False,
        needs_performance=True,
        code='''public long total(List<Integer> values) {
    Long sum = 0L;
    for (Integer v : values) {
        sum += v;
    }
    return sum;
}
''',
    ),
    RoutingCase(
        id="sql-missing-index-join",
        language="sql",
        needs_security=False,
        needs_performance=True,
        code='''SELECT o.id, c.name
FROM orders o
JOIN customers c ON c.email = LOWER(TRIM(o.contact_email))
WHERE o.created_at > NOW() - INTERVAL '30 days';
''',
    ),
    RoutingCase(
        id="ts-await-in-loop",
        language="typescript",
        needs_security=False,
        needs_performance=True,
        code='''export async function loadAll(ids: string[]) {
  const out = []
  for (const id of ids) {
    out.push(await fetchRecord(id))
  }
  return out
}
''',
    ),
    RoutingCase(
        id="python-readlines-whole-file",
        language="python",
        needs_security=False,
        needs_performance=True,
        code='''def count_errors(path):
    with open(path) as fh:
        lines = fh.readlines()
    return len([l for l in lines if "ERROR" in l])
''',
    ),
    # ------------------------------------------------------------------- both
    RoutingCase(
        id="python-auth-check-in-loop",
        language="python",
        needs_security=True,
        needs_performance=True,
        note="broken authz AND a query per item",
        code='''def visible_docs(user_id, doc_ids):
    out = []
    for doc_id in doc_ids:
        doc = db.execute("SELECT * FROM docs WHERE id = %s" % doc_id).fetchone()
        if doc["owner"] or True:
            out.append(doc)
    return out
''',
    ),
    RoutingCase(
        id="js-unbounded-cache-of-tokens",
        language="javascript",
        needs_security=True,
        needs_performance=True,
        code='''const sessions = {}

export function remember(token, user) {
  sessions[token] = { user, raw: token }
  return Object.keys(sessions).find((t) => sessions[t].user === user)
}
''',
    ),
    # ------------------------------------- neither, with adversarial vocabulary
    RoutingCase(
        id="token-as-lexer-term",
        language="python",
        needs_security=False,
        needs_performance=False,
        note='"token" here is a parser token, not a credential',
        code='''from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    column: int
''',
    ),
    RoutingCase(
        id="author-field-not-auth",
        language="typescript",
        needs_security=False,
        needs_performance=False,
        note='"author" contains "auth" as a substring',
        code='''export interface Post {
  title: string
  author: string
  publishedAt: string
}
''',
    ),
    RoutingCase(
        id="query-selector-styling",
        language="css",
        needs_security=False,
        needs_performance=False,
        note='"query" appears as @media query',
        code='''@media (min-width: 960px) {
  .sidebar {
    position: sticky;
    top: 0;
  }
}
''',
    ),
    RoutingCase(
        id="yaml-ci-config",
        language="yaml",
        needs_security=False,
        needs_performance=False,
        code='''name: lint
on: [push]
jobs:
  ruff:
    runs-on: ubuntu-latest
''',
    ),
    RoutingCase(
        id="enum-of-roles",
        language="java",
        needs_security=False,
        needs_performance=False,
        note='"role" and "admin" with no logic attached',
        code='''public enum Role {
    VIEWER,
    EDITOR,
    ADMIN
}
''',
    ),
    RoutingCase(
        id="markdown-changelog",
        language="markdown",
        needs_security=False,
        needs_performance=False,
        code='''## 2.3.0

- Added password reset emails
- Fixed a slow query on the orders page
''',
    ),
]
