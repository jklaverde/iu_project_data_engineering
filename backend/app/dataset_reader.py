import bisect
import csv
import os
import sys
import threading
from datetime import datetime, timezone


def _iso_epoch(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# Row tuple layout - tuples, not dicts: the derived file is ~330K rows and the
# backend's memory limit is 512 MiB (k8s/base/deployment-backend.yaml).
_TS, _SOURCE_TS, _DEVICE, _CO, _HUMIDITY, _LPG, _SMOKE, _TEMP, _LIGHT, _MOTION = range(10)


class DatasetReader:
    """Read-only access to the derived multi-month dataset (D52, FR-H1) that
    the history-backfill Job writes next to the original Kaggle CSV - the
    Dataset Explorer (D38, FR-P2) serves it independently of
    Kafka/Spark/Cassandra. Each row carries two timestamps: `ts`, its place
    on the derived timeline, and `source_ts`, the original 2020 reading it
    was derived from. The file is sorted ascending by ts, devices
    interleaved (history_backfill.derive writes it that way).

    The file may not exist yet (the Job runs after the backend starts) and
    may be replaced by a re-run, so it is (re)loaded whenever its mtime
    changes, and an absent file reads as "no rows" rather than an error."""

    def __init__(self, csv_path: str):
        self._csv_path = csv_path
        self._lock = threading.Lock()
        self._loaded_mtime: float | None = None
        self._rows: list[tuple] = []
        self._ts: list[float] = []
        self._summary: dict | None = None

    def _current(self) -> tuple[list, list]:
        """Parses the file once per version and caches it. Without the cache,
        every query() re-scanned the whole file, and the "compare to" toggle
        (D39/FR-E6) fires several concurrently - three concurrent full-file
        scans OOM-killed the backend before. The lock makes a query arriving
        mid-load wait instead of starting its own redundant scan."""
        try:
            mtime = os.stat(self._csv_path).st_mtime
        except OSError:
            mtime = None
        if mtime == self._loaded_mtime:
            return self._rows, self._ts
        with self._lock:
            if mtime == self._loaded_mtime:
                return self._rows, self._ts
            rows: list[tuple] = []
            if mtime is not None:
                with open(self._csv_path, newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        rows.append((
                            float(row["ts"]),
                            float(row["source_ts"]),
                            sys.intern(row["device"]),
                            float(row["co"]),
                            float(row["humidity"]),
                            float(row["lpg"]),
                            float(row["smoke"]),
                            float(row["temp"]),
                            row["light"] == "true",
                            row["motion"] == "true",
                        ))
            self._rows = rows
            self._ts = [r[_TS] for r in rows]
            self._summary = None
            self._loaded_mtime = mtime
            return self._rows, self._ts

    @staticmethod
    def _to_dict(r: tuple) -> dict:
        return {
            "ts": _iso_epoch(r[_TS]),
            "source_ts": _iso_epoch(r[_SOURCE_TS]),
            "device_id": r[_DEVICE],
            "co": r[_CO],
            "humidity": r[_HUMIDITY],
            "lpg": r[_LPG],
            "smoke": r[_SMOKE],
            "temp": r[_TEMP],
            "light": r[_LIGHT],
            "motion": r[_MOTION],
        }

    def query(
        self,
        device_id: str | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
    ) -> list[dict]:
        rows, ts = self._current()
        start = bisect.bisect_left(ts, since.timestamp()) if since is not None else 0
        until_epoch = until.timestamp() if until is not None else None
        out: list[dict] = []
        for i in range(start, len(rows)):
            r = rows[i]
            if until_epoch is not None and r[_TS] > until_epoch:
                break
            if device_id and r[_DEVICE] != device_id:
                continue
            out.append(self._to_dict(r))
            if len(out) >= limit:
                break
        return out

    def summary(self) -> dict:
        """Device list with row counts and the derived timeline's range, plus
        `available` so the UI can say "not generated yet" instead of showing
        an empty explorer."""
        rows, _ = self._current()
        if self._summary is not None:
            return self._summary

        devices: dict[str, dict] = {}
        for r in rows:
            d = devices.setdefault(r[_DEVICE], {"row_count": 0, "min": r[_TS], "max": r[_TS]})
            d["row_count"] += 1
            d["min"] = min(d["min"], r[_TS])
            d["max"] = max(d["max"], r[_TS])

        self._summary = {
            "available": bool(rows),
            "devices": [
                {
                    "device_id": device_id,
                    "row_count": d["row_count"],
                    "min_ts": _iso_epoch(d["min"]),
                    "max_ts": _iso_epoch(d["max"]),
                }
                for device_id, d in devices.items()
            ],
        }
        return self._summary
