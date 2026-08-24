import { useState } from "react";
import type { MetricRange, SensorEntry, TimelineGranularity, TimelinePoint, TimelineResponse } from "../types";
import { GRANULARITIES } from "./SensorTimeline";

const SCOPE_UNIT_PLURAL: Record<TimelineGranularity, string> = {
  "1m": "minutes",
  "1h": "hours",
  "1d": "days",
  "1w": "weeks",
  "1mo": "months",
};

function fmt(v: number): string {
  return Math.abs(v) < 1 ? v.toFixed(4) : v.toFixed(1);
}

interface Breach {
  value: number;
  kind: "ceiling" | "above" | "below";
  detail: string;
}

// A window is flagged "unhealthy" from Spark's per-event anomaly count, not
// from the window's own average - so the average alone can look deceptively
// normal even in a flagged window (one spike within it is enough). Checking
// the window's min/max against the sensor's actual thresholds finds the
// real reading that explains the flag, and picks whichever of the two
// deviates furthest so the log always shows the worst moment, not just
// "some" moment.
function worstBreach(point: TimelinePoint, range: MetricRange): Breach | null {
  const candidates = [point.max, point.min].filter((v): v is number => v !== null);

  let best: Breach | null = null;
  let bestDelta = -Infinity;

  for (const v of candidates) {
    if (range.ceiling !== null && v > range.ceiling) {
      const delta = v - range.ceiling;
      if (delta > bestDelta) {
        bestDelta = delta;
        const pct = Math.round((delta / range.ceiling) * 100);
        best = { value: v, kind: "ceiling", detail: `${pct}% over the safety limit (${fmt(range.ceiling)} ${range.unit})` };
      }
    }
    if (v > range.normal_max) {
      const delta = v - range.normal_max;
      if (delta > bestDelta) {
        bestDelta = delta;
        best = { value: v, kind: "above", detail: `above the normal range (≤ ${fmt(range.normal_max)} ${range.unit})` };
      }
    }
    if (v < range.normal_min) {
      const delta = range.normal_min - v;
      if (delta > bestDelta) {
        bestDelta = delta;
        best = { value: v, kind: "below", detail: `below the normal range (≥ ${fmt(range.normal_min)} ${range.unit})` };
      }
    }
  }
  return best;
}

export default function BoundaryLog({
  sensor,
  metric,
  metricLabel,
  data,
}: {
  sensor: SensorEntry;
  metric: string;
  metricLabel: string;
  data: Record<TimelineGranularity, TimelineResponse | null>;
}) {
  const [scope, setScope] = useState<TimelineGranularity>("1d");

  const range = sensor.metric_ranges[metric];
  const response = data[scope];
  const scopeMeta = GRANULARITIES.find((g) => g.key === scope)!;
  const points = response?.points ?? [];

  const entries: { point: TimelinePoint; breach: Breach }[] = [];
  if (range) {
    for (const p of points) {
      if (!p.unhealthy) continue;
      const breach = worstBreach(p, range);
      if (breach) entries.push({ point: p, breach });
    }
    entries.reverse(); // newest first - a log reads most-recent-first
  }

  return (
    <div className="boundary-log">
      <div className="timeline-heading">
        <h3>Out-of-range log — {metricLabel}</h3>
        <div className="metric-tabs">
          {GRANULARITIES.map((g) => (
            <button
              key={g.key}
              className={`metric-tab ${scope === g.key ? "metric-tab-active" : ""}`}
              onClick={() => setScope(g.key)}
            >
              {g.label}
            </button>
          ))}
        </div>
      </div>
      <p className="waiting timeline-caption">
        Every reading is checked against the acceptable range; this log lists only the periods that fell outside it.
      </p>

      {!response || !range ? (
        <p className="waiting">Loading…</p>
      ) : points.length === 0 ? (
        <p className="waiting">No data yet for this period.</p>
      ) : (
        <>
          <p className="waiting boundary-log-summary">
            {entries.length === 0
              ? `No out-of-range ${metricLabel} readings across ${points.length} ${SCOPE_UNIT_PLURAL[scope]}.`
              : `${entries.length} of ${points.length} ${SCOPE_UNIT_PLURAL[scope]} had ${metricLabel} outside the acceptable range.`}
          </p>
          {entries.length > 0 && (
            <ul className="boundary-log-list">
              {entries.map(({ point, breach }) => (
                <li
                  key={point.window_start}
                  className={`boundary-entry boundary-entry-${breach.kind === "ceiling" ? "critical" : "warning"}`}
                >
                  <span className="boundary-entry-time">{scopeMeta.formatLabel(point.window_start)}</span>
                  <span className={`status-badge status-${breach.kind === "ceiling" ? "critical" : "warning"}`}>
                    {breach.kind === "ceiling" ? "over limit" : breach.kind === "above" ? "above normal" : "below normal"}
                  </span>
                  <span className="boundary-entry-value">
                    {fmt(breach.value)} {range.unit}
                  </span>
                  <span className="boundary-entry-detail">{breach.detail}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
