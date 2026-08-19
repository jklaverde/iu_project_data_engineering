import EChartWrapper from "../charts/EChartWrapper";
import StepShell from "../layout/StepShell";
import type { SummaryStep as SummaryStepData } from "../types";

export default function SummaryStep({ data }: { data: SummaryStepData | null }) {
  const grafanaUrl = data ? `${location.protocol}//${location.hostname}:${data.grafana_port}` : null;

  return (
    <StepShell title="6. Summary" data={data}>
      {data && (
        <>
          <EChartWrapper
            option={{
              tooltip: { trigger: "axis" },
              xAxis: {
                type: "category",
                data: ["events ingested", "anomalies detected", "rows in Cassandra sample"],
              },
              yAxis: { type: "value" },
              series: [
                {
                  type: "bar",
                  data: [
                    data.totals.events_ingested,
                    data.totals.anomalies_detected,
                    data.totals.rows_in_cassandra_sample,
                  ],
                },
              ],
            }}
          />
          <p>
            For historical trends and the full KPI dashboard, open{" "}
            <a href={grafanaUrl!} target="_blank" rel="noreferrer">
              Grafana ↗
            </a>
            .
          </p>
        </>
      )}
    </StepShell>
  );
}
