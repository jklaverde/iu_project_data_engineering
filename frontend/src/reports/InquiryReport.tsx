import { useCallback, useState } from "react";
import { fetchInquiryReport } from "../api";
import type { InquiryReport as Report, ReportLocation, ReportMetric } from "../types";
import HourHeatmap from "./HourHeatmap";
import ReportChart, { baseAxis, type ChartPalette } from "./ReportChart";
import ReportSheet from "./ReportSheet";
import {
  METRIC_ORDER,
  addDays,
  daysBetweenInclusive,
  fmtHour,
  fmtHourWindow,
  fmtLocal,
  fmtValue,
  inquiryHeadline,
  todayLocal,
} from "./reportFormat";
import { HEATMAP_CAPTION, MAX_INQUIRY_DAYS } from "./reportText";
import { useReport } from "./useReport";

const HOURS = Array.from({ length: 24 }, (_, h) => h);

interface Query {
  deviceId: string;
  start: string;
  end: string;
  hourFrom: number;
  hourTo: number;
}

function ProfileChart({ report, metric }: { report: Report; metric: ReportMetric }) {
  const build = useCallback(
    (p: ChartPalette) => {
      const { hour_from: from, hour_to: to } = report;
      const areas: [{ xAxis: string }, { xAxis: string }][] = [];
      if (from !== to) {
        const label = (h: number) => fmtHour(h % 24);
        if (from < to) areas.push([{ xAxis: label(from) }, { xAxis: label(to - 1) }]);
        else {
          areas.push([{ xAxis: label(from) }, { xAxis: label(23) }]);
          if (to > 0) areas.push([{ xAxis: label(0) }, { xAxis: label(to - 1) }]);
        }
      }
      return {
        animation: false,
        color: [p.series[0]],
        grid: { left: 56, right: 12, top: 16, bottom: 28 },
        tooltip: { trigger: "axis" as const },
        xAxis: { type: "category" as const, data: HOURS.map(fmtHour), boundaryGap: false, ...baseAxis(p) },
        yAxis: { type: "value" as const, scale: true, name: report.units[metric], nameTextStyle: { color: p.text, fontSize: 10 }, ...baseAxis(p) },
        series: [
          {
            name: report.labels[metric],
            type: "line" as const,
            smooth: true,
            showSymbol: false,
            data: report.metrics[metric].profile,
            markArea: { silent: true, itemStyle: { color: p.band }, data: areas },
          },
        ],
      };
    },
    [report, metric],
  );
  return <ReportChart build={build} height={220} />;
}

