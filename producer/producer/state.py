import threading
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ProducerState:
    """Thread-safe, read-mostly state shared between the publish loop and the
    HTTP state server (FR-I4: producer exposes mode/rate/events-sent)."""

    def __init__(self, configured_rate: float, kafka_topic: str):
        self._lock = threading.Lock()
        self._mode = "replay"
        self._configured_rate = configured_rate
        self._kafka_topic = kafka_topic
        self._events_sent_replay = 0
        self._events_sent_synthetic = 0
        self._anomalies_injected_total = 0
        self._handover_ts = None
        self._started_at = _now_iso()

    def record_event(self, mode: str) -> None:
        with self._lock:
            if mode == "replay":
                self._events_sent_replay += 1
            else:
                self._events_sent_synthetic += 1

    def record_anomaly(self) -> None:
        with self._lock:
            self._anomalies_injected_total += 1

    def record_handover(self) -> None:
        with self._lock:
            self._mode = "synthetic"
            self._handover_ts = _now_iso()

    def as_dict(self) -> dict:
        with self._lock:
            return {
                "mode": self._mode,
                "configured_rate_msgs_per_sec": self._configured_rate,
                "kafka_topic": self._kafka_topic,
                "events_sent_total": self._events_sent_replay + self._events_sent_synthetic,
                "events_sent_replay": self._events_sent_replay,
                "events_sent_synthetic": self._events_sent_synthetic,
                "anomalies_injected_total": self._anomalies_injected_total,
                "handover_ts": self._handover_ts,
                "started_at": self._started_at,
            }
