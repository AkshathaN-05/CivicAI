"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getReport, type Report } from "@/lib/api";
import { formatDate, confidenceLabel } from "@/lib/constants";
import StatusBadge from "@/components/StatusBadge";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start gap-4 px-4 py-3">
      <span className="text-xs font-medium text-muted-foreground w-36 shrink-0 pt-0.5">
        {label}
      </span>
      <span className="text-sm flex-1">{value}</span>
    </div>
  );
}

export default function ReportDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    getReport(id).then(({ data, error }) => {
      setLoading(false);
      if (error) {
        setError(error);
        return;
      }
      setReport(data);
    });
  }, [id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32 text-muted-foreground text-sm">
        Loading report…
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="max-w-xl mx-auto px-4 py-16 text-center">
        <div className="text-4xl mb-3">🔍</div>
        <p className="font-medium mb-1">Report not found</p>
        <p className="text-muted-foreground text-sm mb-4">
          {error ?? "This report does not exist or has been removed."}
        </p>
        <Link
          href="/reports"
          className="inline-block border border-border rounded-md px-5 py-2 text-sm hover:bg-secondary transition-colors"
        >
          ← Back to Reports
        </Link>
      </div>
    );
  }

  const conf = report.confidence;

  return (
    <div className="max-w-xl mx-auto px-4 py-10">
      <div className="flex items-center gap-2 mb-6">
        <Link
          href="/reports"
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          ← All Reports
        </Link>
      </div>

      <h1 className="text-xl font-bold mb-1">Report Detail</h1>
      <p className="text-xs font-mono text-muted-foreground mb-6">{report.report_id}</p>

      <div className="border border-border rounded-lg divide-y divide-border mb-6">
        <Row label="Category" value={report.category_label} />
        <Row label="Area / Location" value={report.area_text} />
        <Row label="Description" value={report.description} />
        <Row label="Status" value={<StatusBadge status={report.status} />} />
        <Row label="Submitted" value={formatDate(report.created_at)} />
        {report.photo_filename && (
          <Row label="Photo" value={report.photo_filename} />
        )}
      </div>

      {report.recommended_authority && (
        <div className="border border-green-200 bg-green-50 rounded-lg p-4 mb-6">
          <p className="text-xs font-semibold text-green-700 uppercase tracking-wide mb-2">
            Recommended Authority
          </p>
          <p className="font-semibold text-green-900">
            {report.recommended_authority.name}
          </p>
          {report.match_reason && (
            <p className="text-sm text-green-800 mt-1">{report.match_reason}</p>
          )}
          <p className="text-xs text-green-700 mt-2">
            Confidence:{" "}
            <strong>
              {confidenceLabel(conf)} ({Math.round(conf * 100)}%)
            </strong>
          </p>
          <div className="mt-2 text-xs text-green-700 space-y-0.5">
            <div>📧 {report.recommended_authority.contact_email}</div>
            <div>📞 {report.recommended_authority.phone}</div>
          </div>
        </div>
      )}

      <div className="flex gap-3">
        <Link
          href="/reports"
          className="flex-1 text-center border border-border rounded-md py-2.5 text-sm font-medium hover:bg-secondary transition-colors"
        >
          ← All Reports
        </Link>
        <Link
          href="/report/new"
          className="flex-1 text-center bg-primary text-primary-foreground font-semibold py-2.5 rounded-md hover:opacity-90 transition-opacity text-sm"
        >
          Report Another Issue
        </Link>
      </div>
    </div>
  );
}
