// Header control for the guided tour (FR-T3): reopen it at any time, and turn
// its automatic start on or off for this browser.
export default function TourControls({
  onStart,
  autoStart,
  onAutoStartChange,
}: {
  onStart: () => void;
  autoStart: boolean;
  onAutoStartChange: (value: boolean) => void;
}) {
  return (
    <div className="tour-controls" data-tour="tour-controls">
      <button className="btn btn-ghost" onClick={onStart}>
        Guided tour
      </button>
      <label className="tour-autostart" title="Start the guided tour by itself when this page opens (remembered in this browser)">
        <input type="checkbox" checked={autoStart} onChange={(e) => onAutoStartChange(e.target.checked)} />
        Show at login
      </label>
    </div>
  );
}
