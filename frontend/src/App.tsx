import { useEffect, useState } from "react";
import { ApiError, logout, me } from "./api";
import AboutModal from "./about/AboutModal";
import AlertsTab from "./admin/AlertsTab";
import LoginForm from "./auth/LoginForm";
import ErrorBoundary from "./layout/ErrorBoundary";
import Stepper from "./layout/Stepper";
import PipelineFlowDiagram from "./pipeline/PipelineFlowDiagram";
import CassandraStep from "./steps/CassandraStep";
import DeploymentStep from "./steps/DeploymentStep";
import IngestionStep from "./steps/IngestionStep";
import KafkaStep from "./steps/KafkaStep";
import SparkStep from "./steps/SparkStep";
import SummaryStep from "./steps/SummaryStep";
import MapView from "./planner/MapView";
import { usePipelineState } from "./state/usePipelineState";
import type { Role, StepName } from "./types";

const STEPS: { name: StepName; label: string }[] = [
  { name: "deployment", label: "1. Deployment" },
  { name: "ingestion", label: "2. Ingestion" },
  { name: "kafka", label: "3. Kafka" },
  { name: "spark", label: "4. Spark" },
  { name: "cassandra", label: "5. Cassandra" },
  { name: "summary", label: "6. Summary" },
];

type AdminTab = "pipeline" | "alerts";

function Shell({ onLogout }: { onLogout: () => void }) {
  const { state, connectionMode } = usePipelineState();
  const [currentStep, setCurrentStep] = useState<StepName>("deployment");
  const [showAbout, setShowAbout] = useState(false);
  const [adminTab, setAdminTab] = useState<AdminTab>("pipeline");

  return (
    <div className="shell">
      <header>
        <h1>Infrastructure Console</h1>
        <div className="header-right">
          <span className={`connection-badge connection-${connectionMode}`}>
            {connectionMode === "ws" ? "live (websocket)" : connectionMode === "polling" ? "live (polling)" : "connecting..."}
          </span>
          <button className="btn btn-accent" onClick={() => setShowAbout(true)}>
            About the project
          </button>
          <button className="btn btn-ghost" onClick={onLogout}>
            Log out
          </button>
        </div>
      </header>

      {showAbout && <AboutModal onClose={() => setShowAbout(false)} />}

      <nav className="admin-tabs">
        <button
          className={`admin-tab ${adminTab === "pipeline" ? "admin-tab-active" : ""}`}
          onClick={() => setAdminTab("pipeline")}
        >
          Pipeline
        </button>
        <button
          className={`admin-tab ${adminTab === "alerts" ? "admin-tab-active" : ""}`}
          onClick={() => setAdminTab("alerts")}
        >
          Alerts
        </button>
      </nav>

      {adminTab === "pipeline" && (
        <>
          <PipelineFlowDiagram state={state} />

          <div className="body">
            <Stepper steps={STEPS} current={currentStep} onSelect={setCurrentStep} />
            <main>
              <ErrorBoundary key={currentStep}>
                {currentStep === "deployment" && <DeploymentStep data={state.deployment} />}
                {currentStep === "ingestion" && <IngestionStep data={state.ingestion} />}
                {currentStep === "kafka" && <KafkaStep data={state.kafka} spark={state.spark} />}
                {currentStep === "spark" && <SparkStep data={state.spark} />}
                {currentStep === "cassandra" && <CassandraStep data={state.cassandra} />}
                {currentStep === "summary" && <SummaryStep data={state.summary} />}
              </ErrorBoundary>
            </main>
          </div>
        </>
      )}

      {adminTab === "alerts" && <AlertsTab grafanaPort={state.summary?.grafana_port ?? null} />}
    </div>
  );
}

interface Session {
  authenticated: boolean;
  role: Role;
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    me()
      .then((res) => setSession(res.authenticated ? res : null))
      .catch((err) => {
        if (!(err instanceof ApiError && err.status === 401)) {
          console.error(err);
        }
        setSession(null);
      })
      .finally(() => setChecked(true));
  }, []);

  const handleLogout = async () => {
    await logout().catch(() => {});
    setSession(null);
  };

  if (!checked) {
    return <div className="loading">Loading...</div>;
  }

  if (!session) {
    return <LoginForm onSuccess={(role) => setSession({ authenticated: true, role })} />;
  }

  if (session.role === "planner") {
    return <MapView onLogout={handleLogout} />;
  }

  return <Shell onLogout={handleLogout} />;
}
