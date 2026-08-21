import { useEffect, useState } from "react";
import { fetchAnomalies } from "../api";
import type { RawEventRow, SensorEntry } from "../types";

const POLL_INTERVAL_MS = 10000;

const METRIC_LABEL: Record<string, string> = {
  co: "CO",
  humidity: "humidity",
  lpg: "LPG",
  smoke: "smoke",
  temp: "temperature",
  pressure: "pressure",
};

// Spark emits raw diagnostic strings like "temp:sigma(-4.23sigma)" or
// "smoke:ceiling(0.01230>0.00987)" (spark_job/spark_job/anomaly_state.py) -
// fine for the admin's anomaly log, too technical for a citizen-facing
// feed. Turns that into e.g. "elevated smoke, unusual temperature".
function friendlyReason(reason: string | null): string {
  if (!reason) return "an elevated reading";
  return reason
    .split(";")
    .map((token) => {
      const [metric, kind] = token.split(":");
      const label = METRIC_LABEL[metric] ?? metric;
      return kind?.startsWith("ceiling") ? `elevated ${label}` : `unusual ${label}`;
    })
    .join(", ");
}

export default function AlertFeed({ sensors }: { sensors: SensorEntry[] }) {
  const [alerts, setAlerts] = useState<RawEventRow[]>([]);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetchAnomalies({ sinceMinutes: 60, limit: 20 });
        if (!cancelled) setAlerts(res.anomalies);
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

  const nameFor = (deviceId: string) => sensors.find((s) => s.device_id === deviceId)?.name ?? deviceId;

  return (
    <div className="step">
      <h3>Recent alerts</h3>
      {alerts.length === 0 && <p className="waiting">No elevated readings in the last hour.</p>}
      <ul className="alert-feed">
        {alerts.map((a) => (
          <li key={a.event_id}>
            <span className="alert-time">{(a.event_ts ?? "").slice(11, 19)}</span>{" "}
            <span>
              {friendlyReason(a.anomaly_reason)} near {nameFor(a.device_id)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
