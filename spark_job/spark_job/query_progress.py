import threading

from pyspark.sql.streaming import StreamingQueryListener


class QueryProgressTracker:
    """Thread-safe latest-progress-per-query store, fed by a
    StreamingQueryListener. FR-S4: streaming-query progress exposed to the
    web app and Prometheus - Spark's own REST API (port 4040) has no stable
    JSON endpoint for StreamingQueryProgress, so this is custom."""

    def __init__(self):
        self._lock = threading.Lock()
        self._progress = {}

    def record(self, name: str, progress: dict) -> None:
        with self._lock:
            self._progress[name] = progress

    def as_dict(self) -> dict:
        with self._lock:
            return {"queries": dict(self._progress)}


def make_listener(tracker: QueryProgressTracker) -> StreamingQueryListener:
    class _Listener(StreamingQueryListener):
        def onQueryStarted(self, event):
            pass

        def onQueryProgress(self, event):
            p = event.progress
            name = p.name or str(p.id)
            watermark = None
            if p.eventTime:
                watermark = p.eventTime.get("watermark")
            tracker.record(name, {
                "batch_id": p.batchId,
                "num_input_rows": p.numInputRows,
                "input_rows_per_second": p.inputRowsPerSecond,
                "processing_time_ms": p.durationMs.get("triggerExecution") if p.durationMs else None,
                "event_time_watermark": watermark,
                "timestamp": p.timestamp,
            })

        def onQueryTerminated(self, event):
            pass

        def onQueryIdle(self, event):
            pass

    return _Listener()
