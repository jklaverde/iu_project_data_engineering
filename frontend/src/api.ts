import type {
  AdminAlert,
  ArchiveResult,
  CassandraDeployProgress,
  CassandraStorageSummary,
  DatasetReadingsResponse,
  DatasetSummaryResponse,
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
  params: { metric: string; granularity: TimelineGranularity; compare?: boolean },
): Promise<TimelineResponse> {
  const search = new URLSearchParams({ metric: params.metric, granularity: params.granularity });
  if (params.compare) search.set("compare", "true");
  return request(`/api/sensors/${encodeURIComponent(deviceId)}/timeline?${search.toString()}`);
}

export function fetchAdminAlerts(): Promise<{ alerts: AdminAlert[] }> {
  return request("/api/admin/alerts");
}

export function runArchive(cutoff?: string): Promise<ArchiveResult> {
  return request("/api/admin/archive", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: true, ...(cutoff ? { cutoff } : {}) }),
  });
}

export function fetchCassandraStorage(): Promise<CassandraStorageSummary> {
  return request("/api/admin/cassandra/storage");
}

export function deployCassandraNode(): Promise<{ status: string }> {
  return request("/api/admin/cassandra/nodes", { method: "POST" });
}

export function fetchDatasetSummary(): Promise<DatasetSummaryResponse> {
  return request("/api/dataset/summary");
}

export function fetchDatasetReadings(params: {
  deviceId?: string; since?: string; until?: string; limit?: number;
} = {}): Promise<DatasetReadingsResponse> {
  const search = new URLSearchParams();
  if (params.deviceId) search.set("device_id", params.deviceId);
  if (params.since) search.set("since", params.since);
  if (params.until) search.set("until", params.until);
  if (params.limit) search.set("limit", String(params.limit));
  const qs = search.toString();
  return request(`/api/dataset/readings${qs ? `?${qs}` : ""}`);
}

export function connectPipelineStateSocket(
  onMessage: (state: PipelineState) => void,
  onOpen: () => void,
  onClose: () => void,
  onCassandraDeployProgress?: (progress: CassandraDeployProgress) => void,
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
      } else if (payload.type === "cassandra-node-deploy") {
        onCassandraDeployProgress?.(payload as CassandraDeployProgress);
      }
    } catch {
      // ignore malformed frames
    }
  };
  return ws;
}
