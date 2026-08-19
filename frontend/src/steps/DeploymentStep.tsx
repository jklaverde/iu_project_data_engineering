import StepShell from "../layout/StepShell";
import type { DeploymentStep as DeploymentStepData } from "../types";

export default function DeploymentStep({ data }: { data: DeploymentStepData | null }) {
  return (
    <StepShell title="1. Deployment" data={data}>
      {data && (
        <>
          <p>
            {data.all_healthy ? "All services are healthy." : "Some services are not reachable yet."} Checked at{" "}
            {new Date(data.checked_at).toLocaleTimeString()}.
          </p>
          <div className="service-grid">
            {data.services.map((svc) => (
              <div key={svc.name} className={`service-card ${svc.healthy ? "healthy" : "unhealthy"}`}>
                <div className="service-name">{svc.name}</div>
                <div className="service-detail">{svc.detail}</div>
                {svc.latency_ms !== null && <div className="service-latency">{svc.latency_ms} ms</div>}
              </div>
            ))}
          </div>
        </>
      )}
    </StepShell>
  );
}
