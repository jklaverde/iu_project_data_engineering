# Build context is the repo root (not ./backend like every other service) -
# the frontend build stage needs to COPY from the sibling frontend/
# directory. See docker-compose.yml's backend service: `context: .`.

FROM node:24.21.0-slim AS frontend-build
WORKDIR /app
# Pinned Node (a floating node:24-slim had already moved to a release younger
# than the 14-day cooldown, NFR-10.3) and a pinned npm on top of the bundled
# one: fetched with `npm pack`, its sha512 checked against the value the
# registry publishes (dist.integrity), installed without lifecycle scripts
# (NFR-10.2). Bump both ARGs together, only to a version >= 14 days old. (D56)
ARG NPM_VERSION=12.2.0
ARG NPM_SHA512=66c2632a94e796649738b2d7894d710c2cc2e1696893823066687f6b0d8a52e5f2b54eeaeaa32ffdc513ecca1e49ff794a5c2ec3f9515d879f1b3182b291cf35
RUN cd /tmp \
 && npm pack --silent "npm@${NPM_VERSION}" > /dev/null \
 && echo "${NPM_SHA512}  npm-${NPM_VERSION}.tgz" | sha512sum -c - \
 && npm install --global --ignore-scripts "./npm-${NPM_VERSION}.tgz" \
 && rm "npm-${NPM_VERSION}.tgz" \
 && npm --version
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11.17-slim-bookworm
WORKDIR /app

# pip itself, upgraded before anything else is installed: the base image ships
# pip 24.0 (Spark: 22.0.2), with known CVEs fixed in later releases. Pinned and
# hash-checked like every other dependency, wheel only (the sdist fallback was
# one of the CVE vectors). Bump both ARGs together; hash from PyPI. (D56)
ARG PIP_VERSION=26.2.1
ARG PIP_WHEEL_SHA256=71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e
RUN echo "pip==${PIP_VERSION} --hash=sha256:${PIP_WHEEL_SHA256}" > /tmp/pip.txt \
 && python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r /tmp/pip.txt \
 && rm /tmp/pip.txt

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
