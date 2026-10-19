import type { SensorEntry } from "../types";
import DataExtract from "./DataExtract";
import FactSheet from "./FactSheet";
import InquiryReport from "./InquiryReport";
import MonthlyReport from "./MonthlyReport";
import { REPORTS, type ReportKind } from "./reportText";

// The environmental officer's Reports tab (D55, UC-15-UC-18): one card per
// report, each phrased as the question it answers, then the chosen report.
export default function ReportsTab({
  sensors,
  kind,
  onKindChange,
  factSheetDevice,
  onFactSheetDeviceChange,
}: {
  sensors: SensorEntry[];
  kind: ReportKind;
  onKindChange: (kind: ReportKind) => void;
  factSheetDevice: string | null;
  onFactSheetDeviceChange: (id: string) => void;
}) {
  const locations = sensors.map((s) => ({ device_id: s.device_id, name: s.name, area: s.area }));

  return (
    <div className="reports-tab">
      <div className="report-picker no-print" data-tour="planner-report-picker">
        {REPORTS.map((r) => (
          <button
            key={r.kind}
            className={`report-card ${kind === r.kind ? "report-card-active" : ""}`}
            onClick={() => onKindChange(r.kind)}
          >
            <span className="report-card-question">{r.question}</span>
            <span className="report-card-title">{r.title}</span>
            <span className="report-card-description">{r.description}</span>
            <span className="report-card-formats">{r.formats}</span>
          </button>
        ))}
      </div>

      {locations.length === 0 ? (
        <p className="waiting">Loading locations…</p>
      ) : (
        <div className="report-body">
          {kind === "monthly" && <MonthlyReport />}
          {kind === "inquiry" && <InquiryReport locations={locations} />}
          {kind === "factsheet" && (
            <FactSheet
              sensors={sensors}
              deviceId={factSheetDevice ?? locations[0].device_id}
              onDeviceChange={onFactSheetDeviceChange}
            />
          )}
          {kind === "extract" && <DataExtract locations={locations} />}
        </div>
      )}
    </div>
  );
}
