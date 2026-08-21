import { useEffect, useState } from "react";
import { fetchSensorHistory } from "../api";
import type { SensorEntry, SensorHistoryResponse } from "../types";
import MetricGauge from "./MetricGauge";

const STATUS_LABEL: Record<string, string> = {
  ok: "OK",
  warning: "Warning",
  critical: "Critical",
  unknown: "No data yet",
};

const METRIC_ORDER = ["co", "lpg", "smoke", "temp", "humidity"];

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
      <div className="step detail-card">
        <h3>Sensor detail</h3>
        <p className="waiting">Select a sensor on the map to see its readings.</p>
      </div>
    );
  }

  const ranges = METRIC_ORDER.filter((m) => sensor.metric_ranges[m]);

  return (
    <div className="step detail-card">
      <div className="detail-enter" key={sensor.device_id}>
        <div className="detail-heading">
          <div>
            <h3>{sensor.name}</h3>
            <p className="waiting">{sensor.area}</p>
          </div>
          <p className={`status-badge status-${sensor.status.overall}`}>
            {STATUS_LABEL[sensor.status.overall] ?? sensor.status.overall}
            {sensor.status.reason ? ` — ${sensor.status.reason}` : ""}
          </p>
        </div>

        <div className="stat-tiles">
          <div className="stat-tile">
            <span className="score-label">Air quality score</span>
            <span className="score-value">{sensor.air_quality_score?.toFixed(0) ?? "–"}</span>
          </div>
          <div className="stat-tile">
            <span className="score-label">Comfort index</span>
            <span className="score-value">{sensor.comfort_index?.toFixed(0) ?? "–"}</span>
          </div>
          {history && (
            <div className="stat-tile">
              <span className="score-label">Chronic exposure (24h)</span>
              <span className="score-value">
                {history.chronic_exposure_ratio !== null
                  ? `${Math.round(history.chronic_exposure_ratio * 100)}%`
                  : "–"}
              </span>
              {history.trend && <span className={`trend-pill trend-${history.trend}`}>{history.trend}</span>}
            </div>
          )}
        </div>

        {ranges.length > 0 && (
          <>
            <h4 className="section-title">Actual vs. acceptable range</h4>
            <div className="gauge-list">
              {ranges.map((metric) => (
                <MetricGauge key={metric} metric={metric} range={sensor.metric_ranges[metric]} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
