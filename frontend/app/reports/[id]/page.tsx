"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { getReport, type Report } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { formatDate, confidenceLabel } from "@/lib/constants";
import StatusBadge from "@/components/StatusBadge";

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-4 px-5 py-3.5">
      <span className="text-xs font-medium text-muted-foreground w-36 shrink-0 pt-0.5 uppercase tracking-wide">
        {label}
      </span>
      <div className="text-sm flex-1">{children}</div>
    </div>
  );
}

export default function ReportDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    supabase.auth.getSession().then(({ data }) => {
      if (!data.session) { router.push("/login"); return; }
      getReport(id, data.session.access_token).then(({ data: r, error: e }) => {
        setLoading(false);
        if (e) { setError(e); return; }
        setReport(r);
      });
    });
  }, [id, router]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-32 gap-3 text-muted-foreground">
        <svg className="w-8 h-8 animate-spin text-primary/40" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <span className="text-sm">Loading report…</span>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="max-w-lg mx-auto px-4 py-20 text-center">
        <div className="w-16 h-16 rounded-full bg-red-50 flex items-center justify-center mx-auto mb-5">
          <svg className="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
          </svg>
        </div>
        <h2 className="font-semibold text-lg mb-2">Report not found</h2>
        <p className="text-muted-foreground text-sm mb-6">
          {error ?? "This report does not exist or you don't have access."}
        </p>
        <Link
          href="/reports"
          className="inline-flex items-center gap-1.5 border border-border rounded-lg px-5 py-2.5 text-sm hover:bg-secondary transition-colors"
        >
          ← Back to Reports
        </Link>
      </div>
    );
  }

  const conf = report.confidence;

  return (
    <div className="max-w-2xl mx-auto px-4 py-10">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-muted-foreground mb-6">
        <Link href="/reports" className="hover:text-foreground transition-colors">Reports</Link>
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
        </svg>
        <span className="text-foreground font-medium">{report.category_label}</span>
      </div>

      {/* Header card */}
      <div className="border border-border rounded-xl bg-card p-5 mb-4">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div>
            <h1 className="text-xl font-bold">{report.category_label}</h1>
            <p className="text-xs text-muted-foreground font-mono mt-1">#{report.report_id.slice(0, 8).toUpperCase()}</p>
          </div>
          <StatusBadge status={report.status} />
        </div>
        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1 1 15 0Z" />
          </svg>
          {report.area_text}
        </div>
      </div>

      {/* Rejection notice — shown prominently when report is rejected */}
      {report.status === "REJECTED" && (
        <div className="border border-red-200 bg-red-50 rounded-xl p-4 mb-4">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-lg bg-red-100 border border-red-200 flex items-center justify-center shrink-0 mt-0.5">
              <svg className="w-4 h-4 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            </div>
            <div>
              <p className="font-semibold text-red-800 text-sm mb-0.5">Report not accepted</p>
              {report.rejection_reason ? (
                <p className="text-sm text-red-700">
                  <span className="font-medium">Reason: </span>{report.rejection_reason}
                </p>
              ) : (
                <p className="text-sm text-red-600 italic">No reason provided.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Detail rows */}
      <div className="border border-border rounded-xl bg-card divide-y divide-border mb-4">
        <DetailRow label="Description">{report.description || <span className="text-muted-foreground italic">No description</span>}</DetailRow>
        <DetailRow label="Status"><StatusBadge status={report.status} /></DetailRow>
        <DetailRow label="Submitted">{formatDate(report.created_at)}</DetailRow>
        {report.photo_filename && (
          <DetailRow label="Photo">
            <span className="font-mono text-xs bg-accent px-2 py-0.5 rounded">{report.photo_filename}</span>
          </DetailRow>
        )}
      </div>

      {/* Authority card */}
      {report.recommended_authority && (
        <div className="border border-blue-200 bg-blue-50 rounded-xl p-5 mb-6">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center">
              <svg className="w-4 h-4 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21m-3.75 3.75h.008v.008h-.008v-.008Zm0 3h.008v.008h-.008v-.008Zm0 3h.008v.008h-.008v-.008Z" />
              </svg>
            </div>
            <div>
              <p className="text-xs font-semibold text-blue-600 uppercase tracking-wide">AI Recommended Authority</p>
            </div>
          </div>
          <h3 className="font-semibold text-blue-900 mb-0.5">{report.recommended_authority.name}</h3>
          {report.match_reason && (
            <p className="text-sm text-blue-800 mb-3">{report.match_reason}</p>
          )}
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs font-medium text-blue-700">Match confidence:</span>
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
              conf >= 0.9 ? "bg-green-100 text-green-700" :
              conf >= 0.7 ? "bg-blue-100 text-blue-700" :
              "bg-yellow-100 text-yellow-700"
            }`}>
              {confidenceLabel(conf)} · {Math.round(conf * 100)}%
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-blue-700">
            <a href={`mailto:${report.recommended_authority.contact_email}`} className="flex items-center gap-1.5 hover:underline">
              <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75" />
              </svg>
              {report.recommended_authority.contact_email}
            </a>
            <div className="flex items-center gap-1.5">
              <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 0 0 2.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 0 1-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 0 0-1.091-.852H4.5A2.25 2.25 0 0 0 2.25 4.5v2.25Z" />
              </svg>
              {report.recommended_authority.phone}
            </div>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-3">
        <Link
          href="/reports"
          className="flex-1 text-center border border-border rounded-lg py-2.5 text-sm font-medium hover:bg-secondary transition-colors"
        >
          ← All Reports
        </Link>
        <Link
          href="/report/new"
          className="flex-1 text-center bg-primary text-primary-foreground font-semibold py-2.5 rounded-lg hover:opacity-90 transition-opacity text-sm"
        >
          Report Another Issue
        </Link>
      </div>
    </div>
  );
}
