from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    database_url: str
    jwt_secret: str = Field(min_length=32)
    frontend_url: str = "http://localhost:3000"
    cookie_secure: bool = False
    access_minutes: int = 15
    refresh_days: int = 14
    auth_rate_limit: int = 10
    auth_rate_window: int = 60
    mail_mode: str = "outbox"
    mail_outbox: Path = ROOT / ".local" / "mail"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    mail_from: str = "Tandem <no-reply@localhost>"
    attachment_dir: Path = ROOT / ".local" / "attachments"
    message_requests_per_minute: int = Field(default=60, ge=1, le=600)
    ws_connections_per_user: int = Field(default=5, ge=1, le=50)
    ws_connections_per_ip: int = Field(default=30, ge=1, le=300)
    ws_frames_per_minute: int = Field(default=120, ge=10, le=1200)
    ws_idle_seconds: int = Field(default=60, ge=10, le=600)
    groq_api_key: SecretStr | None = None
    deepseek_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    tandem_openai_api_key: SecretStr | None = None
    groq_model: str = "openai/gpt-oss-20b"
    deepseek_model: str = "deepseek-flash"
    gemini_model: str = "gemini-3.8-flash"
    openai_model: str = "gpt-5.5"
    ai_primary_provider: str = "groq"
    ai_provider_timeout_seconds: float = Field(default=10, ge=1, le=30)
    ai_max_output_tokens: int = Field(default=512, ge=16, le=2048)
    proposal_expiry_days: int = Field(default=7, ge=1, le=30)
    proposal_pending_per_channel: int = Field(default=20, ge=1, le=100)
    agent_worker_enabled: bool = True
    agent_provider_timeout_seconds: float = Field(default=15, ge=1, le=30)
    agent_max_output_tokens: int = Field(default=2048, ge=256, le=4096)
    agent_fake_provider: bool = False
    agent_run_timeout_seconds: float = Field(default=60, ge=0.01, le=120)
    agent_user_runs_per_minute: int = Field(default=5, ge=1, le=1000)
    agent_workspace_runs_per_minute: int = Field(default=20, ge=1, le=1000)
    agent_workspace_concurrency: int = Field(default=1, ge=1, le=4)
    agent_worker_slots: int = Field(default=4, ge=1, le=8)
    ai_requests_per_minute: int = Field(default=5, ge=1, le=60)

    @field_validator(
        "groq_api_key", "deepseek_api_key", "gemini_api_key", "tandem_openai_api_key", mode="before"
    )
    @classmethod
    def empty_key_is_missing(cls, value):
        return value or None

    @model_validator(mode="after")
    def validate_mail(self):
        if self.ai_primary_provider not in {"groq", "gemini", "deepseek", "openai"}:
            raise ValueError("AI_PRIMARY_PROVIDER must be groq, gemini, deepseek, or openai")
        if self.mail_mode not in {"outbox", "smtp"}:
            raise ValueError("MAIL_MODE must be outbox or smtp")
        if self.cookie_secure and self.mail_mode == "outbox":
            raise ValueError("Production requires SMTP mail delivery")
        if self.mail_mode == "smtp" and not self.smtp_host:
            raise ValueError("SMTP_HOST is required for SMTP delivery")
        return self


settings = Settings()
