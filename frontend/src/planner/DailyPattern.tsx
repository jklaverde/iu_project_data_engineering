import { useEffect, useState } from "react";
import { fetchDailyPattern } from "../api";
import HourHeatmap from "../reports/HourHeatmap";
import { fmtHour } from "../reports/reportFormat";
import { HEATMAP_CAPTION } from "../reports/reportText";
import type { DailyPattern as Pattern, SensorEntry } from "../types";

// Daily rhythm of the selected metric (D55, FR-O7): when in the day it is
// worst, and whether that holds in every month.
export default function DailyPattern({ sensor, metric, metricLabel }: { sensor: SensorEntry; metric: string; metricLabel: string }) {
  const [pattern, setPattern] = useState<Pattern | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setPattern(null);
    setFailed(false);
    fetchDailyPattern(sensor.device_id, metric)
      .then((res) => !cancelled && setPattern(res))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [sensor.device_id, metric]);

  return (
    <div className="daily-pattern" data-tour="planner-pattern">
      <div className="timeline-heading">
        <h3>Daily rhythm — {metricLabel}</h3>
        {pattern?.peak_hour !== null && pattern?.peak_hour !== undefined && (
          <span className="trend-pill">typically highest around {fmtHour(pattern.peak_hour)}</span>
        )}
      </div>
      <p className="waiting timeline-caption">{HEATMAP_CAPTION}</p>
      {failed ? (
        <p className="waiting">The daily rhythm could not be loaded.</p>
      ) : !pattern ? (
        <p className="waiting">Loading…</p>
      ) : (
        <HourHeatmap heatmap={pattern} label={pattern.label} unit={pattern.unit} height={320} />
      )}
    </div>
  );
}
