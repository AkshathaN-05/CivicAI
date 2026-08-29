"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { supabase } from "@/lib/supabase";
import {
  adminListReports,
  adminGetStats,
  adminUpdateReportStatus,
  type Report,
  type AdminStats,
  type ReportStatus,
} from "@/lib/api";
import { formatDate, confidenceLabel } from "@/lib/constants";
import StatusBadge from "@/components/StatusBadge";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CATEGORY_ICONS: Record<string, string> = {
  pothole: "🕳️", waterlogging: "💧", broken_streetlight: "💡",
  garbage_overflow: "🗑️", open_drain: "🏚️", illegal_construction: "🏗️",
  water_supply: "🚿", sewage: "⚠️", road_damage: "🛣️", other: "📋",
};

const REJECTION_REASONS = [
  "Duplicate report",
  "Invalid report",
  "Insufficient / unclear evidence",
  "Wrong category",
  "Other",
] as const;

const REJECTION_REASON_MAX = 500;

// ---------------------------------------------------------------------------
// Reject modal component
// ---------------------------------------------------------------------------

interface RejectModalProps {
  reportId: string;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
  submitting: boolean;
  error: string | null;
}

function RejectModal({ reportId: _reportId, onConfirm, onCancel, submitting, error }: RejectModalProps) {
  const [selected, setSelected] = useState<string>(REJECTION_REASONS[0]);
  const [custom, setCustom] = useState("");
  const dialogRef = useRef<HTMLDivElement>(null);

  // Close on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !submitting) onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [submitting, onCancel]);

  // Focus trap — close on backdrop click
  function handleBackdrop(e: React.MouseEvent) {
    if (dialogRef.current && !dialogRef.current.contains(e.target as Node)) {
      if (!submitting) onCancel();
    }
  }

  function handleConfirm() {
    const reason = selected === "Other" ? custom.trim() : selected;
    onConfirm(reason);
  }

  const effectiveReason = selected === "Other" ? custom.trim() : selected;
  const canSubmit = effectiveReason.length > 0 && effectiveReason.length <= REJECTION_REASON_MAX && !submitting;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm px-4"
      onClick={handleBackdrop}
      role="dialog"
      aria-modal="true"
      aria-labelledby="reject-modal-title"
    >
      <div
        ref={dialogRef}
        className="w-full max-w-sm bg-white rounded-2xl border border-border shadow-lg p-6"
      >
        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <div className="w-9 h-9 rounded-lg bg-red-50 border border-red-200 flex items-center justify-center shrink-0">
            <svg className="w-4.5 h-4.5 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </div>
          <div>
            <h2 id="reject-modal-title" className="font-semibold text-base">Reject Report</h2>
            <p className="text-xs text-muted-foreground mt-0.5">Choose a rejection reason. The citizen will see this.</p>
          </div>
        </div>

        {/* Reason picker */}
        <fieldset className="mb-4">
          <legend className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
            Rejection reason <span className="text-destructive">*</span>
          </legend>
          <div className="space-y-1.5">
            {REJECTION_REASONS.map((r) => (
              <label
                key={r}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-lg border cursor-pointer transition-colors text-sm ${
                  selected === r
                    ? "border-primary bg-accent text-primary"
                    : "border-border hover:border-ring/40 hover:bg-accent/30"
                }`}
              >
                <input
                  type="radio"
                  name="rejection_reason"
                  value={r}
                  checked={selected === r}
                  onChange={() => setSelected(r)}
                  className="accent-primary"
                  disabled={submitting}
                />
                {r}
              </label>
            ))}
          </div>
        </fieldset>

        {/* Custom explanation when "Other" selected */}
        {selected === "Other" && (
          <div className="mb-4">
            <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5" htmlFor="custom-reason">
              Explanation <span className="text-destructive">*</span>
            </label>
            <textarea
              id="custom-reason"
              rows={3}
              maxLength={REJECTION_REASON_MAX}
              placeholder="Briefly describe why this report is being rejected…"
              value={custom}
              onChange={(e) => setCustom(e.target.value)}
              disabled={submitting}
              className="w-full border border-input rounded-lg px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring resize-none disabled:opacity-60 transition-shadow"
            />
            <div className="flex items-center justify-between mt-1">
              {custom.trim().length === 0 && (
                <p className="text-destructive text-xs">Please enter an explanation.</p>
              )}
              {custom.length > REJECTION_REASON_MAX && (
                <p className="text-destructive text-xs">Too long — maximum {REJECTION_REASON_MAX} characters.</p>
              )}
              <span className="ml-auto text-xs text-muted-foreground">{custom.length}/{REJECTION_REASON_MAX}</span>
            </div>
          </div>
        )}

        {/* API error */}
        {error && (
          <div className="mb-4 flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            <svg className="w-4 h-4 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
            </svg>
            <span>{error}</span>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={submitting}
            className="flex-1 border border-border rounded-lg py-2.5 text-sm font-medium hover:bg-secondary transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={!canSubmit}
            className="flex-1 bg-red-600 text-white font-semibold py-2.5 rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2 text-sm"
          >
            {submitting ? (
              <>
                <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Rejecting…
              </>
            ) : "Confirm Rejection"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline action buttons for each report row
// ---------------------------------------------------------------------------

interface ActionButtonsProps {
  report: Report;
  token: string;
  onSuccess: (updated: Report) => void;
}

function ActionButtons({ report, token, onSuccess }: ActionButtonsProps) {
  const [updating, setUpdating] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectSubmitting, setRejectSubmitting] = useState(false);
  const [rejectError, setRejectError] = useState<string | null>(null);

  async function applyStatus(newStatus: ReportStatus) {
    setUpdating(true);
    setActionError(null);
    const { data, error } = await adminUpdateReportStatus(
      report.report_id,
      { new_status: newStatus },
      token
    );
    setUpdating(false);
    if (error) { setActionError(error); return; }
    if (data) onSuccess(data);
  }

  async function applyRejection(reason: string) {
    setRejectSubmitting(true);
    setRejectError(null);
    const { data, error } = await adminUpdateReportStatus(
      report.report_id,
      { new_status: "REJECTED", rejection_reason: reason },
      token
    );
    setRejectSubmitting(false);
    if (error) { setRejectError(error); return; }
    if (data) {
      setShowRejectModal(false);
      onSuccess(data);
    }
  }

  const status = report.status;

  // No actions for terminal / non-actionable states
  if (status === "ARCHIVED" || status === "RESOLVED" || status === "REJECTED") {
    return null;
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-1.5">
        {/* SUBMITTED → UNDER_REVIEW */}
        {status === "SUBMITTED" && (
          <button
            type="button"
            onClick={() => applyStatus("UNDER_REVIEW")}
            disabled={updating}
            className="inline-flex items-center gap-1 bg-yellow-50 border border-yellow-300 text-yellow-800 text-xs font-semibold px-2.5 py-1.5 rounded-lg hover:bg-yellow-100 transition-colors disabled:opacity-50 whitespace-nowrap"
          >
            {updating ? (
              <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 0 1 0-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178Z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
              </svg>
            )}
            Under Review
          </button>
        )}

        {/* UNDER_REVIEW → RESOLVED */}
        {status === "UNDER_REVIEW" && (
          <button
            type="button"
            onClick={() => applyStatus("RESOLVED")}
            disabled={updating}
            className="inline-flex items-center gap-1 bg-green-50 border border-green-300 text-green-800 text-xs font-semibold px-2.5 py-1.5 rounded-lg hover:bg-green-100 transition-colors disabled:opacity-50 whitespace-nowrap"
          >
            {updating ? (
              <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
              </svg>
            )}
            Resolve
          </button>
        )}

        {/* SUBMITTED or UNDER_REVIEW → REJECTED (opens modal) */}
        {(status === "SUBMITTED" || status === "UNDER_REVIEW") && (
          <button
            type="button"
            onClick={() => { setRejectError(null); setShowRejectModal(true); }}
            disabled={updating}
            className="inline-flex items-center gap-1 bg-red-50 border border-red-300 text-red-700 text-xs font-semibold px-2.5 py-1.5 rounded-lg hover:bg-red-100 transition-colors disabled:opacity-50 whitespace-nowrap"
          >
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
            Reject
          </button>
        )}

        {/* Inline error */}
        {actionError && (
          <span className="text-xs text-red-600 ml-1" title={actionError}>
            Error — {actionError.length > 60 ? actionError.slice(0, 60) + "…" : actionError}
          </span>
        )}
      </div>

      {/* Rejection modal */}
      {showRejectModal && (
        <RejectModal
          reportId={report.report_id}
          onConfirm={applyRejection}
          onCancel={() => { if (!rejectSubmitting) setShowRejectModal(false); }}
          submitting={rejectSubmitting}
          error={rejectError}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// StatCard helper
// ---------------------------------------------------------------------------

function StatCard({ label, value, icon }: { label: string; value: number; icon: React.ReactNode }) {
  return (
    <div className="border border-border rounded-xl bg-card p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{label}</span>
        <div className="w-7 h-7 rounded-lg bg-accent flex items-center justify-center text-primary">
          {icon}
        </div>
      </div>
      <div className="text-3xl font-extrabold tabular-nums">{value.toLocaleString()}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Admin page
// ---------------------------------------------------------------------------

export default function AdminPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [authChecked, setAuthChecked] = useState(false);
  const [reports, setReports] = useState<Report[]>([]);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState<string>("");

  useEffect(() => {
    async function loadAdmin() {
      const { data: sessionData } = await supabase.auth.getSession();
      if (!sessionData.session) { router.push("/login"); return; }

      const { data: refreshData, error: refreshError } = await supabase.auth.refreshSession();
      const session = refreshData?.session ?? sessionData.session;

      if (refreshError) { router.push("/login"); return; }

      const role = session?.user?.app_metadata?.role;
      if (role !== "admin") {
        setError(
          "Access denied. You need admin privileges to view this page. " +
          "If you were just granted admin access, please sign out and sign in again."
        );
        setAuthChecked(true);
        setLoading(false);
        return;
      }

      setAuthChecked(true);
      const tok = session.access_token;
      setToken(tok);

      const [reportsRes, statsRes] = await Promise.all([
        adminListReports(tok),
        adminGetStats(tok),
      ]);

      setLoading(false);
      if (reportsRes.error) { setError(reportsRes.error); return; }
      setReports(reportsRes.data?.reports ?? []);
      if (statsRes.data) setStats(statsRes.data);
    }

    loadAdmin();
  }, [router]);

  // Called when a status action succeeds — update the affected row in place
  function handleStatusUpdate(updated: Report) {
    setReports((prev) =>
      prev.map((r) => (r.report_id === updated.report_id ? updated : r))
    );
  }

  if (!authChecked || loading) {
    return (
      <div className="flex flex-col items-center justify-center py-32 gap-3 text-muted-foreground">
        <svg className="w-8 h-8 animate-spin text-primary/40" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <span className="text-sm">Loading admin dashboard…</span>
      </div>
    );
  }

  if (error) {
    const isRoleError = error.includes("admin privileges") || error.includes("Access denied");
    return (
      <div className="max-w-lg mx-auto px-4 py-20 text-center">
        <div className="w-16 h-16 rounded-full bg-red-50 flex items-center justify-center mx-auto mb-5">
          <svg className="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
          </svg>
        </div>
        <h2 className="font-semibold text-lg mb-2">Access Restricted</h2>
        <p className="text-muted-foreground text-sm mb-6">{error}</p>
        {isRoleError && (
          <div className="mb-4 p-4 bg-amber-50 border border-amber-200 rounded-xl text-sm text-amber-800 text-left">
            <p className="font-semibold mb-1">Admin role required</p>
            <p>
              To access this page your Supabase account must have{" "}
              <code className="bg-amber-100 px-1 rounded font-mono text-xs">app_metadata.role = &quot;admin&quot;</code>{" "}
              set by a Supabase administrator.
            </p>
            <p className="mt-2">
              If you have just been granted admin access, sign out and sign back in so your
              session JWT picks up the new role.
            </p>
          </div>
        )}
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          {isRoleError && (
            <button
              onClick={async () => { await supabase.auth.signOut(); router.push("/login"); }}
              className="inline-flex items-center gap-1.5 bg-primary text-primary-foreground rounded-lg px-5 py-2.5 text-sm font-semibold hover:opacity-90 transition-opacity"
            >
              Sign out &amp; Sign back in
            </button>
          )}
          <Link href="/" className="inline-flex items-center gap-1.5 border border-border rounded-lg px-5 py-2.5 text-sm hover:bg-secondary transition-colors">
            ← Back to Home
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-10">
      {/* Page header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-6 h-6 rounded bg-primary/10 flex items-center justify-center">
              <svg className="w-3.5 h-3.5 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3v11.25A2.25 2.25 0 0 0 6 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0 1 18 16.5h-2.25m-7.5 0h7.5m-7.5 0-1 3m8.5-3 1 3m0 0 .5 1.5m-.5-1.5h-9.5m0 0-.5 1.5M9 11.25v1.5M12 9v3.75m3-6v6" />
              </svg>
            </div>
            <span className="text-xs font-semibold text-primary uppercase tracking-wide">Admin Portal</span>
          </div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground text-sm mt-0.5">Manage all civic reports in Mangaluru.</p>
        </div>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
          <StatCard
            label="Total Reports"
            value={stats.total_reports}
            icon={
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
              </svg>
            }
          />
          <StatCard
            label="Categories"
            value={Object.keys(stats.by_category).length}
            icon={
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.568 3H5.25A2.25 2.25 0 0 0 3 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 0 0 5.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 0 0 9.568 3Z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 6h.008v.008H6V6Z" />
              </svg>
            }
          />
          <StatCard
            label="Authorities Routed"
            value={Object.keys(stats.by_authority).length}
            icon={
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21m-3.75 3.75h.008v.008h-.008v-.008Zm0 3h.008v.008h-.008v-.008Zm0 3h.008v.008h-.008v-.008Z" />
              </svg>
            }
          />
          <StatCard
            label="Submitted"
            value={stats.by_status["SUBMITTED"] ?? 0}
            icon={
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
              </svg>
            }
          />
        </div>
      )}

      {/* Breakdown panels */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {stats && Object.keys(stats.by_category).length > 0 && (
          <div className="border border-border rounded-xl bg-card p-5">
            <h2 className="font-semibold text-sm mb-4">By Category</h2>
            <div className="space-y-2">
              {Object.entries(stats.by_category)
                .sort(([, a], [, b]) => b - a)
                .map(([cat, count]) => (
                  <div key={cat} className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">{cat}</span>
                    <span className="font-semibold tabular-nums">{count}</span>
                  </div>
                ))}
            </div>
          </div>
        )}
        {stats && Object.keys(stats.by_authority).length > 0 && (
          <div className="border border-border rounded-xl bg-card p-5">
            <h2 className="font-semibold text-sm mb-4">By Authority</h2>
            <div className="space-y-2">
              {Object.entries(stats.by_authority)
                .sort(([, a], [, b]) => b - a)
                .map(([auth, count]) => (
                  <div key={auth} className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">{auth}</span>
                    <span className="font-semibold tabular-nums">{count}</span>
                  </div>
                ))}
            </div>
          </div>
        )}
        {stats && (
          <div className="border border-border rounded-xl bg-card p-5">
            <h2 className="font-semibold text-sm mb-4">By Status</h2>
            <div className="space-y-2">
              {Object.entries(stats.by_status).map(([s, count]) => (
                <div key={s} className="flex items-center justify-between text-sm">
                  <StatusBadge status={s} />
                  <span className="font-semibold tabular-nums">{count}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Reports table */}
      <div className="border border-border rounded-xl bg-card overflow-hidden">
        <div className="px-5 py-4 border-b border-border">
          <h2 className="font-semibold">All Reports</h2>
          <p className="text-xs text-muted-foreground mt-0.5">{reports.length} total records</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[hsl(217,33%,98%)] border-b border-border">
                <th className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide px-4 py-3">Category</th>
                <th className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide px-4 py-3 hidden sm:table-cell">Location</th>
                <th className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide px-4 py-3 hidden md:table-cell">Authority</th>
                <th className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide px-4 py-3">Status</th>
                <th className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide px-4 py-3 hidden lg:table-cell">Confidence</th>
                <th className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide px-4 py-3 hidden lg:table-cell">Submitted</th>
                <th className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {reports.map((r) => (
                <tr key={r.report_id} className="hover:bg-[hsl(217,33%,99%)] transition-colors align-top">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="text-base">{CATEGORY_ICONS[r.category] ?? "📋"}</span>
                      <div>
                        <span className="font-medium block">{r.category_label}</span>
                        <Link
                          href={`/reports/${r.report_id}`}
                          className="text-xs text-primary hover:underline font-mono"
                        >
                          #{r.report_id.slice(0, 8).toUpperCase()}
                        </Link>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground hidden sm:table-cell max-w-[160px]">
                    <span className="truncate block text-xs">{r.area_text || "–"}</span>
                  </td>
                  <td className="px-4 py-3 hidden md:table-cell">
                    {r.recommended_authority ? (
                      <span className="text-primary/80 font-medium text-xs">{r.recommended_authority.short_name}</span>
                    ) : (
                      <span className="text-muted-foreground text-xs">–</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-col gap-1">
                      <StatusBadge status={r.status} />
                      {/* Show rejection reason inline when rejected */}
                      {r.status === "REJECTED" && r.rejection_reason && (
                        <span className="text-xs text-red-600 italic max-w-[160px] truncate" title={r.rejection_reason}>
                          {r.rejection_reason}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 hidden lg:table-cell text-muted-foreground text-xs">
                    {r.confidence > 0 ? `${Math.round(r.confidence * 100)}%` : "–"}
                  </td>
                  <td className="px-4 py-3 hidden lg:table-cell text-muted-foreground text-xs whitespace-nowrap">
                    {formatDate(r.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <ActionButtons
                      report={r}
                      token={token}
                      onSuccess={handleStatusUpdate}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
