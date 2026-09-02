"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { listReports, type Report } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { formatDate, confidenceLabel } from "@/lib/constants";
import StatusBadge from "@/components/StatusBadge";

const CATEGORY_ICONS: Record<string, string> = {
  pothole: "🕳️",
  waterlogging: "💧",
  broken_streetlight: "💡",
  garbage_overflow: "🗑️",
  open_drain: "🏚️",
  illegal_construction: "🏗️",
  water_supply: "🚿",
  sewage: "⚠️",
  road_damage: "🛣️",
  other: "📋",
};

// ---------------------------------------------------------------------------
// Status notices — derived from the already-loaded report list.
// Priority order: REJECTED > RESOLVED > UNDER_REVIEW.
// Uses only data already returned for the authenticated citizen; no extra
// API calls, no new backend endpoints.
// ---------------------------------------------------------------------------

interface NoticeItem {
  report: Report;
  priority: number; // lower = shown first
}

function buildNotices(reports: Report[]): NoticeItem[] {
  const items: NoticeItem[] = [];
  for (const r of reports) {
    if (r.status === "REJECTED") items.push({ report: r, priority: 0 });
    else if (r.status === "RESOLVED") items.push({ report: r, priority: 1 });
    else if (r.status === "UNDER_REVIEW") items.push({ report: r, priority: 2 });
  }
  // Sort by priority, then newest-first within each priority tier.
  items.sort((a, b) =>
    a.priority !== b.priority
      ? a.priority - b.priority
      : new Date(b.report.created_at).getTime() - new Date(a.report.created_at).getTime()
  );
  return items;
}

function StatusNotices({ reports }: { reports: Report[] }) {
  const notices = buildNotices(reports);

  // Collapse if more than 3 — show "and N more"
  const MAX_VISIBLE = 3;
  // Hook must be called unconditionally (Rules of Hooks).
  const [expanded, setExpanded] = useState(false);

  if (notices.length === 0) return null;

  const visible = expanded ? notices : notices.slice(0, MAX_VISIBLE);
  const hiddenCount = notices.length - MAX_VISIBLE;

  return (
    <div className="mb-6 space-y-2" role="status" aria-label="Report status updates">
      {visible.map(({ report: r }) => {
        if (r.status === "REJECTED") {
          return (
            <Link
              key={r.report_id}
              href={`/reports/${r.report_id}`}
              className="flex items-start gap-3 border border-red-200 bg-red-50 rounded-xl px-4 py-3 hover:bg-red-100 transition-colors group"
            >
              <div className="w-6 h-6 rounded-full bg-red-100 border border-red-300 flex items-center justify-center shrink-0 mt-0.5">
                <svg className="w-3.5 h-3.5 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-red-800 leading-snug">
                  {r.category_label} — report not accepted
                </p>
                {r.rejection_reason ? (
                  <p className="text-xs text-red-700 mt-0.5">
                    Reason: {r.rejection_reason}
                  </p>
                ) : (
                  <p className="text-xs text-red-500 italic mt-0.5">No reason provided.</p>
                )}
                <p className="text-xs text-red-400 mt-0.5 truncate">{r.area_text}</p>
              </div>
              <svg className="w-4 h-4 text-red-300 group-hover:text-red-500 transition-colors shrink-0 mt-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
              </svg>
            </Link>
          );
        }

        if (r.status === "RESOLVED") {
          return (
            <Link
              key={r.report_id}
              href={`/reports/${r.report_id}`}
              className="flex items-start gap-3 border border-green-200 bg-green-50 rounded-xl px-4 py-3 hover:bg-green-100 transition-colors group"
            >
              <div className="w-6 h-6 rounded-full bg-green-100 border border-green-300 flex items-center justify-center shrink-0 mt-0.5">
                <svg className="w-3.5 h-3.5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                </svg>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-green-800 leading-snug">
                  {r.category_label} — your report has been resolved
                </p>
                <p className="text-xs text-green-600 mt-0.5 truncate">{r.area_text}</p>
              </div>
              <svg className="w-4 h-4 text-green-300 group-hover:text-green-500 transition-colors shrink-0 mt-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
              </svg>
            </Link>
          );
        }

        if (r.status === "UNDER_REVIEW") {
          return (
            <Link
              key={r.report_id}
              href={`/reports/${r.report_id}`}
              className="flex items-start gap-3 border border-yellow-200 bg-yellow-50 rounded-xl px-4 py-3 hover:bg-yellow-100 transition-colors group"
            >
              <div className="w-6 h-6 rounded-full bg-yellow-100 border border-yellow-300 flex items-center justify-center shrink-0 mt-0.5">
                <svg className="w-3.5 h-3.5 text-yellow-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 0 1 0-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.964-7.178Z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                </svg>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-yellow-800 leading-snug">
                  {r.category_label} — your report is under review
                </p>
                <p className="text-xs text-yellow-600 mt-0.5 truncate">{r.area_text}</p>
              </div>
              <svg className="w-4 h-4 text-yellow-300 group-hover:text-yellow-500 transition-colors shrink-0 mt-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
              </svg>
            </Link>
          );
        }

        return null;
      })}

      {/* "Show N more" / "Show less" toggle — only if > MAX_VISIBLE notices */}
      {hiddenCount > 0 && !expanded && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="w-full text-xs text-muted-foreground hover:text-foreground border border-border rounded-xl py-2 bg-card hover:bg-secondary transition-colors"
        >
          Show {hiddenCount} more status update{hiddenCount > 1 ? "s" : ""}
        </button>
      )}
      {expanded && notices.length > MAX_VISIBLE && (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="w-full text-xs text-muted-foreground hover:text-foreground border border-border rounded-xl py-2 bg-card hover:bg-secondary transition-colors"
        >
          Show fewer updates
        </button>
      )}
    </div>
  );
}

