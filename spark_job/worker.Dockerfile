# spark-worker's executors run our job's pandas UDF (applyInPandasWithState)
# directly, but PySpark does not auto-distribute pip packages to executors
# the way it auto-distributes --packages JARs - the worker needs the same
# pandas/pyarrow install as the driver (see spark_job/Dockerfile), or
# executor tasks fail with ModuleNotFoundError at runtime (confirmed, not
# assumed - this file exists because that failure actually happened).
FROM apache/spark:3.5.9

USER root
COPY requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
USER spark
