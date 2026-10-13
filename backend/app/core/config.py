from pathlib import Path

from pydantic import Field, model_validator
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

    @model_validator(mode="after")
    def validate_mail(self):
        if self.mail_mode not in {"outbox", "smtp"}:
            raise ValueError("MAIL_MODE must be outbox or smtp")
        if self.cookie_secure and self.mail_mode == "outbox":
            raise ValueError("Production requires SMTP mail delivery")
        if self.mail_mode == "smtp" and not self.smtp_host:
            raise ValueError("SMTP_HOST is required for SMTP delivery")
        return self


settings = Settings()
