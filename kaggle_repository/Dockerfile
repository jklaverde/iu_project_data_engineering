# One-shot dataset fetch, same pattern as kafka-volume-init/cassandra-schema-init:
# populates a shared named volume before producer/spark-job/spark-worker start,
# so a fresh `docker compose up -d` needs no manual host-side step to get the
# Kaggle CSV in place (see docs/TROUBLESHOOTING.md before changing this).
FROM python:3.11.9-slim-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY download_repository.py .

ENV PYTHONUNBUFFERED=1

# Runs as root deliberately: it's the sole writer to a fresh named volume
# (which mounts root-owned - see docs/TROUBLESHOOTING.md P1 #2/P3 #5 for the
# same lesson elsewhere in this repo), and it's a bounded one-shot task, not
# a persistent service. The read-only consumers don't need matching UID/GID,
# just the default world-readable file permissions pip/kagglehub produce.
ENTRYPOINT ["python", "download_repository.py"]
