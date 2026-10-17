# ruff: noqa: E402
"""Reproduce similar-bug retrieval metrics in a disposable PostgreSQL database.

backend/.venv/bin/python infra/run_eval.py --output eval/similar_bugs/results.json
Pass --model-path DIR for a verified local candidate; repeat for a model comparison.
No model or workspace text is sent over the network by this evaluation.
"""

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
import time
import uuid
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import settings

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--model-path", type=Path, action="append")
parser.add_argument("--output", type=Path, default=ROOT / "eval/similar_bugs/results.json")
args = parser.parse_args()
original_url = make_url(settings.database_url)
database = "tandem_eval_" + uuid.uuid4().hex
admin = create_engine(original_url, isolation_level="AUTOCOMMIT")
with admin.connect() as connection:
    connection.execute(text(f'CREATE DATABASE "{database}"'))
settings.database_url = original_url.set(database=database).render_as_string(hide_password=False)
settings.agent_worker_enabled = False
# Import the app/database only after redirecting to the disposable database.
from alembic import command
from alembic.config import Config

from app.core.db import SessionLocal, engine
from app.core.models import Membership, User, Workspace
from app.memory.embeddings import LocalEmbedding, ModelUnavailable
from app.memory.indexing import backfill, process_one
from app.memory.models import MemorySource
from app.memory.retrieval import SearchInput, search
from app.tasks.models import Project, Task


def percentile(values, p):
    return sorted(values)[max(0, math.ceil(len(values) * p) - 1)] if values else None


def evaluate(wid, uid, queries, document_ids, method, selected):
    rows = []
    latencies = []
    for query in queries:
        start = time.perf_counter()
        with SessionLocal() as db:
            result = search(
                db,
                wid,
                uid,
                SearchInput(query=query["query"], mode=method, limit=30),
                bugs_only=True,
                embedder=selected,
            )
        latencies.append((time.perf_counter() - start) * 1000)
        all_items = list(result["items"])
        cursor = result["next_cursor"]
        while cursor:
            with SessionLocal() as db:
                page = search(
                    db,
                    wid,
                    uid,
                    SearchInput(query=query["query"], mode=method, limit=30, cursor=cursor),
                    bugs_only=True,
                    embedder=selected,
                )
            all_items.extend(page["items"])
            cursor = page["next_cursor"]
        if method != "full_text" and result["degraded"]:
            return {"status": "not_run_model_unavailable"}
        retrieved = [document_ids[r["source_id"]] for r in all_items]
        ranks = [retrieved.index(i) + 1 for i in query["relevant_ids"] if i in retrieved]
        rank = min(ranks) if ranks else None
        rows.append(
            {
                "language": query["language"],
                "hit5": bool(rank and rank <= 5),
                "rr": 1 / rank if rank else 0,
            }
        )
    groups = {}
    for lang in ["en", "ar", "overall"]:
        part = [r for r in rows if lang == "overall" or r["language"] == lang]
        groups[lang] = {
            "queries": len(part),
            "recall_at_5": round(statistics.mean(int(r["hit5"]) for r in part), 4),
            "mrr": round(statistics.mean(r["rr"] for r in part), 4),
        }
    return {
        "status": "completed",
        "metrics": groups,
        "p95_retrieval_ms": round(percentile(latencies, 0.95), 2),
    }