export default function ReportsPage() {
  const router = useRouter();
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Keep an up-to-date token ref so the Realtime refetch can use it without
  // capturing a stale closure.
  const tokenRef = useRef<string>("");

  useEffect(() => {
    // cancelled is set to true when the effect is cleaned up (unmount or
    // re-run).  All async continuations check this flag before touching state
    // or creating subscriptions so that:
    //   • state is never updated after unmount, and
    //   • a stale async run does not create a zombie channel.
    let cancelled = false;

    // channel is set synchronously (before any await) so the cleanup function
    // can always find and remove it, even when React Strict Mode fires the
    // cleanup before the first async tick completes.
    //
    // We use a unique suffix so that each effect invocation gets a brand-new
    // Supabase channel object.  Supabase internally caches channels by name;
    // reusing "citizen-reports-status" across effect runs (before the previous
    // channel is fully cleaned up) causes the SDK to find the already-subscribed
    // object and throw:
    //   "cannot add postgres_changes callbacks … after subscribe()"
    const channelName = `citizen-reports-status-${Date.now()}`;
    const channel = supabase
      .channel(channelName)
      .on(
        "postgres_changes",
        { event: "UPDATE", schema: "public", table: "reports" },
        async () => {
          // Re-fetch from backend to get the authoritative persisted status.
          // Use the ref so we always have a non-stale token.
          if (cancelled) return;
          const freshToken = tokenRef.current;
          if (!freshToken) return;
          const { data: updated, error: fetchErr } = await listReports(freshToken);
          // Guard again after the await — component may have unmounted.
          if (cancelled) return;
          if (!fetchErr && updated) {
            setReports(updated.reports);
          }
        }
      );

    async function loadReports() {
      // Check we have a session first.
      const { data: sessionData } = await supabase.auth.getSession();
      if (cancelled) return;
      if (!sessionData.session) {
        router.push("/login");
        return;
      }

      // Refresh the token so the JWT's sub matches the current user.
      // A stale cached token could carry the wrong user_id, causing the
      // backend to filter reports for a different account.
      const { data: refreshData, error: refreshError } =
        await supabase.auth.refreshSession();

      if (cancelled) return;
      if (refreshError || !refreshData.session) {
        // Refresh failed — session is dead; send to login.
        router.push("/login");
        return;
      }

      const token = refreshData.session.access_token;
      tokenRef.current = token;

      const { data: d, error: e } = await listReports(token);
      if (cancelled) return;
      setLoading(false);
      if (e) { setError(e); return; }
      setReports(d?.reports ?? []);

      // -----------------------------------------------------------------------
      // Supabase Realtime — subscribe to status changes on the reports table.
      // The channel was created (and the postgres_changes handler registered)
      // synchronously above, BEFORE this async function was called, so
      // .subscribe() is always the final step — never called before .on().
      // -----------------------------------------------------------------------
      if (!cancelled) {
        channel.subscribe();
      }
    }

    loadReports();

    return () => {
      cancelled = true;
      // Remove the channel regardless of whether subscribe() was reached.
      // supabase.removeChannel handles channels that were never subscribed.
      supabase.removeChannel(channel);
    };
  }, [router]);

  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      {/* Page header */}
      <div className="flex items-start justify-between mb-8 gap-4">
        <div>
          <h1 className="text-2xl font-bold">My Reports</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Civic issues you have submitted in Mangaluru.
            {!loading && !error && reports.length > 0 && (
              <span className="ml-1 inline-flex items-center bg-accent text-accent-foreground text-xs font-medium px-2 py-0.5 rounded-full">
                {reports.length} {reports.length === 1 ? "report" : "reports"}
              </span>
            )}
          </p>
        </div>
        <Link
          href="/report/new"
          className="inline-flex items-center gap-1.5 bg-primary text-primary-foreground text-sm font-semibold px-4 py-2 rounded-lg hover:opacity-90 transition-opacity shrink-0"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          Report Issue
        </Link>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex flex-col items-center justify-center py-24 gap-3 text-muted-foreground">
          <svg className="w-8 h-8 animate-spin text-primary/40" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="text-sm">Loading your reports…</span>
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <div className="border border-red-200 bg-red-50 rounded-xl p-8 text-center">
          <div className="text-3xl mb-3">⚠️</div>
          <p className="font-medium text-red-700 mb-1">Could not load reports</p>
          <p className="text-sm text-red-600">{error}</p>
          <p className="text-xs text-muted-foreground mt-3">
            Make sure the backend is running on{" "}
            <code className="font-mono bg-white px-1 rounded">http://127.0.0.1:8000</code>
          </p>
        </div>
      )}

      {/* Empty */}
      {!loading && !error && reports.length === 0 && (
        <div className="border-2 border-dashed border-border rounded-xl p-16 text-center">
          <div className="w-16 h-16 rounded-full bg-accent flex items-center justify-center mx-auto mb-5">
            <svg className="w-8 h-8 text-primary/50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
            </svg>
          </div>
          <h3 className="font-semibold text-lg mb-2">No reports yet</h3>
          <p className="text-muted-foreground text-sm mb-6 max-w-xs mx-auto">
            Be the first to report a civic issue in Mangaluru.
          </p>
          <Link
            href="/report/new"
            className="inline-flex items-center gap-1.5 bg-primary text-primary-foreground text-sm font-semibold px-5 py-2.5 rounded-lg hover:opacity-90 transition-opacity"
          >
            Report an Issue
          </Link>
        </div>
      )}

      {/* Status notices — only shown when reports are loaded and any have actionable statuses */}
      {!loading && !error && reports.length > 0 && (
        <StatusNotices reports={reports} />
      )}

      {/* Reports list */}
      {!loading && !error && reports.length > 0 && (
        <div className="space-y-3">
          {reports.map((r) => (
            <Link
              key={r.report_id}
              href={`/reports/${r.report_id}`}
              className={`group flex items-start gap-4 border rounded-xl p-4 bg-card hover:shadow-sm transition-all ${
                r.status === "REJECTED"
                  ? "border-red-200 hover:border-red-300"
                  : r.status === "RESOLVED"
                  ? "border-green-200 hover:border-green-300"
                  : "border-border hover:border-ring/50"
              }`}
            >
              {/* Category icon */}
              <div className="w-10 h-10 rounded-lg bg-accent flex items-center justify-center shrink-0 text-lg">
                {CATEGORY_ICONS[r.category] ?? "📋"}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className="font-semibold text-sm">{r.category_label}</span>
                  <StatusBadge status={r.status} />
                </div>
                <div className="flex items-center gap-1 text-xs text-muted-foreground mb-1">
                  <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1 1 15 0Z" />
                  </svg>
                  <span className="truncate">{r.area_text || "–"}</span>
                </div>
                {/* Inline rejection reason on the card — shown directly without opening the report */}
                {r.status === "REJECTED" && r.rejection_reason && (
                  <p className="text-xs text-red-600 mt-1">
                    Reason: {r.rejection_reason}
                  </p>
                )}
                {r.recommended_authority && r.status !== "REJECTED" && (
                  <div className="flex items-center gap-1 text-xs text-primary/70">
                    <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21m-3.75 3.75h.008v.008h-.008v-.008Zm0 3h.008v.008h-.008v-.008Zm0 3h.008v.008h-.008v-.008Z" />
                    </svg>
                    {r.recommended_authority.short_name}
                    {r.confidence > 0 && (
                      <span className="ml-1 text-muted-foreground">
                        · {confidenceLabel(r.confidence)}
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* Timestamp + arrow */}
              <div className="text-right shrink-0">
                <div className="text-xs text-muted-foreground whitespace-nowrap mb-2">
                  {formatDate(r.created_at)}
                </div>
                <svg className="w-4 h-4 text-muted-foreground group-hover:text-foreground transition-colors ml-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                </svg>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
