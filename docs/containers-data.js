// Container Manifest — data model.
// Every number here is transcribed by hand from docker-compose.yml / .env.example
// at the repo root. If you change a mem_limit, port, or depends_on there, update
// the matching entry here too — this file is documentation, not a build artifact,
// so nothing keeps it in sync automatically.

const CATEGORY_COLOR = {
  ingest: "var(--cat-ingest)",
  broker: "var(--cat-broker)",
  stream: "var(--cat-stream)",
  storage: "var(--cat-storage)",
  web: "var(--cat-web)",
  observe: "var(--cat-observe)",
};

// id must match the docker-compose.yml service key AND (where a detail card
// exists) the card's element id, so click-to-jump can find it with getElementById.
const SERVICES = [
  { id: "dataset-init", category: "ingest", mem: 384, lifecycle: "oneshot", build: "custom", hasCard: true },
  { id: "producer", category: "ingest", mem: 384, lifecycle: "running", build: "custom", hasCard: true },

  { id: "kafka-volume-init", category: "broker", mem: 128, lifecycle: "oneshot", build: "official", hasCard: true },
  { id: "kafka", category: "broker", mem: 1500, lifecycle: "running", build: "official", hasCard: true },
  { id: "kafka-topic-init", category: "broker", mem: 256, lifecycle: "oneshot", build: "official", hasCard: true },
  { id: "kafka-ui", category: "broker", mem: 512, lifecycle: "running", build: "official", hasCard: true },

  { id: "spark-master", category: "stream", mem: 1024, lifecycle: "running", build: "official", hasCard: true },
  { id: "spark-job-volume-init", category: "stream", mem: 128, lifecycle: "oneshot", build: "official", hasCard: true },
  { id: "spark-worker", category: "stream", mem: 2560, lifecycle: "running", build: "custom", hasCard: true },
  { id: "spark-job", category: "stream", mem: 2000, lifecycle: "running", build: "custom", hasCard: true },

  { id: "cassandra", category: "storage", mem: 2048, lifecycle: "running", build: "custom", hasCard: true },
  { id: "cassandra-schema-init", category: "storage", mem: 256, lifecycle: "oneshot", build: "official", hasCard: true },

  { id: "backend", category: "web", mem: 384, lifecycle: "running", build: "custom", hasCard: true },

  { id: "prometheus", category: "observe", mem: 512, lifecycle: "running", build: "official", hasCard: true },
  { id: "kafka-exporter", category: "observe", mem: 256, lifecycle: "running", build: "official", hasCard: true },
  { id: "node-exporter", category: "observe", mem: 128, lifecycle: "running", build: "official", hasCard: true },
  { id: "loki", category: "observe", mem: 512, lifecycle: "running", build: "official", hasCard: true },
  { id: "promtail", category: "observe", mem: 256, lifecycle: "running", build: "official", hasCard: true },
  { id: "grafana", category: "observe", mem: 512, lifecycle: "running", build: "custom", hasCard: true },
];

const SERVICES_BY_ID = Object.fromEntries(SERVICES.map((s) => [s.id, s]));

// Startup dependency edges — one row per depends_on relationship in
// docker-compose.yml. `cond` is the exact Compose condition keyword.
const DEP_EDGES = [
  { source: "kafka-volume-init", target: "kafka", cond: "completed" },
  { source: "kafka", target: "kafka-topic-init", cond: "healthy" },
  { source: "kafka", target: "kafka-exporter", cond: "healthy" },
  { source: "kafka", target: "kafka-ui", cond: "healthy" },
  { source: "kafka", target: "backend", cond: "healthy" },
  { source: "kafka-topic-init", target: "producer", cond: "completed" },
  { source: "dataset-init", target: "producer", cond: "completed" },
  { source: "producer", target: "backend", cond: "healthy" },
  { source: "kafka-topic-init", target: "spark-job", cond: "completed" },
  { source: "dataset-init", target: "spark-job", cond: "completed" },
  { source: "dataset-init", target: "spark-worker", cond: "completed" },
  { source: "cassandra", target: "cassandra-schema-init", cond: "healthy" },
  { source: "cassandra-schema-init", target: "spark-job", cond: "completed" },
  { source: "cassandra-schema-init", target: "backend", cond: "completed" },
  { source: "spark-master", target: "spark-worker", cond: "healthy" },
  { source: "spark-master", target: "spark-job", cond: "healthy" },
  { source: "spark-job-volume-init", target: "spark-worker", cond: "completed" },
  { source: "spark-job-volume-init", target: "spark-job", cond: "completed" },
  { source: "loki", target: "promtail", cond: "started" },
];

