# One-shot dataset fetch, same pattern as kafka-volume-init/cassandra-schema-init:
# populates a shared named volume before producer/spark-job/spark-worker start,
# so a fresh `docker compose up -d` needs no manual host-side step to get the
# Kaggle CSV in place (see docs/operations.html before changing this).
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

COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY download_repository.py .

ENV PYTHONUNBUFFERED=1

# Runs as root deliberately: it's the sole writer to a fresh named volume
# (which mounts root-owned - see docs/operations.html#p1-2 and #p3-5 for the
# same lesson elsewhere in this repo), and it's a bounded one-shot task, not
# a persistent service. The read-only consumers don't need matching UID/GID,
# just the default world-readable file permissions pip/kagglehub produce.
ENTRYPOINT ["python", "download_repository.py"]
