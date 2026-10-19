# spark-worker's executors run our job's pandas UDF (applyInPandasWithState)
# directly, but PySpark does not auto-distribute pip packages to executors
# the way it auto-distributes --packages JARs - the worker needs the same
# pandas/pyarrow install as the driver (see spark_job/Dockerfile), or
# executor tasks fail with ModuleNotFoundError at runtime (confirmed, not
# assumed - this file exists because that failure actually happened).
FROM apache/spark:3.5.9

USER root
# pip itself, upgraded before anything else is installed: the base image ships
# pip 24.0 (Spark: 22.0.2), with known CVEs fixed in later releases. Pinned and
# hash-checked like every other dependency, wheel only (the sdist fallback was
# one of the CVE vectors). Bump both ARGs together; hash from PyPI. (D56)
ARG PIP_VERSION=26.2.1
ARG PIP_WHEEL_SHA256=71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e
RUN echo "pip==${PIP_VERSION} --hash=sha256:${PIP_WHEEL_SHA256}" > /tmp/pip.txt \
 && python3 -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r /tmp/pip.txt \
 && rm /tmp/pip.txt \
 && apt-get purge -y -q python3-pip  # the old pip 22 would stay on disk otherwise
COPY requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt && rm /tmp/requirements.txt
USER spark
