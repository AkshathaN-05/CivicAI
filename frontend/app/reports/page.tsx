"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listReports, type Report } from "@/lib/api";
import { formatDate } from "@/lib/constants";
import StatusBadge from "@/components/StatusBadge";

export default function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listReports().then(({ data, error }) => {
      setLoading(false);
      if (error) {
        setError(error);
        return;
      }
      setReports(data?.reports ?? []);
    });
  }, []);

  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold">Recent Reports</h1>
          <p className="text-muted-foreground text-sm mt-0.5">
            All civic issues submitted this session.
          </p>
        </div>
        <Link
          href="/report/new"
          className="bg-primary text-primary-foreground text-sm font-medium px-4 py-2 rounded-md hover:opacity-90 transition-opacity"
        >
          + Report Issue
        </Link>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-20 text-muted-foreground text-sm">
          Loading reports…
        </div>
      )}

      {!loading && error && (
        <div className="border border-destructive/20 bg-destructive/5 rounded-lg p-6 text-center">
          <p className="text-destructive text-sm">{error}</p>
          <p className="text-muted-foreground text-xs mt-1">
            Make sure the backend is running on{" "}
            <code className="font-mono">http://127.0.0.1:8000</code>.
          </p>
        </div>
      )}

      {!loading && !error && reports.length === 0 && (
        <div className="border border-border rounded-lg p-12 text-center">
          <div className="text-4xl mb-3">📭</div>
          <p className="font-medium mb-1">No reports yet</p>
          <p className="text-muted-foreground text-sm mb-4">
            Be the first to report a civic issue in Mangaluru.
          </p>
          <Link
            href="/report/new"
            className="inline-block bg-primary text-primary-foreground text-sm font-medium px-5 py-2 rounded-md hover:opacity-90 transition-opacity"
          >
            Report an Issue
          </Link>
        </div>
      )}

      {!loading && !error && reports.length > 0 && (
        <div className="space-y-3">
          {reports.map((r) => (
            <Link
              key={r.report_id}
              href={`/reports/${r.report_id}`}
              className="block border border-border rounded-lg p-4 hover:border-ring transition-colors bg-card"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="font-medium text-sm">{r.category_label}</span>
                    <StatusBadge status={r.status} />
                  </div>
                  <p className="text-sm text-muted-foreground truncate">{r.area_text}</p>
                  {r.recommended_authority && (
                    <p className="text-xs text-muted-foreground mt-0.5">
                      → {r.recommended_authority.short_name}
                    </p>
                  )}
                </div>
                <div className="text-xs text-muted-foreground whitespace-nowrap shrink-0">
                  {formatDate(r.created_at)}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
