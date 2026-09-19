"""Semantic memory: facts distilled from clusters of episodes.

Built on episodic memory rather than beside it. An episode is one data point
("this snippet, this finding, this verdict"); a fact is what several episodes
sharing a signature collapse into, once there are enough to call it a pattern
rather than noise.

Both verdicts produce a fact, and they say different things. A finding
repeatedly *fixed* is a recurring defect worth flagging early; one repeatedly
*dismissed* is a likely false positive for this codebase. An earlier version
consolidated only dismissals, which meant that in normal use - where the patch
generator almost always changes something - no fact was ever written.

``consolidate_facts`` is a periodic job, not something every review runs. It is
a GROUP BY over the whole episodes table - a per-request cost for an answer that
only changes once new episodes accumulate.
"""

from __future__ import annotations

import logging
import time

from .store import get_connection

log = logging.getLogger(__name__)

# Below this many episodes sharing a signature, a repeated verdict is as
# likely to be coincidence as a real pattern - not worth stating as fact.
_MIN_EPISODES_FOR_FACT = 3


def _fact_text(title: str, verdict: str, count: int) -> str:
    """The sentence a cluster of episodes collapses into."""
    if verdict == "dismissed":
        return (
            f'"{title}" on this code shape was reported {count} times and never '
            "followed by a fix - likely a false positive for this codebase."
        )
    return (
        f'"{title}" on this code shape was found and fixed {count} times - '
        "a recurring defect in this codebase."
    )


def consolidate_facts() -> int:
    """Scan episodes for repeated (signature, finding, verdict) clusters and
    write a fact for each.

    Returns the number of facts written or updated. No LLM call: the fact is a
    title, a verdict and a count, which a ``GROUP BY`` answers exactly. A model
    would add cost and nondeterminism for nothing.
    """
    conn = get_connection()
    if conn is None:
        return 0
    try:
        rows = conn.execute(
            "SELECT signature, finding_title, verdict, COUNT(*) as n "
            "FROM episodes GROUP BY signature, finding_title, verdict "
            "HAVING n >= ?",
            (_MIN_EPISODES_FOR_FACT,),
        ).fetchall()
        written = 0
        for signature, title, verdict, count in rows:
            prefix = signature.split(":", 1)[0]
            fact = _fact_text(title, verdict, count)
            # Keyed on the verdict too, not just (prefix, title): one snippet
            # can accumulate a "fixed" cluster and a "dismissed" cluster for the
            # same finding, and they say opposite things. Keying on the pair
            # alone would let the second overwrite the first on every run. The
            # schema has no verdict column, so the marker is matched in the fact
            # text - the count in it changes between runs, the marker does not.
            marker = "never followed by a fix" if verdict == "dismissed" else "found and fixed"
            existing = conn.execute(
                "SELECT id FROM semantic_facts WHERE signature_prefix = ? "
                "AND finding_title = ? AND fact LIKE ?",
                (prefix, title, f"%{marker}%"),
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
            # Case-insensitive: the same defect comes back as "Hardcoded
            # database password" one run and "Hardcoded Database Password" the
            # next, and an exact match silently loses the fact.
            rows = conn.execute(
                "SELECT fact FROM semantic_facts WHERE signature_prefix = ? "
                "AND LOWER(finding_title) = LOWER(?)",
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
