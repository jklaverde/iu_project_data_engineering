import { useEffect } from "react";

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
      <div className="modal-card" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="about-title">
        <div className="modal-header">
          <h2 id="about-title">About this project</h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className="modal-body">
          <p className="about-summary">
            Read-only API and guided walkthrough for a real Kafka → Spark → Cassandra
            streaming sensor-data pipeline.
          </p>

          <p>
            A producer replays a public environmental-sensor dataset into Kafka, then
            hands over to synthetic generation once the dataset is exhausted. Apache
            Spark Structured Streaming consumes the stream, flags statistical anomalies
            against an adaptive per-device baseline, and writes raw events plus
            1-minute/1-hour windowed aggregates to Apache Cassandra. This web app polls
            the producer, Spark, Kafka, and Cassandra and streams a combined snapshot to
            the browser over WebSocket (with a polling fallback), covering deployment
            health, ingestion, brokering, processing, and storage as six guided steps.
          </p>

          <h3>Integration</h3>
          <p>
            Runs as the <code>backend</code> service in the project's own{" "}
            <code>docker-compose.yml</code> stack, alongside Kafka, Cassandra, Spark,
            Prometheus, and Grafana — built together with the React/TypeScript frontend
            into a single container. Read-only by design: it never writes to Kafka or
            Cassandra, only observes what the producer and Spark job are already doing.
          </p>

          <h3>Academic context</h3>
          <p>
            Developed as part of the <strong>Project: Data Engineering</strong> series
            (DLBDSEDE02 — Big Data Masterclass) at{" "}
            <strong>IU International University of Applied Sciences</strong> · Academic
            Year 2025–2026.
          </p>
          <p>Academic supervisors: Prof. Dr. Paul Libbrecht</p>

          <h3>Contact</h3>
          <p>
            Juan Carlos Laverde
            <br />
            Student ID: UPS10797707 · Academic Year 2025–2026
          </p>

          <h3>License</h3>
          <p>
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
