import type { StepName } from "../types";

interface Props {
  steps: { name: StepName; label: string }[];
  current: StepName;
  onSelect: (name: StepName) => void;
}

export default function Stepper({ steps, current, onSelect }: Props) {
  return (
    <nav className="stepper">
      {steps.map((step) => (
        <button
          key={step.name}
          className={step.name === current ? "step-active" : ""}
          onClick={() => onSelect(step.name)}
        >
          {step.label}
        </button>
      ))}
    </nav>
  );
}
