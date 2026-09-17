// Mirrors the JSON shapes assembled by backend/app/state_poller.py,
// backend/app/kafka_client.py, and backend/app/cassandra_client.py.

export interface DeploymentService {
  name: string;
  healthy: boolean;
  detail: string;
  latency_ms: number | null;
}

export interface DeploymentStep {
  checked_at: string;
  all_healthy: boolean;
  services: DeploymentService[];
}

export interface RawEventWire {
  event_id: string;
  device_id: string;
  event_ts: string;
  ingest_ts: string;
  co: number;
  humidity: number;
  lpg: number;
  smoke: number;
  temp: number;
  light: boolean;
  motion: boolean;
  pressure: number;
  is_synthetic: boolean;
}

export interface IngestionStep {
  mode: "replay" | "synthetic";
  configured_rate_msgs_per_sec: number;
  kafka_topic: string;
  events_sent_total: number;
  events_sent_replay: number;
  events_sent_synthetic: number;
  anomalies_injected_total: number;
  handover_ts: string | null;
  started_at: string;
  recent_events: RawEventWire[];
  source_reachable: boolean;
}

export interface KafkaQueryLag {
  consumed_offsets: Record<string, number>;
  lag_per_partition: Record<string, number>;
  total_lag: number;
}

export interface KafkaStep {
  produced_offsets: Record<string, number>;
  queries: Record<string, KafkaQueryLag>;
}

export interface SparkQueryProgress {
  batch_id: number;
  num_input_rows: number;
  input_rows_per_second: number | null;
  processing_time_ms: number | null;
  event_time_watermark: string | null;
  timestamp: string;
  kafka_consumed_offsets: Record<string, number>;
}

export interface SparkLatency {
  e2e_p50_seconds?: number;
  e2e_p95_seconds?: number;
  e2e_max_seconds?: number;
  hop_produce_to_ingest_p50_seconds?: number;
  hop_produce_to_ingest_p95_seconds?: number;
  hop_ingest_to_write_p50_seconds?: number;
  hop_ingest_to_write_p95_seconds?: number;
}

export interface SparkStep {
  queries: Record<string, SparkQueryProgress>;
  latency: SparkLatency;
}

export interface RawEventRow extends RawEventWire {
  bucket_start: string | null;
  source_ts: string | null;
  write_ts: string | null;
  is_anomaly: boolean;
  anomaly_reason: string | null;
}

export interface CassandraStep {
  recent_raw_events: RawEventRow[];
}

export interface SummaryStep {
  grafana_port: number;
  totals: {
    events_ingested: number;
    anomalies_detected: number;
    rows_in_cassandra_sample: number;
  };
}

export interface PipelineState {
  deployment: DeploymentStep | null;
  ingestion: IngestionStep | null;
  kafka: KafkaStep | null;
  spark: SparkStep | null;
  cassandra: CassandraStep | null;
  summary: SummaryStep | null;
}

export type StepName = keyof PipelineState;

// Mirrors backend/app/routers/sensors.py + backend/app/environment.py (R1 of the
// role-based redirect - environmental/planner role).

export type Role = "admin" | "planner";

export type MetricStatus = "ok" | "warning" | "critical";

export interface DeviceReading {
  device_id: string;
  bucket_start: string | null;
  event_ts: string | null;
  event_id: string;
  ingest_ts: string | null;
  source_ts: string | null;
  write_ts: string | null;
  co: number;
  humidity: number;
  lpg: number;
  smoke: number;
  temp: number;
  light: boolean;
  motion: boolean;
  pressure: number;
  is_synthetic: boolean;
  is_anomaly: boolean;
  anomaly_reason: string | null;
}

export interface DeviceStatus {
  overall: MetricStatus | "unknown";
  reason: string | null;
  metrics: Record<string, MetricStatus>;
}

export interface MetricRange {
  value: number;
  unit: string;
  normal_min: number;
  normal_max: number;
  ceiling: number | null;
  status: MetricStatus;
}

export interface ReadingProvenance {
  kind: "replayed" | "synthetic";
  label: string;
}

