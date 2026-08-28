from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All fields match the .env.example keys exactly.
    Pydantic-settings reads from a .env file if present.
    """

    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    GROQ_API_KEY: str = ""
    ALLOWED_ORIGINS: str = "http://localhost:3000"
    ENV: str = "development"
    # UUID of the demo/anonymous profile row used for unauthenticated inserts.
    # Required for Supabase persistence (reports.user_id NOT NULL).
    # Remains empty until T3-1 (JWT auth) is implemented; Supabase path is
    # skipped when this is unset, preserving the in-memory fallback.
    DEMO_USER_ID: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
