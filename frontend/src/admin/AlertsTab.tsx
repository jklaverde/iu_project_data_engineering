import { useEffect, useState } from "react";
import { fetchAdminAlerts } from "../api";
import type { AdminAlert } from "../types";

const POLL_INTERVAL_MS = 10000;

function exploreUrl(grafanaPort: number | null, service: string | null): string | null {
  if (!grafanaPort || !service) return null;
  const query = {
    datasource: "loki",
    queries: [{ refId: "A", expr: `{container=~".*${service}.*"}` }],
    range: { from: "now-30m", to: "now" },
  };
  const left = encodeURIComponent(JSON.stringify(query));
  return `${location.protocol}//${location.hostname}:${grafanaPort}/explore?left=${left}`;
}

export default function AlertsTab({ grafanaPort }: { grafanaPort: number | null }) {
  const [alerts, setAlerts] = useState<AdminAlert[]>([]);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetchAdminAlerts();
        if (!cancelled) setAlerts(res.alerts);
      } catch {
        // transient - next tick retries
      }
    };
    poll();
    const timer = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return (
    <div className="step">
      <h3>Alerts</h3>
      <p className="waiting">
        Fired by Grafana's provisioned alert rules (consumer lag, Cassandra write latency, elevated
        ERROR log rate, service down) and pushed here via a webhook contact point.
      </p>
      {alerts.length === 0 && <p className="waiting">No alerts fired yet.</p>}
      <ul className="alert-feed">
        {alerts.map((a) => {
          const url = exploreUrl(grafanaPort, a.service);
          return (
            <li key={a.id}>
              <span className={`status-badge status-${a.status === "firing" ? "critical" : "ok"}`}>
                {a.status}
              </span>{" "}
              <strong>{a.alertname}</strong>
              <div className="waiting">{a.summary}</div>
              {url && (
                <a className="alert-drilldown" href={url} target="_blank" rel="noreferrer">
                  Drill into logs ↗
                </a>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
