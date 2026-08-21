"use client";

import { useState, useRef } from "react";
import Image from "next/image";
import Link from "next/link";
import { createReport, type Report } from "@/lib/api";
import { ISSUE_CATEGORIES, confidenceLabel, formatDate } from "@/lib/constants";
import StatusBadge from "@/components/StatusBadge";

type Step = "form" | "review" | "success";

interface FormValues {
  category: string;
  area_text: string;
  description: string;
  photo: File | null;
}

const EMPTY: FormValues = {
  category: "",
  area_text: "",
  description: "",
  photo: null,
};

export default function NewReportPage() {
  const [step, setStep] = useState<Step>("form");
  const [values, setValues] = useState<FormValues>(EMPTY);
  const [preview, setPreview] = useState<string | null>(null);
  const [errors, setErrors] = useState<Partial<FormValues & { submit: string }>>({});
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<Report | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // -----------------------------------------------------------------------
  // Validation
  // -----------------------------------------------------------------------
  function validate(): boolean {
    const e: typeof errors = {};
    if (!values.category) e.category = "Please select an issue category.";
    if (!values.area_text.trim() || values.area_text.trim().length < 2)
      e.area_text = "Please enter the area or location (min 2 characters).";
    if (!values.description.trim() || values.description.trim().length < 10)
      e.description = "Description must be at least 10 characters.";
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setValues((v) => ({ ...v, photo: file }));
    if (file) {
      const reader = new FileReader();
      reader.onload = (ev) => setPreview(ev.target?.result as string);
      reader.readAsDataURL(file);
    } else {
      setPreview(null);
    }
  }

  function handleReview(e: React.FormEvent) {
    e.preventDefault();
    if (validate()) setStep("review");
  }

  async function handleSubmit() {
    setSubmitting(true);
    setErrors({});
    const fd = new FormData();
    fd.append("category", values.category);
    fd.append("area_text", values.area_text.trim());
    fd.append("description", values.description.trim());
    if (values.photo) fd.append("photo", values.photo);

    const { data, error } = await createReport(fd);
    setSubmitting(false);

    if (error || !data) {
      setErrors({ submit: error ?? "Submission failed. Please try again." });
      return;
    }
    setResult(data);
    setStep("success");
  }

  const categoryLabel =
    ISSUE_CATEGORIES.find((c) => c.value === values.category)?.label ?? values.category;

  // -----------------------------------------------------------------------
  // STEP: form
  // -----------------------------------------------------------------------
  if (step === "form") {
    return (
      <div className="max-w-xl mx-auto px-4 py-10">
        <h1 className="text-2xl font-bold mb-1">Report a Civic Issue</h1>
        <p className="text-muted-foreground text-sm mb-8">
          Fill in the details below. AI will recommend the relevant authority — you
          review before anything is submitted.
        </p>

        <form onSubmit={handleReview} noValidate className="space-y-5">
          {/* Category */}
          <div>
            <label className="block text-sm font-medium mb-1" htmlFor="category">
              Issue Category <span className="text-destructive">*</span>
            </label>
            <select
              id="category"
              value={values.category}
              onChange={(e) => setValues((v) => ({ ...v, category: e.target.value }))}
              className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="">Select a category…</option>
              {ISSUE_CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
            {errors.category && (
              <p className="text-destructive text-xs mt-1">{errors.category}</p>
            )}
          </div>

          {/* Area */}
          <div>
            <label className="block text-sm font-medium mb-1" htmlFor="area_text">
              Area / Location <span className="text-destructive">*</span>
            </label>
            <input
              id="area_text"
              type="text"
              placeholder="e.g. Hampankatta main road, near bus stand"
              value={values.area_text}
              onChange={(e) => setValues((v) => ({ ...v, area_text: e.target.value }))}
              className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
            />
            {errors.area_text && (
              <p className="text-destructive text-xs mt-1">{errors.area_text}</p>
            )}
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium mb-1" htmlFor="description">
              Description <span className="text-destructive">*</span>
            </label>
            <textarea
              id="description"
              rows={4}
              placeholder="Describe the issue in detail…"
              value={values.description}
              onChange={(e) => setValues((v) => ({ ...v, description: e.target.value }))}
              className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring resize-none"
            />
            {errors.description && (
              <p className="text-destructive text-xs mt-1">{errors.description}</p>
            )}
          </div>

          {/* Photo */}
          <div>
            <label className="block text-sm font-medium mb-1">
              Photo{" "}
              <span className="text-muted-foreground font-normal">(optional)</span>
            </label>
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="w-full border-2 border-dashed border-input rounded-md py-4 text-sm text-muted-foreground hover:border-ring transition-colors"
            >
              {values.photo ? values.photo.name : "Click to attach a photo (JPEG/PNG, max 10 MB)"}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={handleFileChange}
            />
            {preview && (
              <div className="mt-3 relative w-full h-40 rounded-md overflow-hidden border border-border">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={preview}
                  alt="Preview"
                  className="object-cover w-full h-full"
                />
              </div>
            )}
          </div>

          <button
            type="submit"
            className="w-full bg-primary text-primary-foreground font-semibold py-2.5 rounded-md hover:opacity-90 transition-opacity"
          >
            Next: Review AI Recommendation →
          </button>
        </form>
      </div>
    );
  }

  // -----------------------------------------------------------------------
  // STEP: review
  // -----------------------------------------------------------------------
  if (step === "review") {
    return (
      <div className="max-w-xl mx-auto px-4 py-10">
        <div className="mb-6">
          <span className="inline-block bg-yellow-100 text-yellow-800 text-xs font-semibold px-2.5 py-1 rounded mb-3">
            ⚠️ AI Recommendation — Please review before submitting
          </span>
          <h1 className="text-2xl font-bold">Review Your Report</h1>
          <p className="text-muted-foreground text-sm mt-1">
            The AI has recommended an authority based on your issue type and
            location. Review carefully — nothing is filed until you confirm.
          </p>
        </div>

        <div className="border border-border rounded-lg divide-y divide-border">
          <Row label="Category" value={categoryLabel} />
          <Row label="Area / Location" value={values.area_text} />
          <Row label="Description" value={values.description} />
          {values.photo && <Row label="Photo" value={values.photo.name} />}
        </div>

        {/* Authority recommendation — fetched on submit; shown as optimistic preview */}
        <div className="mt-6 border border-blue-200 bg-blue-50 rounded-lg p-4">
          <p className="text-xs font-semibold text-blue-700 uppercase tracking-wide mb-2">
            Authority will be recommended after submission
          </p>
          <p className="text-sm text-blue-900">
            Based on <strong>{categoryLabel}</strong> issues in{" "}
            <strong>{values.area_text}</strong>, the AI will route to the most
            relevant Mangaluru authority. You will see the full recommendation in
            the confirmation screen.
          </p>
        </div>

        {errors.submit && (
          <div className="mt-4 p-3 bg-destructive/10 border border-destructive/20 rounded-md text-sm text-destructive">
            {errors.submit}
          </div>
        )}

        <div className="mt-6 flex gap-3">
          <button
            type="button"
            onClick={() => setStep("form")}
            disabled={submitting}
            className="flex-1 border border-border rounded-md py-2.5 text-sm font-medium hover:bg-secondary transition-colors disabled:opacity-50"
          >
            ← Edit
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting}
            className="flex-1 bg-primary text-primary-foreground font-semibold py-2.5 rounded-md hover:opacity-90 transition-opacity disabled:opacity-60"
          >
            {submitting ? "Submitting…" : "Confirm & Submit"}
          </button>
        </div>
      </div>
    );
  }

  // -----------------------------------------------------------------------
  // STEP: success
  // -----------------------------------------------------------------------
  if (step === "success" && result) {
    const conf = result.confidence;
    return (
      <div className="max-w-xl mx-auto px-4 py-10">
        <div className="text-center mb-8">
          <div className="text-5xl mb-3">✅</div>
          <h1 className="text-2xl font-bold mb-1">Report Submitted</h1>
          <p className="text-muted-foreground text-sm">
            Your civic issue has been recorded successfully.
          </p>
        </div>

        <div className="border border-border rounded-lg divide-y divide-border mb-6">
          <Row
            label="Report ID"
            value={
              <span className="font-mono text-xs">{result.report_id}</span>
            }
          />
          <Row label="Category" value={result.category_label} />
          <Row label="Area" value={result.area_text} />
          <Row
            label="Status"
            value={<StatusBadge status={result.status} />}
          />
          <Row label="Submitted" value={formatDate(result.created_at)} />
        </div>

        {result.recommended_authority && (
          <div className="border border-green-200 bg-green-50 rounded-lg p-4 mb-6">
            <p className="text-xs font-semibold text-green-700 uppercase tracking-wide mb-1">
              Recommended Authority
            </p>
            <p className="font-semibold text-green-900">
              {result.recommended_authority.name}
            </p>
            {result.match_reason && (
              <p className="text-sm text-green-800 mt-1">{result.match_reason}</p>
            )}
            <p className="text-xs text-green-700 mt-2">
              Match confidence:{" "}
              <strong>
                {confidenceLabel(conf)} ({Math.round(conf * 100)}%)
              </strong>
            </p>
            <div className="mt-2 text-xs text-green-700 space-y-0.5">
              <div>📧 {result.recommended_authority.contact_email}</div>
              <div>📞 {result.recommended_authority.phone}</div>
            </div>
          </div>
        )}

        <div className="flex gap-3">
          <Link
            href="/reports"
            className="flex-1 text-center border border-border rounded-md py-2.5 text-sm font-medium hover:bg-secondary transition-colors"
          >
            View All Reports
          </Link>
          <button
            type="button"
            onClick={() => {
              setValues(EMPTY);
              setPreview(null);
              setResult(null);
              setErrors({});
              setStep("form");
            }}
            className="flex-1 bg-primary text-primary-foreground font-semibold py-2.5 rounded-md hover:opacity-90 transition-opacity"
          >
            Submit Another
          </button>
        </div>
      </div>
    );
  }

  return null;
}

// ---------------------------------------------------------------------------
// Helper component
// ---------------------------------------------------------------------------
function Row({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-4 px-4 py-3">
      <span className="text-xs font-medium text-muted-foreground w-32 shrink-0 pt-0.5">
        {label}
      </span>
      <span className="text-sm flex-1">{value}</span>
    </div>
  );
}
