import type { ReactNode } from "react";
import { PERSONA, PRINT_HINT } from "./reportText";

// The printable frame shared by all reports (D55, FR-O8/FR-O9): letterhead,
// title and period, the body, and the caveats. Everything outside a
// .print-area is hidden when printing (styles.css @media print).
export default function ReportSheet({
  title,
  subtitle,
  caveats,
  xlsxUrl,
  printable = true,
  children,
}: {
  title: string;
  subtitle?: string;
  caveats?: string[];
  xlsxUrl?: string;
  printable?: boolean;
  children: ReactNode;
}) {
  const generated = new Date().toLocaleString("en-GB", {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
  return (
    <section className="step report-sheet print-area">
      <div className="report-actions no-print">
        {printable && (
          <button className="btn btn-accent" title={PRINT_HINT} onClick={() => window.print()}>
            Print / save as PDF
          </button>
        )}
        {xlsxUrl && (
          <a className="btn btn-ghost" href={xlsxUrl} download>
            Download Excel
          </a>
        )}
      </div>
      <div className="report-letterhead">
        <span>
          {PERSONA.office} · {PERSONA.role}
        </span>
        {/* A printed page leaves the app: say it is a scenario, not an official document. */}
        <span>Illustrative scenario · generated {generated}</span>
      </div>
      <h2 className="report-title">{title}</h2>
      {subtitle && <p className="report-subtitle">{subtitle}</p>}
      {children}
      {caveats && caveats.length > 0 && (
        <div className="report-caveats">
          <h4 className="section-title">About these numbers</h4>
          <ul>
            {caveats.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
