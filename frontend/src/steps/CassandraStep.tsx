import StepShell from "../layout/StepShell";
import type { CassandraStep as CassandraStepData } from "../types";

export default function CassandraStep({ data }: { data: CassandraStepData | null }) {
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
        </>
      )}
    </StepShell>
  );
}
