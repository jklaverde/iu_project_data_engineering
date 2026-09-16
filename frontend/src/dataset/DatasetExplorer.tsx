import { useEffect, useMemo, useRef, useState } from "react";
import EChartWrapper from "../charts/EChartWrapper";
import { fetchDatasetReadings, fetchDatasetSummary } from "../api";
import type { DatasetDeviceSummary, DatasetReading } from "../types";

type MetricKey = "co" | "lpg" | "smoke" | "temp" | "humidity";

const METRICS: { key: MetricKey; label: string }[] = [
  { key: "co", label: "CO" },
  { key: "lpg", label: "LPG" },
  { key: "smoke", label: "Smoke" },
  { key: "temp", label: "Temperature" },
  { key: "humidity", label: "Humidity" },
];

// Half-window fetched around the scrub cursor. A device produces roughly one
// reading every ~4.5s (405k rows / 3 devices / 7 days), so a 30-minute span
// is a few hundred points - enough for a smooth line, well under the fetch
// limit below.
const HALF_WINDOW_MS = 15 * 60 * 1000;
const REFETCH_THRESHOLD_MS = HALF_WINDOW_MS / 2;
const SLIDER_STEP_MS = 60 * 1000;
const PLAY_STEP_MS = 5 * 60 * 1000;
const PLAY_TICK_MS = 200;

function fmt(ms: number): string {
  return new Date(ms).toISOString().replace("T", " ").slice(0, 19) + " UTC";
}

