import { useEffect, useRef, useState } from "react";
import EChartWrapper from "../charts/EChartWrapper";
import StepShell from "../layout/StepShell";
import type { KafkaStep as KafkaStepData, SparkStep as SparkStepData } from "../types";

const MAX_POINTS = 30;

export default function KafkaStep({ data, spark }: { data: KafkaStepData | null; spark: SparkStepData | null }) {
  const prevRef = useRef<{ offsets: Record<string, number>; time: number } | null>(null);
  const [rateHistory, setRateHistory] = useState<{ time: string; rate: number }[]>([]);

  useEffect(() => {
    if (!data) return;
    const total = Object.values(data.produced_offsets).reduce((a, b) => a + b, 0);
    const now = Date.now();
    const prev = prevRef.current;
    if (prev) {
      const prevTotal = Object.values(prev.offsets).reduce((a, b) => a + b, 0);
      const dt = (now - prev.time) / 1000;
      const rate = dt > 0 ? Math.max((total - prevTotal) / dt, 0) : 0;
      setRateHistory((h) => [...h, { time: new Date(now).toLocaleTimeString(), rate }].slice(-MAX_POINTS));
    }
    prevRef.current = { offsets: data.produced_offsets, time: now };
  }, [data]);

  return (
    <StepShell title="3. Kafka" data={data}>
      {data && (
        <>
          <p>Broker watermark offsets: {JSON.stringify(data.produced_offsets)}</p>

          <EChartWrapper
            option={{
              xAxis: { type: "category", data: rateHistory.map((p) => p.time) },
              yAxis: { type: "value", name: "msgs/sec" },
              tooltip: { trigger: "axis" },
              series: [{ type: "line", data: rateHistory.map((p) => p.rate), smooth: true }],
            }}
          />

          <h3>Consumer lag by Spark query</h3>
          <EChartWrapper
            option={{
              xAxis: { type: "category", data: Object.keys(data.queries) },
              yAxis: { type: "value", name: "total lag (messages)" },
              tooltip: { trigger: "axis" },
              series: [
                {
                  type: "bar",
                  data: Object.values(data.queries).map((q) => q.total_lag),
                },
              ],
            }}
          />
          {!spark && <p className="waiting">Spark step not reachable yet - lag figures may be stale.</p>}
        </>
      )}
    </StepShell>
  );
}
