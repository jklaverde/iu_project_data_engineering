def render_prometheus_text(progress: dict, latency: dict) -> bytes:
    """Hand-formatted Prometheus text exposition (no prometheus_client
    dependency - matches producer/producer/metrics.py's same choice)."""
    lines = []
    queries = progress.get("queries", {})

    lines += [
        "# HELP spark_job_query_input_rows Rows processed in the last micro-batch, per query.",
        "# TYPE spark_job_query_input_rows gauge",
    ]
    for name, q in queries.items():
        if q.get("num_input_rows") is not None:
            lines.append(f'spark_job_query_input_rows{{query="{name}"}} {q["num_input_rows"]}')

    lines += [
        "# HELP spark_job_query_input_rows_per_second Spark's own consumption rate estimate, per query.",
        "# TYPE spark_job_query_input_rows_per_second gauge",
    ]
    for name, q in queries.items():
        if q.get("input_rows_per_second") is not None:
            lines.append(f'spark_job_query_input_rows_per_second{{query="{name}"}} {q["input_rows_per_second"]}')

    lines += [
        "# HELP spark_job_query_processing_time_ms Micro-batch processing time, per query.",
        "# TYPE spark_job_query_processing_time_ms gauge",
    ]
    for name, q in queries.items():
        if q.get("processing_time_ms") is not None:
            lines.append(f'spark_job_query_processing_time_ms{{query="{name}"}} {q["processing_time_ms"]}')

    lines += [
        "# HELP spark_job_kafka_consumed_offset Last Kafka offset Spark has read, per query and partition.",
        "# TYPE spark_job_kafka_consumed_offset gauge",
    ]
    for name, q in queries.items():
        for partition, offset in (q.get("kafka_consumed_offsets") or {}).items():
            lines.append(f'spark_job_kafka_consumed_offset{{query="{name}",partition="{partition}"}} {offset}')

    if latency:
        lines += [
            "# HELP spark_job_e2e_latency_seconds End-to-end latency (Cassandra write time - event production time), per micro-batch.",
            "# TYPE spark_job_e2e_latency_seconds gauge",
        ]
        if latency.get("e2e_p50_seconds") is not None:
            lines.append(f'spark_job_e2e_latency_seconds{{quantile="0.5"}} {latency["e2e_p50_seconds"]}')
        if latency.get("e2e_p95_seconds") is not None:
            lines.append(f'spark_job_e2e_latency_seconds{{quantile="0.95"}} {latency["e2e_p95_seconds"]}')

        lines += [
            "# HELP spark_job_e2e_latency_seconds_max Max end-to-end latency in the last micro-batch.",
            "# TYPE spark_job_e2e_latency_seconds_max gauge",
        ]
        if latency.get("e2e_max_seconds") is not None:
            lines.append(f'spark_job_e2e_latency_seconds_max {latency["e2e_max_seconds"]}')

        lines += [
            "# HELP spark_job_hop_latency_seconds Per-hop latency breakdown, per micro-batch.",
            "# TYPE spark_job_hop_latency_seconds gauge",
        ]
        if latency.get("hop_produce_to_ingest_p50_seconds") is not None:
            lines.append(f'spark_job_hop_latency_seconds{{hop="produce_to_ingest",quantile="0.5"}} {latency["hop_produce_to_ingest_p50_seconds"]}')
        if latency.get("hop_produce_to_ingest_p95_seconds") is not None:
            lines.append(f'spark_job_hop_latency_seconds{{hop="produce_to_ingest",quantile="0.95"}} {latency["hop_produce_to_ingest_p95_seconds"]}')
        if latency.get("hop_ingest_to_write_p50_seconds") is not None:
            lines.append(f'spark_job_hop_latency_seconds{{hop="ingest_to_write",quantile="0.5"}} {latency["hop_ingest_to_write_p50_seconds"]}')
        if latency.get("hop_ingest_to_write_p95_seconds") is not None:
            lines.append(f'spark_job_hop_latency_seconds{{hop="ingest_to_write",quantile="0.95"}} {latency["hop_ingest_to_write_p95_seconds"]}')

    return ("\n".join(lines) + "\n").encode("utf-8")
