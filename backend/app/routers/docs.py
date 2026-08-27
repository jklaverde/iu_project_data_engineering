import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

logger = logging.getLogger(__name__)

# Admin-only surface (gated at app.include_router() in main.py, matching this
# codebase's existing pattern - see admin.alerts_router). Serves the project's
# own .md documentation from inside the image (backend/Dockerfile copies these
# files in at build time - see docs_bundle/), so an administrator can read how
# the system was conceived and built without leaving the app or needing repo
# access on the host.
router = APIRouter(prefix="/api/admin/docs", tags=["admin"])

DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs_bundle"

# Ordered the way a newcomer should read them: project overview first, then
# how the system is built, then what every file does, then how to deploy it.
# Scoped to what an administrator needs to understand the running system -
# REQUIREMENTS.md (full decision log), PROGRESS.md (development status) and
# TROUBLESHOOTING.md (dev-time incident notes) stay in the repository as the
# project's own record but are deliberately not served here.
CATALOG = [
    {"id": "readme", "title": "README — Project Overview & Quick Start", "filename": "README.md"},
    {"id": "architecture", "title": "Architecture — How the System Is Built", "filename": "ARCHITECTURE.md"},
    {"id": "project-structure", "title": "Project Structure — What Every File Does", "filename": "PROJECT_STRUCTURE.md"},
    {"id": "deployment", "title": "Deployment — Putting This on a Public VPS", "filename": "DEPLOYMENT.md"},
]
CATALOG_BY_ID = {entry["id"]: entry for entry in CATALOG}


@router.get("")
async def list_docs():
    return {"docs": [{"id": entry["id"], "title": entry["title"]} for entry in CATALOG]}


@router.get("/{doc_id}")
async def get_doc(doc_id: str):
    entry = CATALOG_BY_ID.get(doc_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown document")

    path = DOCS_DIR / entry["filename"]
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        # Would mean the Dockerfile's COPY list and this CATALOG have drifted
        # apart - a build-time problem, not a client error.
        logger.error("doc file missing from image: %s", path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document unavailable")

    return {"id": entry["id"], "title": entry["title"], "content": content}
