import { useEffect, useState } from "react";
import { ApiError, logout, me } from "./api";
import AboutModal from "./about/AboutModal";
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
import { usePipelineState } from "./state/usePipelineState";
import type { StepName } from "./types";

const STEPS: { name: StepName; label: string }[] = [
  { name: "deployment", label: "1. Deployment" },
  { name: "ingestion", label: "2. Ingestion" },
  { name: "kafka", label: "3. Kafka" },
  { name: "spark", label: "4. Spark" },
  { name: "cassandra", label: "5. Cassandra" },
  { name: "summary", label: "6. Summary" },
];

function Shell({ onLogout }: { onLogout: () => void }) {
  const { state, connectionMode } = usePipelineState();
  const [currentStep, setCurrentStep] = useState<StepName>("deployment");
  const [showAbout, setShowAbout] = useState(false);

  return (
    <div className="shell">
      <header>
        <h1>Sensor Pipeline Walkthrough</h1>
        <div className="header-right">
          <span className={`connection-badge connection-${connectionMode}`}>
            {connectionMode === "ws" ? "live (websocket)" : connectionMode === "polling" ? "live (polling)" : "connecting..."}
          </span>
          <button onClick={() => setShowAbout(true)}>About the project</button>
          <button onClick={onLogout}>Log out</button>
        </div>
      </header>

      {showAbout && <AboutModal onClose={() => setShowAbout(false)} />}

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
    </div>
  );
}

export default function App() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);

  useEffect(() => {
    me()
      .then(() => setAuthenticated(true))
      .catch((err) => setAuthenticated(err instanceof ApiError && err.status === 401 ? false : false));
  }, []);

  const handleLogout = async () => {
    await logout().catch(() => {});
    setAuthenticated(false);
  };

  if (authenticated === null) {
    return <div className="loading">Loading...</div>;
  }

  if (!authenticated) {
    return <LoginForm onSuccess={() => setAuthenticated(true)} />;
  }

  return <Shell onLogout={handleLogout} />;
}
