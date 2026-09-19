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

    # Comma-separated Groq ids to fall back to. Empty by default — same-provider
    # fallback only; see get_llm().
    guardian_fallback_models: str = ""

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
        # One stateless callback shared by every cached client; the per-review
        # tracker it writes to is set in graph.py.
        callbacks=[TRACKING_CALLBACK],
    )


@lru_cache(maxsize=4)
def get_llm(temperature: float = 0.0):
    """The shared LLM client: a ``with_fallbacks`` chain when
    ``GUARDIAN_FALLBACK_MODELS`` is set, a single ``ChatGroq`` otherwise.

    Cached per temperature so callers do not each open their own client.

    The gateway exists because Groq retired ``llama-3.3-70b-versatile``
    mid-project and every audit started 404ing — a failure no mock had caught.
    ``with_fallbacks`` rather than try/except at each call site because it
    returns a Runnable that still answers ``.bind_tools()``, which
    ``supervisor.py`` depends on.

    Fallbacks are other **Groq** ids, so this protects against a dead or
    saturated model, not against Groq being down.
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
