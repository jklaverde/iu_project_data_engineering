import type {
  AdminAlert,
  AdminDoc,
  AdminDocSummary,
  PipelineState,
  Role,
  SensorsResponse,
  SensorHistoryResponse,
  TimelineGranularity,
  TimelineResponse,
} from "./types";

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

export function login(username: string, password: string): Promise<{ username: string; role: Role }> {
  return request("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export function logout(): Promise<{ status: string }> {
  return request("/api/auth/logout", { method: "POST" });
}

export function me(): Promise<{ authenticated: boolean; role: Role }> {
  return request("/api/auth/me");
}

export function fetchSensors(): Promise<SensorsResponse> {
  return request("/api/sensors");
}

export function fetchSensorHistory(
  deviceId: string,
  params: { granularity?: "1m" | "1h"; hours?: number } = {},
): Promise<SensorHistoryResponse> {
  const search = new URLSearchParams();
  if (params.granularity) search.set("granularity", params.granularity);
  if (params.hours) search.set("hours", String(params.hours));
  const qs = search.toString();
  return request(`/api/sensors/${encodeURIComponent(deviceId)}/history${qs ? `?${qs}` : ""}`);
}

export function fetchPipelineState(): Promise<PipelineState> {
  return request("/api/pipeline-state");
}

export function fetchSensorTimeline(
  deviceId: string,
  params: { metric: string; granularity: TimelineGranularity },
): Promise<TimelineResponse> {
  const search = new URLSearchParams({ metric: params.metric, granularity: params.granularity });
  return request(`/api/sensors/${encodeURIComponent(deviceId)}/timeline?${search.toString()}`);
}

export function fetchAdminAlerts(): Promise<{ alerts: AdminAlert[] }> {
  return request("/api/admin/alerts");
}

export function fetchAdminDocs(): Promise<{ docs: AdminDocSummary[] }> {
  return request("/api/admin/docs");
}

export function fetchAdminDoc(docId: string): Promise<AdminDoc> {
  return request(`/api/admin/docs/${encodeURIComponent(docId)}`);
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
