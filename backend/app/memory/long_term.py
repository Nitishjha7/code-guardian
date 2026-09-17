"""Long-term memory: explicit, per-repo review preferences.

Scoped by ``repo_id`` (``PullRequestRef.repo_full_name`` from
``app/mcp_clients/github_client.py``) because that is the only standing
identity this project has - there is no user account, no login, and a
review triggered through the ad-hoc ``/api/review`` endpoint has no repo at
all and simply gets no preferences applied (empty scope, not an error).

Never inferred from a review's content, same rule as
self-healing-sql-agent's long-term memory: a preference exists only because
something explicitly called ``set_preference``.
"""

from __future__ import annotations

import logging

from .store import get_connection

log = logging.getLogger(__name__)


def set_preference(repo_id: str, key: str, value: str) -> None:
    conn = get_connection()
    if conn is None or not repo_id:
        return
    try:
        conn.execute(
            "INSERT INTO repo_preferences (repo_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(repo_id, key) DO UPDATE SET value = excluded.value",
            (repo_id, key, value),
        )
        conn.commit()
    except Exception as exc:  # noqa: BLE001 - fail open
        log.warning("set_preference failed (%s)", exc)


def get_preferences(repo_id: str) -> dict[str, str]:
    conn = get_connection()
    if conn is None or not repo_id:
        return {}
    try:
        rows = conn.execute(
            "SELECT key, value FROM repo_preferences WHERE repo_id = ?", (repo_id,)
        ).fetchall()
        return {k: v for k, v in rows}
    except Exception as exc:  # noqa: BLE001 - fail open
        log.warning("get_preferences failed (%s)", exc)
        return {}


def format_preferences_for_prompt(preferences: dict[str, str]) -> str:
    if not preferences:
        return ""
    lines = [f"- {k}: {v}" for k, v in preferences.items()]
    return "This repository's stated review preferences:\n" + "\n".join(lines)
