import json
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

            # sources[].endOffset is a JSON string Spark already provides per
            # progress event, e.g. {"sensor-readings":{"0":123,"1":456}} -
            # last offset this query has read per partition (KPI-1 lag,
            # combined in PromQL with kafka-exporter's broker-side offset).
            kafka_offsets = {}
            for source in (p.sources or []):
                end_offset = getattr(source, "endOffset", None)
                if not end_offset:
                    continue
                try:
                    for _topic, partitions in json.loads(end_offset).items():
                        kafka_offsets.update(partitions)
                except (ValueError, TypeError, AttributeError):
                    pass

            tracker.record(name, {
                "batch_id": p.batchId,
                "num_input_rows": p.numInputRows,
                "input_rows_per_second": p.inputRowsPerSecond,
                "processing_time_ms": p.durationMs.get("triggerExecution") if p.durationMs else None,
                "event_time_watermark": watermark,
                "timestamp": p.timestamp,
                "kafka_consumed_offsets": kafka_offsets,
            })

        def onQueryTerminated(self, event):
            pass

        def onQueryIdle(self, event):
            pass

    return _Listener()
