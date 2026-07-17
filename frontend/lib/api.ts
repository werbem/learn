import type {
  AnalysisInput,
  ReportCreateResponse,
  ReportDetailResponse,
  TaskProgressResponse,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const API_PREFIX = `${API_BASE}/api`;

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
    throw new Error(`API Error ${res.status}: ${body}`);
  }
  return res.json();
}

export async function createReport(input: AnalysisInput): Promise<ReportCreateResponse> {
  return request<ReportCreateResponse>(`${API_PREFIX}/reports`, {
    method: "POST",
    body: JSON.stringify(input),
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
