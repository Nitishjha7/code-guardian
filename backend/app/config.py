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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="", extra="ignore"
    )

    groq_api_key: str = ""
    guardian_model: str = "llama-3.3-70b-versatile"
    guardian_cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Phase 2
    github_token: str = ""
    github_webhook_secret: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.guardian_cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=4)
def get_llm(temperature: float = 0.0) -> ChatGroq:
    """Return a shared ChatGroq client.

    Cached per temperature so the supervisor (0.0) and the patch generator
    (which may want a little slack) do not each open their own client.
    """
    settings = get_settings()
    if not settings.groq_api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Copy backend/.env.example to backend/.env "
            "and fill it in, or export the variable before starting the server."
        )
    return ChatGroq(
        model=settings.guardian_model,
        api_key=settings.groq_api_key,
        temperature=temperature,
        max_retries=2,
        timeout=120,
    )
