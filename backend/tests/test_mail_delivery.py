"""HTTPS mail transport contracts; no external email is sent."""

import json
from urllib.error import HTTPError, URLError

import pytest
from pydantic import SecretStr, ValidationError

from app.core import mail
from app.core.config import Settings, settings


def configured(**changes):
    values = {
        "database_url": "postgresql+psycopg://synthetic:synthetic@localhost/test",
        "jwt_secret": "synthetic-signing-material-at-least-32-characters",
        "mail_mode": "resend",
        "resend_api_key": "synthetic-mail-key",
        "mail_from": "Tandem <owner@example.com>",
        "cookie_secure": True,
    }
    values.update(changes)
    return Settings(_env_file=None, **values)


def test_https_mail_configuration_keeps_secure_cookies():
    config = configured()
    assert config.cookie_secure
    assert config.resend_api_key.get_secret_value() not in repr(config.resend_api_key)


@pytest.mark.parametrize(
    "changes",
    [
        {"resend_api_key": None},
        {"resend_api_key": " "},
        {"mail_from": "Tandem <no-reply@localhost>"},
        {"mail_from": ""},
        {"mail_mode": "outbox"},
    ],
)
def test_incomplete_real_mail_configuration_is_rejected(changes):
    with pytest.raises(ValidationError):
        configured(**changes)


def enable(monkeypatch):
    monkeypatch.setattr(settings, "mail_mode", "resend")
    monkeypatch.setattr(settings, "resend_api_key", SecretStr("synthetic-mail-key"))
    monkeypatch.setattr(settings, "mail_from", "Tandem <owner@example.com>")


def test_reset_email_uses_https_and_preserves_existing_reset_link(monkeypatch):
    enable(monkeypatch)
    requests = []

    class Response:
        status = 202

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    def send(request, *, timeout):
        requests.append(request)
        assert timeout == 10
        return Response()

    monkeypatch.setattr(mail, "urlopen", send)
    url = "https://synthetic.example.test/reset-password?token=synthetic-token"
    mail.send_reset("recipient@example.com", url)
    assert len(requests) == 1
    request = requests[0]
    assert request.full_url == "https://api.resend.com/emails"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer synthetic-mail-key"
    data = json.loads(request.data)
    assert data["from"] == settings.mail_from
    assert data["to"] == ["recipient@example.com"]
    assert data["subject"] == "Reset your Tandem password"
    assert url in data["text"]
    assert "30 minutes" in data["text"]
    assert "synthetic-mail-key" not in request.data.decode()


@pytest.mark.parametrize("failure", ["http", "network", "timeout"])
def test_provider_failures_do_not_expose_reset_tokens_or_provider_content(monkeypatch, failure):
    enable(monkeypatch)

    def send(*_, **__):
        if failure == "http":
            raise HTTPError("https://api.resend.com/emails", 429, "private-provider-body", {}, None)
        if failure == "timeout":
            raise TimeoutError("synthetic-mail-key")
        raise URLError("synthetic-token")

    monkeypatch.setattr(mail, "urlopen", send)
    with pytest.raises(RuntimeError, match="^Email delivery unavailable$") as error:
        mail.send_reset(
            "recipient@example.com", "https://synthetic.example.test/?token=synthetic-token"
        )
    assert error.value.__suppress_context__
