import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

# Admin-only surface (gated at app.include_router() in main.py, matching this
# codebase's existing pattern - see admin.alerts_router). Serves the local
# docs/ site (backend/Dockerfile copies it in at build time - see docs_site/)
# byte-for-byte, so an administrator sees exactly the same pages a developer
# opens directly via file://, one authored place, two ways to read it (D36/D37).
router = APIRouter(prefix="/api/admin/docs-site", tags=["admin"])

DOCS_DIR = (Path(__file__).resolve().parent.parent.parent / "docs_site").resolve()

# The frontend's DocsTab.tsx hardcodes this same small set of top-level pages
# to iframe - docs/assets/ and docs/vendor/ are fetched by those pages
# themselves via relative paths, never listed here.
PAGES = ["index.html", "containers.html", "deployment.html", "operations.html", "reference.html"]


@router.get("")
async def docs_site_index():
    return await get_doc_asset("index.html")


@router.get("/{path:path}")
async def get_doc_asset(path: str):
    target = (DOCS_DIR / (path or "index.html")).resolve()
    if not target.is_relative_to(DOCS_DIR) or not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    media_type, _ = mimetypes.guess_type(str(target))
    return FileResponse(target, media_type=media_type)
