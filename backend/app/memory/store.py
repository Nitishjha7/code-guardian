"""Lazy, fail-open SQLite connection shared by episodic/semantic/long-term memory.

Mirrors the lazy-singleton pattern used everywhere else optional
infrastructure appears in this kind of project (see
self-healing-sql-agent's ``app/checkpointer.py`` for the sibling pattern this
was modeled on): try once, cache the result including failure, never crash
the caller.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading

log = logging.getLogger(__name__)

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_tried = False

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signature TEXT NOT NULL,
    language TEXT NOT NULL,
    finding_title TEXT NOT NULL,
    severity TEXT NOT NULL,
    verdict TEXT NOT NULL,
    repo_id TEXT,
    recorded_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_episodes_signature ON episodes(signature);

CREATE TABLE IF NOT EXISTS semantic_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signature_prefix TEXT NOT NULL,
    finding_title TEXT NOT NULL,
    fact TEXT NOT NULL,
    episode_count INTEGER NOT NULL,
    recorded_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_prefix ON semantic_facts(signature_prefix);

CREATE TABLE IF NOT EXISTS repo_preferences (
    repo_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (repo_id, key)
);
"""


def _default_path() -> str:
    # /data is the conventional writable mount in this project's Dockerfile
    # (see backend/Dockerfile); falls back to the working directory for local
    # `uvicorn` runs where no volume is mounted.
    return os.environ.get("MEMORY_DB_PATH", "/data/memory.db")


def get_connection() -> sqlite3.Connection | None:
    """Return the shared connection, or None if memory is disabled/unavailable."""
    global _conn, _tried
    if _tried:
        return _conn
    with _lock:
        if _tried:
            return _conn
        _tried = True
        if os.environ.get("DISABLE_MEMORY_STORE", "").lower() in ("1", "true", "yes"):
            log.info("Memory store disabled by DISABLE_MEMORY_STORE.")
            return None
        path = _default_path()
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            conn = sqlite3.connect(path, check_same_thread=False)
            conn.executescript(_SCHEMA)
            conn.commit()
            _conn = conn
        except Exception as exc:  # noqa: BLE001 - fail open, never crash a review over this
            log.warning("Memory store setup failed (%s). Reviews run without memory.", exc)
            _conn = None
    return _conn


def reset_for_tests() -> None:
    """Test-only hook, mirrors the sibling project's ``reset_for_tests``."""
    global _conn, _tried
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None
        _tried = False
