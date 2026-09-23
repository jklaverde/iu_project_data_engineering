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
      <h3 className="section-title">Storage capacity</h3>
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

      {/* Was worded as "Demo/illustration only" - misleading: this button drives a real Kubernetes
          scale-up (real pod, real 5 GiB PersistentVolumeClaim, real ring join), previously confirmed
          against production-shaped infrastructure. There is also no matching remove-a-node action, so
          a deploy here is a standing resource commitment, not something to undo with another click.
          Rewritten to state that plainly instead of implying it's a toy. */}
      <p className="cassandra-deploy-warning">
        ⚠ Real action, not a simulation: this scales the actual Cassandra StatefulSet by one, so a
        genuine pod is created with its own 5&nbsp;GiB persistent volume and streamed with live ring
        data — the same effect as scaling it from the command line, just kept narrowly scoped (this
        button can only touch this one StatefulSet, nothing else in the cluster). There is no
        matching "remove a node" action here — taking one back out safely needs a manual operator
        step outside this UI. Only deploy a node when there's a genuine capacity need, and check the
        cluster's available memory first.
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
