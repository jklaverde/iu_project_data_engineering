from datetime import datetime, timezone


def _iso_to_epoch(iso_ts: str) -> float:
    return datetime.fromisoformat(iso_ts.replace("Z", "+00:00")).timestamp()


def render_prometheus_text(state: dict) -> bytes:
    """Hand-formatted Prometheus text exposition (no prometheus_client
    dependency - the metric set is small and static-shaped, matching this
    project's stdlib-only NFR-10.8 minimal-deps pattern)."""
    lines = []

    lines += [
        "# HELP producer_events_sent_total Events published to Kafka, by mode.",
        "# TYPE producer_events_sent_total counter",
        f'producer_events_sent_total{{mode="replay"}} {state["events_sent_replay"]}',
        f'producer_events_sent_total{{mode="synthetic"}} {state["events_sent_synthetic"]}',
    ]
    lines += [
        "# HELP producer_anomalies_injected_total Synthetic anomalies injected (producer-side).",
        "# TYPE producer_anomalies_injected_total counter",
        f'producer_anomalies_injected_total {state["anomalies_injected_total"]}',
    ]
    lines += [
        "# HELP producer_configured_rate_msgs_per_second Configured target publish rate.",
        "# TYPE producer_configured_rate_msgs_per_second gauge",
        f'producer_configured_rate_msgs_per_second {state["configured_rate_msgs_per_sec"]}',
    ]
    lines += [
        "# HELP producer_mode_info Current ingestion mode (1 = active).",
        "# TYPE producer_mode_info gauge",
        f'producer_mode_info{{mode="{state["mode"]}"}} 1',
    ]
    if state["handover_ts"]:
        lines += [
            "# HELP producer_handover_timestamp_seconds Unix time of the replay-to-synthetic hand-over.",
            "# TYPE producer_handover_timestamp_seconds gauge",
            f'producer_handover_timestamp_seconds {_iso_to_epoch(state["handover_ts"])}',
        ]
    lines += [
        "# HELP producer_started_at_timestamp_seconds Unix time the producer process started.",
        "# TYPE producer_started_at_timestamp_seconds gauge",
        f'producer_started_at_timestamp_seconds {_iso_to_epoch(state["started_at"])}',
    ]

    return ("\n".join(lines) + "\n").encode("utf-8")
