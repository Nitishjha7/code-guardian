"""Labelled snippets for measuring the supervisor's routing quality.

docs/TECHNICAL_SPEC.md §3a names three mitigations for the router's false-negative
risk. This file is the third one: a labelled set that makes the risk *measurable*
instead of merely acknowledged.

Labelling rule: ``needs_security`` / ``needs_performance`` say whether a
competent human reviewer would consider that audit **worth paying for** on this
snippet - not whether the auditor would necessarily find something. A snippet
that handles user input needs a security audit even if it happens to be safe;
that is exactly the judgement the router has to make without seeing the findings.

The metric that matters is **security recall**. A false negative (skipping the
security audit on code that needed one) is a missed vulnerability; a false
positive is a few wasted cents.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoutingCase:
    id: str
    language: str
    code: str
    needs_security: bool
    needs_performance: bool
    note: str = ""


CASES: list[RoutingCase] = [
    # ---------------------------------------------------------------- security
    RoutingCase(
        id="sql-injection",
        language="python",
        needs_security=True,
        needs_performance=False,
        note="classic string-concatenated query",
        code='''def find_user(conn, name):
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE name = '" + name + "'")
    return cur.fetchone()
''',
    ),
    RoutingCase(
        id="command-injection",
        language="python",
        needs_security=True,
        needs_performance=False,
        code='''import os

def convert(filename):
    os.system("ffmpeg -i " + filename + " out.mp4")
''',
    ),
    RoutingCase(
        id="insecure-deserialization",
        language="python",
        needs_security=True,
        needs_performance=False,
        code='''import pickle

def load_session(blob):
    return pickle.loads(blob)
''',
    ),
    RoutingCase(
        id="hardcoded-credentials",
        language="python",
        needs_security=True,
        needs_performance=False,
        code='''STRIPE_KEY = "sk_live_4eC39HqLyjWDarjtT1zdp7dc"
SMTP_PASSWORD = "hunter2-prod"


def client():
    return Stripe(STRIPE_KEY)
''',
    ),
    RoutingCase(
        id="path-traversal",
        language="python",
        needs_security=True,
        needs_performance=False,
        code='''def read_upload(request):
    name = request.args["file"]
    with open("/var/uploads/" + name) as fh:
        return fh.read()
''',
    ),
    RoutingCase(
        id="jwt-verification-disabled",
        language="python",
        needs_security=True,
        needs_performance=False,
        code='''import jwt

def decode(token):
    return jwt.decode(token, options={"verify_signature": False})
''',
    ),
    RoutingCase(
        id="xss-dangerous-html",
        language="javascript",
        needs_security=True,
        needs_performance=False,
        note="React sink fed straight from props",
        code='''export function Comment({ body }) {
  return <div dangerouslySetInnerHTML={{ __html: body }} />
}
''',
    ),
    RoutingCase(
        id="missing-authorization",
        language="python",
        needs_security=True,
        needs_performance=False,
        code='''@app.post("/admin/users/{user_id}/delete")
def delete_user(user_id: int):
    db.delete(User, user_id)
    return {"deleted": user_id}
''',
    ),
    RoutingCase(
        id="weak-password-hashing",
        language="python",
        needs_security=True,
        needs_performance=False,
        code='''import hashlib

def store_password(raw):
    return hashlib.sha1(raw.encode()).hexdigest()
''',
    ),
    # ------------------------------------------------------------- performance
    RoutingCase(
        id="quadratic-join",
        language="javascript",
        needs_security=False,
        needs_performance=True,
        code='''function attachTotals(users, events) {
  return users.map((u) => ({
    ...u,
    total: events.filter((e) => e.userId === u.id).length,
  }))
}
''',
    ),
    RoutingCase(
        id="n-plus-one-orm",
        language="python",
        needs_security=False,
        needs_performance=True,
        code='''def order_summaries(orders):
    out = []
    for order in orders:
        out.append({"id": order.id, "customer": order.customer.name})
    return out
''',
    ),
    RoutingCase(
        id="unclosed-file-handle",
        language="python",
        needs_security=False,
        needs_performance=True,
        code='''def read_all(paths):
    data = []
    for path in paths:
        fh = open(path)
        data.append(fh.read())
    return data
''',
    ),
    RoutingCase(
        id="quadratic-string-build",
        language="python",
        needs_security=False,
        needs_performance=True,
        code='''def render_rows(rows):
    html = ""
    for row in rows:
        html += "<tr><td>" + str(row) + "</td></tr>"
    return html
''',
    ),
    RoutingCase(
        id="sort-inside-loop",
        language="javascript",
        needs_security=False,
        needs_performance=True,
        code='''function topPerGroup(groups) {
  const out = []
  for (const g of groups) {
    const sorted = g.items.slice().sort((a, b) => b.score - a.score)
    out.push(sorted[0])
  }
  return out
}
''',
    ),
    # -------------------------------------------------------------------- both
    RoutingCase(
        id="sqli-inside-loop",
        language="python",
        needs_security=True,
        needs_performance=True,
        note="the vulnerable-Python demo case",
        code='''def orders_for(conn, username):
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE name = '" + username + "'")
    uid = cur.fetchone()[0]
    out = []
    for oid in cur.execute("SELECT id FROM orders WHERE user_id = %s" % uid):
        out.append(cur.execute("SELECT * FROM items WHERE oid = " + str(oid)).fetchall())
    return out
''',
    ),
    # ------------------------------------------------------------------ neither
    RoutingCase(
        id="plain-css",
        language="css",
        needs_security=False,
        needs_performance=False,
        code='''.card {
  display: flex;
  gap: 12px;
  padding: 16px;
  border-radius: 10px;
}
''',
    ),
    RoutingCase(
        id="static-config",
        language="json",
        needs_security=False,
        needs_performance=False,
        code='''{
  "name": "widgets",
  "version": "2.1.0",
  "license": "MIT"
}
''',
    ),
    RoutingCase(
        id="pure-formatting-helper",
        language="python",
        needs_security=False,
        needs_performance=False,
        code='''def initials(first: str, last: str) -> str:
    """Return the two-letter initials for a name."""
    return (first[:1] + last[:1]).upper()
''',
    ),
    RoutingCase(
        id="constants-module",
        language="python",
        needs_security=False,
        needs_performance=False,
        note="looks credential-adjacent but holds no secret",
        code='''RETRY_LIMIT = 3
PAGE_SIZE = 50
SUPPORTED_LOCALES = ("en", "hi", "fr")
''',
    ),
    RoutingCase(
        id="markup-only",
        language="html",
        needs_security=False,
        needs_performance=False,
        code='''<section class="hero">
  <h1>Ship better code</h1>
  <p>Automated multi-agent review for every pull request.</p>
</section>
''',
    ),
]
