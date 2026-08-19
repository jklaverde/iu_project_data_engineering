import asyncio
import json
import logging
import time
import urllib.request

logger = logging.getLogger(__name__)


def _fetch_json_sync(url: str, timeout: float = 3.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        logger.warning(json.dumps({"event": "upstream_fetch_failed", "url": url, "error": str(exc)}))
        return None


async def fetch_json(url: str, timeout: float = 3.0) -> dict | None:
    return await asyncio.to_thread(_fetch_json_sync, url, timeout)


def _check_url_sync(url: str, timeout: float = 2.0) -> tuple[bool, str, float]:
    started = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            latency_ms = (time.monotonic() - started) * 1000
            return resp.status < 400, f"HTTP {resp.status}", latency_ms
    except Exception as exc:
        latency_ms = (time.monotonic() - started) * 1000
        return False, str(exc), latency_ms


async def check_url(url: str, timeout: float = 2.0) -> tuple[bool, str, float]:
    """Plain reachability probe (deployment step, UC-1) - the response body
    isn't parsed, some targets return HTML (Spark UI) or Prometheus text
    (exporters) rather than JSON."""
    return await asyncio.to_thread(_check_url_sync, url, timeout)
