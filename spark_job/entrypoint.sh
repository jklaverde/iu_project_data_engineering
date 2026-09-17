#!/usr/bin/env bash
set -euo pipefail

# Kubernetes (D43): a plain Deployment pod has no DNS record for its own
# bare hostname (unlike a Docker Compose container, always self-resolvable
# on the user-defined network), so without this, the driver advertises an
# address executors can't dial back to and the job hangs registering
# resources forever. SPARK_LOCAL_IP (Downward API status.podIP, see
# k8s/base/deployment-spark-job.yaml) isn't picked up as spark.driver.host
# automatically in this Spark version - it has to be passed explicitly.
# Under Compose, SPARK_LOCAL_IP is unset and this --conf is simply absent.
DRIVER_HOST_OPTS=()
if [ -n "${SPARK_LOCAL_IP:-}" ]; then
  DRIVER_HOST_OPTS=(--conf "spark.driver.host=${SPARK_LOCAL_IP}")
fi

exec /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --deploy-mode client \
  --packages "${SPARK_PACKAGES}" \
  --py-files /opt/app/spark_job.zip \
  --conf spark.jars.ivy=/opt/spark/.ivy2 \
  --conf spark.cassandra.connection.host="${CASSANDRA_HOST}" \
  --conf spark.cassandra.connection.port="${CASSANDRA_PORT}" \
  --conf spark.sql.shuffle.partitions=3 \
  "${DRIVER_HOST_OPTS[@]}" \
  /opt/app/run.py
