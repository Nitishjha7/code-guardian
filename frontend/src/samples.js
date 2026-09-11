// Demo payloads for the live walkthrough described in docs/BUILD_AND_DEPLOY.md.
// The first snippet is deliberately awful in both dimensions; the second has no
// security surface at all, which is what makes the router's decision visible.

export const SAMPLES = [
  {
    id: 'vulnerable-python',
    label: 'Vulnerable Python (SQLi + N+1)',
    language: 'python',
    filename: 'orders.py',
    code: `import sqlite3
import hashlib

DB_PASSWORD = "sup3rs3cret-prod-pw"


def get_user_orders(username):
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()

    # look up the user
    cursor.execute("SELECT id FROM users WHERE name = '" + username + "'")
    user = cursor.fetchone()

    order_ids = cursor.execute(
        "SELECT id FROM orders WHERE user_id = %s" % user[0]
    ).fetchall()

    orders = []
    for order_id in order_ids:
        row = cursor.execute(
            "SELECT * FROM order_items WHERE order_id = " + str(order_id[0])
        ).fetchall()
        orders.append(row)

    return orders


def check_password(raw, stored_hash):
    return hashlib.md5(raw.encode()).hexdigest() == stored_hash
`,
  },
  {
    id: 'plain-css',
    label: 'Plain CSS (router should skip security)',
    language: 'css',
    filename: 'card.css',
    code: `.card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-radius: 10px;
  background: #111827;
}

.card__title {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
`,
  },
  {
    id: 'slow-js',
    label: 'Slow JavaScript (O(n^2) lookup)',
    language: 'javascript',
    filename: 'activity.js',
    code: `function mergeUserActivity(users, events) {
  const result = []

  for (const user of users) {
    let total = 0
    for (const event of events) {
      if (event.userId === user.id) {
        total += event.duration
      }
    }
    result.push({ ...user, total })
  }

  return result.sort((a, b) => b.total - a.total)
}
`,
  },
]
