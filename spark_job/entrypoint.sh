#!/usr/bin/env bash
set -euo pipefail

exec /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --deploy-mode client \
  --packages "${SPARK_PACKAGES}" \
  --py-files /opt/app/spark_job.zip \
  --conf spark.jars.ivy=/opt/spark/.ivy2 \
  --conf spark.cassandra.connection.host="${CASSANDRA_HOST}" \
  --conf spark.cassandra.connection.port="${CASSANDRA_PORT}" \
  --conf spark.sql.shuffle.partitions=3 \
  /opt/app/run.py
