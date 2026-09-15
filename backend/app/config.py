"""Runtime configuration and the shared LLM factory.

Every agent goes through :func:`get_llm` so that the model, temperature and
retry policy are decided in exactly one place.  Temperature is pinned to 0 by
default: the supervisor's routing decision is a classification, not a creative
act, and a wandering router is the failure mode we care most about (see
docs/TECHNICAL_SPEC.md §3a).
"""

from __future__ import annotations

from functools import lru_cache

from langchain_groq import ChatGroq
from pydantic_settings import BaseSettings, SettingsConfigDict

from .token_usage import TRACKING_CALLBACK


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="", extra="ignore"
    )

    groq_api_key: str = ""
    guardian_model: str = "openai/gpt-oss-120b"
    guardian_cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # A gateway needs somewhere to fail over *to*. Empty by default - a single
    # model is the honest default for a project with one Groq key, and this
    # only turns on when a fallback list is actually configured. See
    # get_llm() for why this is one model, not a chain: this project has one
    # provider, one key, so a genuine cross-provider gateway is not being
    # simulated here.
    guardian_fallback_models: str = ""

    # Phase 2
    github_token: str = ""
    github_webhook_secret: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.guardian_cors_origins.split(",") if o.strip()]

    @property
    def fallback_model_list(self) -> list[str]:
        return [m.strip() for m in self.guardian_fallback_models.split(",") if m.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def _client(model: str, temperature: float, settings: Settings) -> ChatGroq:
    return ChatGroq(
        model=model,
        api_key=settings.groq_api_key,
        temperature=temperature,
        max_retries=2,
        timeout=120,
        # Bound once, here, rather than passed at every one of the five call
        # sites — see app/token_usage.py for why one stateless callback
        # instance shared across every cached client is the correct scope,
        # and app/graph.py for where the per-review tracker it reads from
        # actually gets set.
        callbacks=[TRACKING_CALLBACK],
    )


@lru_cache(maxsize=4)
def get_llm(temperature: float = 0.0):
    """Return the shared LLM client - a fallback chain when one is configured,
    a single ``ChatGroq`` otherwise.

    Cached per temperature so the supervisor (0.0) and the patch generator
    (which may want a little slack) do not each open their own client.

    **Why a gateway matters here specifically:** this project has already hit
    a dead model id in production (docs/BUILD_AND_DEPLOY.md - Groq retired
    ``llama-3.3-70b-versatile`` mid-project, a 404 no mock ever caught). A
    retired or rate-limited model is not a bug in the code, and every one of
    the five callers below has no way to tell the difference between "the
    model is gone" and "my prompt is wrong" unless something sits in front of
    the client and retries elsewhere.

    ``with_fallbacks`` was chosen over a hand-rolled try/except around every
    call site for one reason: it returns something that still satisfies the
    same interface every caller already depends on. ``supervisor.py`` calls
    ``.bind_tools(TOOLS)`` on whatever this returns - a fallback chain has to
    survive that call unchanged, or the gateway would only work for the four
    callers that just call ``.invoke()`` and silently break the one caller
    that matters most. Verified directly against the pinned
    ``langchain-core==0.3.29``: ``RunnableWithFallbacks.bind_tools(...)``
    returns another bindable, invokable Runnable - not a plain ChatGroq, but
    every caller here only ever calls ``.bind_tools()`` or ``.invoke()``, both
    of which the wrapper honours.

    **Only one provider.** ``GUARDIAN_FALLBACK_MODELS`` is a list of Groq
    model ids, not other providers - this account has one Groq key, so a
    genuine multi-provider gateway would need a second vendor's key this
    project does not have. Falling over to a second Groq model is real
    protection against a retired or saturated model id; it is not protection
    against Groq itself being down. Overclaiming that distinction is the
    difference between describing a gateway and describing this one.
    """
    settings = get_settings()
    if not settings.groq_api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Copy backend/.env.example to backend/.env "
            "and fill it in, or export the variable before starting the server."
        )

    primary = _client(settings.guardian_model, temperature, settings)
    fallback_ids = [m for m in settings.fallback_model_list if m != settings.guardian_model]
    if not fallback_ids:
        return primary

    fallbacks = [_client(m, temperature, settings) for m in fallback_ids]
    return primary.with_fallbacks(fallbacks)
