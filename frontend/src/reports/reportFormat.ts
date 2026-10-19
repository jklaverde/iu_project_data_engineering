// Formatting and plain-language summaries for the reports (D55).
// Pure functions, no imports beyond types: unit-tested by frontend/tests.
// Times without a zone are local (Europe/Berlin) as the backend sends them.

import type { InquiryReport, MonthlyReport, ReportMetric } from "../types";

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export const METRIC_ORDER: ReportMetric[] = ["co", "lpg", "smoke", "temp", "humidity"];
export const POLLUTANTS: ReportMetric[] = ["co", "lpg", "smoke"];

export function fmtValue(v: number | null | undefined, metric: ReportMetric): string {
  if (v === null || v === undefined) return "–";
  if (metric === "temp") return v.toFixed(1);
  if (metric === "humidity") return v.toFixed(0);
  return v.toFixed(4);
}

export function fmtMonth(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  return `${MONTHS[m - 1]} ${y}`;
}

export function fmtShortMonth(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  return `${MONTHS[m - 1].slice(0, 3)} ${String(y).slice(2)}`;
}

export function fmtLocal(iso: string | null | undefined): string {
  if (!iso) return "–";
  const [d, t] = iso.split("T");
  const [y, m, day] = d.split("-").map(Number);
  return `${day} ${MONTHS[m - 1].slice(0, 3)} ${y}${t ? `, ${t.slice(0, 5)}` : ""}`;
}

export function fmtDay(iso: string): string {
  return fmtLocal(iso.slice(0, 10));
}

export function fmtHour(h: number | null | undefined): string {
  return h === null || h === undefined ? "–" : `${String(h).padStart(2, "0")}:00`;
}

export function fmtHourWindow(from: number, to: number): string {
  return from === to ? "the whole day" : `${fmtHour(from)}–${fmtHour(to)}`;
}

export function fmtChange(n: number | null | undefined): string {
  if (n === null || n === undefined) return "–";
  if (n === 0) return "±0";
  return n > 0 ? `+${n}` : `−${Math.abs(n)}`;
}

export function fmtShare(share: number | null | undefined): string {
  return share === null || share === undefined ? "–" : `${Math.round(share * 100)} %`;
}

export function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

export function todayLocal(now: Date = new Date()): string {
  // The browser's own local date - good enough for a default in a form.
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function addDays(day: string, n: number): string {
  const [y, m, d] = day.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d + n));
  return date.toISOString().slice(0, 10);
}

export function daysBetweenInclusive(start: string, end: string): number {
  const toUtc = (s: string) => {
    const [y, m, d] = s.split("-").map(Number);
    return Date.UTC(y, m - 1, d);
  };
  return Math.round((toUtc(end) - toUtc(start)) / 86_400_000) + 1;
}

// ------------------------------------------------- plain-language summaries ---

export function monthlyHeadline(report: MonthlyReport): string[] {
  const month = fmtMonth(report.month);
  const previous = fmtMonth(report.previous_month);
  const withData = report.ranking.filter((r) => r.hours_with_data > 0);
  if (withData.length === 0) return [`There is no stored data for ${month}.`];

  const lines: string[] = [];
  const top = withData[0];
  if (top.out_of_range_hours === 0) {
    lines.push(`In ${month} no location had an hour outside its normal range.`);
  } else {
    let change = "";
    if (top.change_vs_previous !== null && top.change_vs_previous !== 0) {
      change = `, ${Math.abs(top.change_vs_previous)} ${top.change_vs_previous > 0 ? "more" : "fewer"} than in ${previous}`;
    } else if (top.change_vs_previous === 0) {
      change = `, the same as in ${previous}`;
    }
    // "Most often outside its own normal range", never "most polluted": each
    // location is judged against its own baseline (seen live, D55: the quiet
    // residential site out-ranked the main-road site on humidity).
    lines.push(
      `In ${month}, ${top.name} was outside its own normal range most often: ${plural(top.out_of_range_hours, "hour", "hours")}${change}.`,
    );
  }

  const over = withData.reduce((sum, r) => sum + r.over_limit_hours, 0);
  lines.push(
    over === 0
      ? "No hour was over a safety limit at any location."
      : `${plural(over, "hour was", "hours were")} over a safety limit across all locations.`,
  );

  const quiet = withData.filter((r) => r.out_of_range_hours === 0).map((r) => r.name);
  if (quiet.length > 0 && quiet.length < withData.length) {
    lines.push(`${quiet.join(" and ")} stayed within the normal range all month.`);
  }
  const missing = report.ranking.filter((r) => r.hours_with_data === 0).map((r) => r.name);
  if (missing.length > 0) lines.push(`No data for ${missing.join(" and ")} in this month.`);
  return lines;
}

export function inquiryHeadline(report: InquiryReport, metric: ReportMetric): string[] {
  const m = report.metrics[metric];
  const label = report.labels[metric];
  const unit = report.units[metric];
  const window = fmtHourWindow(report.hour_from, report.hour_to);
  if (m.inside.hours_with_data === 0) return [`There is no stored data for ${window} in this period.`];

  const lines: string[] = [];
  const inAvg = m.inside.average;
  const outAvg = m.outside.average;
  if (inAvg !== null && outAvg !== null && outAvg !== 0 && report.hour_from !== report.hour_to) {
    const pct = Math.round(((inAvg - outAvg) / Math.abs(outAvg)) * 100);
    const comparison =
      Math.abs(pct) < 5 ? "about the same as" : `${Math.abs(pct)} % ${pct > 0 ? "higher" : "lower"} than`;
    lines.push(
      `Between ${fmtHour(report.hour_from)} and ${fmtHour(report.hour_to)}, ${label} averaged ${fmtValue(inAvg, metric)} ${unit} — ${comparison} the rest of the day (${fmtValue(outAvg, metric)} ${unit}).`,
    );
  } else if (inAvg !== null) {
    lines.push(`${label} averaged ${fmtValue(inAvg, metric)} ${unit} over the period.`);
  }
  const inShare = `${m.inside.out_of_range_hours} of ${m.inside.hours_with_data}`;
  if (report.hour_from !== report.hour_to && m.outside.hours_with_data > 0) {
    lines.push(
      `${inShare} hours in that window were outside the normal range, against ${m.outside.out_of_range_hours} of ${m.outside.hours_with_data} in the rest of the day.`,
    );
  } else {
    lines.push(`${inShare} hours were outside the normal range.`);
  }
  if (m.inside.over_limit_hours > 0) {
    lines.push(`${plural(m.inside.over_limit_hours, "hour was", "hours were")} over the safety limit.`);
  }
  return lines;
}