// D38 - reachable by both roles (FR-W8, FR-P2): browses the original Kaggle
// CSV directly, independent of Kafka/Spark/Cassandra, on its own real 2020
// timeline. A scrub control (not a raw grid) drives the chart, so moving
// through time is the interaction, not scrolling a table - the direct
// answer to "how does live data relate to the dataset" is watching values
// change as you move a cursor through the dataset's own real collection
// window.
export default function DatasetExplorer({ onClose }: { onClose: () => void }) {
  const [summary, setSummary] = useState<DatasetDeviceSummary[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null);
  const [metric, setMetric] = useState<MetricKey>("co");
  const [cursorMs, setCursorMs] = useState<number | null>(null);
  const [windowReadings, setWindowReadings] = useState<DatasetReading[]>([]);
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const loadedCenterRef = useRef<number | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    fetchDatasetSummary()
      .then((res) => {
        setSummary(res.devices);
        if (res.devices.length > 0) setSelectedDevice((cur) => cur ?? res.devices[0].device_id);
      })
      .catch(() => setSummary([]));
  }, []);

  const range = useMemo(() => {
    const d = summary.find((s) => s.device_id === selectedDevice);
    return d ? { min: Date.parse(d.min_source_ts), max: Date.parse(d.max_source_ts) } : null;
  }, [summary, selectedDevice]);

  // Jump to the start of the selected device's real timeline on device
  // change - a fresh scrub, not carried over from the last device.
  useEffect(() => {
    const d = summary.find((s) => s.device_id === selectedDevice);
    if (!d) return;
    loadedCenterRef.current = null;
    setCursorMs(Date.parse(d.min_source_ts));
  }, [selectedDevice, summary]);

  // Only refetch once the cursor drifts past the inner half of the loaded
  // window - keeps both dragging and auto-play from firing a request per
  // tick, while still staying ahead of the visible cursor.
  useEffect(() => {
    if (!selectedDevice || cursorMs === null) return;
    if (loadedCenterRef.current !== null && Math.abs(cursorMs - loadedCenterRef.current) <= REFETCH_THRESHOLD_MS) {
      return;
    }
    loadedCenterRef.current = cursorMs;
    let cancelled = false;
    setLoading(true);
    fetchDatasetReadings({
      deviceId: selectedDevice,
      since: new Date(cursorMs - HALF_WINDOW_MS).toISOString(),
      until: new Date(cursorMs + HALF_WINDOW_MS).toISOString(),
      limit: 800,
    })
      .then((res) => {
        if (!cancelled) setWindowReadings(res.readings);
      })
      .catch(() => {
        if (!cancelled) setWindowReadings([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedDevice, cursorMs]);

  // Auto-advance the cursor through this device's real timeline, so "move
  // through time" works as playback, not just manual dragging.
  useEffect(() => {
    if (!playing || !range) return;
    const id = window.setInterval(() => {
      setCursorMs((cur) => {
        if (cur === null) return cur;
        const next = cur + PLAY_STEP_MS;
        if (next >= range.max) {
          setPlaying(false);
          return range.max;
        }
        return next;
      });
    }, PLAY_TICK_MS);
    return () => window.clearInterval(id);
  }, [playing, range]);

  // Index, not just the reading, so the chart's markLine can position itself
  // on the category axis below (a numeric time-type axis renders its own
  // tick labels in the browser's local timezone, which would silently
  // disagree with the UTC label above it - exactly the provenance confusion
  // D38 exists to remove, so this chart uses source_ts's own UTC text
  // instead, same convention as SensorTimeline's formatLabel functions).
  const nearestIndex = useMemo(() => {
    if (cursorMs === null || windowReadings.length === 0) return null;
    let bestIdx = 0;
    let bestDelta = Infinity;
    windowReadings.forEach((r, i) => {
      const delta = Math.abs(Date.parse(r.source_ts) - cursorMs);
      if (delta < bestDelta) {
        bestDelta = delta;
        bestIdx = i;
      }
    });
    return bestIdx;
  }, [windowReadings, cursorMs]);

  const nearest = nearestIndex !== null ? windowReadings[nearestIndex] : null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-card dataset-explorer-card"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="dataset-explorer-title"
      >
        <button className="modal-close" onClick={onClose} aria-label="Close">
          ×
        </button>
        <h2 id="dataset-explorer-title">Dataset Explorer</h2>
        <p className="waiting">
          Scrub through the original Kaggle source file's own real collection timeline — not the
          live/synthetic pipeline. Every value here is genuine, dated to when it was actually collected.
        </p>

        <div className="dataset-device-picker">
          {summary.map((d) => (
            <button
              key={d.device_id}
              className={`dataset-device-btn ${d.device_id === selectedDevice ? "dataset-device-btn-active" : ""}`}
              onClick={() => setSelectedDevice(d.device_id)}
            >
              <span className="dataset-device-id">{d.device_id}</span>
              <span className="dataset-device-meta">
                {d.row_count.toLocaleString()} rows · {d.min_source_ts.slice(0, 10)} → {d.max_source_ts.slice(0, 10)}
              </span>
            </button>
          ))}
        </div>

        {range && cursorMs !== null && (
          <>
            <div className="dataset-scrub-row">
              <button
                className="dataset-play-btn"
                onClick={() => setPlaying((p) => !p)}
                aria-label={playing ? "Pause" : "Play"}
              >
                {playing ? "⏸" : "▶"}
              </button>
              <input
                type="range"
                className="dataset-scrub-slider"
                min={range.min}
                max={range.max}
                step={SLIDER_STEP_MS}
                value={cursorMs}
                onChange={(e) => {
                  setPlaying(false);
                  setCursorMs(Number(e.target.value));
                }}
              />
              <span className="dataset-scrub-label">{fmt(cursorMs)}</span>
            </div>

            <div className="metric-tabs">
              {METRICS.map((m) => (
                <button
                  key={m.key}
                  className={`metric-tab ${metric === m.key ? "metric-tab-active" : ""}`}
                  onClick={() => setMetric(m.key)}
                >
                  {m.label}
                </button>
              ))}
            </div>

            {nearest && (
              <p className="dataset-nearest-reading">
                Nearest reading — CO {nearest.co.toFixed(4)} · LPG {nearest.lpg.toFixed(4)} · Smoke{" "}
                {nearest.smoke.toFixed(4)} · Temp {nearest.temp.toFixed(1)}°C · Humidity{" "}
                {nearest.humidity.toFixed(0)}%
              </p>
            )}

            {loading && windowReadings.length === 0 && <p className="waiting">Loading…</p>}

            <EChartWrapper
              height={260}
              option={{
                grid: { left: 48, right: 16, top: 16, bottom: 40 },
                xAxis: {
                  type: "category",
                  data: windowReadings.map((r) => r.source_ts.slice(11, 19)),
                  axisLabel: { fontSize: 10 },
                },
                yAxis: { type: "value" },
                tooltip: { trigger: "axis" },
                series: [
                  {
                    type: "line",
                    data: windowReadings.map((r) => r[metric]),
                    smooth: true,
                    symbol: "none",
                    lineStyle: { width: 2, color: "#7dd3fc" },
                    markLine: {
                      symbol: "none",
                      label: { show: false },
                      lineStyle: { color: "#fb5a6e", width: 2 },
                      data: nearestIndex !== null ? [{ xAxis: nearestIndex }] : [],
                    },
                  },
                ],
              }}
            />
          </>
        )}
      </div>
    </div>
  );
}
