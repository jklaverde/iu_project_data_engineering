// Text for the environmental officer's Reports tab (D55, UC-15-UC-18).
//
// Pure data, no imports: unit-tested by frontend/tests (node --test) for the
// same rule as the tour - no internal codes (decision/requirement ids) in
// anything a user reads or prints. The caveats printed on every report come
// from the backend (reports.CAVEATS), so a PDF and an Excel file say the same.

export type ReportKind = "monthly" | "inquiry" | "factsheet" | "extract";

export const PERSONA = {
  role: "Environmental officer",
  office: "Umweltamt Lingen (Ems)",
};

export interface ReportInfo {
  kind: ReportKind;
  title: string;
  question: string;
  description: string;
  formats: string;
}

export const REPORTS: ReportInfo[] = [
  {
    kind: "monthly",
    title: "Monthly environment report",
    question: "How did last month go, and where should attention go?",
    description:
      "Every location and metric for one month: hours outside the normal range, hours over the safety limit, " +
      "averages and peaks, compared with the previous month and the same month a year earlier, the locations " +
      "ranked by how often they left their own normal range, and the longest episodes. Written for the " +
      "environment committee.",
    formats: "On screen · PDF · Excel",
  },
  {
    kind: "inquiry",
    title: "Response to a resident's inquiry",
    question: "What do I tell a resident who complains?",
    description:
      "One location, a period and the hours the resident means (for example 22:00–06:00): what was measured in " +
      "those hours compared with the rest of the day, how often it was outside the normal range, and whether it " +
      "is a pattern that recurs month after month.",
    formats: "On screen · PDF",
  },
  {
    kind: "factsheet",
    title: "Location fact sheet",
    question: "What is this location like?",
    description:
      "A one-page profile of a location for a colleague or a meeting: current status, the character of each " +
      "measurement over the last 30 days, the typical worst hour, and its daily rhythm over the year.",
    formats: "On screen · PDF",
  },
  {
    kind: "extract",
    title: "Data extract",
    question: "Can I hand the data to someone else?",
    description:
      "Hourly values for one or all locations and any period up to a year, with the hours outside the normal " +
      "range and a notes sheet explaining units, ranges and where the data comes from.",
    formats: "Excel",
  },
];

export const CHARACTER_TEXT: Record<"steady" | "variable" | "spiky", string> = {
  steady: "Steady — values stay close to their average; a lasting change would stand out.",
  variable: "Variable — values move noticeably from hour to hour.",
  spiky: "Spiky — mostly calm with sharp bursts; look at the peaks, not the average.",
};

export const HEATMAP_CAPTION =
  "Average value by month (rows) and hour of the day (columns, local time); the stronger the colour, the higher " +
  "the value. A column that stands out in every row is a daily pattern that recurs all year; a row that differs " +
  "from the others is a seasonal effect.";

export const PRINT_HINT = "Opens the print dialog — choose “Save as PDF” as the printer to get a PDF file.";

export const MAX_INQUIRY_DAYS = 92;
export const MAX_EXTRACT_DAYS = 366;
