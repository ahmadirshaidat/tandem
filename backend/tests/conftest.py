import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings

# Every invocation gets a disposable database. Never truncate the development DB.
original_url = make_url(settings.database_url)
test_database = f"tandem_test_{uuid.uuid4().hex}"
settings.database_url = original_url.set(database=test_database).render_as_string(
    hide_password=False
)

from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    admin = create_engine(original_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{test_database}"'))
    try:
        config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
        config.set_main_option("script_location", str(Path(__file__).parents[1] / "migrations"))
        command.upgrade(config, "head")
        yield
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{test_database}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture(autouse=True)
def isolated_state(migrated_database, tmp_path):
    with engine.begin() as connection:
        tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
        connection.execute(text(f"TRUNCATE {tables} CASCADE"))
    limiter.hits.clear()
    settings.mail_outbox = tmp_path / "mail"
    yield


class Client(TestClient):
    def request(self, method, url, **kwargs):
        if method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            if not self.cookies.get("tandem_csrf"):
                super().request("GET", "/api/auth/csrf")
            headers = kwargs.pop("headers", None) or {}
            headers.setdefault("X-CSRF-Token", self.cookies.get("tandem_csrf"))
            kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


@pytest.fixture
def client():
    with Client(app) as value:
        yield value


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client_factory():
    clients = []

    def create(email, name="Teammate"):
        client = Client(app)
        clients.append(client)
        response = client.post(
            "/api/auth/register",
            json={"email": email, "name": name, "password": "a-long-test-password"},
        )
        assert response.status_code == 201, response.text
        return client, response.json()

    yield create
    for client in clients:
        client.close()
