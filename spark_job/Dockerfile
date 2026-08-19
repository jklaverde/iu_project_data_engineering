FROM apache/spark:3.5.9

USER root
WORKDIR /opt/app

ENV SPARK_PACKAGES="org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.9,com.datastax.spark:spark-cassandra-connector-assembly_2.12:3.5.1"

# Pre-warm the Ivy cache at BUILD time (network available here) so
# `spark-submit --packages` at container RUNTIME resolves purely from the
# local cache - no Maven download on every `docker compose up` (FR-D1).
RUN /opt/spark/bin/spark-submit \
      --packages "${SPARK_PACKAGES}" \
      --conf spark.jars.ivy=/opt/spark/.ivy2 \
      --class org.apache.spark.examples.SparkPi \
      /opt/spark/examples/jars/spark-examples.jar 1

COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir --require-hashes -r requirements.txt

COPY spark_job/ ./spark_job/
COPY run.py ./run.py
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# cloudpickle pickles functions defined in an importable module (as opposed
# to __main__) BY REFERENCE, not by value - the applyInPandasWithState
# closures in spark_job.anomaly_state therefore need the spark_job package
# to be importable on EXECUTORS too, not just the driver (confirmed by a
# ModuleNotFoundError on first real run, not assumed). --py-files ships this
# zip to every executor.
RUN python3 -c "import shutil; shutil.make_archive('/opt/app/spark_job', 'zip', '/opt/app', 'spark_job')"

RUN chown -R spark:spark /opt/app /opt/spark/.ivy2

ENV PYTHONUNBUFFERED=1

USER spark

ENTRYPOINT ["/opt/app/entrypoint.sh"]
