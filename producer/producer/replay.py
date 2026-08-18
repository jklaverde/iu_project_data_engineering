import csv
import itertools
import json
import logging
from datetime import datetime, timezone

from .device_stats import BaselineStats, generate_pressure
from .kafka_client import KafkaEventPublisher
from .rate_limiter import RateLimiter
from .schema import build_event
from .state import ProducerState

logger = logging.getLogger(__name__)


def run_replay(
    *,
    csv_path: str,
    row_limit: int,
    stats: BaselineStats,
    publisher: KafkaEventPublisher,
    topic: str,
    rate_limiter: RateLimiter,
    state: ProducerState,
) -> None:
    """Streams the CSV top-to-bottom, publishing each row as a canonical
    event. The file is already globally sorted ascending by ts across all
    devices interleaved, so reading it in file order alone preserves
    per-device ordering - no per-device demux/remux is needed.
    """
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if row_limit > 0 and stats.total_rows > row_limit:
            reader = itertools.islice(reader, stats.total_rows - row_limit, None)

        for row in reader:
            event_ts = datetime.fromtimestamp(float(row["ts"]), tz=timezone.utc)
            ingest_ts = datetime.now(timezone.utc)
            device_id = row["device"]

            event = build_event(
                device_id=device_id,
                event_ts=event_ts,
                ingest_ts=ingest_ts,
                co=float(row["co"]),
                humidity=float(row["humidity"]),
                lpg=float(row["lpg"]),
                smoke=float(row["smoke"]),
                temp=float(row["temp"]),
                light=row["light"].strip().lower() == "true",
                motion=row["motion"].strip().lower() == "true",
                pressure=generate_pressure(),
                is_synthetic=False,
            )

            publisher.publish(topic, event, key=device_id)
            state.record_event(mode="replay")
            rate_limiter.wait_for_next_tick()

    logger.info(json.dumps({
        "event": "mode_handover",
        "from_mode": "replay",
        "to_mode": "synthetic",
        "handover_ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "replay_events_sent": state.as_dict()["events_sent_replay"],
        "csv_rows_total": stats.total_rows,
    }))
    state.record_handover()
