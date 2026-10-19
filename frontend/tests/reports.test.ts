// Unit tests for the environmental officer's reports (D55, UC-15-UC-18).
// Same runner and rules as tutorial.test.ts: Node's built-in test runner, no
// test dependency (NFR-10), pure modules imported with explicit .ts paths.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  addDays,
  daysBetweenInclusive,
  fmtChange,
  fmtHourWindow,
  fmtLocal,
  fmtMonth,
  fmtValue,
  inquiryHeadline,
  monthlyHeadline,
} from "../src/reports/reportFormat.ts";
import { CHARACTER_TEXT, HEATMAP_CAPTION, PERSONA, PRINT_HINT, REPORTS } from "../src/reports/reportText.ts";
import { TOURS } from "../src/tutorial/tourContent.ts";
import type { InquiryReport, MetricSummary, MonthlyReport, RankingEntry } from "../src/types.ts";

const INTERNAL = /\b(D\d{1,3}|UC-\d+|FR-[A-Z]+\d*|NFR-\d+)\b|REQUIREMENTS\.md/;

const LABELS = { co: "CO", lpg: "LPG", smoke: "Smoke", temp: "Temperature", humidity: "Humidity" } as const;
const UNITS = { co: "ppm-eq", lpg: "ppm-eq", smoke: "ppm-eq", temp: "°C", humidity: "%" } as const;

function summary(over: Partial<MetricSummary> = {}): MetricSummary {
  return {
    hours_with_data: 0, out_of_range_hours: 0, over_limit_hours: 0, out_of_range_share: null,
    average: null, peak: null, peak_at: null, ...over,
  };
}

function ranking(name: string, over: Partial<RankingEntry> = {}): RankingEntry {
  return {
    device_id: name, name, area: "", hours_with_data: 720, out_of_range_hours: 0, over_limit_hours: 0,
    change_vs_previous: null, change_vs_year_ago: null, ...over,
  };
}

function monthly(rank: RankingEntry[]): MonthlyReport {
  return {
    month: "2026-09", previous_month: "2026-08", year_ago_month: "2025-09",
    period: { start: "", end: "" }, available_from: "2024-08", locations: [], ranking: rank, episodes: [],
    units: UNITS, labels: LABELS, caveats: [],
  };
}

// --------------------------------------------------------------- content ---

test("there are exactly the four agreed reports, each phrased as the officer's question", () => {
  assert.deepEqual(REPORTS.map((r) => r.kind), ["monthly", "inquiry", "factsheet", "extract"]);
  for (const r of REPORTS) {
    assert.ok(r.question.endsWith("?"), `${r.kind} question`);
    assert.ok(r.title && r.description && r.formats, `${r.kind} text missing`);
  }
});

test("report text never cites internal codes", () => {
  const texts = [
    PERSONA.role, PERSONA.office, HEATMAP_CAPTION, PRINT_HINT, ...Object.values(CHARACTER_TEXT),
    ...REPORTS.flatMap((r) => [r.title, r.question, r.description, r.formats]),
  ];
  for (const t of texts) assert.doesNotMatch(t, INTERNAL, t);
});

test("the planner tour introduces the officer and the reports", () => {
  const planner = TOURS.planner;
  assert.match(planner[0].body.en, /environmental officer/);
  const reports = planner.find((s) => s.id === "planner-reports")!;
  assert.equal(reports.target, "planner-tab-reports");
  assert.equal(reports.bullets!.en.length, REPORTS.length);
});

// ------------------------------------------------------------ formatting ---

test("values are formatted per metric", () => {
  assert.equal(fmtValue(0.004512, "co"), "0.0045");
  assert.equal(fmtValue(21.26, "temp"), "21.3");
  assert.equal(fmtValue(55.4, "humidity"), "55");
  assert.equal(fmtValue(null, "co"), "–");
});

test("dates, months, changes and hour windows read naturally", () => {
  assert.equal(fmtMonth("2026-09"), "September 2026");
  assert.equal(fmtLocal("2026-09-10T13:00"), "10 Sep 2026, 13:00");
  assert.equal(fmtLocal("2026-09-10"), "10 Sep 2026");
  assert.equal(fmtChange(3), "+3");
  assert.equal(fmtChange(-2), "−2");
  assert.equal(fmtChange(0), "±0");
  assert.equal(fmtChange(null), "–");
  assert.equal(fmtHourWindow(22, 6), "22:00–06:00");
  assert.equal(fmtHourWindow(5, 5), "the whole day");
});

test("day arithmetic crosses months and years", () => {
  assert.equal(addDays("2026-03-01", -1), "2026-02-28");
  assert.equal(addDays("2025-12-31", 1), "2026-01-01");
  assert.equal(daysBetweenInclusive("2026-09-01", "2026-09-30"), 30);
  assert.equal(daysBetweenInclusive("2026-09-02", "2026-09-01"), 0);
});

// ------------------------------------------------------------- headlines ---

test("the monthly headline names the location most often outside its own range, and the change", () => {
  const lines = monthlyHeadline(monthly([
    ranking("Kaiserstrasse", { out_of_range_hours: 12, change_vs_previous: 4, over_limit_hours: 2 }),
    ranking("Baccum"),
  ]));
  assert.equal(lines[0], "In September 2026, Kaiserstrasse was outside its own normal range most often: 12 hours, 4 more than in August 2026.");
  assert.equal(lines[1], "2 hours were over a safety limit across all locations.");
  assert.equal(lines[2], "Baccum stayed within the normal range all month.");
});

test("the monthly headline handles a quiet month and missing data", () => {
  const lines = monthlyHeadline(monthly([ranking("Baccum"), ranking("Emsbruecke", { hours_with_data: 0 })]));
  assert.equal(lines[0], "In September 2026 no location had an hour outside its normal range.");
  assert.ok(lines.includes("No data for Emsbruecke in this month."));
  assert.deepEqual(monthlyHeadline(monthly([ranking("Baccum", { hours_with_data: 0 })])), ["There is no stored data for September 2026."]);
});

test("the inquiry headline compares the hours in question with the rest of the day", () => {
  const report = {
    hour_from: 22, hour_to: 6, labels: LABELS, units: UNITS,
    metrics: {
      co: {
        inside: summary({ hours_with_data: 240, out_of_range_hours: 16, average: 0.006 }),
        outside: summary({ hours_with_data: 480, out_of_range_hours: 3, average: 0.005 }),
        profile: [],
      },
    },
  } as unknown as InquiryReport;
  const lines = inquiryHeadline(report, "co");
  assert.equal(lines[0], "Between 22:00 and 06:00, CO averaged 0.0060 ppm-eq — 20 % higher than the rest of the day (0.0050 ppm-eq).");
  assert.equal(lines[1], "16 of 240 hours in that window were outside the normal range, against 3 of 480 in the rest of the day.");
  for (const line of lines) assert.doesNotMatch(line, INTERNAL);
});
