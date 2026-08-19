FROM cassandra:4.1.12

USER root

# Base image has neither curl nor wget, and no CA bundle for TLS - install
# both (build-time only, not needed at runtime) to fetch the JMX exporter
# javaagent jar over HTTPS. curl alone isn't enough: without ca-certificates
# it fails with "error setting certificate file: /etc/ssl/certs/ca-certificates.crt".
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG JMX_EXPORTER_VERSION=1.6.0
RUN mkdir -p /opt/jmx-exporter \
    && curl -fsSL -o /opt/jmx-exporter/jmx_prometheus_javaagent.jar \
       "https://github.com/prometheus/jmx_exporter/releases/download/${JMX_EXPORTER_VERSION}/jmx_prometheus_javaagent-${JMX_EXPORTER_VERSION}.jar"

COPY jmx-exporter/cassandra-jmx-exporter.yml /opt/jmx-exporter/cassandra-jmx-exporter.yml
RUN chown -R cassandra:cassandra /opt/jmx-exporter

USER cassandra
