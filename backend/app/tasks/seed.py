"""Create a separate synthetic workspace for an existing local account.

Run from backend: .venv/bin/python -m app.tasks.seed --owner-email you@example.com
No existing workspace, credentials or provider settings are changed.
"""

import argparse
import json

from sqlalchemy import select

from app.channels.models import Channel  # noqa: F401
from app.core.db import SessionLocal
from app.core.models import Membership, User, Workspace
from app.tasks.models import Project
from app.tasks.schemas import TaskInput
from app.tasks.service import create_task


def seed(owner_email, count=1000):
    if not 1 <= count <= 10000:
        raise ValueError("Choose between 1 and 10,000 synthetic tasks")
    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.email == owner_email.lower().strip()))
        if not owner:
            raise ValueError("Create an account first, then pass its email")
        workspace = Workspace(name="Task performance demo")
        db.add(workspace)
        db.flush()
        db.add(Membership(workspace_id=workspace.id, user_id=owner.id, role="owner"))
        project = Project(
            workspace_id=workspace.id,
            name="Web app",
            key="WEB",
            color="brand",
            description="Synthetic tasks for measuring board performance.",
        )
        db.add(project)
        db.flush()
        for index in range(count):
            create_task(
                db,
                workspace.id,
                TaskInput(
                    project_id=project.id,
                    title=f"Synthetic task {index + 1:04d}",
                    description="Synthetic measurement data. No customer content.",
                    type="bug" if index % 5 == 0 else "task",
                    status=["todo", "in_progress", "done"][index % 3],
                    priority=["P1", "P2", "P3"][index % 3],
                    assignee_id=owner.id if index % 2 == 0 else None,
                ),
                owner.id,
            )
        db.commit()
        return {"workspace_id": workspace.id, "project_id": project.id, "tasks": count}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-email", required=True)
    parser.add_argument("--count", type=int, default=1000)
    args = parser.parse_args()
    try:
        print(json.dumps(seed(args.owner_email, args.count)))
    except ValueError as error:
        parser.exit(1, str(error) + "\n")
