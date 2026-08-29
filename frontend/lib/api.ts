// Frontend API client — all backend calls go through here.
// Base URL from env; falls back to localhost for local dev.
// Never hardcode elsewhere.
//
// Auth: protected endpoints require a Supabase access_token.
// Pass the token from supabase.auth.getSession() as the second argument.

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
  // Admin status management (Priority 2)
  rejection_reason: string | null;
  // T3-3 / Priority 3 — AI pipeline fields
  image_original_url: string | null;
  image_redacted_url: string | null;
  is_duplicate: boolean;
  duplicate_report_id: string | null;
  yolo_class: string | null;
  llm_provider_used: string | null;
}

export interface ReportPatchRequest {
  category?: IssueCategory;
  description?: string;
  authority_id?: string;
}

export interface AdminStatusUpdateRequest {
  new_status: ReportStatus;
  rejection_reason?: string;
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
  init?: RequestInit,
  token?: string
): Promise<{ data: T | null; error: string | null }> {
  try {
    const authHeader: Record<string, string> = token
      ? { Authorization: `Bearer ${token}` }
      : {};

    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...authHeader,
        ...init?.headers,
      },
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

// POST /api/v1/reports/ — requires auth token (JWT from Supabase session)
export async function createReport(formData: FormData, token: string) {
  return apiFetch<Report>(
    "/api/v1/reports/",
    { method: "POST", body: formData },
    token
  );
}

// GET /api/v1/reports/ — requires auth token (returns user-scoped reports)
export async function listReports(token: string) {
  return apiFetch<ReportListResponse>("/api/v1/reports/", undefined, token);
}

// GET /api/v1/reports/{id} — requires auth token (ownership check)
export async function getReport(id: string, token: string) {
  return apiFetch<Report>(`/api/v1/reports/${id}`, undefined, token);
}

// PATCH /api/v1/reports/{id} — citizen confirms/edits AI result (Priority 3)
export async function patchReport(
  reportId: string,
  body: ReportPatchRequest,
  token: string
) {
  return apiFetch<Report>(
    `/api/v1/reports/${reportId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    token
  );
}

// -------------------------------------------------------------------------
// Admin API (admin role required)
// -------------------------------------------------------------------------

export interface AdminStats {
  total_reports: number;
  by_category: Record<string, number>;
  by_status: Record<string, number>;
  by_authority: Record<string, number>;
}

// GET /api/v1/admin/reports — all reports, admin only
export async function adminListReports(token: string) {
  return apiFetch<ReportListResponse>("/api/v1/admin/reports", undefined, token);
}

// GET /api/v1/admin/stats — aggregate stats, admin only
export async function adminGetStats(token: string) {
  return apiFetch<AdminStats>("/api/v1/admin/stats", undefined, token);
}

// PATCH /api/v1/admin/reports/{id}/status — update report status, admin only
export async function adminUpdateReportStatus(
  reportId: string,
  body: AdminStatusUpdateRequest,
  token: string
) {
  return apiFetch<Report>(
    `/api/v1/admin/reports/${reportId}/status`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    token
  );
}
