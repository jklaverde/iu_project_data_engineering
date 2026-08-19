# grafana_data is an already-existing named volume (created in P1) mounted
# at /var/lib/grafana - Grafana's DEFAULT plugin dir (/var/lib/grafana/plugins)
# is inside it, and Docker only auto-populates a named volume from the image
# on first creation. Baking a plugin into the default path would be silently
# shadowed by the pre-existing (plugin-less) volume forever. Installing to a
# path OUTSIDE the volume mount avoids that.
FROM grafana/grafana:13.1.4

USER root
ENV GF_PATHS_PLUGINS=/usr/local/grafana-plugins
ARG CASSANDRA_PLUGIN_VERSION=3.3.0
RUN mkdir -p "${GF_PATHS_PLUGINS}" \
    && grafana cli --pluginsDir "${GF_PATHS_PLUGINS}" plugins install hadesarchitect-cassandra-datasource "${CASSANDRA_PLUGIN_VERSION}" \
    && chown -R grafana:root "${GF_PATHS_PLUGINS}"
USER grafana
