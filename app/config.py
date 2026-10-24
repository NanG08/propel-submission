# config.py
"""Application configuration settings.
Uses pydantic-settings to load from environment variables with defaults.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    """Configuration values for the app.

    - ``TRIAGE_MODE`` defaults to ``"replay"`` when no API keys are set.
    - ``DB_PATH`` defaults to ``"triage_state.db"``.
    - ``CONFIDENCE_THRESHOLD`` defaults to ``0.75``.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Determine default triage mode based on presence of API keys
    @property
    def TRIAGE_MODE(self) -> str:
        if os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY"):
            return os.getenv("TRIAGE_MODE", "live")
        return "replay"

    DB_PATH: str = "triage_state.db"
    CONFIDENCE_THRESHOLD: float = 0.75

settings = Settings()
