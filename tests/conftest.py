"""Shared test setup.

The three Python services are separate images with separate package roots
(backend/app, producer/producer, spark_job/spark_job); tests import them the
way their containers do, by putting each service directory on sys.path.

Unit tests never talk to Kafka, Cassandra or Spark. The modules under test
import those client libraries at module level, so when a library is not
installed in the test environment it is replaced by an inert stub module
(attribute access returns a MagicMock). Tests that exercise Cassandra-facing
code pass fake sessions explicitly - the stubs only make the imports succeed.
"""

import csv
import importlib
import math
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
for service_dir in ("backend", "producer", "spark_job"):
    path = str(ROOT / service_dir)
    if path not in sys.path:
        sys.path.insert(0, path)

_OPTIONAL_MODULES = (
    "cassandra",
    "cassandra.cluster",
    "cassandra.concurrent",
    "confluent_kafka",
    "pyspark",
    "pyspark.sql",
    "pyspark.sql.functions",
    "pyspark.sql.types",
    "pyspark.sql.streaming",
    "pyspark.sql.streaming.state",
)


def _stub_module(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__getattr__ = lambda attr: MagicMock(name=f"{name}.{attr}")  # PEP 562
    module.__path__ = []  # lets "import pkg.sub" treat it as a package
    return module


for _name in _OPTIONAL_MODULES:
    try:
        importlib.import_module(_name)
    except ImportError:
        sys.modules[_name] = _stub_module(_name)


# ---------------------------------------------------------------------------
# A small synthetic stand-in for the Kaggle source file: same columns, same
# global ordering (ascending ts, devices interleaved), 8 days starting at
# 2020-07-12 00:00 UTC like the real one, one reading per device every 10 min.
# Temperature follows a day/night cycle so time-of-day handling is observable.
# ---------------------------------------------------------------------------

SOURCE_DEVICES = ("dev-a", "dev-b", "dev-c")
SOURCE_START = datetime(2020, 7, 12, 0, 0, 30, tzinfo=timezone.utc)
SOURCE_STEP = timedelta(minutes=10)
SOURCE_STEPS = 8 * 24 * 6  # 8 days


def source_temp(device_index: int, at: datetime) -> float:
    """Day/night cycle: warmest at 14:00 UTC, coldest at 02:00 UTC."""
    hour = at.hour + at.minute / 60.0
    return 20.0 + device_index + 2.0 * math.cos(2 * math.pi * (hour - 14) / 24)


def write_source_csv(path: Path) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["ts", "device", "co", "humidity", "light", "lpg", "motion", "smoke", "temp"])
        for step in range(SOURCE_STEPS):
            at = SOURCE_START + step * SOURCE_STEP
            for i, device in enumerate(SOURCE_DEVICES):
                w.writerow([
                    repr(at.timestamp()), device,
                    repr(0.004 + 0.0001 * (step % 7)),
                    repr(50.0 + i + (step % 5) * 0.2),
                    "true" if 6 <= at.hour < 20 else "false",
                    repr(0.006 + 0.0001 * (step % 3)),
                    "true" if step % 11 == 0 else "false",
                    repr(0.02 + 0.0005 * (step % 4)),
                    repr(source_temp(i, at)),
                ])
    return path


@pytest.fixture
def source_csv(tmp_path) -> Path:
    return write_source_csv(tmp_path / "iot_telemetry_data.csv")
