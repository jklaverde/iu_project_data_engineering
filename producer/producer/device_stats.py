import csv
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone

NUMERIC_METRICS = ("co", "humidity", "lpg", "smoke", "temp")
BOOLEAN_METRICS = ("light", "motion")

# Pressure has no real column in the source dataset (D23): simulated for every
# row, both replay and synthetic modes, from fixed global parameters rather
# than a per-device baseline.
PRESSURE_MEAN_HPA = 1013.25
PRESSURE_STD_HPA = 6.0
PRESSURE_MIN_HPA = 980.0
PRESSURE_MAX_HPA = 1040.0


def generate_pressure(rng: random.Random = random) -> float:
    value = rng.gauss(PRESSURE_MEAN_HPA, PRESSURE_STD_HPA)
    return min(max(value, PRESSURE_MIN_HPA), PRESSURE_MAX_HPA)


@dataclass
class RunningStat:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0
    min: float = float("inf")
    max: float = float("-inf")

    def update(self, x: float) -> None:
        self.count += 1
        delta = x - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (x - self.mean)
        if x < self.min:
            self.min = x
        if x > self.max:
            self.max = x

    @property
    def std(self) -> float:
        return math.sqrt(self.m2 / self.count) if self.count > 1 else 0.0


@dataclass
class _HourBucket:
    temp_stat: RunningStat = field(default_factory=RunningStat)
    light_true_count: int = 0
    light_total_count: int = 0

    @property
    def light_fraction(self) -> float:
        return self.light_true_count / self.light_total_count if self.light_total_count else 0.0


@dataclass
class BaselineStats:
    device_ids: list
    metric_stats: dict  # (device_id, metric) -> RunningStat
    bool_true_count: dict  # (device_id, metric) -> int
    bool_total_count: dict  # (device_id, metric) -> int
    hour_buckets: dict  # (device_id, hour) -> _HourBucket
    total_rows: int

    def bool_fraction(self, device_id: str, metric: str) -> float:
        total = self.bool_total_count.get((device_id, metric), 0)
        if total == 0:
            return 0.0
        return self.bool_true_count.get((device_id, metric), 0) / total

    def hour_temp_mean(self, device_id: str, hour: int) -> float:
        bucket = self.hour_buckets.get((device_id, hour))
        if bucket is None or bucket.temp_stat.count == 0:
            return self.metric_stats[(device_id, "temp")].mean
        return bucket.temp_stat.mean

    def hour_light_fraction(self, device_id: str, hour: int) -> float:
        bucket = self.hour_buckets.get((device_id, hour))
        if bucket is None or bucket.light_total_count == 0:
            return self.bool_fraction(device_id, "light")
        return bucket.light_fraction


def _read_rows(csv_path: str):
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row


def compute_baseline_stats(csv_path: str) -> BaselineStats:
    """Single streaming pass over the CSV computing per-device baseline
    statistics in O(1) memory via Welford's online algorithm."""
    device_ids: set = set()
    metric_stats: dict = {}
    bool_true_count: dict = {}
    bool_total_count: dict = {}
    hour_buckets: dict = {}
    total_rows = 0

    for row in _read_rows(csv_path):
        total_rows += 1
        device_id = row["device"]
        device_ids.add(device_id)

        for metric in NUMERIC_METRICS:
            key = (device_id, metric)
            if key not in metric_stats:
                metric_stats[key] = RunningStat()
            metric_stats[key].update(float(row[metric]))

        for metric in BOOLEAN_METRICS:
            is_true = row[metric].strip().lower() == "true"
            key = (device_id, metric)
            bool_total_count[key] = bool_total_count.get(key, 0) + 1
            if is_true:
                bool_true_count[key] = bool_true_count.get(key, 0) + 1

        ts = float(row["ts"])
        hour = datetime.fromtimestamp(ts, tz=timezone.utc).hour
        bucket_key = (device_id, hour)
        if bucket_key not in hour_buckets:
            hour_buckets[bucket_key] = _HourBucket()
        bucket = hour_buckets[bucket_key]
        bucket.temp_stat.update(float(row["temp"]))
        bucket.light_total_count += 1
        if row["light"].strip().lower() == "true":
            bucket.light_true_count += 1

    return BaselineStats(
        device_ids=sorted(device_ids),
        metric_stats=metric_stats,
        bool_true_count=bool_true_count,
        bool_total_count=bool_total_count,
        hour_buckets=hour_buckets,
        total_rows=total_rows,
    )
