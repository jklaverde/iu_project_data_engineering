import type { PipelineState } from "../types";

interface Props {
  state: PipelineState;
}

// Static positions for a 4-box SVG flow: Producer -> Kafka -> Spark -> Cassandra.
// Particle animation uses pure CSS Motion Path (offset-path/offset-distance) -
// no framer-motion or similar isn't on the NFR-10.1 dependency allowlist, so
// this is a deliberate "don't need it" rather than a workaround.
const BOX_Y = 50;
const BOX_H = 100;
const BOXES = [
  { key: "producer", label: "Producer", x: 20 },
  { key: "kafka", label: "Kafka", x: 280 },
  { key: "spark", label: "Spark", x: 540 },
  { key: "cassandra", label: "Cassandra", x: 800 },
];
const BOX_W = 180;
const CENTER_Y = BOX_Y + BOX_H / 2;

function boxCenterX(x: number) {
  return x + BOX_W / 2;
}

function speedFor(rate: number): number {
  // Higher throughput -> faster particle. Clamped to a sane visual range.
  const seconds = rate > 0 ? Math.max(1.5, Math.min(8, 200 / rate)) : 8;
  return seconds;
}

export default function PipelineFlowDiagram({ state }: Props) {
  const ingestion = state.ingestion;
  const kafkaTotal = state.kafka ? Object.values(state.kafka.produced_offsets).reduce((a, b) => a + b, 0) : 0;
  const sparkRows = state.spark
    ? Object.values(state.spark.queries).reduce((a, q) => a + (q.input_rows_per_second ?? 0), 0)
    : 0;
  const cassandraRows = state.cassandra?.recent_raw_events.length ?? 0;

  const mode = ingestion?.mode ?? "replay";
  const producerRate = ingestion?.configured_rate_msgs_per_sec ?? 0;

  const values: Record<string, string> = {
    producer: ingestion ? `${ingestion.events_sent_total.toLocaleString()} sent` : "-",
    kafka: `${kafkaTotal.toLocaleString()} offset`,
    spark: `${sparkRows.toFixed(0)} rows/s`,
    cassandra: `${cassandraRows} recent rows`,
  };

  const paths = [
    { from: BOXES[0], to: BOXES[1] },
    { from: BOXES[1], to: BOXES[2] },
    { from: BOXES[2], to: BOXES[3] },
  ];

  return (
    <div className="pipeline-flow">
      <svg viewBox="0 0 980 150" width="100%" height="150">
        {paths.map((p, i) => {
          const x1 = boxCenterX(p.from.x) + BOX_W / 2;
          const x2 = boxCenterX(p.to.x) - BOX_W / 2;
          const d = `M ${x1} ${CENTER_Y} L ${x2} ${CENTER_Y}`;
          return (
            <g key={i}>
              <path d={d} stroke="var(--flow-line)" strokeWidth={2} fill="none" />
              <circle
                r={5}
                className="flow-particle"
                style={{ offsetPath: `path('${d}')`, animationDuration: `${speedFor(producerRate)}s` }}
              />
            </g>
          );
        })}

        {BOXES.map((box) => (
          <g key={box.key} transform={`translate(${box.x}, ${BOX_Y})`}>
            <rect width={BOX_W} height={BOX_H} rx={10} className="flow-box" />
            <text x={BOX_W / 2} y={30} textAnchor="middle" className="flow-box-label">
              {box.label}
            </text>
            <text x={BOX_W / 2} y={60} textAnchor="middle" className="flow-box-value">
              {values[box.key]}
            </text>
            {box.key === "producer" && (
              <g key={mode} className="handover-badge">
                <text x={BOX_W / 2} y={82} textAnchor="middle" className={`mode-badge mode-badge-${mode}`}>
                  {mode.toUpperCase()}
                </text>
              </g>
            )}
          </g>
        ))}
      </svg>
      {ingestion?.handover_ts && (
        <p className="handover-caption">Handed over to synthetic generation at {new Date(ingestion.handover_ts).toLocaleString()}</p>
      )}
    </div>
  );
}
