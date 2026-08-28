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

# Bundles the local docs/ site (see docs/index.html) into the image so the
# admin-only "Docs" tab (backend/app/routers/docs.py) can serve it in-app,
# byte-for-byte the same pages a developer opens directly via file://. Listed
# explicitly, one file/dir at a time - never `COPY docs/`, which would also
# pick up docs/internal/ from the host filesystem (.gitignore doesn't stop a
# Docker build context from seeing it; only listing exactly what's wanted
# does). REQUIREMENTS.md and root README.md stay repository-only, kept in
# sync with docs/index.html's own "Outside this site" links.
COPY docs/index.html docs/containers.html docs/containers-data.js docs/containers-charts.js \
     docs/deployment.html docs/operations.html docs/reference.html ./docs_site/
COPY docs/assets/ ./docs_site/assets/
COPY docs/vendor/ ./docs_site/vendor/

ENV PYTHONUNBUFFERED=1

USER 1000:1000

ENTRYPOINT ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
