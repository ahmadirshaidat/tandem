"""Deployment bootstrap regressions; no provider calls, database writes or credentials."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "hosted_backend", Path(__file__).with_name("hosted_backend.py")
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def valid():
    return {
        "DATABASE_URL": "postgresql+psycopg://synthetic:canary-db-password@db/test",
        "JWT_SECRET": "synthetic-test-signing-material-32-characters",
        "FRONTEND_URL": "https://synthetic.example.test",
        "SMTP_HOST": "smtp.synthetic.example.test",
        "MAIL_MODE": "smtp",
        "COOKIE_SECURE": "true",
        "AGENT_FAKE_PROVIDER": "false",
    }


def test_valid_hosted_settings():
    module.validate(valid())


def test_https_mail_without_smtp():
    data = valid()
    data.update(
        MAIL_MODE="resend", RESEND_API_KEY="synthetic-key", MAIL_FROM="Tandem <test@example.com>"
    )
    del data["SMTP_HOST"]
    module.validate(data)


@pytest.mark.parametrize("field", ["RESEND_API_KEY", "MAIL_FROM"])
def test_https_mail_cannot_start_without_credentials_and_sender(field):
    data = valid()
    data.update(MAIL_MODE="resend", RESEND_API_KEY="synthetic-key", MAIL_FROM="test@example.com")
    del data[field]
    with pytest.raises(ValueError, match=field):
        module.validate(data)


@pytest.mark.parametrize(
    "key,value",
    [
        ("COOKIE_SECURE", "false"),
        ("MAIL_MODE", "outbox"),
        ("SMTP_HOST", ""),
        ("JWT_SECRET", "short"),
        ("FRONTEND_URL", "http://synthetic.example.test"),
        ("FRONTEND_URL", "https://canary-user:canary-password@synthetic.example.test"),
        ("FRONTEND_URL", "https://synthetic.example.test/path"),
        ("AGENT_FAKE_PROVIDER", "true"),
    ],
)
def test_invalid_hosted_settings_do_not_echo_values(key, value):
    data = valid()
    data[key] = value
    with pytest.raises(ValueError) as error:
        module.validate(data)
    assert "canary-db-password" not in str(error.value)
    assert "canary-password" not in str(error.value)
    assert data["JWT_SECRET"] not in str(error.value)
    assert key in str(error.value)


def test_data_directories_are_created_without_changing_existing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(module.os, "geteuid", lambda: 10001)
    root = tmp_path / "data"
    module.prepare_data(root, 10001, 10001)
    item = root / "attachments" / "synthetic.txt"
    item.write_text("synthetic attachment")
    module.prepare_data(root, 10001, 10001)
    assert item.read_text() == "synthetic attachment"
    assert {p.name for p in root.iterdir()} == {"attachments", "models", "mail"}
    assert all(p.stat().st_mode & 0o777 == 0o700 for p in root.iterdir())


def test_symlinked_volume_root_is_rejected(tmp_path):
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic"):
        module.prepare_data(link, 10001, 10001)


def test_symlinked_child_is_rejected_without_touching_target(tmp_path, monkeypatch):
    monkeypatch.setattr(module.os, "geteuid", lambda: 10001)
    root = tmp_path / "data"
    root.mkdir()
    target = tmp_path / "protected"
    target.mkdir(mode=0o755)
    before_mode = target.stat().st_mode
    (root / "attachments").symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic"):
        module.prepare_data(root, 10001, 10001)
    assert target.stat().st_mode == before_mode
