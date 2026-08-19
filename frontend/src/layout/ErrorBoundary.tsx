import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

// Without this, an uncaught render error anywhere in the tree unmounts the
// whole React root permanently (confirmed live: a transient upstream hiccup
// during a producer restart left one step's data momentarily incomplete,
// which crashed the entire app until a manual reload). Scoped around each
// step's content so one bad render only takes down that step, not the
// walkthrough.
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Step render error", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="step-error">
          Something went wrong rendering this step. Switch to another step and back to retry.
        </div>
      );
    }
    return this.props.children;
  }
}
