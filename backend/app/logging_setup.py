import json
import logging
import sys
from datetime import datetime, timezone


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
        }
        msg = record.getMessage()
        try:
            structured = json.loads(msg)
            if isinstance(structured, dict):
                payload.update(structured)
            else:
                payload["message"] = msg
        except (json.JSONDecodeError, TypeError):
            payload["message"] = msg
        return json.dumps(payload)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLineFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