result = {
    "mode": "synthetic_evaluation",
    "seed": 20261017,
    "ranking": {
        "rrf_k": 60,
        "full_text_weight": 1,
        "vector_weight": 1,
        "test_set_tuning": "none; parameters fixed before test",
    },
    "mrr_scope": "reciprocal rank over every returned page within the service candidate cap of 200; corpus has 75 documents; missing targets contribute zero",
    "models": [],
}
try:
    migration = Config(str(ROOT / "backend/alembic.ini"))
    migration.set_main_option("script_location", str(ROOT / "backend/migrations"))
    command.upgrade(migration, "head")
    dataset = json.loads((ROOT / "eval/similar_bugs/cases.json").read_text())
    result.update(documents=len(dataset["documents"]), queries=len(dataset["queries"]))
    with SessionLocal() as db:
        user = User(
            email="synthetic-eval@example.com",
            name="Synthetic evaluation",
            password_hash="not-an-authentication-fixture",
        )
        workspace = Workspace(name="Disposable synthetic retrieval evaluation")
        db.add_all([user, workspace])
        db.flush()
        wid, uid = workspace.id, user.id
        db.add(Membership(workspace_id=wid, user_id=uid, role="owner"))
        project = Project(workspace_id=wid, name="Synthetic bugs", key="EVAL")
        db.add(project)
        db.flush()
        document_ids = {}
        for number, doc in enumerate(dataset["documents"], 1):
            task = Task(
                id=str(
                    uuid.uuid5(uuid.NAMESPACE_URL, f"tandem-eval-{dataset['seed']}-{doc['id']}")
                ),
                workspace_id=wid,
                project_id=project.id,
                number=number,
                key=f"BUG-{number}",
                title=doc["title"],
                description=doc["description"],
                type="bug",
                status="done",
                reporter_id=uid,
                rank=Decimal(number),
            )
            db.add(task)
            db.flush()
            document_ids[task.id] = doc["id"]
        db.commit()
    candidates = args.model_path or [settings.memory_model_path]
    for candidate in candidates:
        try:
            selected = LocalEmbedding(candidate)
            identity = {
                "id": selected.identity[0],
                "version": selected.identity[1],
                "dimension": 384,
                "license": selected.manifest["license"],
                "model_bytes": selected.manifest["bytes"],
            }
        except ModelUnavailable:
            selected = None
            identity = {"id": "unavailable", "status": "model_not_downloaded_or_invalid"}
        with SessionLocal() as db:
            backfill(db, wid)
            db.commit()
        # Disable implicit use of another configured model in a missing-candidate run.
        prior_enabled = settings.memory_embedding_enabled
        settings.memory_embedding_enabled = bool(selected)
        started = time.perf_counter()
        jobs = 0
        while process_one(embedder=selected, raise_errors=True):
            jobs += 1
        seconds = time.perf_counter() - started
        with SessionLocal() as db:
            lags = [
                s.lag_ms
                for s in db.scalars(select(MemorySource).where(MemorySource.workspace_id == wid))
                if s.lag_ms is not None
            ]
        methods = {}
        for method in ["full_text", "vector", "hybrid"]:
            if not selected and method != "full_text":
                methods[method] = {"status": "not_run_model_unavailable"}
            else:
                methods[method] = evaluate(
                    wid, uid, dataset["queries"], document_ids, method, selected
                )
        settings.memory_embedding_enabled = prior_enabled
        result["models"].append(
            {
                "model": identity,
                "indexing": {
                    "jobs": jobs,
                    "seconds": round(seconds, 3),
                    "source_documents_per_second": round(len(dataset["documents"]) / seconds, 2),
                    "p95_lag_ms": percentile(lags, 0.95),
                },
                "methods": methods,
            }
        )
    completed = [
        m["methods"]["hybrid"]
        for m in result["models"]
        if m["methods"]["hybrid"].get("status") == "completed"
    ]
    result["hybrid_target_status"] = (
        "passed"
        if any(m["metrics"]["overall"]["recall_at_5"] >= 0.7 for m in completed)
        else "failed"
        if completed
        else "not_verified_model_unavailable"
    )
    child_environment = os.environ.copy()
    child_environment.update(DATABASE_URL=settings.database_url, MEMORY_EMBEDDING_ENABLED="false")
    cli = subprocess.run(
        [sys.executable, str(ROOT / "infra/memory_backfill.py"), "--workspace", wid, "--drain"],
        cwd=ROOT,
        env=child_environment,
        capture_output=True,
        text=True,
        timeout=120,
    )
    result["backfill_cli"] = {
        "exit_code": cli.returncode,
        "status": "passed" if cli.returncode == 0 else "failed",
    }
    if cli.returncode == 0:
        result["backfill_cli"]["metadata"] = json.loads(cli.stdout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
finally:
    engine.dispose()
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))
    admin.dispose()
