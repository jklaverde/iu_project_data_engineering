# Build context is the repo root (not ./backend like every other service) -
# the frontend build stage needs to COPY from the sibling frontend/
# directory. See docker-compose.yml's backend service: `context: .`.

FROM node:24-slim AS frontend-build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11.9-slim-bookworm
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY backend/app/ ./app/
COPY --from=frontend-build /app/dist ./static

# Bundled for the admin-only "Docs" tab (backend/app/routers/docs.py) so an
# administrator can read how the system was conceived and built from inside
# the running app, with no repo checkout on the host required. Kept in sync
# with docs.py's CATALOG by hand - deliberately excludes REQUIREMENTS.md,
# docs/PROGRESS.md and docs/TROUBLESHOOTING.md (repository-only project
# record, not served in-app) and docs/internal/ (gitignored, local-only).
COPY README.md ./docs_bundle/
COPY docs/ARCHITECTURE.md docs/DEPLOYMENT.md docs/PROJECT_STRUCTURE.md ./docs_bundle/

ENV PYTHONUNBUFFERED=1

USER 1000:1000

ENTRYPOINT ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
