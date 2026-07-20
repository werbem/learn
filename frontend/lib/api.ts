import type {
  AnalysisInput,
  ReportCreateResponse,
  ReportDetailResponse,
  TaskProgressResponse,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";
const API_PREFIX = `${API_BASE}/api`;

export class ApiError extends Error {
  status: number;
  detail: any;
  constructor(status: number, detail: any, message?: string) {
    super(message || `API Error ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const body = await res.text();
    let detail: any = body;
    try {
      detail = JSON.parse(body);
    } catch {
      // keep as string if not JSON
    }
    throw new ApiError(res.status, detail, `API Error ${res.status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
  }
  return res.json();
}

export async function createReport(input: AnalysisInput, signal?: AbortSignal): Promise<ReportCreateResponse> {
  return request<ReportCreateResponse>(`${API_PREFIX}/reports`, {
    method: "POST",
    body: JSON.stringify(input),
    signal,
  });
}

export async function getReport(taskId: string): Promise<ReportDetailResponse> {
  return request<ReportDetailResponse>(`${API_PREFIX}/reports/${taskId}`);
}

export async function getProgress(taskId: string): Promise<TaskProgressResponse> {
  return request<TaskProgressResponse>(`${API_PREFIX}/tasks/${taskId}/progress`);
}

export async function listReports(): Promise<{ reports: ReportDetailResponse[]; total: number }> {
  return request(`${API_PREFIX}/reports`);
}

// ── SSE Streaming ──

export function subscribeProgress(
  taskId: string,
  onEvent: (event: import("@/types").StreamEvent) => void,
  onDone: (status: string) => void,
  onError?: (err: Event) => void,
): EventSource {
  const url = `${API_PREFIX}/tasks/${taskId}/stream`;
  const es = new EventSource(url);

  es.addEventListener("phase_update", (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      onEvent(data);
    } catch {
      // ignore parse errors
    }
  });

  es.addEventListener("done", (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      const status = data.status || "completed";
      onDone(status);
      es.close();
    } catch {
      onDone("completed");
      es.close();
    }
  });

  es.addEventListener("heartbeat", () => {
    // Keep-alive, no action needed
  });

  es.onerror = (err) => {
    onError?.(err);
  };

  return es;
}

export async function deleteReport(taskId: string): Promise<void> {
  await request(`${API_PREFIX}/reports/${taskId}`, { method: "DELETE" });
}
