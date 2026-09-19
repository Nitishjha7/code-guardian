"""Deliberately vulnerable sample used to exercise the PR bot end to end.

This file exists to give Code Guardian something real to find on a real pull
request. It is never imported by the application and is excluded from the test
suite. Do not copy anything from here.
"""

import os
import pickle
import sqlite3
import subprocess

# Hardcoded credential - the guardrail scanner should flag this.
# Deliberately not a real provider's key format: GitHub push protection blocks
# anything that looks like one, which would stop this file reaching the PR it
# exists to be reviewed on.
API_TOKEN = "EXAMPLE-NOT-REAL-a1b2c3d4e5f6a7b8c9d0e1f2"
DB_PASSWORD = "admin123"
DB_PATH = "users.db"


def find_user(username):
    """String-concatenated SQL - classic injection."""
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT id, email, role FROM users WHERE username = '" + username + "'"
    return conn.execute(query).fetchone()


def search_users(term):
    """Same problem via f-string, plus SELECT * on a wide table."""
    conn = sqlite3.connect(DB_PATH)
    return conn.execute(f"SELECT * FROM users WHERE email LIKE '%{term}%'").fetchall()


def run_report(report_name):
    """Shell injection - user input straight into a shell command."""
    return subprocess.check_output(f"python reports/{report_name}.py", shell=True)


def load_session(blob):
    """Deserialising untrusted input executes arbitrary code."""
    return pickle.loads(blob)


def evaluate_rule(expression, context):
    """eval() on caller-supplied text."""
    return eval(expression, {}, context)


def bulk_lookup(usernames):
    """O(n) queries and a new connection per iteration."""
    results = []
    for name in usernames:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT id FROM users WHERE username = '" + name + "'"
        ).fetchone()
        results.append(row)
    return results


def write_audit(entry):
    """File handle is never closed."""
    f = open(os.path.join("/tmp", "audit.log"), "a")
    f.write(entry + "\n")
