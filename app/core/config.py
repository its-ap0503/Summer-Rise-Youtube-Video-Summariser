import os
from dotenv import load_dotenv

# Load key-value pairs from the .env file into the OS environment table
load_dotenv()


def _getenv_int(key: str, default: int) -> int:
    """Return an environment variable as int, falling back to *default* when
    the variable is missing OR set to an empty string."""
    value = os.getenv(key, "").strip()
    return int(value) if value else default


class Settings:
    """Centralized application configuration loaded from environment variables."""

    # LLM Configuration
    
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "").strip() or "gemini-3.5-flash-lite"

    # Redis Configuration (Defaults to local Redis instance, DB index 0)
    REDIS_URL: str = os.getenv("REDIS_URL", "").strip() or "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = _getenv_int("CACHE_TTL_SECONDS", 86400)  # 24 hours

    # Rate Limiting Configuration (5 Cache-Miss LLM calls per 60 seconds per IP)
    RATE_LIMIT_MAX_REQUESTS: int = _getenv_int("RATE_LIMIT_MAX_REQUESTS", 5)
    RATE_LIMIT_WINDOW_SECONDS: int = _getenv_int("RATE_LIMIT_WINDOW_SECONDS", 60)

    # PostgreSQL Configuration
    DATABASE_URL: str = (
        os.getenv("DATABASE_URL", "").strip()
        or "postgresql://postgres:postgres@localhost:5432/YouTube_video_summariser"
    )


# Instantiate a singleton config object to import across services
settings = Settings()
