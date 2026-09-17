"""app/memory/ — episodic, semantic, long-term, and the SQLite store beneath them.

Each test points ``MEMORY_DB_PATH`` at a fresh temp file and calls
``reset_for_tests()`` first, so tests never share state with each other or
with a real ``/data/memory.db``.
"""

import os

import pytest

from app.memory import episodic, long_term, semantic, store


@pytest.fixture(autouse=True)
def _fresh_store(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    monkeypatch.setenv("MEMORY_DB_PATH", str(db_path))
    monkeypatch.delenv("DISABLE_MEMORY_STORE", raising=False)
    store.reset_for_tests()
    yield
    store.reset_for_tests()


class TestStore:
    def test_get_connection_creates_schema(self):
        conn = store.get_connection()
        assert conn is not None
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {"episodes", "semantic_facts", "repo_preferences"} <= tables

    def test_disabled_by_env_returns_none(self, monkeypatch):
        monkeypatch.setenv("DISABLE_MEMORY_STORE", "true")
        store.reset_for_tests()
        assert store.get_connection() is None

    def test_unwritable_path_fails_open(self, monkeypatch):
        # A path under a file (not a directory) can never be created.
        monkeypatch.setenv("MEMORY_DB_PATH", "/dev/null/impossible/memory.db")
        store.reset_for_tests()
        assert store.get_connection() is None

    def test_cached_after_first_call(self):
        first = store.get_connection()
        second = store.get_connection()
        assert first is second


class TestEpisodic:
    def test_signature_stable_across_identifier_renames(self):
        a = episodic.make_signature("def foo(x): return x + 1", "SQL injection")
        b = episodic.make_signature("def bar(y): return y + 1", "SQL injection")
        assert a == b

    def test_signature_differs_for_different_finding(self):
        a = episodic.make_signature("SELECT * FROM t", "SQL injection")
        b = episodic.make_signature("SELECT * FROM t", "Missing index")
        assert a != b

    def test_recall_similar_empty_when_nothing_recorded(self):
        assert episodic.recall_similar("some code", "some finding") == []

    def test_record_then_recall_round_trips(self):
        episodic.record_episode(
            signature=episodic.make_signature("code", "finding"),
            language="python",
            finding_title="finding",
            severity="High",
            verdict=episodic.VERDICT_DISMISSED,
        )
        recalled = episodic.recall_similar("code", "finding")
        assert len(recalled) == 1
        assert recalled[0]["verdict"] == episodic.VERDICT_DISMISSED

    def test_record_episode_from_result_marks_fixed_when_code_changed(self):
        episodic.record_episode_from_result(
            source_code="original",
            language="python",
            findings=[{"title": "XSS", "severity": "High"}],
            fixed_code="patched",
        )
        recalled = episodic.recall_similar("original", "XSS")
        assert recalled[0]["verdict"] == episodic.VERDICT_FIXED

    def test_record_episode_from_result_marks_dismissed_when_unchanged(self):
        episodic.record_episode_from_result(
            source_code="original",
            language="python",
            findings=[{"title": "XSS", "severity": "Low"}],
            fixed_code="original",
        )
        recalled = episodic.recall_similar("original", "XSS")
        assert recalled[0]["verdict"] == episodic.VERDICT_DISMISSED

    def test_recall_fails_open_when_store_disabled(self, monkeypatch):
        monkeypatch.setenv("DISABLE_MEMORY_STORE", "true")
        store.reset_for_tests()
        assert episodic.recall_similar("x", "y") == []

    def test_format_episodes_for_prompt_empty(self):
        assert episodic.format_episodes_for_prompt([]) == ""

    def test_format_episodes_for_prompt_counts_fixed_and_dismissed(self):
        text = episodic.format_episodes_for_prompt(
            [
                {"verdict": episodic.VERDICT_FIXED, "severity": "High", "recorded_at": 1},
                {"verdict": episodic.VERDICT_DISMISSED, "severity": "Low", "recorded_at": 2},
            ]
        )
        assert "2 time(s)" in text
        assert "1 fixed" in text
        assert "1 reported" in text


class TestSemantic:
    def test_consolidate_writes_nothing_below_threshold(self):
        for _ in range(semantic._MIN_EPISODES_FOR_FACT - 1):
            episodic.record_episode(
                signature=episodic.make_signature("code", "finding"),
                language="python",
                finding_title="finding",
                severity="Low",
                verdict=episodic.VERDICT_DISMISSED,
            )
        assert semantic.consolidate_facts() == 0

    def test_consolidate_writes_fact_at_threshold(self):
        for _ in range(semantic._MIN_EPISODES_FOR_FACT):
            episodic.record_episode(
                signature=episodic.make_signature("code", "finding"),
                language="python",
                finding_title="finding",
                severity="Low",
                verdict=episodic.VERDICT_DISMISSED,
            )
        assert semantic.consolidate_facts() == 1
        prefix = episodic.make_signature("code", "finding").split(":", 1)[0]
        facts = semantic.recall_facts(prefix, "finding")
        assert len(facts) == 1
        assert "3 times" in facts[0]

    def test_consolidate_ignores_fixed_episodes(self):
        for _ in range(semantic._MIN_EPISODES_FOR_FACT):
            episodic.record_episode(
                signature=episodic.make_signature("code", "finding"),
                language="python",
                finding_title="finding",
                severity="Low",
                verdict=episodic.VERDICT_FIXED,
            )
        assert semantic.consolidate_facts() == 0

    def test_recall_facts_empty_when_none_recorded(self):
        assert semantic.recall_facts("nonexistent") == []

    def test_format_facts_for_prompt_empty(self):
        assert semantic.format_facts_for_prompt([]) == ""

    def test_format_facts_for_prompt_lists_each_fact(self):
        text = semantic.format_facts_for_prompt(["fact one", "fact two"])
        assert "fact one" in text and "fact two" in text


class TestLongTerm:
    def test_get_preferences_empty_for_unknown_repo(self):
        assert long_term.get_preferences("owner/repo") == {}

    def test_set_then_get_round_trips(self):
        long_term.set_preference("owner/repo", "min_severity", "High")
        assert long_term.get_preferences("owner/repo") == {"min_severity": "High"}

    def test_set_overwrites_existing_key(self):
        long_term.set_preference("owner/repo", "min_severity", "High")
        long_term.set_preference("owner/repo", "min_severity", "Critical")
        assert long_term.get_preferences("owner/repo") == {"min_severity": "Critical"}

    def test_preferences_scoped_per_repo(self):
        long_term.set_preference("owner/repo-a", "k", "a")
        long_term.set_preference("owner/repo-b", "k", "b")
        assert long_term.get_preferences("owner/repo-a") == {"k": "a"}
        assert long_term.get_preferences("owner/repo-b") == {"k": "b"}

    def test_set_preference_noop_without_repo_id(self):
        long_term.set_preference("", "k", "v")
        assert long_term.get_preferences("") == {}

    def test_format_preferences_for_prompt_empty(self):
        assert long_term.format_preferences_for_prompt({}) == ""

    def test_format_preferences_for_prompt_lists_each(self):
        text = long_term.format_preferences_for_prompt({"min_severity": "High"})
        assert "min_severity" in text and "High" in text
