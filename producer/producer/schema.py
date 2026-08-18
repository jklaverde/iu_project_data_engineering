import uuid
from datetime import datetime


def _iso(ts: datetime) -> str:
    return ts.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_event(
    *,
    device_id: str,
    event_ts: datetime,
    ingest_ts: datetime,
    co: float,
    humidity: float,
    lpg: float,
    smoke: float,
    temp: float,
    light: bool,
    motion: bool,
    pressure: float,
    is_synthetic: bool,
) -> dict:
    """Builds one canonical event dict (REQUIREMENTS.md Sec 5.2).

    Producer-owned fields only: is_anomaly, anomaly_reason, write_ts, and
    bucket_start are NOT included here - those are populated later by the
    Spark job (P3) and the Cassandra sink, not the producer.
    """
    return {
        "event_id": str(uuid.uuid4()),
        "device_id": device_id,
        "event_ts": _iso(event_ts),
        "ingest_ts": _iso(ingest_ts),
        "co": co,
        "humidity": humidity,
        "lpg": lpg,
        "smoke": smoke,
        "temp": temp,
        "light": light,
        "motion": motion,
        "pressure": pressure,
        "is_synthetic": is_synthetic,
    }
