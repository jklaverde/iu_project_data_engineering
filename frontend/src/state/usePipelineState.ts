import { useEffect, useState } from "react";
import { connectPipelineStateSocket, fetchPipelineState } from "../api";
import type { PipelineState } from "../types";

const POLL_INTERVAL_MS = Number(import.meta.env.VITE_POLL_INTERVAL_MS ?? 2000);
const WS_CONNECT_TIMEOUT_MS = 3000;

export type ConnectionMode = "connecting" | "ws" | "polling";

const EMPTY_STATE: PipelineState = {
  deployment: null,
  ingestion: null,
  kafka: null,
  spark: null,
  cassandra: null,
  summary: null,
};

export function usePipelineState() {
  const [state, setState] = useState<PipelineState>(EMPTY_STATE);
  const [connectionMode, setConnectionMode] = useState<ConnectionMode>("connecting");

  useEffect(() => {
    let cancelled = false;
    let ws: WebSocket | null = null;
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    let wsOpenedOnce = false;

    const startPolling = () => {
      if (pollTimer !== null || cancelled) return;
      setConnectionMode("polling");
      const poll = async () => {
        try {
          const data = await fetchPipelineState();
          if (!cancelled) setState(data);
        } catch {
          // transient - next tick retries
        }
      };
      poll();
      pollTimer = setInterval(poll, POLL_INTERVAL_MS);
    };

    const stopPolling = () => {
      if (pollTimer !== null) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    };

    ws = connectPipelineStateSocket(
      (data) => {
        if (!cancelled) setState(data);
      },
      () => {
        wsOpenedOnce = true;
        stopPolling();
        if (!cancelled) setConnectionMode("ws");
      },
      () => {
        if (!cancelled) startPolling();
      },
    );

    const fallbackTimer = setTimeout(() => {
      if (!wsOpenedOnce) startPolling();
    }, WS_CONNECT_TIMEOUT_MS);

    return () => {
      cancelled = true;
      clearTimeout(fallbackTimer);
      stopPolling();
      ws?.close();
    };
  }, []);

  return { state, connectionMode };
}
