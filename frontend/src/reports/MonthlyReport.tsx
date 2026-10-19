import { useCallback, useState } from "react";
import { fetchMonthlyReport, monthlyReportXlsxUrl } from "../api";
import type { MonthlyReport as Report } from "../types";
import ReportChart, { baseAxis, type ChartPalette } from "./ReportChart";
import ReportSheet from "./ReportSheet";
import {
  METRIC_ORDER,
  POLLUTANTS,
  fmtChange,
  fmtLocal,
  fmtMonth,
  fmtShare,
  fmtValue,
  monthlyHeadline,
} from "./reportFormat";
import { useReport } from "./useReport";

function RankingChart({ report }: { report: Report }) {
  const build = useCallback(
    (p: ChartPalette) => {
      const names = report.ranking.map((r) => r.name);
      const byPeriod = (key: "current" | "previous" | "year_ago") =>
        report.ranking.map((r) => {
          // The comparison months come back as changes; a null change means
          // that month has no data, which is a missing bar, not a zero.
          if (key === "current") return r.out_of_range_hours;
          const change = key === "previous" ? r.change_vs_previous : r.change_vs_year_ago;
          return change === null ? null : r.out_of_range_hours - change;
        });
      return {
        animation: false,
        color: [p.series[0], p.series[1], p.axis],
        legend: { top: 0, textStyle: { color: p.text, fontSize: 11 } },
        grid: { left: 44, right: 12, top: 30, bottom: 28 },
        tooltip: { trigger: "axis" as const },
        xAxis: { type: "category" as const, data: names, ...baseAxis(p) },
        yAxis: { type: "value" as const, name: "hours", nameTextStyle: { color: p.text, fontSize: 10 }, minInterval: 1, ...baseAxis(p) },
        series: [
          { name: fmtMonth(report.month), type: "bar" as const, data: byPeriod("current") },
          { name: fmtMonth(report.previous_month), type: "bar" as const, data: byPeriod("previous") },
          { name: fmtMonth(report.year_ago_month), type: "bar" as const, data: byPeriod("year_ago") },
        ],
      };
    },
    [report],
  );
  return <ReportChart build={build} height={240} />;
}

export default function MonthlyReport() {
  const [month, setMonth] = useState<string | null>(null);
  const { data: report, loading, error } = useReport(() => fetchMonthlyReport(month ?? undefined), [month]);

  return (
    <>
      <div className="report-controls no-print">
        <label>
          Month
          <input
            type="month"
            value={month ?? report?.month ?? ""}
            min={report?.available_from ?? undefined}
            onChange={(e) => e.target.value && setMonth(e.target.value)}
          />
        </label>
        {loading && <span className="waiting">Loading…</span>}
      </div>
      {error && <p className="step-error">{error}</p>}

      {report && (
        <ReportSheet
          title={`Monthly environment report — ${fmtMonth(report.month)}`}
          subtitle={`Compared with ${fmtMonth(report.previous_month)} and ${fmtMonth(report.year_ago_month)}. All times local (Europe/Berlin).`}
          caveats={report.caveats}
          xlsxUrl={monthlyReportXlsxUrl(report.month)}
        >
          <div className="report-headline">
            {monthlyHeadline(report).map((line) => (
              <p key={line}>{line}</p>
            ))}
          </div>

          <h4 className="section-title">Locations ranked by hours outside their own normal range</h4>
          <RankingChart report={report} />
          <table className="report-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Location</th>
                <th>Hours with data</th>
                <th>Hours out of range</th>
                <th>vs {fmtMonth(report.previous_month)}</th>
                <th>vs {fmtMonth(report.year_ago_month)}</th>
                <th>Over a safety limit</th>
              </tr>
            </thead>
            <tbody>
              {report.ranking.map((r, i) => (
                <tr key={r.device_id}>
                  <td>{i + 1}</td>
                  <td>
                    <strong>{r.name}</strong>
                    <span className="report-muted"> · {r.area}</span>
                  </td>
                  <td>{r.hours_with_data}</td>
                  <td>{r.out_of_range_hours}</td>
                  <td>{fmtChange(r.change_vs_previous)}</td>
                  <td>{fmtChange(r.change_vs_year_ago)}</td>
                  <td>{r.over_limit_hours}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {report.locations.map((loc) => (
            <div key={loc.device_id} className="report-block">
              <h4 className="section-title">
                {loc.name} · {loc.area}
              </h4>
              <table className="report-table">
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Average</th>
                    <th>Peak</th>
                    <th>Hours out of range</th>
                    <th>Share</th>
                    <th>vs prev. month</th>
                    <th>vs a year ago</th>
                    <th>Over limit</th>
                  </tr>
                </thead>
                <tbody>
                  {METRIC_ORDER.map((metric) => {
                    const m = loc.metrics[metric];
                    const cur = m.current;
                    const delta = (k: "previous" | "year_ago") =>
                      m[k].hours_with_data ? fmtChange(cur.out_of_range_hours - m[k].out_of_range_hours) : "–";
                    return (
                      <tr key={metric}>
                        <td>
                          {report.labels[metric]} <span className="report-muted">{report.units[metric]}</span>
                        </td>
                        <td>{fmtValue(cur.average, metric)}</td>
                        <td>
                          {fmtValue(cur.peak, metric)}
                          {cur.peak_at && <span className="report-muted"> · {fmtLocal(cur.peak_at)}</span>}
                        </td>
                        <td>{cur.out_of_range_hours}</td>
                        <td>{fmtShare(cur.out_of_range_share)}</td>
                        <td>{delta("previous")}</td>
                        <td>{delta("year_ago")}</td>
                        <td>{POLLUTANTS.includes(metric) ? cur.over_limit_hours : "–"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ))}

          <h4 className="section-title">Longest episodes outside the normal range</h4>
          {report.episodes.length === 0 ? (
            <p className="waiting">None this month.</p>
          ) : (
            <table className="report-table">
              <thead>
                <tr>
                  <th>Location</th>
                  <th>Metric</th>
                  <th>From</th>
                  <th>To</th>
                  <th>Hours</th>
                  <th>Peak</th>
                </tr>
              </thead>
              <tbody>
                {report.episodes.map((e) => (
                  <tr key={`${e.device_id}-${e.metric}-${e.start}`}>
                    <td>{e.name}</td>
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
        </ReportSheet>
      )}
    </>
  );
}
