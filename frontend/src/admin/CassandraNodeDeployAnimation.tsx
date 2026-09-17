import type { CassandraDeployProgress, CassandraDeployStep } from "../types";

// Same technique as pipeline/PipelineFlowDiagram.tsx (D26): plain SVG + CSS
// Motion Path for the traveling particle, no animation library (not on the
// NFR-10.1 dependency allowlist). D42's UX ask was specifically for this to
// read as "alive" while a step is running, not a static list - the particle
// only runs across the segment currently in flight, and each box gets an
// unambiguous done/active/pending/error look.
const STEPS: { key: CassandraDeployStep; label: string }[] = [
  { key: "creating", label: "Schedule pod" },
  { key: "healthy", label: "Pod healthy" },
  { key: "joining_ring", label: "Joining the ring" },
  { key: "done", label: "Ready" },
];

const BOX_W = 190;
const BOX_H = 80;
const GAP = 60;
const BOX_Y = 20;
const CENTER_Y = BOX_Y + BOX_H / 2;

function boxX(i: number) {
  return i * (BOX_W + GAP);
}

type BoxState = "done" | "active" | "pending" | "error";

function stateFor(stepIndex: number, currentIndex: number, erroredIndex: number | null): BoxState {
  if (erroredIndex !== null) {
    if (stepIndex < erroredIndex) return "done";
    if (stepIndex === erroredIndex) return "error";
    return "pending";
  }
  if (stepIndex < currentIndex) return "done";
  if (stepIndex === currentIndex) return "active";
  return "pending";
}

export default function CassandraNodeDeployAnimation({ progress }: { progress: CassandraDeployProgress }) {
  const currentIndex = STEPS.findIndex((s) => s.key === progress.step);
  const erroredIndex = progress.status === "error" && currentIndex >= 0 ? currentIndex : null;
  // "done" arrives with status "done" too (the whole sequence finished) -
  // treat that as every box complete rather than the last box merely active.
  const effectiveCurrent = progress.step === "done" && progress.status === "done" ? STEPS.length : currentIndex;

  const width = boxX(STEPS.length - 1) + BOX_W;

  return (
    <div className="cassandra-deploy-animation">
      <svg viewBox={`0 0 ${width} 120`} width="100%" height="120">
        {STEPS.slice(0, -1).map((_, i) => {
          const x1 = boxX(i) + BOX_W;
          const x2 = boxX(i + 1);
          const d = `M ${x1} ${CENTER_Y} L ${x2} ${CENTER_Y}`;
          const segmentActive = erroredIndex === null && i === effectiveCurrent - 1 && effectiveCurrent <= STEPS.length;
          const segmentDone = erroredIndex !== null ? i < erroredIndex : i < effectiveCurrent - 1;
          return (
            <g key={i}>
              <path d={d} stroke="var(--flow-line)" strokeWidth={2} fill="none" />
              {(segmentActive || segmentDone) && (
                <path d={d} stroke="var(--accent)" strokeWidth={2} fill="none" opacity={segmentDone ? 0.6 : 1} />
              )}
              {segmentActive && (
                <circle r={5} className="flow-particle deploy-particle" style={{ offsetPath: `path('${d}')` }} />
              )}
            </g>
          );
        })}

        {STEPS.map((step, i) => {
          const boxState = stateFor(i, effectiveCurrent, erroredIndex);
          return (
            <g key={step.key} transform={`translate(${boxX(i)}, ${BOX_Y})`}>
              <rect
                width={BOX_W}
                height={BOX_H}
                rx={10}
                className={`deploy-box deploy-box-${boxState}`}
              />
              <text x={BOX_W / 2} y={30} textAnchor="middle" className="flow-box-label">
                {step.label}
              </text>
              <text x={BOX_W / 2} y={54} textAnchor="middle" className={`deploy-box-status deploy-box-status-${boxState}`}>
                {boxState === "done" && "✓ done"}
                {boxState === "active" && "in progress…"}
                {boxState === "pending" && "waiting"}
                {boxState === "error" && "✕ failed"}
              </text>
            </g>
          );
        })}
      </svg>
      {progress.status === "error" && (
        <p className="status-badge status-critical">{progress.message ?? "Node deploy failed."}</p>
      )}
    </div>
  );
}
