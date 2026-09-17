"""Semantic memory: facts distilled from clusters of episodes.

Built on top of episodic memory, not independent of it - same relationship
as self-healing-sql-agent's semantic memory to its episodic memory. An
episode is one data point ("this snippet, this finding, this verdict"); a
semantic fact is what several episodes sharing a signature prefix collapse
into, once there are enough of them to call it a pattern rather than noise.

Deliberately not automatic. Running this after every single review would
mean re-deriving the same fact from the same growing pile of episodes on
every request - wasted work, and a fact that "distilled itself" after every
review is not meaningfully distilled. ``consolidate_facts`` is a periodic,
explicitly-invoked job (a cron, an admin endpoint, or a one-off script) - the
same category of thing as self-healing-sql-agent's ``consolidate_facts``.
"""

from __future__ import annotations

import logging
import time

from .store import get_connection

log = logging.getLogger(__name__)

# Below this many episodes sharing a signature, a repeated dismissal is just
# as likely to be coincidence as a real pattern - not worth stating as fact.
_MIN_EPISODES_FOR_FACT = 3


def consolidate_facts() -> int:
    """Scan episodes for signatures repeatedly dismissed, write a fact for each.

    Returns the number of new/updated facts written. Deterministic on
    purpose - no LLM call. Unlike self-healing-sql-agent's semantic memory
    (which needs an LLM to describe a *novel* error pattern in words), the
    fact here is a direct aggregate of a title and a dismissal count, so
    reaching for a model would add a paid call and nondeterminism to
    something a `GROUP BY` already answers exactly.
    """
    conn = get_connection()
    if conn is None:
        return 0
    try:
        rows = conn.execute(
            "SELECT signature, finding_title, COUNT(*) as n "
            "FROM episodes WHERE verdict = 'dismissed' "
            "GROUP BY signature, finding_title HAVING n >= ?",
            (_MIN_EPISODES_FOR_FACT,),
        ).fetchall()
        written = 0
        for signature, title, count in rows:
            prefix = signature.split(":", 1)[0]
            fact = (
                f'"{title}" on this code shape was reported {count} times and '
                f"never followed by a fix - likely a false positive for this codebase."
            )
            existing = conn.execute(
                "SELECT id FROM semantic_facts WHERE signature_prefix = ? AND finding_title = ?",
                (prefix, title),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE semantic_facts SET fact = ?, episode_count = ?, recorded_at = ? WHERE id = ?",
                    (fact, count, time.time(), existing[0]),
                )
            else:
                conn.execute(
                    "INSERT INTO semantic_facts (signature_prefix, finding_title, fact, episode_count, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (prefix, title, fact, count, time.time()),
                )
            written += 1
        conn.commit()
        return written
    except Exception as exc:  # noqa: BLE001 - fail open
        log.warning("consolidate_facts failed (%s)", exc)
        return 0


def recall_facts(source_code_signature_prefix: str, finding_title: str = "") -> list[str]:
    """Facts recorded for this snippet's signature prefix.

    Called with the *prefix* half of ``episodic.make_signature``'s output
    (everything before the ``:``), so a fact keyed to a finding title still
    matches when a different finding is raised against the same snippet.
    """
    conn = get_connection()
    if conn is None:
        return []
    try:
        if finding_title:
            rows = conn.execute(
                "SELECT fact FROM semantic_facts WHERE signature_prefix = ? AND finding_title = ?",
                (source_code_signature_prefix, finding_title),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT fact FROM semantic_facts WHERE signature_prefix = ?",
                (source_code_signature_prefix,),
            ).fetchall()
        return [r[0] for r in rows]
    except Exception as exc:  # noqa: BLE001 - fail open
        log.warning("recall_facts failed (%s)", exc)
        return []


def format_facts_for_prompt(facts: list[str]) -> str:
    if not facts:
        return ""
    return "Known pattern for this codebase:\n" + "\n".join(f"- {f}" for f in facts)
