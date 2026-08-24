import { useEffect, useState } from "react";
import EChartWrapper from "../charts/EChartWrapper";
import { fetchSensorTimeline } from "../api";
import type { SensorEntry, TimelineGranularity, TimelinePoint, TimelineResponse } from "../types";
import BoundaryLog from "./BoundaryLog";

export const METRICS: { key: string; label: string }[] = [
  { key: "co", label: "CO" },
  { key: "lpg", label: "LPG" },
  { key: "smoke", label: "Smoke" },
  { key: "temp", label: "Temperature" },
  { key: "humidity", label: "Humidity" },
];

const MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export const GRANULARITIES: { key: TimelineGranularity; label: string; formatLabel: (iso: string) => string }[] = [
  { key: "1m", label: "Per minute", formatLabel: (iso) => iso.slice(11, 16) },
  { key: "1h", label: "Per hour", formatLabel: (iso) => `${iso.slice(5, 10)} ${iso.slice(11, 16)}` },
  { key: "1d", label: "Per day", formatLabel: (iso) => iso.slice(5, 10) },
  { key: "1w", label: "Per week", formatLabel: (iso) => `wk ${iso.slice(5, 10)}` },
  {
    key: "1mo",
    label: "Per month",
    formatLabel: (iso) => `${MONTH_ABBR[parseInt(iso.slice(5, 7), 10) - 1]} ${iso.slice(0, 4)}`,
  },
];

const EMPTY_DATA: Record<TimelineGranularity, TimelineResponse | null> = {
  "1m": null,
  "1h": null,
  "1d": null,
  "1w": null,
  "1mo": null,
};

// Contiguous runs of unhealthy=true points, as [startIndex, endIndex] pairs
// - the caller turns these into shaded chart regions (one per run) rather
// than one per point, so a stretch of bad readings reads as a single band.
function unhealthyRanges(points: TimelinePoint[]): [number, number][] {
  const ranges: [number, number][] = [];
  let start: number | null = null;
  points.forEach((p, i) => {
    if (p.unhealthy && start === null) start = i;
    if (!p.unhealthy && start !== null) {
      ranges.push([start, i - 1]);
      start = null;
    }
  });
  if (start !== null) ranges.push([start, points.length - 1]);
  return ranges;
}

function TimelineChart({
  title,
  formatLabel,
  response,
}: {
  title: string;
  formatLabel: (iso: string) => string;
  response: TimelineResponse | null;
}) {
  if (!response || response.points.length === 0) {
    return (
      <div className="timeline-chart">
        <h4>{title}</h4>
        <p className="waiting">No data yet.</p>
      </div>
    );
  }

  // backend/app/environment.py's metric_windows/rollup_metric_windows both
  // guarantee ascending (oldest-first) order - unlike CassandraReader.
  // aggregates_sync's own raw output (newest-first, sorted for "most
  // recent N" use cases like GET .../history). No reversal needed here;
  // the chart reads left (older) to right (now).
  const points = response.points;
  const ranges = unhealthyRanges(points);

  return (
    <div className="timeline-chart">
      <h4>{title}</h4>
      <EChartWrapper
        height={230}
        option={{
          grid: { left: 42, right: 10, top: 10, bottom: 22 },
          xAxis: { type: "category", data: points.map((p) => formatLabel(p.window_start)), axisLabel: { fontSize: 10 } },
          yAxis: { type: "value" },
          tooltip: { trigger: "axis" },
          series: [
            {
              type: "line",
              data: points.map((p) => p.avg),
              smooth: true,
              symbol: "none",
              // No areaStyle here on purpose: a translucent fill under the
              // line used to sit on top of markArea and muddy its red into
              // a brownish blend. The shaded region is the one color that
              // actually needs to read clearly, so it gets to be the only
              // fill in the chart.
              lineStyle: { width: 2.5, color: "#7dd3fc" },
              markArea: {
                itemStyle: {
                  color: "rgba(251, 90, 110, 0.32)",
                  borderColor: "rgba(251, 90, 110, 0.9)",
                  borderWidth: 1,
                },
                data: ranges.map(([s, e]) => [{ xAxis: s - 0.5 }, { xAxis: e + 0.5 }]),
              },
            },
          ],
        }}
      />
    </div>
  );
}

export default function SensorTimeline({ sensor }: { sensor: SensorEntry }) {
  const [metric, setMetric] = useState("co");
  const [data, setData] = useState(EMPTY_DATA);

  useEffect(() => {
    let cancelled = false;
    setData(EMPTY_DATA);
    Promise.all(
      GRANULARITIES.map((g) =>
        fetchSensorTimeline(sensor.device_id, { metric, granularity: g.key })
          .then((res) => [g.key, res] as const)
          .catch(() => [g.key, null] as const),
      ),
    ).then((results) => {
      if (cancelled) return;
      setData((prev) => {
        const next = { ...prev };
        for (const [key, res] of results) next[key] = res;
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [sensor.device_id, metric]);

  return (
    <div className="step timeline-panel">
      <div className="timeline-heading">
        <h3>Behavior over time — {sensor.name}</h3>
        <div className="metric-tabs">
          {METRICS.map((m) => (
            <button
              key={m.key}
              className={`metric-tab ${metric === m.key ? "metric-tab-active" : ""}`}
              onClick={() => setMetric(m.key)}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>
      <p className="waiting timeline-caption">
        Shaded regions mark windows where readings fell outside the acceptable range.
      </p>
      <div className="timeline-grid">
        {GRANULARITIES.map((g) => (
          <TimelineChart key={g.key} title={g.label} formatLabel={g.formatLabel} response={data[g.key]} />
        ))}
      </div>

      <BoundaryLog
        sensor={sensor}
        metric={metric}
        metricLabel={METRICS.find((m) => m.key === metric)?.label ?? metric}
        data={data}
      />
    </div>
  );
}
