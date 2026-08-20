import { useEffect } from "react";

const FLOW = ["Producer", "Kafka", "Spark", "Cassandra"];

export default function AboutModal({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-card about-card"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="about-title"
      >
        <div className="about-banner">
          <button className="modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
          <div className="about-eyebrow">IU International University of Applied Sciences</div>
          <h2 id="about-title">Project: Data Engineering (class project)</h2>
          <div className="about-kicker">Big Data Masterclass · DLBDSEDE02 · Academic Year 2025–2026</div>
          <div className="about-flow" aria-hidden="true">
            {FLOW.map((step, i) => (
              <span className="about-flow-step" key={step}>
                <span className="about-flow-dot" />
                {step}
                {i < FLOW.length - 1 && <span className="about-flow-arrow">→</span>}
              </span>
            ))}
          </div>
        </div>

        <div className="modal-body">
          <p className="about-summary">
            Ever wondered what actually happens the instant a sensor reading is sent,
            processed, and stored — all in real time? This project builds that pipeline
            for real, end to end, so you can watch it happen live instead of just
            reading about it.
          </p>

          <p>
            A producer replays a public environmental-sensor dataset into Apache Kafka,
            then seamlessly hands over to synthetic data generation once the dataset
            runs out. Apache Spark Structured Streaming picks up the stream, flags
            statistical anomalies against an adaptive per-device baseline, and writes
            both raw events and 1-minute/1-hour rollups to Apache Cassandra. This web
            app quietly watches all of it — producer, Kafka, Spark, and Cassandra — and
            streams a live snapshot to your browser, turning "deployment → ingestion →
            brokering → processing → storage" into six steps you can actually follow.
          </p>

          <h3>How it fits together</h3>
          <p>
            Runs as the <code>backend</code> service in the project's own{" "}
            <code>docker-compose.yml</code> stack, alongside Kafka, Cassandra, Spark,
            Prometheus, and Grafana — built together with the React/TypeScript frontend
            into a single container. Read-only by design: it never writes to Kafka or
            Cassandra, only observes what the producer and Spark job are already doing.
          </p>

          <div className="about-divider" />

          <div className="about-people">
            <div className="about-avatar" aria-hidden="true">
              JCL
            </div>
            <div className="about-people-text">
              <p className="about-author">
                <strong>Juan Carlos Laverde</strong>
                <br />
                <span className="about-meta">Student ID UPS10797707</span>
              </p>
              <p className="about-supervisor">
                Supervised by <strong>Prof. Dr. Paul Libbrecht</strong>
              </p>
            </div>
          </div>

          <p className="about-license">
            IU Internationale Hochschule — Academic Use. The author donates all rights
            over this work to IU Internationale Hochschule for any academic purpose.
            Source code may be used, adapted, or redistributed freely for academic and
            educational purposes.
          </p>

          <p className="about-version">Version 1.0.0</p>
        </div>
      </div>
    </div>
  );
}
