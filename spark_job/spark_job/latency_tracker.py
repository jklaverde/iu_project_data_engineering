import threading


class LatencyTracker:
    """Thread-safe latest-batch latency snapshot, fed by the raw_events
    foreachBatch writer (KPI-2). A per-micro-batch snapshot, not a true
    cross-batch streaming quantile - an accepted Phase 1 tradeoff, since a
    fresh reading every trigger interval is what actually matters for
    checking NFR-1's latency bound is currently met."""

    def __init__(self):
        self._lock = threading.Lock()
        self._stats = {}

    def record(self, stats: dict) -> None:
        with self._lock:
            self._stats = stats

    def as_dict(self) -> dict:
        with self._lock:
            return dict(self._stats)
