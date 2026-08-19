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
