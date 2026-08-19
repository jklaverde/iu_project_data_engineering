import type { PipelineState, RawEventRow } from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { ...init, credentials: "include" });
  if (!res.ok) {
    throw new ApiError(res.status, `${init?.method ?? "GET"} ${path} -> ${res.status}`);
  }
  return (await res.json()) as T;
}

export function login(username: string, password: string): Promise<{ username: string }> {
  return request("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export function logout(): Promise<{ status: string }> {
  return request("/api/auth/logout", { method: "POST" });
}

export function me(): Promise<{ authenticated: boolean }> {
  return request("/api/auth/me");
}

export function fetchPipelineState(): Promise<PipelineState> {
  return request("/api/pipeline-state");
}

export function fetchAnomalies(params: {
  deviceId?: string;
  sinceMinutes?: number;
  limit?: number;
}): Promise<{ anomalies: RawEventRow[] }> {
  const search = new URLSearchParams();
  if (params.deviceId) search.set("device_id", params.deviceId);
  if (params.sinceMinutes) search.set("since_minutes", String(params.sinceMinutes));
  if (params.limit) search.set("limit", String(params.limit));
  const qs = search.toString();
  return request(`/api/anomalies${qs ? `?${qs}` : ""}`);
}

export function connectPipelineStateSocket(
  onMessage: (state: PipelineState) => void,
  onOpen: () => void,
  onClose: () => void,
): WebSocket {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${protocol}//${location.host}/ws/pipeline-state`);
  ws.onopen = onOpen;
  ws.onclose = onClose;
  ws.onerror = () => ws.close();
  ws.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.type === "pipeline-state") {
        onMessage(payload.data as PipelineState);
      }
    } catch {
      // ignore malformed frames
    }
  };
  return ws;
}
