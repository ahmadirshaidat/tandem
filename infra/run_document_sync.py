"""Start the Node document service using backend private configuration; prints no secrets."""
import os
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.core.config import settings
from app.documents.service import sync_secret
environment=os.environ.copy()
environment.update(DOCUMENT_SYNC_SECRET=sync_secret(),FRONTEND_URL=settings.frontend_url)
raise SystemExit(subprocess.call(['node','sync/server.mjs'],cwd=ROOT,env=environment))
