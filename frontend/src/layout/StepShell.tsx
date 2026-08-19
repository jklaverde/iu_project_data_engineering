import type { ReactNode } from "react";

export default function StepShell({ title, data, children }: { title: string; data: unknown; children: ReactNode }) {
  return (
    <section className="step">
      <h2>{title}</h2>
      {data === null || data === undefined ? <p className="waiting">Waiting for data...</p> : children}
    </section>
  );
}