// Data/observation-flow diagram — hand-authored, fixed layout (this is a
// curated illustration of the mechanism, not a derived graph like DEP_EDGES).
// Nodes not in SERVICES (csv, admin-ui, planner-ui) are drawn but not clickable
// into a detail card, and are visually marked "external".
const FLOW_NODES = [
  { id: "csv", label: "Kaggle CSV", sub: "historical dataset", x: 40, y: 90, w: 120, external: true },
  { id: "producer", label: "producer", sub: "ingest", x: 220, y: 90, w: 130 },
  { id: "kafka", label: "kafka", sub: "sensor-readings", x: 410, y: 90, w: 130 },
  { id: "spark-job", label: "spark-job", sub: "structured streaming", x: 600, y: 90, w: 140 },
  { id: "cassandra", label: "cassandra", sub: "keyspace: iot", x: 800, y: 90, w: 130 },
  { id: "backend", label: "backend", sub: "FastAPI", x: 990, y: 90, w: 130 },
  { id: "admin-ui", label: "Admin UI", sub: "pipeline tour + Alerts", x: 1190, y: 40, w: 150, external: true },
  { id: "planner-ui", label: "Planner UI", sub: "Leaflet map", x: 1190, y: 145, w: 150, external: true },

  { id: "kafka-exporter", label: "kafka-exporter", sub: "", x: 410, y: 235, w: 130 },
  { id: "node-exporter", label: "node-exporter", sub: "", x: 600, y: 320, w: 130 },
  { id: "prometheus", label: "prometheus", sub: "", x: 800, y: 235, w: 130 },
  { id: "promtail", label: "promtail", sub: "", x: 600, y: 400, w: 130 },
  { id: "loki", label: "loki", sub: "", x: 800, y: 400, w: 130 },
  { id: "grafana", label: "grafana", sub: "", x: 990, y: 320, w: 130 },
];

const FLOW_EDGES = [
  { source: "csv", target: "producer", kind: "data", label: "read once at startup" },
  { source: "producer", target: "kafka", kind: "data", label: "JSON events · key=device_id" },
  { source: "kafka", target: "spark-job", kind: "data", label: "" },
  { source: "spark-job", target: "cassandra", kind: "data", label: "raw_events · agg_1m · agg_1h · thresholds" },
  { source: "producer", target: "backend", kind: "observe", label: "GET /state" },
  { source: "kafka", target: "backend", kind: "observe", label: "offsets" },
  { source: "spark-job", target: "backend", kind: "observe", label: "GET /state" },
  { source: "cassandra", target: "backend", kind: "observe", label: "CQL reads" },
  { source: "backend", target: "admin-ui", kind: "data", label: "" },
  { source: "backend", target: "planner-ui", kind: "data", label: "" },
  { source: "kafka", target: "kafka-exporter", kind: "observe", label: "" },
  { source: "kafka-exporter", target: "prometheus", kind: "observe", label: "" },
  { source: "cassandra", target: "prometheus", kind: "observe", label: "JMX :7070" },
  { source: "node-exporter", target: "prometheus", kind: "observe", label: "" },
  { source: "promtail", target: "loki", kind: "data", label: "container logs" },
  { source: "prometheus", target: "grafana", kind: "observe", label: "" },
  { source: "loki", target: "grafana", kind: "observe", label: "" },
  { source: "cassandra", target: "grafana", kind: "observe", label: "direct CQL" },
  { source: "grafana", target: "backend", kind: "alert", label: "alert webhook" },
];
