import { useState } from "react";
import { extractXlsxUrl } from "../api";
import type { ReportLocation, ReportMetric } from "../types";
import ReportSheet from "./ReportSheet";
import { METRIC_ORDER, addDays, daysBetweenInclusive, todayLocal } from "./reportFormat";
import { MAX_EXTRACT_DAYS } from "./reportText";

const LABELS: Record<ReportMetric, string> = { co: "CO", lpg: "LPG", smoke: "Smoke", temp: "Temperature", humidity: "Humidity" };

export default function DataExtract({ locations }: { locations: ReportLocation[] }) {
  const today = todayLocal();
  const [deviceId, setDeviceId] = useState("all");
  const [start, setStart] = useState(addDays(today, -91));
  const [end, setEnd] = useState(today);
  const [metrics, setMetrics] = useState<ReportMetric[]>([...METRIC_ORDER]);

  const days = daysBetweenInclusive(start, end);
  const count = deviceId === "all" ? locations.length : 1;
  const invalid =
    days < 1
      ? "The end date is before the start date."
      : days > MAX_EXTRACT_DAYS
        ? `Choose a period of at most ${MAX_EXTRACT_DAYS} days.`
        : metrics.length === 0
          ? "Choose at least one measurement."
          : null;

  const toggle = (m: ReportMetric) =>
    setMetrics((prev) => (prev.includes(m) ? prev.filter((x) => x !== m) : METRIC_ORDER.filter((x) => x === m || prev.includes(x))));

  return (
    <ReportSheet title="Data extract" subtitle="Hourly values as an Excel workbook, for colleagues and external experts." printable={false}>
      <div className="report-controls">
        <label>
          Location
          <select value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
            <option value="all">All locations</option>
            {locations.map((l) => (
              <option key={l.device_id} value={l.device_id}>
                {l.name} — {l.area}
              </option>
            ))}
          </select>
        </label>
        <label>
          From
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </label>
        <label>
          To
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </label>
      </div>
      <div className="report-controls">
        {METRIC_ORDER.map((m) => (
          <label key={m} className="report-check">
            <input type="checkbox" checked={metrics.includes(m)} onChange={() => toggle(m)} />
            {LABELS[m]}
          </label>
        ))}
      </div>
      <p className="waiting">
        {invalid ??
          `About ${(days * 24 * count).toLocaleString("en-GB")} hourly rows: ${days} days × 24 hours × ${count} location${count === 1 ? "" : "s"}.`}
      </p>
      <h4 className="section-title">The workbook contains</h4>
      <ul className="report-legend">
        <li>Notes — the period, the locations, units, and what the numbers mean and where they come from.</li>
        <li>Hourly data — one row per location and hour: average, lowest and highest value of each chosen measurement.</li>
        <li>Out-of-range hours — every hour outside the normal range, with the range and safety limit that applied.</li>
      </ul>
      <p className="report-muted">A year of all locations is a large workbook and can take up to a minute to prepare.</p>
      {invalid ? (
        <button className="btn btn-accent" disabled>
          Download Excel
        </button>
      ) : (
        <a className="btn btn-accent" href={extractXlsxUrl({ deviceId, start, end, metrics })} download>
          Download Excel
        </a>
      )}
    </ReportSheet>
  );
}
