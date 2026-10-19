import { useCallback, useState } from "react";
import { fetchFactSheet } from "../api";
import type { FactSheet as Sheet, ReportMetric, SensorEntry } from "../types";
import HourHeatmap from "./HourHeatmap";
import ReportChart, { baseAxis, type ChartPalette } from "./ReportChart";
import ReportSheet from "./ReportSheet";
import { METRIC_ORDER, fmtDay, fmtHour, fmtShare, fmtValue } from "./reportFormat";
import { CHARACTER_TEXT, HEATMAP_CAPTION } from "./reportText";
import { useReport } from "./useReport";

const STATUS_LABEL: Record<string, string> = { ok: "OK", warning: "Warning", critical: "Critical", unknown: "No data yet" };

function DailyChart({ sheet, metric }: { sheet: Sheet; metric: ReportMetric }) {
  const build = useCallback(
    (p: ChartPalette) => {
      const daily = sheet.metrics[metric].daily;
      return {
        animation: false,
        color: [p.series[0], p.series[1]],
        legend: { top: 0, textStyle: { color: p.text, fontSize: 11 } },
        grid: { left: 56, right: 40, top: 30, bottom: 28 },
        tooltip: { trigger: "axis" as const },
        xAxis: { type: "category" as const, data: daily.map((d) => fmtDay(d.day).replace(/ \d{4}$/, "")), ...baseAxis(p) },
        yAxis: [
          { type: "value" as const, scale: true, name: sheet.units[metric], nameTextStyle: { color: p.text, fontSize: 10 }, ...baseAxis(p) },
          { type: "value" as const, name: "h out", minInterval: 1, nameTextStyle: { color: p.text, fontSize: 10 }, ...baseAxis(p), splitLine: { show: false } },
        ],
        series: [
          // Small markers: a day with data between two empty days has no line to draw.
          { name: "daily average", type: "line" as const, symbolSize: 4, data: daily.map((d) => d.average) },
          { name: "daily highest", type: "line" as const, symbolSize: 4, lineStyle: { type: "dashed" as const }, data: daily.map((d) => d.max) },
          {
            name: "hours out of range", type: "bar" as const, yAxisIndex: 1, barWidth: 6,
            itemStyle: { color: p.bad }, data: daily.map((d) => d.out_of_range_hours),
          },
        ],
      };
    },
    [sheet, metric],
  );
  return <ReportChart build={build} height={230} />;
}

export default function FactSheet({
  sensors,
  deviceId,
  onDeviceChange,
}: {
  sensors: SensorEntry[];
  deviceId: string;
  onDeviceChange: (id: string) => void;
}) {
  const [metric, setMetric] = useState<ReportMetric>("co");
  const { data: sheet, loading, error } = useReport(deviceId ? () => fetchFactSheet(deviceId) : null, [deviceId]);
  const sensor = sensors.find((s) => s.device_id === deviceId) ?? null;

  return (
    <>
      <div className="report-controls no-print">
        <label>
          Location
          <select value={deviceId} onChange={(e) => onDeviceChange(e.target.value)}>
            {sensors.map((s) => (
              <option key={s.device_id} value={s.device_id}>
                {s.name} — {s.area}
              </option>
            ))}
          </select>
        </label>
        {loading && <span className="waiting">Loading…</span>}
      </div>
      {error && <p className="step-error">{error}</p>}

      {sheet && sheet.location.device_id === deviceId && (
        <ReportSheet
          title={`Location fact sheet — ${sheet.location.name}`}
          subtitle={`${sheet.location.area}. Figures for the last ${sheet.period.days} days; daily rhythm over the last 12 months.`}
          caveats={sheet.caveats}
        >
          {sensor && (
            <div className="stat-tiles report-tiles">
              <div className="stat-tile">
                <span className="score-label">Status now</span>
                <span className={`status-badge status-${sensor.status.overall}`}>
                  {STATUS_LABEL[sensor.status.overall] ?? sensor.status.overall}
                  {sensor.status.reason ? ` — ${sensor.status.reason}` : ""}
                </span>
              </div>
              <div className="stat-tile">
                <span className="score-label">Air quality score</span>
                <span className="score-value">{sensor.air_quality_score?.toFixed(0) ?? "–"}</span>
              </div>
              <div className="stat-tile">
                <span className="score-label">Comfort index</span>
                <span className="score-value">{sensor.comfort_index?.toFixed(0) ?? "–"}</span>
              </div>
              <div className="stat-tile">
                <span className="score-label">Hours with data (30 days)</span>
                <span className="score-value">{sheet.hours_with_data}</span>
              </div>
            </div>
          )}

          <h4 className="section-title">What each measurement is like here (last {sheet.period.days} days)</h4>
          <table className="report-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Average</th>
                <th>Character</th>
                <th>Typical peak hour</th>
                <th>Hours out of range</th>
                <th>Highest</th>
              </tr>
            </thead>
            <tbody>
              {METRIC_ORDER.map((m) => {
                const s = sheet.metrics[m];
                const c = s.character;
                return (
                  <tr key={m} className={m === metric ? "report-row-focus" : undefined}>
                    <td>
                      {sheet.labels[m]} <span className="report-muted">{sheet.units[m]}</span>
                    </td>
                    <td>{fmtValue(s.average, m)}</td>
                    <td>
                      {c.label ? (
                        <span title={CHARACTER_TEXT[c.label]}>
                          {c.label}
                          {c.variation !== null && <span className="report-muted"> · varies {fmtShare(c.variation)}</span>}
                        </span>
                      ) : c.low !== null ? (
                        <span>
                          {fmtValue(c.low, m)} to {fmtValue(c.high, m)}
                        </span>
                      ) : (
                        "–"
                      )}
                    </td>
                    <td>{fmtHour(s.peak_hour)}</td>
                    <td>
                      {s.out_of_range_hours} <span className="report-muted">({fmtShare(s.out_of_range_share)})</span>
                    </td>
                    <td>{fmtValue(s.peak, m)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <ul className="report-legend">
            {(["steady", "variable", "spiky"] as const).map((k) => (
              <li key={k}>{CHARACTER_TEXT[k]}</li>
            ))}
          </ul>

          <div className="metric-tabs no-print report-metric-tabs">
            {METRIC_ORDER.map((m) => (
              <button
                key={m}
                className={`metric-tab ${metric === m ? "metric-tab-active" : ""}`}
                onClick={() => setMetric(m)}
              >
                {sheet.labels[m]}
              </button>
            ))}
          </div>
          <h4 className="section-title">{sheet.labels[metric]}, day by day</h4>
          <DailyChart sheet={sheet} metric={metric} />
          <h4 className="section-title">{sheet.labels[metric]}: daily rhythm by month</h4>
          <p className="report-muted report-caption">{HEATMAP_CAPTION}</p>
          <HourHeatmap heatmap={sheet.heatmaps[metric]} label={sheet.labels[metric]} unit={sheet.units[metric]} />
        </ReportSheet>
      )}
    </>
  );
}
