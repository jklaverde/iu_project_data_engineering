import { useEffect, useState } from "react";
import StepShell from "../layout/StepShell";
import { deployCassandraNode, fetchCassandraStorage } from "../api";
import CassandraNodeDeployAnimation from "../admin/CassandraNodeDeployAnimation";
import type { CassandraDeployProgress, CassandraStorageSummary, CassandraStep as CassandraStepData } from "../types";

const STORAGE_POLL_MS = 10000;

function formatBytes(bytes: number): string {
  const gib = bytes / 1024 ** 3;
  return gib >= 1 ? `${gib.toFixed(2)} GiB` : `${(bytes / 1024 ** 2).toFixed(0)} MiB`;
}

function StorageControl({ deploying, onDeploy }: { deploying: boolean; onDeploy: () => void }) {
  const [storage, setStorage] = useState<CassandraStorageSummary | null>(null);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetchCassandraStorage();
        if (!cancelled) setStorage(res);
      } catch {
        // transient - next tick retries
      }
    };
    poll();
    const timer = setInterval(poll, STORAGE_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return (
    <div className="cassandra-storage-control">
      <h3 className="section-title">Storage capacity (D42, UC-12)</h3>
      <p className="waiting">
        Each node's <code>Storage_Load</code> against a configured budget — a monitored threshold this
        admin UI compares Cassandra's own reported usage to, not a kernel-enforced disk quota (Docker
        Desktop doesn't support per-container storage limits).
      </p>

      {storage && (
        <div className="storage-node-list">
          {storage.nodes.map((n) => (
            <div key={n.address} className="storage-node-row">
              <div className="storage-node-name">
                {n.container_name} {!n.up_normal && <span className="status-badge status-warning">not ready</span>}
              </div>
              <div className="storage-bar-track">
                <div
                  className={`storage-bar-fill ${n.percent_of_budget >= 85 ? "storage-bar-critical" : ""}`}
                  style={{ width: `${Math.min(100, n.percent_of_budget)}%` }}
                />
              </div>
              <div className="storage-node-value">
                {formatBytes(n.load_bytes)} · {n.percent_of_budget}% of {formatBytes(storage.budget_bytes)}
              </div>
            </div>
          ))}
        </div>
      )}

      <p className="demo-only-notice">
        ⚠ Demo/illustration only: deploying a database node straight from a web UI is not a safe
        production practice, even now that it goes through a narrowly-scoped Kubernetes RBAC Role
        instead of a Docker socket (D43, NFR-16) — the backend can only scale this one StatefulSet by
        name, nothing else in the cluster. A real deployment scales Cassandra through its own cluster
        tooling, not an app button.
      </p>

      {!confirming && (
        <button className="btn btn-ghost" onClick={() => setConfirming(true)} disabled={deploying}>
          Deploy new Cassandra node…
        </button>
      )}

      {confirming && (
        <div className="archive-confirm">
          <p>
            <strong>This starts a real second Cassandra container</strong> and joins it to the running
            ring. It can take several minutes (bootstrap streaming). Continue?
          </p>
          <button
            className="btn btn-accent"
            onClick={() => {
              setConfirming(false);
              onDeploy();
            }}
            disabled={deploying}
          >
            Yes, deploy a node
          </button>
          <button className="btn btn-ghost" onClick={() => setConfirming(false)} disabled={deploying}>
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}

export default function CassandraStep({
  data,
  deployProgress,
}: {
  data: CassandraStepData | null;
  deployProgress: CassandraDeployProgress | null;
}) {
  const deploying = deployProgress !== null && deployProgress.status === "in_progress";

  const handleDeploy = async () => {
    try {
      await deployCassandraNode();
    } catch {
      // progress/error surfaces over the WebSocket regardless of whether
      // this call itself failed to even start (e.g. a 409 if one's already
      // running) - nothing further to do here.
    }
  };

  return (
    <StepShell title="5. Cassandra" data={data}>
      {data && (
        <>
          <p>Most recent rows written to <code>iot.raw_events</code>:</p>
          <table className="event-table">
            <thead>
              <tr>
                <th>device</th>
                <th>event_ts</th>
                <th>write_ts</th>
                <th>anomaly</th>
              </tr>
            </thead>
            <tbody>
              {data.recent_raw_events.map((row) => (
                <tr key={row.event_id} className={row.is_anomaly ? "anomaly-row" : ""}>
                  <td>{row.device_id}</td>
                  <td>{row.event_ts ? new Date(row.event_ts).toLocaleTimeString() : "-"}</td>
                  <td>{row.write_ts ? new Date(row.write_ts).toLocaleTimeString() : "-"}</td>
                  <td>{row.is_anomaly ? row.anomaly_reason ?? "yes" : ""}</td>
                </tr>
              ))}
              {data.recent_raw_events.length === 0 && (
                <tr>
                  <td colSpan={4}>No rows in the current 15-minute buckets yet.</td>
                </tr>
              )}
            </tbody>
          </table>

          <StorageControl deploying={deploying} onDeploy={handleDeploy} />

          {deployProgress && <CassandraNodeDeployAnimation progress={deployProgress} />}
        </>
      )}
    </StepShell>
  );
}
