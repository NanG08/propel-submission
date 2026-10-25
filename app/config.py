"""Application configuration settings.

A lightweight stub that mimics the original ``pydantic‑settings`` behaviour
without requiring the external ``pydantic‑settings`` package. Only the
few settings needed by the codebase are defined.

The class inherits from ``BaseModel`` (not ``BaseSettings``) and manually
loads environment variables in ``__init__`` so the rest of the code can
continue to use ``settings.<attr>`` unchanged.
"""
import os
from pydantic import BaseModel, Field, validator

class Settings(BaseModel):
    """Configuration values for the app.

    - ``TRIAGE_MODE`` defaults to ``"replay"`` when no API keys are set.
    - ``DB_PATH`` defaults to ``"triage_state.db"``.
    - ``CONFIDENCE_THRESHOLD`` defaults to ``0.75``.
    """
    DB_PATH: str = Field(default="triage_state.db")
    CONFIDENCE_THRESHOLD: float = Field(default=0.75)

    # -----------------------------------------------------------------------
    # Initialise from environment – replicates a tiny subset of BaseSettings
    # -----------------------------------------------------------------------
    def __init__(self, **data):
        # Pull known vars from the environment, falling back to defaults.
        env_overrides = {
            "DB_PATH": os.getenv("DB_PATH", self.__fields__["DB_PATH"].default),
            "CONFIDENCE_THRESHOLD": float(
                os.getenv(
                    "CONFIDENCE_THRESHOLD",
                    self.__fields__["CONFIDENCE_THRESHOLD"].default,
                )
            ),
        }
        # Merge any explicit kwargs (unlikely) with env values.
        combined = {**env_overrides, **data}
        super().__init__(**combined)

    # -----------------------------------------------------------------------
    # Helper property – decides if we run in live or replay mode.
    # -----------------------------------------------------------------------
    @property
    def TRIAGE_MODE(self) -> str:
        """Return ``live`` when an LLM API key is present, otherwise ``replay``.

        The optional ``TRIAGE_MODE`` env var can override the automatic
        detection (useful for explicit testing).
        """
        if os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY"):
            return os.getenv("TRIAGE_MODE", "live")
        return "replay"


# Export a singleton instance used throughout the application.
settings = Settings()