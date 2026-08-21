from collections import deque


class AlertStore:
    """Small in-memory ring buffer of recent Grafana-fired alerts (R4 of the
    role-based redirect). No persistence needed - this is a live "what's
    currently/recently wrong" feed for the admin role, not a durable audit
    log (Grafana itself remains the system of record for alert history)."""

    def __init__(self, max_size: int = 200):
        self._alerts: deque = deque(maxlen=max_size)

    def add(self, alert: dict) -> None:
        self._alerts.appendleft(alert)

    def recent(self, limit: int = 50) -> list:
        return list(self._alerts)[:limit]
