"""Create private local configuration without overwriting any existing files."""
import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / ".env"
if not path.exists():
    password = secrets.token_hex(24)
    content = (f"POSTGRES_PASSWORD={password}\n"
               f"DATABASE_URL=postgresql+psycopg://tandem:{password}@localhost:5432/tandem\n"
               f"JWT_SECRET={secrets.token_hex(32)}\n"
               "FRONTEND_URL=http://localhost:3000\nCOOKIE_SECURE=false\nMAIL_MODE=outbox\n")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(content)
    print("Created private local .env; no credentials were printed.")
else:
    print("Existing .env preserved.")
