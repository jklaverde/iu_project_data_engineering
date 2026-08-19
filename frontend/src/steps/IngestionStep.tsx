import EChartWrapper from "../charts/EChartWrapper";
import StepShell from "../layout/StepShell";
import type { IngestionStep as IngestionStepData } from "../types";

export default function IngestionStep({ data }: { data: IngestionStepData | null }) {
  return (
    <StepShell title="2. Ingestion" data={data}>
      {data && (
        <>
          <div className="stat-row">
            <div className="stat">
              <div className="stat-value">{(data.events_sent_total ?? 0).toLocaleString()}</div>
              <div className="stat-label">events sent</div>
            </div>
            <div className="stat">
              <div className="stat-value">{data.configured_rate_msgs_per_sec ?? "-"}</div>
              <div className="stat-label">msgs/sec target</div>
            </div>
            <div className="stat">
              <div className="stat-value">{(data.anomalies_injected_total ?? 0).toLocaleString()}</div>
              <div className="stat-label">anomalies injected</div>
            </div>
            <div className="stat">
              <div className={`stat-value mode-${data.mode ?? "replay"}`}>{(data.mode ?? "unknown").toUpperCase()}</div>
              <div className="stat-label">
                {!data.source_reachable
                  ? "producer unreachable - showing last known data"
                  : data.handover_ts
                    ? `since ${new Date(data.handover_ts).toLocaleTimeString()}`
                    : "replaying dataset"}
              </div>
            </div>
          </div>

          <EChartWrapper
            height={200}
            option={{
              tooltip: { trigger: "item" },
              series: [
                {
                  type: "pie",
                  radius: "70%",
                  data: [
                    { name: "replay", value: data.events_sent_replay ?? 0 },
                    { name: "synthetic", value: data.events_sent_synthetic ?? 0 },
                  ],
                },
              ],
            }}
          />

          <h3>Recent events (topic: {data.kafka_topic ?? "-"})</h3>
          <table className="event-table">
            <thead>
              <tr>
                <th>device</th>
                <th>event_ts</th>
                <th>temp</th>
                <th>co</th>
                <th>smoke</th>
              </tr>
            </thead>
            <tbody>
              {(data.recent_events ?? []).map((ev) => (
                <tr key={ev.event_id}>
                  <td>{ev.device_id}</td>
                  <td>{new Date(ev.event_ts).toLocaleTimeString()}</td>
                  <td>{ev.temp.toFixed(2)}</td>
                  <td>{ev.co.toFixed(4)}</td>
                  <td>{ev.smoke.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </StepShell>
  );
}
