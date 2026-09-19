"""Episodic memory: has a near-identical piece of code been reviewed before?

One episode = one (code signature, finding, verdict) triple. "Verdict" is
whatever the human reviewer effectively decided by *not* overriding the
guardian - see ``record_episode_from_result`` for the one place that
decision is made.

Global, not scoped by repo: a SQL string built with f-string interpolation
looks the same character-for-character whether it appears in repo A or repo
B, so siloing episodes per repo would only make each repo's memory colder
for no benefit. Long-term preferences are the layer that is repo-scoped
(``long_term.py``); this one is not.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time

from .store import get_connection

log = logging.getLogger(__name__)

_TOP_K = 3

# Verdicts recorded so a future match can say something more useful than
# "seen before" - whether it was actually acted on.
VERDICT_FIXED = "fixed"       # a patch was generated for this finding
VERDICT_DISMISSED = "dismissed"  # the finding was reported but no patch followed


def make_signature(source_code: str, finding_title: str) -> str:
    """A normalized signature for the snippet a finding was raised against.

    Not an AST hash - this project does not parse the target language (it
    reviews Python, JS, CSS and more through one LLM path; a real AST
    comparison would need a parser per language, which is a different
    project). Whitespace and identifier-length changes are normalized away
    so two copies of the same vulnerable pattern with renamed variables still
    match; a genuinely different snippet does not.
    """
    normalized = re.sub(r"\s+", " ", source_code.strip().lower())
    normalized = re.sub(r"\b[a-z_][a-z0-9_]{0,2}\b", "_", normalized)  # short identifiers
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{digest}:{finding_title.strip().lower()}"


def record_episode(
    signature: str,
    language: str,
    finding_title: str,
    severity: str,
    verdict: str,
    repo_id: str = "",
) -> None:
    conn = get_connection()
    if conn is None:
        return
    try:
        conn.execute(
            "INSERT INTO episodes (signature, language, finding_title, severity, verdict, repo_id, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (signature, language, finding_title, severity, verdict, repo_id, time.time()),
        )
        conn.commit()
    except Exception as exc:  # noqa: BLE001 - fail open
        log.warning("record_episode failed (%s)", exc)


def record_episode_from_result(
    source_code: str,
    language: str,
    findings: list[dict],
    fixed_code: str,
    repo_id: str = "",
) -> None:
    """Record this review's findings. Called once per review from ``graph.py``.

    A finding counts as "fixed" when the patch generator changed the code
    (``fixed_code`` differs from ``source_code``), and "dismissed" otherwise.
    Dismissed does not mean a human rejected it - it is the only signal
    available for an action not taken. Unfixed findings are recorded rather
    than skipped so semantic consolidation can pick up patterns that are
    flagged repeatedly and never acted on.
    """
    was_fixed = bool(fixed_code) and fixed_code != source_code
    verdict = VERDICT_FIXED if was_fixed else VERDICT_DISMISSED
    for finding in findings:
        title = finding.get("title", "")
        if not title:
            continue
        record_episode(
            signature=make_signature(source_code, title),
            language=language,
            finding_title=title,
            severity=finding.get("severity", "Low"),
            verdict=verdict,
            repo_id=repo_id,
        )


def recall_similar(source_code: str, finding_title: str, limit: int = _TOP_K) -> list[dict]:
    """Past episodes whose signature matches this exact (snippet, finding) pair.

    Exact signature match, not fuzzy - see ``make_signature``'s normalization
    for what "the same" means here. Fail-open: any error returns no episodes
    rather than raising into the review.
    """
    conn = get_connection()
    if conn is None:
        return []
    try:
        signature = make_signature(source_code, finding_title)
        rows = conn.execute(
            "SELECT verdict, severity, recorded_at FROM episodes "
            "WHERE signature = ? ORDER BY recorded_at DESC LIMIT ?",
            (signature, limit),
        ).fetchall()
        return [
            {"verdict": r[0], "severity": r[1], "recorded_at": r[2]}
            for r in rows
        ]
    except Exception as exc:  # noqa: BLE001 - fail open
        log.warning("recall_similar failed (%s)", exc)
        return []


def format_episodes_for_prompt(episodes: list[dict]) -> str:
    if not episodes:
        return ""
    fixed = sum(1 for e in episodes if e["verdict"] == VERDICT_FIXED)
    dismissed = len(episodes) - fixed
    lines = [
        f"Precedent: this exact pattern was seen {len(episodes)} time(s) before "
        f"({fixed} fixed, {dismissed} reported without a follow-up fix)."
    ]
    return "\n".join(lines)
