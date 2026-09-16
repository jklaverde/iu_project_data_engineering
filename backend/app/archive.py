import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DEFAULT_CUTOFF_FRACTION = 0.10  # FR-A1's "sane default": oldest 10% of partitions by time


def _archive_path(archive_dir: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    return os.path.join(archive_dir, f"archive-{stamp}.ndjson")


def run_archive(reader, archive_dir: str, cutoff: datetime | None) -> dict:
    """Archive-and-trim (D40, FR-A1-A3): exports the oldest raw-event
    partitions to a local NDJSON file, then drops them from Cassandra. If no
    cutoff is given, defaults to the oldest DEFAULT_CUTOFF_FRACTION of
    partitions by bucket_start - not a row count, since bucket_start
    partitions are roughly equal-sized by construction (NFR-3's 15-minute
    bucket sizing note). This is the sole write/mutate action in Phase 1
    (FR-A1) - irreversible against the live store, so the caller (the admin
    route) must have already confirmed intent before this runs."""
    buckets = sorted(reader.raw_event_buckets_sync(), key=lambda b: b[1])

    if cutoff is None:
        if not buckets:
            cutoff = datetime.now(timezone.utc)
        else:
            cutoff_index = max(0, int(len(buckets) * DEFAULT_CUTOFF_FRACTION) - 1)
            cutoff = buckets[cutoff_index][1]

    targets = [b for b in buckets if b[1] <= cutoff]

    os.makedirs(archive_dir, exist_ok=True)
    archive_path = _archive_path(archive_dir)
    row_count = 0

    with open(archive_path, "w", encoding="utf-8") as f:
        for device_id, bucket_start in targets:
            rows = reader.export_and_delete_partition_sync(device_id, bucket_start)
            for row in rows:
                f.write(json.dumps(row) + "\n")
            row_count += len(rows)

    result = {
        "cutoff": cutoff.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "partitions_archived": len(targets),
        "rows_archived": row_count,
        "archive_path": archive_path,
    }
    logger.info(json.dumps({"event": "archive_and_trim", **result}))
    return result
