import { useEffect, useState } from "react";
import { fetchKubernetesStatus } from "../api";
import type { KubernetesStatusResponse } from "../types";

const POLL_INTERVAL_MS = 10000;

function phaseClass(phase: string): string {
  if (phase === "Running" || phase === "Succeeded") return "status-ok";
  if (phase === "Pending") return "status-warning";
  return "status-critical";
}

export default function KubernetesStatusTab() {
  const [data, setData] = useState<KubernetesStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetchKubernetesStatus();
        if (!cancelled) {
          setData(res);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error && err.message.includes("503")
              ? "Kubernetes API not available — this backend is running under the historical docker-compose.yml, not the k3d/k3s deployment."
              : "Could not reach the Kubernetes status endpoint.",
          );
        }
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
      <h3>Kubernetes status</h3>
      <p className="waiting">
        Pod and workload health read directly from the Kubernetes API, via the same narrowly-scoped
        RBAC Role the Cassandra node-deploy action uses — the same "is the deployment actually
        healthy" question the Deployment step answers per-service, now answerable at the orchestration
        layer too.
      </p>

      {error && <p className="status-badge status-critical">{error}</p>}

      {data && (
        <>
          <h4 className="section-title">Workloads</h4>
          <table className="event-table">
            <thead>
              <tr>
                <th>kind</th>
                <th>name</th>
                <th>ready</th>
              </tr>
            </thead>
            <tbody>
              {data.workloads.map((w) => (
                <tr key={`${w.kind}-${w.name}`}>
                  <td>{w.kind}</td>
                  <td>{w.name}</td>
                  <td className={w.ready < w.desired ? "status-badge status-warning" : ""}>
                    {w.ready} / {w.desired}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h4 className="section-title">Pods</h4>
          <table className="event-table">
            <thead>
              <tr>
                <th>name</th>
                <th>phase</th>
                <th>ready</th>
                <th>restarts</th>
                <th>node</th>
              </tr>
            </thead>
            <tbody>
              {data.pods.map((p) => (
                <tr key={p.name}>
                  <td>{p.name}</td>
                  <td><span className={`status-badge ${phaseClass(p.phase)}`}>{p.phase}</span></td>
                  <td>{p.ready}</td>
                  <td>{p.restarts}</td>
                  <td>{p.node ?? "-"}</td>
                </tr>
              ))}
              {data.pods.length === 0 && (
                <tr>
                  <td colSpan={5}>No pods found in the iot-pipeline namespace.</td>
                </tr>
              )}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
