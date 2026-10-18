"""Start one hosted backend; never print configuration values or provider content."""

import os
import pwd
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


def validate(environment):
    errors = []
    for name in ("DATABASE_URL", "JWT_SECRET", "FRONTEND_URL", "SMTP_HOST"):
        if not environment.get(name):
            errors.append(name)
    if len(environment.get("JWT_SECRET", "")) < 32:
        errors.append("JWT_SECRET (at least 32 characters)")
    try:
        url = urlsplit(environment.get("FRONTEND_URL", ""))
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            errors.append("FRONTEND_URL (HTTPS origin required)")
        if url.path not in ("", "/") or url.query or url.fragment:
            errors.append("FRONTEND_URL (origin only)")
    except ValueError:
        errors.append("FRONTEND_URL (valid HTTPS origin required)")
    if environment.get("COOKIE_SECURE", "").lower() not in ("true", "1"):
        errors.append("COOKIE_SECURE=true")
    if environment.get("MAIL_MODE") != "smtp":
        errors.append("MAIL_MODE=smtp")
    if environment.get("AGENT_FAKE_PROVIDER", "false").lower() not in ("false", "0"):
        errors.append("AGENT_FAKE_PROVIDER=false")
    if errors:
        raise ValueError("Hosted configuration requires: " + ", ".join(dict.fromkeys(errors)))


def prepare_data(root, uid, gid):
    for folder in (root, root / "attachments", root / "models", root / "mail"):
        if folder.is_symlink():
            raise ValueError("Persistent directories must not be symbolic links")
        folder.mkdir(mode=0o700, parents=False, exist_ok=True)
        if os.geteuid() == 0:
            os.chown(folder, uid, gid)
        folder.chmod(0o700)


def main():
    try:
        validate(os.environ)
        data = Path("/data")
        user = pwd.getpwnam("tandem")
        prepare_data(data, user.pw_uid, user.pw_gid)
        if os.geteuid() == 0:
            os.setgroups([])
            os.setgid(user.pw_gid)
            os.setuid(user.pw_uid)
        if os.geteuid() != user.pw_uid:
            raise ValueError("Backend must run as the tandem service user")
        os.environ.update(
            ATTACHMENT_DIR=str(data / "attachments"),
            MEMORY_MODEL_PATH=str(data / "models" / "e5-small"),
            MAIL_OUTBOX=str(data / "mail"),
        )
        database = os.environ["DATABASE_URL"]
        for prefix in ("postgres://", "postgresql://"):
            if database.startswith(prefix):
                os.environ["DATABASE_URL"] = "postgresql+psycopg://" + database[len(prefix) :]
                break
        subprocess.run(["alembic", "upgrade", "head"], check=True)
        # Verification and source/hash/license checks remain in the existing downloader.
        # First startup needs a model download; later starts reuse the persistent cache.
        model = data / "models" / "e5-small"
        if not (model / "manifest.json").is_file():
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app.memory.embeddings",
                    "e5-small",
                    "--destination",
                    str(model),
                ],
                check=True,
            )
        subprocess.run(
            [
                sys.executable,
                "-c",
                "from app.memory.embeddings import model; model().encode(['Synthetic startup check'])",
            ],
            check=True,
        )
        os.execv(
            sys.executable,
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--no-access-log",
                "--ws-max-size",
                "8192",
                "--ws-ping-interval",
                "15",
                "--ws-ping-timeout",
                "20",
            ],
        )
    except ValueError as error:
        # Only the controlled, value-free messages above reach this output.
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, KeyError, subprocess.SubprocessError):
        print(
            "Hosted startup failed; inspect service health and private configuration",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
