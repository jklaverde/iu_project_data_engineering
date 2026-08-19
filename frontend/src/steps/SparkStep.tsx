import EChartWrapper from "../charts/EChartWrapper";
import StepShell from "../layout/StepShell";
import type { SparkStep as SparkStepData } from "../types";

export default function SparkStep({ data }: { data: SparkStepData | null }) {
  const queryNames = data ? Object.keys(data.queries) : [];

  return (
    <StepShell title="4. Spark Structured Streaming" data={data}>
      {data && (
        <>
          <div className="query-grid">
            {queryNames.map((name) => {
              const q = data.queries[name];
              return (
                <div key={name} className="query-card">
                  <h3>{name}</h3>
                  <p>batch #{q.batch_id}</p>
                  <p>{q.num_input_rows} rows this batch</p>
                  <p>{q.input_rows_per_second?.toFixed(1) ?? "-"} rows/sec</p>
                  <p>{q.processing_time_ms ?? "-"} ms processing time</p>
                </div>
              );
            })}
          </div>

          <h3>End-to-end latency (event produced → written to Cassandra)</h3>
          <EChartWrapper
            option={{
              tooltip: { trigger: "axis" },
              xAxis: { type: "category", data: ["p50", "p95", "max"] },
              yAxis: { type: "value", name: "seconds" },
              series: [
                {
                  type: "bar",
                  data: [
                    data.latency.e2e_p50_seconds ?? 0,
                    data.latency.e2e_p95_seconds ?? 0,
                    data.latency.e2e_max_seconds ?? 0,
                  ],
                },
              ],
            }}
          />
        </>
      )}
    </StepShell>
  );
}
