import { useEffect, useState } from "react";
import { fetchAdminAlerts, runArchive } from "../api";
import type { AdminAlert, ArchiveResult } from "../types";

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
  const [confirming, setConfirming] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [archiveResult, setArchiveResult] = useState<ArchiveResult | null>(null);
  const [archiveError, setArchiveError] = useState<string | null>(null);

  const handleArchive = async () => {
    setArchiving(true);
    setArchiveError(null);
    try {
      const result = await runArchive();
      setArchiveResult(result);
    } catch (err) {
      setArchiveError(err instanceof Error ? err.message : "Archive action failed");
    } finally {
      setArchiving(false);
      setConfirming(false);
    }
  };

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

      <h3 className="section-title">Disk capacity — archive & trim (D40, UC-11)</h3>
      <p className="waiting">
        Exports the oldest raw-event partitions (default: the oldest 10% by time) to a local archive
        file, then drops them from Cassandra — the sanctioned way to free space without a full,
        destructive reset (NFR-4). Irreversible against the live store; the exported file is the only
        remaining copy.
      </p>

      {!confirming && (
        <button className="btn btn-ghost" onClick={() => setConfirming(true)} disabled={archiving}>
          Archive oldest data…
        </button>
      )}

      {confirming && (
        <div className="archive-confirm">
          <p>
            <strong>This will permanently delete the oldest raw events from Cassandra</strong> after
            exporting them to a local NDJSON file. Continue?
          </p>
          <button className="btn btn-accent" onClick={handleArchive} disabled={archiving}>
            {archiving ? "Archiving…" : "Yes, archive and trim"}
          </button>
          <button className="btn btn-ghost" onClick={() => setConfirming(false)} disabled={archiving}>
            Cancel
          </button>
        </div>
      )}

      {archiveError && <p className="status-badge status-critical">{archiveError}</p>}

      {archiveResult && (
        <p className="waiting">
          Archived {archiveResult.rows_archived} rows across {archiveResult.partitions_archived} partitions
          (cutoff {archiveResult.cutoff}) to <code>{archiveResult.archive_path}</code>.
        </p>
      )}
    </div>
  );
}