export interface SensorEntry {
  device_id: string;
  name: string;
  area: string;
  lat: number;
  lon: number;
  reading: DeviceReading | null;
  status: DeviceStatus;
  air_quality_score: number | null;
  comfort_index: number | null;
  metric_ranges: Record<string, MetricRange>;
  provenance: ReadingProvenance | null;
}

export interface SensorsResponse {
  sensors: SensorEntry[];
}

export interface AggregateWindow {
  device_id: string;
  window_start: string | null;
  window_end: string | null;
  event_count: number;
  anomaly_count: number;
  co_avg: number; co_min: number; co_max: number;
  humidity_avg: number; humidity_min: number; humidity_max: number;
  lpg_avg: number; lpg_min: number; lpg_max: number;
  smoke_avg: number; smoke_min: number; smoke_max: number;
  temp_avg: number; temp_min: number; temp_max: number;
  pressure_avg: number; pressure_min: number; pressure_max: number;
  light_active_count: number; light_active_ratio: number;
  motion_active_count: number; motion_active_ratio: number;
}

export interface SensorHistoryResponse {
  device_id: string;
  granularity: "1m" | "1h";
  windows: AggregateWindow[];
  chronic_exposure_ratio: number | null;
  trend: "improving" | "worsening" | "stable" | null;
}

export type TimelineGranularity = "1m" | "1h" | "1d" | "1w" | "1mo";

export interface TimelinePoint {
  window_start: string;
  avg: number | null;
  min: number | null;
  max: number | null;
  anomaly_count: number;
  event_count: number;
  unhealthy: boolean;
}

export type CompareSource = "live" | "dataset";

export interface CompareTimeline {
  source: CompareSource;
  offset_label: string;
  points: TimelinePoint[];
}

export interface TimelineResponse {
  device_id: string;
  metric: string;
  granularity: TimelineGranularity;
  points: TimelinePoint[];
  compare: CompareTimeline | null;
}

// Mirrors backend/app/routers/dataset.py (D38 - Dataset Explorer, FR-P2).

export interface DatasetDeviceSummary {
  device_id: string;
  row_count: number;
  min_source_ts: string;
  max_source_ts: string;
}

export interface DatasetSummaryResponse {
  devices: DatasetDeviceSummary[];
}

export interface DatasetReading {
  source_ts: string;
  device_id: string;
  co: number;
  humidity: number;
  lpg: number;
  smoke: number;
  temp: number;
  light: boolean;
  motion: boolean;
}

export interface DatasetReadingsResponse {
  readings: DatasetReading[];
}

// Mirrors backend/app/routers/admin.py (R4 - infrastructure/admin role, alerting).

export interface AdminAlert {
  id: string;
  status: "firing" | "resolved";
  alertname: string;
  severity: string;
  service: string | null;
  summary: string;
  starts_at: string | null;
  ends_at: string | null;
  generator_url: string | null;
  received_at: string;
}

// Mirrors backend/app/archive.py (D40 - archive-and-trim, FR-A1-A3).
export interface ArchiveResult {
  cutoff: string;
  partitions_archived: number;
  rows_archived: number;
  archive_path: string;
}

// Mirrors backend/app/cassandra_nodes.py (D42 - storage control + node deploy, FR-N1/N2).
export interface CassandraStorageNode {
  container_name: string;
  address: string;
  load_bytes: number;
  percent_of_budget: number;
  up_normal: boolean;
}

export interface CassandraStorageSummary {
  budget_bytes: number;
  nodes: CassandraStorageNode[];
}

export type CassandraDeployStep = "creating" | "healthy" | "joining_ring" | "done" | "error";

export interface CassandraDeployProgress {
  step: CassandraDeployStep;
  status: "in_progress" | "done" | "error";
  node_name?: string;
  message?: string;
}

// Mirrors backend/app/cassandra_nodes.py's cluster_status_sync (D43 - FR-K1).
export interface KubernetesPodStatus {
  name: string;
  phase: string;
  ready: string;
  restarts: number;
  node: string | null;
}

export interface KubernetesWorkloadStatus {
  kind: "StatefulSet" | "Deployment";
  name: string;
  desired: number;
  ready: number;
}

export interface KubernetesStatusResponse {
  pods: KubernetesPodStatus[];
  workloads: KubernetesWorkloadStatus[];
}

