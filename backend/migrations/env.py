from alembic import context

from app.channels import models as channel_models  # noqa: F401
from app.core import models  # noqa: F401
from app.core.db import Base, engine
from app.tasks import models as task_models  # noqa: F401

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
