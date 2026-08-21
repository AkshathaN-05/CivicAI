// Frontend API client — all backend calls go through here.
// Base URL from env; falls back to localhost for local dev.
// Never hardcode elsewhere.

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type IssueCategory =
  | "pothole"
  | "waterlogging"
  | "broken_streetlight"
  | "garbage_overflow"
  | "open_drain"
  | "illegal_construction"
  | "water_supply"
  | "sewage"
  | "road_damage"
  | "other";

export type ReportStatus =
  | "SUBMITTED"
  | "UNDER_REVIEW"
  | "RESOLVED"
  | "REJECTED"
  | "ARCHIVED";

export interface Authority {
  id: string;
  name: string;
  short_name: string;
  contact_email: string;
  phone: string;
}

export interface Report {
  report_id: string;
  category: IssueCategory;
  category_label: string;
  area_text: string;
  description: string;
  status: ReportStatus;
  recommended_authority: Authority | null;
  match_reason: string | null;
  confidence: number;
  created_at: string;
  photo_filename: string | null;
}

export interface ReportListResponse {
  reports: Report[];
  total: number;
}

// -------------------------------------------------------------------------
// API helpers
// -------------------------------------------------------------------------

async function apiFetch<T>(
  path: string,
  init?: RequestInit
): Promise<{ data: T | null; error: string | null }> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
    });
    if (!res.ok) {
      const text = await res.text();
      let detail = `HTTP ${res.status}`;
      try {
        detail = JSON.parse(text)?.detail ?? detail;
      } catch {}
      return { data: null, error: detail };
    }
    const data: T = await res.json();
    return { data, error: null };
  } catch (err) {
    return {
      data: null,
      error: "Cannot reach the backend. Make sure it is running on port 8000.",
    };
  }
}

export async function createReport(formData: FormData) {
  return apiFetch<Report>("/api/v1/reports/", {
    method: "POST",
    body: formData,
  });
}

export async function listReports() {
  return apiFetch<ReportListResponse>("/api/v1/reports/");
}

export async function getReport(id: string) {
  return apiFetch<Report>(`/api/v1/reports/${id}`);
}