export default function InquiryReport({ locations }: { locations: ReportLocation[] }) {
  const today = todayLocal();
  const [draft, setDraft] = useState<Query>({
    deviceId: locations[0]?.device_id ?? "",
    start: addDays(today, -30),
    end: today,
    hourFrom: 22,
    hourTo: 6,
  });
  const [query, setQuery] = useState<Query | null>(null);
  const [metric, setMetric] = useState<ReportMetric>("co");
  const { data: report, loading, error } = useReport(query ? () => fetchInquiryReport(query) : null, [query]);

  const days = daysBetweenInclusive(draft.start, draft.end);
  const invalid =
    !draft.deviceId
      ? "Choose a location."
      : days < 1
        ? "The end date is before the start date."
        : days > MAX_INQUIRY_DAYS
          ? `Choose a period of at most ${MAX_INQUIRY_DAYS} days.`
          : null;

  return (
    <>
      <div className="report-controls no-print">
        <label>
          Location
          <select value={draft.deviceId} onChange={(e) => setDraft({ ...draft, deviceId: e.target.value })}>
            {locations.map((l) => (
              <option key={l.device_id} value={l.device_id}>
                {l.name} — {l.area}
              </option>
            ))}
          </select>
        </label>
        <label>
          From
          <input type="date" value={draft.start} onChange={(e) => setDraft({ ...draft, start: e.target.value })} />
        </label>
        <label>
          To
          <input type="date" value={draft.end} onChange={(e) => setDraft({ ...draft, end: e.target.value })} />
        </label>
        <label>
          Hours from
          <select value={draft.hourFrom} onChange={(e) => setDraft({ ...draft, hourFrom: Number(e.target.value) })}>
            {HOURS.map((h) => (
              <option key={h} value={h}>
                {fmtHour(h)}
              </option>
            ))}
          </select>
        </label>
        <label>
          to
          <select value={draft.hourTo} onChange={(e) => setDraft({ ...draft, hourTo: Number(e.target.value) })}>
            {HOURS.map((h) => (
              <option key={h} value={h}>
                {fmtHour(h)}
              </option>
            ))}
          </select>
        </label>
        <button className="btn btn-accent" disabled={!!invalid} onClick={() => setQuery({ ...draft })}>
          Create response
        </button>
        {loading && <span className="waiting">Loading…</span>}
      </div>
      {invalid && <p className="waiting no-print">{invalid}</p>}
      {error && <p className="step-error">{error}</p>}
      {!report && !loading && !error && (
        <p className="waiting">
          Pick the location nearest to the resident, the period they mean and the hours they describe, then create
          the response.
        </p>
      )}

      {report && (
        <ReportSheet
          title={`Response to a resident's inquiry — ${report.location.name}`}
          subtitle={`${report.location.area}. ${fmtLocal(report.period.start_local.slice(0, 10))} to ${fmtLocal(addDays(report.period.end_local.slice(0, 10), -1))}, hours ${fmtHourWindow(report.hour_from, report.hour_to)} (local time).`}
          caveats={report.caveats}
        >
          <div className="metric-tabs no-print report-metric-tabs">
            {METRIC_ORDER.map((m) => (
              <button
                key={m}
                className={`metric-tab ${metric === m ? "metric-tab-active" : ""}`}
                onClick={() => setMetric(m)}
              >
                {report.labels[m]}
              </button>
            ))}
          </div>
          <div className="report-headline">
            {inquiryHeadline(report, metric).map((line) => (
              <p key={line}>{line}</p>
            ))}
          </div>

          <h4 className="section-title">All measurements: the hours in question vs the rest of the day</h4>
          <table className="report-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Average in window</th>
                <th>Rest of day</th>
                <th>Out of range in window</th>
                <th>Rest of day</th>
                <th>Peak in window</th>
              </tr>
            </thead>
            <tbody>
              {METRIC_ORDER.map((m) => {
                const s = report.metrics[m];
                return (
                  <tr key={m} className={m === metric ? "report-row-focus" : undefined}>
                    <td>
                      {report.labels[m]} <span className="report-muted">{report.units[m]}</span>
                    </td>
                    <td>{fmtValue(s.inside.average, m)}</td>
                    <td>{fmtValue(s.outside.average, m)}</td>
                    <td>
                      {s.inside.out_of_range_hours} / {s.inside.hours_with_data} h
                    </td>
                    <td>
                      {s.outside.out_of_range_hours} / {s.outside.hours_with_data} h
                    </td>
                    <td>
                      {fmtValue(s.inside.peak, m)}
                      {s.inside.peak_at && <span className="report-muted"> · {fmtLocal(s.inside.peak_at)}</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <h4 className="section-title">
            {report.labels[metric]} by hour of the day over the period (shaded: the hours in question)
          </h4>
          <ProfileChart report={report} metric={metric} />

          <h4 className="section-title">Does it recur? {report.labels[metric]} by month and hour, last 12 months</h4>
          <p className="report-muted report-caption">{HEATMAP_CAPTION}</p>
          <HourHeatmap heatmap={report.heatmaps[metric]} label={report.labels[metric]} unit={report.units[metric]} />

          <h4 className="section-title">Episodes outside the normal range within those hours</h4>
          {report.episodes.length === 0 ? (
            <p className="waiting">None in this period.</p>
          ) : (
            <table className="report-table">
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>From</th>
                  <th>To</th>
                  <th>Hours</th>
                  <th>Peak</th>
                </tr>
              </thead>
              <tbody>
                {report.episodes
                  .slice()
                  .reverse()
                  .slice(0, 15)
                  .map((e) => (
                    <tr key={`${e.metric}-${e.start}`}>
                      <td>{report.labels[e.metric]}</td>
                      <td>{fmtLocal(e.start)}</td>
                      <td>{fmtLocal(e.end)}</td>
                      <td>{e.hours}</td>
                      <td>
                        {fmtValue(e.peak, e.metric)} {report.units[e.metric]}
                        {e.over_limit && <span className="status-badge status-critical report-badge">over limit</span>}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          )}
          {report.episodes.length > 15 && (
            <p className="report-muted">The 15 most recent of {report.episodes.length} episodes are listed.</p>
          )}
        </ReportSheet>
      )}
    </>
  );
}
