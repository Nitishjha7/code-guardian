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

    def test_consolidate_covers_fixed_episodes_too(self):
        """Consolidation once read only dismissals, so in normal use - where
        the patch generator does change the code - it never wrote a fact."""
        for _ in range(semantic._MIN_EPISODES_FOR_FACT):
            episodic.record_episode(
                signature=episodic.make_signature("code", "finding"),
                language="python",
                finding_title="finding",
                severity="Low",
                verdict=episodic.VERDICT_FIXED,
            )
        assert semantic.consolidate_facts() == 1

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

    def test_prompt_block_refuses_to_let_a_preference_hide_a_real_finding(self):
        """A preference is a triage threshold, not consent to hide a
        vulnerability. Whatever the repo asked for, the block has to carry the
        floor with it - otherwise "Critical only" reads to the model as
        permission to drop an exploitable High."""
        text = long_term.format_preferences_for_prompt({"min_severity": "Critical"})
        assert "may not suppress" in text
        assert "Critical or High" in text

    def test_current_prompt_block_is_empty_until_preferences_are_installed(self):
        """The ad-hoc /api/review path has no repo, so the auditors must run on
        their base prompts rather than on some other repo's leftovers."""
        long_term.set_current({})
        assert long_term.current_prompt_block() == ""

    def test_current_prompt_block_reflects_the_installed_preferences(self):
        long_term.set_current({"house_style": "prefix every title with X-"})
        try:
            assert "prefix every title with X-" in long_term.current_prompt_block()
        finally:
            long_term.set_current({})


class TestPreferencesReachTheAuditors:
    """The wiring, not the storage.

    Preferences shipped stored, readable over the API, and completely
    disconnected: ``format_preferences_for_prompt`` existed but its only callers
    were its own unit tests, no agent imported the memory package, and
    ``/api/review`` had no ``repo_id`` field to scope them by. Every test above
    passed throughout. These assert on the seam that was missing.
    """

    def _capture_system_prompt(self, monkeypatch, agent_module):
        """Run the agent against a stub LLM and return the system prompt it sent."""
        captured = {}

        class _StubLLM:
            def invoke(self, messages):
                captured["system"] = messages[0].content

                class _R:
                    content = "[]"

                return _R()

        monkeypatch.setattr(agent_module, "get_llm", lambda **kw: _StubLLM())
        return captured

    def test_security_agent_sends_the_preferences(self, monkeypatch):
        from app.agents import security_agent

        captured = self._capture_system_prompt(monkeypatch, security_agent)
        monkeypatch.setattr(
            security_agent.static_analysis, "audit", lambda *a, **k: ([], "")
        )
        long_term.set_current({"house_style": "prefix titles with X-"})
        try:
            security_agent.audit("x = 1", "python")
        finally:
            long_term.set_current({})

        assert "prefix titles with X-" in captured["system"]

    def test_performance_agent_sends_the_preferences(self, monkeypatch):
        from app.agents import performance_agent

        captured = self._capture_system_prompt(monkeypatch, performance_agent)
        long_term.set_current({"house_style": "prefix titles with X-"})
        try:
            performance_agent.audit("x = 1", "python")
        finally:
            long_term.set_current({})

        assert "prefix titles with X-" in captured["system"]

    def test_no_preferences_leaves_the_base_prompt_untouched(self, monkeypatch):
        from app.agents import performance_agent

        captured = self._capture_system_prompt(monkeypatch, performance_agent)
        long_term.set_current({})
        performance_agent.audit("x = 1", "python")

        assert captured["system"] == performance_agent.SYSTEM_PROMPT

    def test_run_review_installs_the_reviewed_repos_preferences(self, monkeypatch):
        """The graph has to look the preferences up by repo_id. Passing repo_id
        through to the episode writer but not to the auditors is exactly the
        half-wiring that shipped."""
        import app.graph as graph_module

        long_term.set_preference("owner/repo", "house_style", "prefix titles with X-")
        seen = {}

        class _FakeGraph:
            def invoke(self, state, config=None):
                seen["block"] = long_term.current_prompt_block()
                return dict(state)

        monkeypatch.setattr(graph_module, "get_graph", lambda: _FakeGraph())
        graph_module.run_review("x = 1", "python", repo_id="owner/repo")

        assert "prefix titles with X-" in seen["block"]

    def test_a_review_with_no_repo_gets_no_preferences(self, monkeypatch):
        import app.graph as graph_module

        long_term.set_preference("owner/repo", "house_style", "prefix titles with X-")
        seen = {}

        class _FakeGraph:
            def invoke(self, state, config=None):
                seen["block"] = long_term.current_prompt_block()
                return dict(state)

        monkeypatch.setattr(graph_module, "get_graph", lambda: _FakeGraph())
        graph_module.run_review("x = 1", "python", repo_id="")

        assert seen["block"] == ""


