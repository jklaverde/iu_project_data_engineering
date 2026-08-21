import { useEffect, useState } from "react";
import EChartWrapper from "../charts/EChartWrapper";
import { fetchSensorHistory } from "../api";
import type { SensorEntry, SensorHistoryResponse } from "../types";

const STATUS_LABEL: Record<string, string> = {
  ok: "OK",
  warning: "Warning",
  critical: "Critical",
  unknown: "No data yet",
};

export default function SensorDetailPanel({ sensor }: { sensor: SensorEntry | null }) {
  const [history, setHistory] = useState<SensorHistoryResponse | null>(null);

  useEffect(() => {
    if (!sensor) {
      setHistory(null);
      return;
    }
    let cancelled = false;
    fetchSensorHistory(sensor.device_id, { granularity: "1h", hours: 24 })
      .then((res) => {
        if (!cancelled) setHistory(res);
      })
      .catch(() => {
        if (!cancelled) setHistory(null);
      });
    return () => {
      cancelled = true;
    };
  }, [sensor]);

  if (!sensor) {
    return (
      <div className="step">
        <h3>Sensor detail</h3>
        <p className="waiting">Select a sensor on the map to see its readings.</p>
      </div>
    );
  }

  const windows = [...history?.windows ?? []].reverse();

  return (
    <div className="step">
      <h3>{sensor.name}</h3>
      <p className="waiting">{sensor.area}</p>
      <p className={`status-badge status-${sensor.status.overall}`}>
        {STATUS_LABEL[sensor.status.overall] ?? sensor.status.overall}
        {sensor.status.reason ? ` — ${sensor.status.reason}` : ""}
      </p>

      {sensor.reading && (
        <ul className="metric-list">
          <li>CO: {sensor.reading.co.toFixed(4)}</li>
          <li>LPG: {sensor.reading.lpg.toFixed(4)}</li>
          <li>Smoke: {sensor.reading.smoke.toFixed(4)}</li>
          <li>Temperature: {sensor.reading.temp.toFixed(1)} °C</li>
          <li>Humidity: {sensor.reading.humidity.toFixed(0)}%</li>
        </ul>
      )}

      <div className="score-row">
        <div>
          <span className="score-label">Air quality score</span>
          <span className="score-value">{sensor.air_quality_score?.toFixed(0) ?? "–"}</span>
        </div>
        <div>
          <span className="score-label">Comfort index</span>
          <span className="score-value">{sensor.comfort_index?.toFixed(0) ?? "–"}</span>
        </div>
      </div>

      {history && windows.length > 0 && (
        <>
          <p>
            Chronic exposure (last 24h):{" "}
            {history.chronic_exposure_ratio !== null
              ? `${Math.round(history.chronic_exposure_ratio * 100)}%`
              : "n/a"}
            {history.trend ? ` · trend: ${history.trend}` : ""}
          </p>
          <EChartWrapper
            height={180}
            option={{
              xAxis: { type: "category", data: windows.map((w) => (w.window_start ?? "").slice(11, 16)) },
              yAxis: { type: "value", name: "CO (avg)" },
              tooltip: { trigger: "axis" },
              series: [{ type: "line", data: windows.map((w) => w.co_avg), smooth: true }],
            }}
          />
        </>
      )}
    </div>
  );
}
