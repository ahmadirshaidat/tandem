"""Queue backfill/reindex with current settings. Run using backend dependencies."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core.db import SessionLocal
from app.core.models import Workspace
from app.memory.indexing import backfill, process_one

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--workspace", required=True)
parser.add_argument(
    "--drain",
    action="store_true",
    help="Process pending jobs with local embeddings or degraded full-text",
)
args = parser.parse_args()
with SessionLocal() as db:
    if not db.get(Workspace, args.workspace):
        raise SystemExit("Workspace not found")
    backfill(db, args.workspace)
    db.commit()
count = 0
if args.drain:
    while process_one():
        count += 1
print(json.dumps({"status": "queued" if not args.drain else "processed", "jobs_processed": count}))
