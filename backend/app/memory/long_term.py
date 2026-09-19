"""Long-term memory: explicit, per-repo review preferences.

Scoped by ``repo_id`` (``PullRequestRef.repo_full_name`` from
``app/mcp_clients/github_client.py``) because that is the only standing
identity this project has - there is no user account, no login, and a
review triggered through the ad-hoc ``/api/review`` endpoint has no repo at
all and simply gets no preferences applied (empty scope, not an error).

Never inferred from a review's content: a preference exists only because
something explicitly called ``set_preference``.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

from .store import get_connection

log = logging.getLogger(__name__)

# The preferences in force for the review running on this task. A ContextVar for
# the same reason the supervisor's current input is one: the API serves
# concurrent reviews, and a module global would let one repo's preferences be
# applied to another repo's code.
_CURRENT: ContextVar[dict[str, str]] = ContextVar(
    "code_guardian_current_preferences", default={}
)


def set_current(preferences: dict[str, str]) -> None:
    """Install the preferences for this review. Called once, by ``run_review``."""
    _CURRENT.set(preferences or {})


def current_prompt_block() -> str:
    """The preference text to append to an auditor's prompt, or ``""``.

    The agents call this rather than being handed preferences as an argument:
    the alternative is threading a parameter through every agent, the graph and
    both entry points to deliver something that is empty on the ad-hoc
    ``/api/review`` path anyway.
    """
    return format_preferences_for_prompt(_CURRENT.get())


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
    """Render preferences as a prompt block, or ``""`` when there are none.

    Phrased as standing instructions with an explicit floor: a preference may
    narrow what gets reported, but it must never suppress an exploitable
    finding. A repo that has asked for "Critical only" is expressing a triage
    threshold, not consenting to have a SQL injection hidden from it.
    """
    if not preferences:
        return ""
    lines = [f"- {k}: {v}" for k, v in preferences.items()]
    return (
        "\n\nThis repository has stated the following review preferences. "
        "Honour them where they apply:\n"
        + "\n".join(lines)
        + "\n\nA preference may not suppress a Critical or High severity finding. "
        "If one conflicts, report the finding anyway and say so in its explanation."
    )
