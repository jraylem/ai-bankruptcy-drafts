from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # OpenAI Configuration
    OPENAI_API_KEY: str

    # Anthropic Configuration
    ANTHROPIC_API_KEY: str
    
    # Server Configuration
    HOST: str
    PORT: int
    
    # CORS Configuration
    ALLOWED_ORIGINS: list
    
    # File Upload Configuration
    MAX_FILE_SIZE_MB: int

    # Vectorstore Configuration
    VECTORSTORE_USER: str
    VECTORSTORE_PASSWORD: str
    VECTORSTORE_DB: str
    VECTORSTORE_HOST: str
    VECTORSTORE_PORT: int
    VECTORSTORE_URL: str

    # Database Configuration for Sessions and PDFs
    CHAT_DATABASE_USER: str
    CHAT_DATABASE_PASSWORD: str
    CHAT_DATABASE_DB: str
    CHAT_DATABASE_HOST: str
    CHAT_DATABASE_PORT: int
    CHAT_DATABASE_URL: str

    # Database Configuration for User Authentication
    USER_DATABASE_USER: str
    USER_DATABASE_PASSWORD: str
    USER_DATABASE_DB: str
    USER_DATABASE_HOST: str
    USER_DATABASE_PORT: int
    USER_DATABASE_URL: str

    # JWT Configuration
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int

    # Cookie / Session Configuration
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # Set False in local HTTP dev; True in production (HTTPS)
    COOKIE_SECURE: bool = True

    # Court mail polling worker configuration
    COURT_MAIL_POLL_WORKER_ENABLED: bool = True
    COURT_MAIL_POLL_INTERVAL_SECONDS: int = Field(default=3600, ge=5)
    COURT_MAIL_POLL_MAX_RESULTS_PER_TRIGGER: int = Field(default=50, ge=1, le=200)
    COURT_MAIL_POLL_RUN_ON_STARTUP: bool = True

    # Redis Configuration
    REDIS_URL: str = "redis://redis:6379/0"

    # Task Queue Concurrency
    MAX_CONCURRENT_PLEADING_TASKS: int = 20
    MAX_CONCURRENT_REVIEW_TASKS: int = 20

    # Stripe Configuration
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_PUBLIC_KEY: str | None = None

    # Email (Resend) Configuration
    EMAIL_API_KEY: str
    EMAIL_FROM_ADDRESS: str
    FRONTEND_URL: str
    APPROVAL_ADMIN_EMAIL: str

    # LangSmith Configuration (tracing/observability)
    LANGSMITH_TRACING: bool = False
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_PROJECT: str = "bkdrafts-agt-revamp"

    # Case-vector vision-fallback agent (re-extracts low-confidence
    # case_vector values directly from the petition PDF via claude-opus-4-6).
    CASE_VECTOR_VISION_FALLBACK_ENABLED: bool = True
    CASE_VECTOR_VISION_FALLBACK_THRESHOLD: Literal["low", "medium"] = "medium"

    # Web-search enhancement for case_vector fields. When True (default),
    # WebSearchEnhanceResolver runs after the case_vector vision pass for
    # every case_vector field whose source_params has enable_web_search=True.
    # Set False in staging or to halt all web-lookup spend across templates
    # without touching individual specs.
    WEB_SEARCH_ENHANCE_ENABLED: bool = True

    # v2 ECF inbox — cron-driven Gmail/PACER intake.
    # ENABLE_ECF_INGEST gates the `ingest_ecf_inbox` cron at the task body.
    # Default False on purpose: PACER notice emails carry one-shot "free
    # look" links that are consumed by the first GET. If every dev's local
    # taskiq_worker_core ran the cron, the first one to fire would burn the
    # link before the firm's prod ingest could grab it. Operators with
    # legitimate access (prod, or the dev who owns the shared OAuth token)
    # set ENABLE_ECF_INGEST=true in their .env to opt in. Other devs leave
    # it unset and their local cron self-skips, logging a clear INFO. The
    # archive_stale_inbox cron is NOT gated — it's idempotent and harmless.
    ENABLE_ECF_INGEST: bool = False
    # DEFAULT_INTAKE_FIRM_ID is the firm_id all cron-ingested petitions are
    # attributed to (single-firm in v1 since the Gmail OAuth token is shared).
    # Multi-firm support is a future PR; set once per env.
    DEFAULT_INTAKE_FIRM_ID: str = ""
    ECF_INBOX_GMAIL_LOOKBACK_MINUTES: int = 30
    ECF_INBOX_GMAIL_MAX_RESULTS: int = 50

    @computed_field
    @property
    def CELERY_BROKER_URL(self) -> str:
        return self.REDIS_URL

    @computed_field
    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        return self.REDIS_URL

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

# Global settings instance
settings = Settings()
