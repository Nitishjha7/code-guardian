"""``get_llm`` and its fallback chain.

No real Groq call happens here - ``ChatGroq.invoke`` is mocked so this tests
what this project actually owns: whether the *chain* is assembled correctly
and whether it still behaves like the plain client every caller (including
the tool-calling supervisor) depends on. Whether the underlying Groq API
itself fails over correctly is not this project's code to test.
"""

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables.fallbacks import RunnableWithFallbacks
from langchain_groq import ChatGroq

from app.config import Settings, get_llm


@pytest.fixture(autouse=True)
def _clear_llm_cache():
    """``get_llm`` is ``@lru_cache``'d in production so agents share one
    client - exactly what would leak settings from one test into the next if
    left alone."""
    get_llm.cache_clear()
    yield
    get_llm.cache_clear()


def _settings(**overrides):
    base = {"groq_api_key": "test-key", "guardian_model": "openai/gpt-oss-120b"}
    return Settings(**{**base, **overrides})


def test_no_fallback_configured_returns_a_plain_client():
    """The honest default: one project, one key, one model - no gateway
    machinery for a project that never configured one."""
    with patch("app.config.get_settings", return_value=_settings()):
        llm = get_llm()
    assert isinstance(llm, ChatGroq)
    assert llm.model_name == "openai/gpt-oss-120b"


def test_fallback_configured_returns_a_chain():
    with patch(
        "app.config.get_settings",
        return_value=_settings(guardian_fallback_models="openai/gpt-oss-20b"),
    ):
        llm = get_llm()
    assert isinstance(llm, RunnableWithFallbacks)


def test_fallback_list_drops_a_duplicate_of_the_primary_model():
    """Listing the primary model as its own fallback would make the chain
    retry the exact thing that just failed - not a fallback, a second
    attempt at the identical dead model id."""
    with patch(
        "app.config.get_settings",
        return_value=_settings(
            guardian_model="openai/gpt-oss-120b",
            guardian_fallback_models="openai/gpt-oss-120b,openai/gpt-oss-20b",
        ),
    ):
        llm = get_llm()
    assert isinstance(llm, RunnableWithFallbacks)
    assert len(llm.fallbacks) == 1
    assert llm.fallbacks[0].model_name == "openai/gpt-oss-20b"


def test_the_chain_still_supports_bind_tools():
    """The one caller a gateway could break silently: supervisor.py calls
    .bind_tools(TOOLS) on whatever get_llm() returns. A fallback wrapper that
    only worked for plain .invoke() callers would leave the tool-calling
    router - the project's actual differentiator - broken."""
    with patch(
        "app.config.get_settings",
        return_value=_settings(guardian_fallback_models="openai/gpt-oss-20b"),
    ):
        llm = get_llm()
    bound = llm.bind_tools([])
    assert hasattr(bound, "invoke")


def test_primary_failure_falls_through_to_the_fallback_model():
    """The behaviour the whole feature exists for: a dead or rate-limited
    primary model does not surface as an error to the caller, it surfaces as
    an answer from the fallback model."""
    with patch(
        "app.config.get_settings",
        return_value=_settings(guardian_fallback_models="openai/gpt-oss-20b"),
    ):
        llm = get_llm()

    calls = []

    def fake_invoke(self, messages, *args, **kwargs):
        calls.append(self.model_name)
        if self.model_name == "openai/gpt-oss-120b":
            raise RuntimeError("model_not_found: this id was retired")
        return AIMessage(content="answered by the fallback")

    with patch.object(ChatGroq, "invoke", fake_invoke):
        result = llm.invoke("does this project have SQL injection?")

    assert calls == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    assert result.content == "answered by the fallback"