class TestSemanticConsolidatesBothVerdicts:
    """Consolidation used to read only ``verdict='dismissed'``.

    A finding is recorded as dismissed only when the patch generator returns
    the code unchanged, which in practice almost never happens - so with 113
    real episodes in the local database, ``semantic_facts`` was still empty.
    The layer shipped, was tested, and could not fire.
    """

    def _record(self, n, verdict, title="SQL injection"):
        for _ in range(n):
            episodic.record_episode(
                signature=episodic.make_signature("code", title),
                language="python",
                finding_title=title,
                severity="High",
                verdict=verdict,
            )

    def test_repeated_fixes_produce_a_fact(self):
        self._record(semantic._MIN_EPISODES_FOR_FACT, episodic.VERDICT_FIXED)
        assert semantic.consolidate_facts() == 1
        prefix = episodic.make_signature("code", "SQL injection").split(":", 1)[0]
        facts = semantic.recall_facts(prefix, "SQL injection")
        assert len(facts) == 1
        assert "recurring defect" in facts[0]

    def test_repeated_dismissals_still_produce_a_fact(self):
        self._record(semantic._MIN_EPISODES_FOR_FACT, episodic.VERDICT_DISMISSED)
        assert semantic.consolidate_facts() == 1
        prefix = episodic.make_signature("code", "SQL injection").split(":", 1)[0]
        assert "false positive" in semantic.recall_facts(prefix, "SQL injection")[0]

    def test_the_two_verdicts_are_separate_facts(self):
        """Fixed and dismissed say opposite things, so they must not merge."""
        self._record(semantic._MIN_EPISODES_FOR_FACT, episodic.VERDICT_FIXED)
        self._record(semantic._MIN_EPISODES_FOR_FACT, episodic.VERDICT_DISMISSED)
        assert semantic.consolidate_facts() == 2

    def test_below_threshold_still_writes_nothing(self):
        self._record(semantic._MIN_EPISODES_FOR_FACT - 1, episodic.VERDICT_FIXED)
        assert semantic.consolidate_facts() == 0

    def test_recall_survives_a_change_of_title_case(self):
        """The model returns "Hardcoded database password" one run and
        "Hardcoded Database Password" the next; an exact match loses the fact."""
        self._record(semantic._MIN_EPISODES_FOR_FACT, episodic.VERDICT_FIXED,
                     title="Hardcoded database password")
        semantic.consolidate_facts()
        prefix = episodic.make_signature(
            "code", "Hardcoded database password"
        ).split(":", 1)[0]
        assert semantic.recall_facts(prefix, "Hardcoded Database Password")

    def test_rerunning_consolidation_updates_rather_than_duplicates(self):
        self._record(semantic._MIN_EPISODES_FOR_FACT, episodic.VERDICT_FIXED)
        semantic.consolidate_facts()
        self._record(2, episodic.VERDICT_FIXED)  # same cluster grows
        semantic.consolidate_facts()

        prefix = episodic.make_signature("code", "SQL injection").split(":", 1)[0]
        facts = semantic.recall_facts(prefix, "SQL injection")
        assert len(facts) == 1, "the fact should be updated in place, not duplicated"
        assert "5 times" in facts[0]

    def test_both_verdicts_on_one_snippet_survive_a_rerun(self):
        """The upsert keys on the verdict as well as (prefix, title). Without
        that, the second cluster overwrites the first on every run and the
        stored fact flips meaning depending on row order."""
        self._record(semantic._MIN_EPISODES_FOR_FACT, episodic.VERDICT_FIXED)
        self._record(semantic._MIN_EPISODES_FOR_FACT, episodic.VERDICT_DISMISSED)
        semantic.consolidate_facts()
        semantic.consolidate_facts()

        prefix = episodic.make_signature("code", "SQL injection").split(":", 1)[0]
        facts = semantic.recall_facts(prefix, "SQL injection")
        assert len(facts) == 2
        assert any("recurring defect" in f for f in facts)
        assert any("false positive" in f for f in facts)
