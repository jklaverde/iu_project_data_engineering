import itertools
import json
import logging
import random
from datetime import datetime, timezone

from .device_stats import BaselineStats, NUMERIC_METRICS, generate_pressure
from .kafka_client import KafkaEventPublisher
from .rate_limiter import RateLimiter
from .schema import build_event
from .state import ProducerState

logger = logging.getLogger(__name__)

# Continuous fields eligible for anomaly injection - booleans excluded since
# REQUIREMENTS.md Sec 5.4's rule is about numeric deviation / ceiling
# crossing, not booleans. "pressure" is included even though it has no real
# baseline table (device_stats.generate_pressure supplies mean/std for it).
ANOMALY_ELIGIBLE_METRICS = (*NUMERIC_METRICS, "pressure")

# Metrics that physically only spike upward from a near-zero baseline (a
# dangerous reading is a spike up, matching Sec 5.4's "ceiling" language).
POSITIVE_ONLY_METRICS = ("co", "lpg", "smoke")

# Weighted distribution over how many metrics spike together in one
# anomalous event (multiple simultaneous spikes allowed, per user decision).
_SPIKE_COUNT_CHOICES = (1, 2, 3)
_SPIKE_COUNT_WEIGHTS = (0.70, 0.25, 0.05)

_PRESSURE_BASELINE = {"mean": 1013.25, "std": 6.0, "min": 980.0, "max": 1040.0}


class SyntheticGenerator:
    def __init__(self, stats: BaselineStats, anomaly_probability: float, anomaly_sigma_multiplier: float):
        self._stats = stats
        self._anomaly_probability = anomaly_probability
        self._anomaly_sigma_multiplier = anomaly_sigma_multiplier
        self._device_cycle = itertools.cycle(stats.device_ids)

    def _baseline(self, device_id: str, metric: str):
        if metric == "pressure":
            return _PRESSURE_BASELINE["mean"], _PRESSURE_BASELINE["std"], _PRESSURE_BASELINE["min"], _PRESSURE_BASELINE["max"]
        stat = self._stats.metric_stats[(device_id, metric)]
        return stat.mean, stat.std, stat.min, stat.max

    def _draw_metric(self, device_id: str, metric: str, hour: int) -> float:
        if metric == "temp":
            mean = self._stats.hour_temp_mean(device_id, hour)
            _, std, lo, hi = self._baseline(device_id, "temp")
            value = random.gauss(mean, std * 0.3)
        elif metric == "pressure":
            return generate_pressure()
        else:
            mean, std, lo, hi = self._baseline(device_id, metric)
            value = random.gauss(mean, std if std > 0 else 1e-6)
        return min(max(value, lo), hi)

    def _draw_light(self, device_id: str, hour: int) -> bool:
        return random.random() < self._stats.hour_light_fraction(device_id, hour)

    def _draw_motion(self, device_id: str) -> bool:
        return random.random() < self._stats.bool_fraction(device_id, "motion")

    def _maybe_inject_anomaly(self, device_id: str, values: dict) -> list:
        if random.random() >= self._anomaly_probability:
            return []

        k = random.choices(_SPIKE_COUNT_CHOICES, weights=_SPIKE_COUNT_WEIGHTS, k=1)[0]
        metrics = random.sample(ANOMALY_ELIGIBLE_METRICS, k=min(k, len(ANOMALY_ELIGIBLE_METRICS)))

        for metric in metrics:
            _mean, std, _lo, hi = self._baseline(device_id, metric)
            std = std if std > 0 else 1e-6
            sign = 1 if metric in POSITIVE_ONLY_METRICS else random.choice((-1, 1))
            offset = sign * self._anomaly_sigma_multiplier * std
            spiked = values[metric] + offset
            outer_bound = 3 * (hi if hi not in (float("inf"), 0) else 1.0)
            values[metric] = max(min(spiked, outer_bound), -outer_bound)

        return metrics

    def next_event(self) -> dict:
        device_id = next(self._device_cycle)
        now = datetime.now(timezone.utc)
        hour = now.hour

        values = {metric: self._draw_metric(device_id, metric, hour) for metric in NUMERIC_METRICS}
        values["pressure"] = self._draw_metric(device_id, "pressure", hour)

        spiked_metrics = self._maybe_inject_anomaly(device_id, values)

        event = build_event(
            device_id=device_id,
            event_ts=now,
            ingest_ts=now,
            co=values["co"],
            humidity=values["humidity"],
            lpg=values["lpg"],
            smoke=values["smoke"],
            temp=values["temp"],
            light=self._draw_light(device_id, hour),
            motion=self._draw_motion(device_id),
            pressure=values["pressure"],
            is_synthetic=True,
        )
        return event, spiked_metrics


def run_synthetic(
    *,
    stats: BaselineStats,
    anomaly_probability: float,
    anomaly_sigma_multiplier: float,
    publisher: KafkaEventPublisher,
    topic: str,
    rate_limiter: RateLimiter,
    state: ProducerState,
) -> None:
    generator = SyntheticGenerator(stats, anomaly_probability, anomaly_sigma_multiplier)

    while True:
        event, spiked_metrics = generator.next_event()
        publisher.publish(topic, event, key=event["device_id"])
        state.record_event(mode="synthetic")

        if spiked_metrics:
            state.record_anomaly()
            logger.info(json.dumps({
                "event": "anomaly_injected",
                "device_id": event["device_id"],
                "metrics_spiked": spiked_metrics,
                "sigma_multiplier": anomaly_sigma_multiplier,
            }))

        rate_limiter.wait_for_next_tick()
