import type { MetricRange } from "../types";

const METRIC_LABEL: Record<string, string> = {
  co: "CO",
  humidity: "Humidity",
  lpg: "LPG",
  smoke: "Smoke",
  temp: "Temperature",
};

function fmt(v: number): string {
  return Math.abs(v) < 1 ? v.toFixed(4) : v.toFixed(1);
}

export default function MetricGauge({ metric, range }: { metric: string; range: MetricRange }) {
  const domainMin = Math.min(0, range.normal_min - (range.normal_max - range.normal_min) * 0.3);
  const domainMax = Math.max(range.ceiling ?? 0, range.normal_max, range.value) * 1.15 || 1;
  const span = domainMax - domainMin || 1;
  const pct = (v: number) => Math.max(0, Math.min(100, ((v - domainMin) / span) * 100));

  const bandLeft = pct(range.normal_min);
  const bandWidth = Math.max(0, pct(range.normal_max) - bandLeft);
  const valuePct = pct(range.value);
  const ceilingPct = range.ceiling !== null ? pct(range.ceiling) : null;

  return (
    <div className={`gauge gauge-${range.status}`}>
      <div className="gauge-header">
        <span className="gauge-label">{METRIC_LABEL[metric] ?? metric}</span>
        <span className="gauge-value">
          {fmt(range.value)} <span className="gauge-unit">{range.unit}</span>
        </span>
      </div>
      <div className="gauge-track">
        <div className="gauge-band" style={{ left: `${bandLeft}%`, width: `${bandWidth}%` }} />
        {ceilingPct !== null && <div className="gauge-ceiling" style={{ left: `${ceilingPct}%` }} />}
        <div className="gauge-marker" style={{ left: `${valuePct}%` }} />
      </div>
      <div className="gauge-footer">
        <span>
          normal {fmt(range.normal_min)}–{fmt(range.normal_max)} {range.unit}
        </span>
        {range.ceiling !== null && (
          <span className="gauge-limit">
            limit {fmt(range.ceiling)} {range.unit}
          </span>
        )}
      </div>
    </div>
  );
}
