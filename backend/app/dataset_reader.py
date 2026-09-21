import csv
import threading
from datetime import datetime, timezone


def _parse_ts(raw: str) -> datetime:
    return datetime.fromtimestamp(float(raw), tz=timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class DatasetReader:
    """Read-only access to the original Kaggle CSV (D38's Dataset Explorer,
    FR-P2) - reads the same file dataset-init already fetched into the
    kaggle_dataset volume, independent of Kafka/Spark/Cassandra, no
    duplicate ingestion or storage. The file is globally sorted ascending by
    ts across all devices interleaved (confirmed by
    producer/producer/replay.py's own read-order assumption), so a linear
    scan can stop as soon as it passes the requested range."""

    def __init__(self, csv_path: str):
        self._csv_path = csv_path
        self._summary_cache: dict | None = None
        self._rows_cache: list[dict] | None = None
        self._rows_lock = threading.Lock()

    def _rows(self) -> list[dict]:
        """Parses the CSV once and caches every row for the reader's
        lifetime - the file is static and small enough (~405K rows) to hold
        in memory outright. Without this, every query() call re-scans the
        whole file from disk; the "compare to an earlier period" toggle
        (D39/FR-E6) fires up to three of these concurrently in one
        Promise.all (one per day/week/month granularity), and three
        concurrent full-file scans each building their own ~135K-row list
        OOM-killed the backend under real memory pressure. The lock only
        guards the first build - a query() arriving mid-build blocks briefly
        rather than racing its own redundant scan."""
        if self._rows_cache is not None:
            return self._rows_cache
        with self._rows_lock:
            if self._rows_cache is not None:
                return self._rows_cache
            rows: list[dict] = []
            with open(self._csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ts = _parse_ts(row["ts"])
                    rows.append({
                        "ts": ts,
                        "source_ts": _iso(ts),
                        "device_id": row["device"],
                        "co": float(row["co"]),
                        "humidity": float(row["humidity"]),
                        "lpg": float(row["lpg"]),
                        "smoke": float(row["smoke"]),
                        "temp": float(row["temp"]),
                        "light": row["light"].strip().lower() == "true",
                        "motion": row["motion"].strip().lower() == "true",
                    })
            self._rows_cache = rows
            return rows

    def query(
        self,
        device_id: str | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
    ) -> list[dict]:
        rows: list[dict] = []
        for row in self._rows():
            if until is not None and row["ts"] > until:
                break
            if since is not None and row["ts"] < since:
                continue
            if device_id and row["device_id"] != device_id:
                continue
            rows.append({k: v for k, v in row.items() if k != "ts"})
            if len(rows) >= limit:
                break
        return rows

    def summary(self) -> dict:
        """Device list with row counts and real min/max source_ts - the
        direct answer to "how old is the dataset, and how much of it is
        there." Cached for the reader's lifetime: the file is static, and
        this view is low-traffic (provenance browsing, not the live path)."""
        if self._summary_cache is not None:
            return self._summary_cache

        devices: dict[str, dict] = {}
        for row in self._rows():
            ts = row["ts"]
            d = devices.setdefault(row["device_id"], {
                "device_id": row["device_id"], "row_count": 0, "min_ts": ts, "max_ts": ts,
            })
            d["row_count"] += 1
            if ts < d["min_ts"]:
                d["min_ts"] = ts
            if ts > d["max_ts"]:
                d["max_ts"] = ts

        self._summary_cache = {
            "devices": [
                {
                    "device_id": d["device_id"],
                    "row_count": d["row_count"],
                    "min_source_ts": _iso(d["min_ts"]),
                    "max_source_ts": _iso(d["max_ts"]),
                }
                for d in devices.values()
            ],
        }
        return self._summary_cache
