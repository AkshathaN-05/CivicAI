"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  createReport,
  patchReport,
  type Report,
  type IssueCategory,
  type ReportPatchRequest,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";
import {
  ISSUE_CATEGORIES,
  MANGALURU_AUTHORITIES,
  confidenceLabel,
  formatDate,
} from "@/lib/constants";
import StatusBadge from "@/components/StatusBadge";

// ---------------------------------------------------------------------------
// Stage types
// ---------------------------------------------------------------------------
// capture   — citizen provides photo + location; POST triggers AI pipeline
// ai_review — AI result displayed; citizen reviews/edits category/authority/description
// success   — final confirmed report (from PATCH response)
type Stage = "capture" | "ai_review" | "success";
type PhotoMode = "idle" | "camera" | "preview";
type LocationState = "idle" | "detecting" | "detected" | "error";
// Voice: idle=available, listening=recording, unsupported=no SpeechRecognition
type VoiceState = "idle" | "listening" | "unsupported";

// ---------------------------------------------------------------------------
// Web Speech API — local type definitions (TypeScript dom lib declares these
// on window but not always as standalone globals depending on tsconfig/target)
// ---------------------------------------------------------------------------
interface ISpeechRecognition {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: ISpeechRecognitionEvent) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
interface ISpeechRecognitionEvent {
  results: { [index: number]: { [index: number]: { transcript: string } } };
}

// ---------------------------------------------------------------------------
// Category icon map (unchanged from original)
// ---------------------------------------------------------------------------
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
// Small helpers
// ---------------------------------------------------------------------------
function ErrIcon() {
  return (
    <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
      <path
        fillRule="evenodd"
        d="M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Zm-8-5a.75.75 0 0 1 .75.75v4.5a.75.75 0 0 1-1.5 0v-4.5A.75.75 0 0 1 10 5Zm0 10a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function Spinner({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={`${className} animate-spin`} fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

function ConfidenceChip({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const label = confidenceLabel(value);
  const cls =
    value >= 0.8
      ? "bg-green-100 text-green-700 border-green-200"
      : value >= 0.6
      ? "bg-blue-100 text-blue-700 border-blue-200"
      : "bg-yellow-100 text-yellow-700 border-yellow-200";
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full border ${cls}`}
    >
      {label} · {pct}%
    </span>
  );
}

function StepIndicator({ current }: { current: Stage }) {
  const steps: { id: Stage; label: string }[] = [
    { id: "capture", label: "Photo & Location" },
    { id: "ai_review", label: "AI Review" },
    { id: "success", label: "Submitted" },
  ];
  const idx = steps.findIndex((s) => s.id === current);
  return (
    <div className="flex items-center gap-3 mb-8">
      {steps.map((s, i) => (
        <div key={s.id} className="flex items-center gap-2">
          <div
            className={`w-6 h-6 rounded-full text-xs font-bold flex items-center justify-center ${
              i < idx
                ? "bg-primary/30 text-primary"
                : i === idx
                ? "bg-primary text-primary-foreground"
                : "border-2 border-border text-muted-foreground"
            }`}
          >
            {i < idx ? (
              <svg
                className="w-3 h-3"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={3}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
            ) : (
              i + 1
            )}
          </div>
          <span
            className={`text-xs font-medium hidden sm:block ${
              i === idx ? "text-foreground" : "text-muted-foreground"
            }`}
          >
            {s.label}
          </span>
          {i < steps.length - 1 && <div className="w-8 h-px bg-border" />}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------
export default function NewReportPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [stage, setStage] = useState<Stage>("capture");

  // ── Capture stage ─────────────────────────────────────────────────────────
  const [areaText, setAreaText] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const [submittingCapture, setSubmittingCapture] = useState(false);

  // AI result from Stage 1 POST
  const [aiReport, setAiReport] = useState<Report | null>(null);

  // ── AI Review stage ───────────────────────────────────────────────────────
  const [editCategory, setEditCategory] = useState<IssueCategory | "">("");
  const [editAuthorityId, setEditAuthorityId] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [submittingConfirm, setSubmittingConfirm] = useState(false);

  // Voice input
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const recognitionRef = useRef<ISpeechRecognition | null>(null);

  // ── Success stage ─────────────────────────────────────────────────────────
  const [finalReport, setFinalReport] = useState<Report | null>(null);

  // ── Camera state ──────────────────────────────────────────────────────────
  const [photoMode, setPhotoMode] = useState<PhotoMode>("idle");
  const [cameraError, setCameraError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // ── Location state ────────────────────────────────────────────────────────
  const [locationState, setLocationState] = useState<LocationState>("idle");
  const [locationError, setLocationError] = useState<string | null>(null);
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);

  // ── Auth ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    async function initAuth() {
      const { data: sessionData } = await supabase.auth.getSession();
      if (!sessionData.session) { router.push("/login"); return; }
      const { data: refreshData, error: refreshError } = await supabase.auth.refreshSession();
      if (refreshError || !refreshData.session) { router.push("/login"); return; }
      setToken(refreshData.session.access_token);
      setAuthChecked(true);
    }
    initAuth();
  }, [router]);

  // ── Check voice support on mount ─────────────────────────────────────────
  useEffect(() => {
    if (typeof window === "undefined") return;
    const w = window as unknown as {
      SpeechRecognition?: new () => ISpeechRecognition;
      webkitSpeechRecognition?: new () => ISpeechRecognition;
    };
    if (!w.SpeechRecognition && !w.webkitSpeechRecognition) {
      setVoiceState("unsupported");
    }
  }, []);

  // ── Camera helpers ────────────────────────────────────────────────────────
  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) videoRef.current.srcObject = null;
  }, []);

  useEffect(() => {
    return () => {
      stopCamera();
      if (recognitionRef.current) recognitionRef.current.abort();
    };
  }, [stopCamera]);

  async function openCamera() {
    setCameraError(null);
    setPhotoMode("camera");
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("Camera not available in this browser. Please upload a photo instead.");
      setPhotoMode("idle");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
      streamRef.current = stream;
      setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch(() => {});
        }
      }, 50);
    } catch (err: unknown) {
      stopCamera();
      setPhotoMode("idle");
      const name = (err as { name?: string })?.name ?? "";
      if (name === "NotAllowedError" || name === "PermissionDeniedError") {
        setCameraError("Camera permission was denied. Please allow camera access in your browser settings, or upload a photo instead.");
      } else if (name === "NotFoundError" || name === "DevicesNotFoundError") {
        setCameraError("No camera found on this device. Please upload a photo instead.");
      } else {
        setCameraError("Could not access the camera. Please upload a photo instead.");
      }
    }
  }

  function capturePhoto() {
    if (!videoRef.current || !canvasRef.current) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    stopCamera();
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          setCameraError("Failed to capture photo. Please try again.");
          setPhotoMode("idle");
          return;
        }
        const file = new File([blob], `civic-photo-${Date.now()}.jpg`, { type: "image/jpeg" });
        setPhoto(file);
        setPreview(canvas.toDataURL("image/jpeg"));
        setPhotoMode("preview");
      },
      "image/jpeg",
      0.92
    );
  }

  function retakePhoto() {
    stopCamera();
    setPhoto(null);
    setPreview(null);
    setPhotoMode("idle");
    setCameraError(null);
  }

  function usePhoto() {
    setPhotoMode("idle");
    setCameraError(null);
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setPhoto(file);
    if (file) {
      const reader = new FileReader();
      reader.onload = (ev) => setPreview(ev.target?.result as string);
      reader.readAsDataURL(file);
    } else {
      setPreview(null);
    }
    stopCamera();
    setPhotoMode("idle");
  }

  function removePhoto() {
    stopCamera();
    setPhoto(null);
    setPreview(null);
    setPhotoMode("idle");
    setCameraError(null);
    if (fileRef.current) fileRef.current.value = "";
  }

  // ── Location ──────────────────────────────────────────────────────────────
  function detectLocation() {
    if (!navigator.geolocation) {
      setLocationState("error");
      setLocationError("Location services are not supported by this browser. Please enter your location manually.");
      return;
    }
    setLocationState("detecting");
    setLocationError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords;
        setCoords({ lat: latitude, lng: longitude });
        setAreaText(`${latitude.toFixed(5)}, ${longitude.toFixed(5)}`);
        setLocationState("detected");
        setLocationError(null);
      },
      (err) => {
        setLocationState("error");
        setCoords(null);
        if (err.code === err.PERMISSION_DENIED) {
          setLocationError("Location permission was denied. Please enter your location manually.");
        } else if (err.code === err.POSITION_UNAVAILABLE) {
          setLocationError("Location could not be determined. Please enter your location manually.");
        } else if (err.code === err.TIMEOUT) {
          setLocationError("Location request timed out. Please enter your location manually.");
        } else {
          setLocationError("Could not detect location. Please enter your location manually.");
        }
      },
      { timeout: 10000, maximumAge: 60000 }
    );
  }

  function clearLocation() {
    setLocationState("idle");
    setLocationError(null);
    setAreaText("");
    setCoords(null);
  }

  // ── Stage 1: submit photo + location → POST → AI pipeline ────────────────
  async function handleCaptureSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) { router.push("/login"); return; }

    if (!photo) {
      setCaptureError("Please take or upload a photo of the issue.");
      return;
    }
    if (!areaText.trim() || areaText.trim().length < 2) {
      setCaptureError("Please enter the area or location (minimum 2 characters).");
      return;
    }

    setCaptureError(null);
    setSubmittingCapture(true);

    const fd = new FormData();
    fd.append("area_text", areaText.trim());
    fd.append("photo", photo);
    // Deliberately omit category + description → triggers AI pipeline path on backend
    if (coords) {
      fd.append("lat", String(coords.lat));
      fd.append("lng", String(coords.lng));
    }

    const { data, error } = await createReport(fd, token);
    setSubmittingCapture(false);

    if (error || !data) {
      // apiFetch extracts the backend `detail` string from the JSON body and
      // returns it as `error`.  For image-validation failures (wrong size,
      // unsupported format, corrupt file) the backend sends the exact
      // ImageValidationError message — show it directly so the citizen sees
      // what the problem is.  For AI-pipeline 422s (image valid but
      // unclassifiable) and any other non-HTTP errors, use a generic message.
      const isImageValidationError =
        typeof error === "string" &&
        (error.includes("too small") ||
          error.includes("too large") ||
          error.includes("MIME type") ||
          error.includes("image format") ||
          error.includes("could not be decoded"));
      setCaptureError(
        isImageValidationError
          ? error
          : error === "HTTP 429"
          ? "Too many requests. Please wait a moment and try again."
          : error === "HTTP 422" || (typeof error === "string" && !error.startsWith("HTTP"))
          ? "This photo could not be analysed. It may be unclear or not a civic issue. Please try a different photo."
          : error ?? "Could not process the image. Please try again."
      );
      return;
    }

    setAiReport(data);
    // Pre-fill review fields from AI result
    setEditCategory(data.category as IssueCategory);
    setEditAuthorityId(data.recommended_authority?.id ?? "");
    setEditDescription(data.description ?? "");
    setStage("ai_review");
  }

  // ── Voice input ───────────────────────────────────────────────────────────
  function startVoice() {
    const w = window as unknown as {
      SpeechRecognition?: new () => ISpeechRecognition;
      webkitSpeechRecognition?: new () => ISpeechRecognition;
    };
    const SpeechRec = w.SpeechRecognition ?? w.webkitSpeechRecognition;
    if (!SpeechRec) { setVoiceState("unsupported"); return; }

    const recognition = new SpeechRec();
    recognition.lang = "en-IN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognitionRef.current = recognition;

    recognition.onresult = (event: ISpeechRecognitionEvent) => {
      const transcript = event.results[0]?.[0]?.transcript ?? "";
      if (transcript) {
        setEditDescription((prev) => (prev ? `${prev} ${transcript}` : transcript));
      }
      setVoiceState("idle");
    };
    recognition.onerror = () => setVoiceState("idle");
    recognition.onend = () => setVoiceState("idle");
    recognition.start();
    setVoiceState("listening");
  }

  function stopVoice() {
    if (recognitionRef.current) { recognitionRef.current.stop(); recognitionRef.current = null; }
    setVoiceState("idle");
  }

  // ── Stage 2: citizen confirms → PATCH ────────────────────────────────────
  async function handleConfirmSubmit() {
    if (!token || !aiReport) { router.push("/login"); return; }

    if (!editDescription.trim() || editDescription.trim().length < 10) {
      setConfirmError("Description must be at least 10 characters.");
      return;
    }

    setConfirmError(null);
    setSubmittingConfirm(true);

    const body: ReportPatchRequest = {
      // Always send description — captures what the citizen confirmed/edited
      description: editDescription.trim(),
    };
    if (editCategory && editCategory !== aiReport.category) {
      body.category = editCategory as IssueCategory;
    }
    if (editAuthorityId && editAuthorityId !== (aiReport.recommended_authority?.id ?? "")) {
      body.authority_id = editAuthorityId;
    }

    const { data, error } = await patchReport(aiReport.report_id, body, token);
    setSubmittingConfirm(false);

    if (error || !data) {
      setConfirmError(error ?? "Failed to confirm report. Please try again.");
      return;
    }

    setFinalReport(data);
    setStage("success");
  }

  // ── Reset all ─────────────────────────────────────────────────────────────
  function resetAll() {
    setStage("capture");
    setAreaText("");
    setPhoto(null);
    setPreview(null);
    setPhotoMode("idle");
    setCameraError(null);
    setCaptureError(null);
    setLocationState("idle");
    setLocationError(null);
    setCoords(null);
    setAiReport(null);
    setEditCategory("");
    setEditAuthorityId("");
    setEditDescription("");
    setConfirmError(null);
    setFinalReport(null);
    if (voiceState === "listening") stopVoice();
    if (fileRef.current) fileRef.current.value = "";
  }

  // ── Auth loading ──────────────────────────────────────────────────────────
  if (!authChecked) {
    return (
      <div className="flex flex-col items-center justify-center py-32 gap-3 text-muted-foreground">
        <Spinner className="w-8 h-8 text-primary/40" />
        <span className="text-sm">Checking authentication…</span>
      </div>
    );
  }

  // ==========================================================================
  // STAGE 1 — capture: photo + location only
  // ==========================================================================
  if (stage === "capture") {
    return (
      <div className="max-w-2xl mx-auto px-4 py-10">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-2 text-sm text-muted-foreground mb-3">
            <Link href="/" className="hover:text-foreground transition-colors">Home</Link>
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
            </svg>
            <span className="text-foreground font-medium">Report an Issue</span>
          </div>
          <StepIndicator current="capture" />
          <h1 className="text-2xl font-bold">Take a Photo</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Take or upload a photo of the civic issue and set your location — AI will detect the issue automatically.
          </p>
        </div>

        <form onSubmit={handleCaptureSubmit} noValidate className="space-y-5">

          {/* ── Photo ── */}
          <div>
            <label className="block text-sm font-medium mb-1.5">
              Photo <span className="text-destructive">*</span>
            </label>

            {/* Camera viewfinder */}
            {photoMode === "camera" && (
              <div className="rounded-xl overflow-hidden border border-border bg-black mb-3">
                <div className="relative aspect-video bg-black">
                  {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                  <video ref={videoRef} playsInline muted autoPlay className="w-full h-full object-cover" />
                  <div className="absolute inset-0 border-2 border-white/10 rounded pointer-events-none" />
                </div>
                <canvas ref={canvasRef} className="hidden" />
                <div className="flex items-center justify-between px-4 py-3 bg-black/80">
                  <button type="button" onClick={() => { stopCamera(); setPhotoMode("idle"); setCameraError(null); }}
                    className="px-3 py-2 text-xs font-medium text-white/70 hover:text-white border border-white/20 rounded-lg transition-colors">
                    Cancel
                  </button>
                  <button type="button" onClick={capturePhoto}
                    className="w-14 h-14 rounded-full bg-white border-4 border-white/30 flex items-center justify-center hover:bg-white/90 transition-colors"
                    aria-label="Capture photo">
                    <div className="w-10 h-10 rounded-full bg-primary" />
                  </button>
                  <div className="w-16" />
                </div>
              </div>
            )}

            {/* Preview after capture */}
            {photoMode === "preview" && preview && (
              <div className="rounded-xl overflow-hidden border border-border mb-3">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={preview} alt="Captured" className="w-full object-cover max-h-64" />
                <div className="flex gap-2 p-3 bg-background border-t border-border">
                  <button type="button" onClick={retakePhoto}
                    className="flex-1 border border-border rounded-lg py-2 text-xs font-medium hover:bg-secondary transition-colors">
                    ↺ Retake
                  </button>
                  <button type="button" onClick={usePhoto}
                    className="flex-1 bg-primary text-primary-foreground rounded-lg py-2 text-xs font-medium hover:opacity-90 transition-opacity">
                    ✓ Use Photo
                  </button>
                </div>
              </div>
            )}

            {/* Photo chosen (idle mode with preview) */}
            {photoMode === "idle" && preview && photo && (
              <div className="relative rounded-xl overflow-hidden border border-border h-48 mb-3">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={preview} alt="Preview" className="object-cover w-full h-full" />
                <button type="button" onClick={removePhoto}
                  className="absolute top-2 right-2 w-8 h-8 rounded-full bg-black/60 text-white flex items-center justify-center hover:bg-black/80 transition-colors">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                  </svg>
                </button>
                <div className="absolute bottom-2 left-2 text-xs text-white bg-black/50 px-2 py-0.5 rounded-full backdrop-blur-sm">
                  {photo.name}
                </div>
              </div>
            )}

            {/* No photo yet */}
            {photoMode === "idle" && !preview && (
              <div className="space-y-2">
                <button type="button" onClick={openCamera}
                  className="w-full flex items-center justify-center gap-2 border-2 border-dashed border-primary/40 bg-primary/5 hover:bg-primary/10 rounded-xl py-5 text-primary font-medium text-sm transition-all">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6.827 6.175A2.31 2.31 0 0 1 5.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 0 0-1.134-.175 2.31 2.31 0 0 1-1.64-1.055l-.822-1.316a2.192 2.192 0 0 0-1.736-1.039 48.774 48.774 0 0 0-5.232 0 2.192 2.192 0 0 0-1.736 1.039l-.821 1.316Z" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 12.75a4.5 4.5 0 1 1-9 0 4.5 4.5 0 0 1 9 0ZM18.75 10.5h.008v.008h-.008V10.5Z" />
                  </svg>
                  Take Photo
                </button>
                <button type="button" onClick={() => fileRef.current?.click()}
                  className="w-full flex items-center justify-center gap-2 border-2 border-dashed border-border hover:border-ring hover:bg-accent/30 rounded-xl py-4 text-muted-foreground text-sm transition-all">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
                  </svg>
                  Upload from device
                  <span className="text-xs text-muted-foreground/70">· JPEG, PNG or WebP · max 10 MB</span>
                </button>
              </div>
            )}

            {cameraError && (
              <div className="mt-2 flex items-start gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 px-3 py-2 rounded-lg">
                <svg className="w-3.5 h-3.5 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
                </svg>
                <span>{cameraError}</span>
              </div>
            )}

            <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={handleFileChange} />
          </div>

          {/* ── Location ── */}
          <div>
            <label className="block text-sm font-medium mb-1.5" htmlFor="area_text">
              Area / Location <span className="text-destructive">*</span>
            </label>

            {locationState === "idle" && (
              <button type="button" onClick={detectLocation}
                className="mb-2 inline-flex items-center gap-1.5 text-xs font-medium text-primary border border-primary/30 bg-primary/5 hover:bg-primary/10 px-3 py-1.5 rounded-lg transition-colors">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1 1 15 0Z" />
                </svg>
                Use My Current Location
              </button>
            )}
            {locationState === "detecting" && (
              <div className="mb-2 inline-flex items-center gap-1.5 text-xs text-muted-foreground border border-border bg-accent/30 px-3 py-1.5 rounded-lg">
                <Spinner className="w-3.5 h-3.5" />
                Detecting your location…
              </div>
            )}
            {locationState === "detected" && (
              <div className="mb-2 flex items-center gap-2 flex-wrap">
                <span className="inline-flex items-center gap-1 text-xs font-medium text-green-700 bg-green-50 border border-green-200 px-2.5 py-1 rounded-lg">
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                  </svg>
                  Location detected
                </span>
                <button type="button" onClick={clearLocation} className="text-xs text-muted-foreground hover:text-foreground underline">
                  Use a different location
                </button>
              </div>
            )}
            {locationState === "error" && locationError && (
              <div className="mb-2 flex items-start gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 px-3 py-2 rounded-lg">
                <svg className="w-3.5 h-3.5 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
                </svg>
                <span>{locationError}</span>
              </div>
            )}

            <div className="relative">
              <div className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1 1 15 0Z" />
                </svg>
              </div>
              <input id="area_text" type="text"
                placeholder="e.g. Hampankatta main road, near bus stand"
                value={areaText}
                onChange={(e) => {
                  setAreaText(e.target.value);
                  if (locationState === "detected") setLocationState("idle");
                }}
                className="w-full border border-input rounded-lg pl-9 pr-3 py-2.5 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition-shadow"
              />
            </div>
            {locationState === "idle" && (
              <p className="text-xs text-muted-foreground mt-1">
                Allow location access to automatically fill your report location, or type it manually.
              </p>
            )}
          </div>

          {captureError && (
            <div className="flex items-start gap-2.5 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              <svg className="w-4 h-4 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
              </svg>
              <div className="flex-1">
                <p>{captureError}</p>
                {/* Retry hint if the error was not a validation failure */}
                {!captureError.includes("take") && !captureError.includes("enter") && (
                  <button type="submit" disabled={submittingCapture}
                    className="mt-2 text-xs font-medium text-red-700 underline hover:no-underline disabled:opacity-50">
                    Try again
                  </button>
                )}
              </div>
            </div>
          )}

          <button type="submit" disabled={submittingCapture || !photo}
            className="w-full bg-primary text-primary-foreground font-semibold py-3 rounded-xl hover:opacity-90 transition-opacity disabled:opacity-60 flex items-center justify-center gap-2">
            {submittingCapture ? (
              <>
                <Spinner />
                Analysing photo with AI…
              </>
            ) : (
              <>
                Analyse with AI
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
                </svg>
              </>
            )}
          </button>
        </form>
      </div>
    );
  }

  // ==========================================================================
  // STAGE 2 — ai_review: show AI result, citizen reviews/edits
  // ==========================================================================
  if (stage === "ai_review" && aiReport) {
    const conf = aiReport.confidence;
    const lowConf = conf < 0.6;
    const isDuplicate = aiReport.is_duplicate;

    return (
      <div className="max-w-2xl mx-auto px-4 py-10">
        <div className="mb-6">
          <StepIndicator current="ai_review" />
          <h1 className="text-2xl font-bold">Review AI Analysis</h1>
          <p className="text-muted-foreground text-sm mt-1">
            The AI has analysed your photo. Review the results below — edit anything that looks wrong, then confirm.
          </p>
        </div>

        {/* ── AI result card ── */}
        <div className="border border-border rounded-xl bg-card divide-y divide-border mb-5">

          {/* Detected issue row */}
          <div className="px-5 py-4">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2 flex items-center gap-1.5">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456Z" />
              </svg>
              AI suggested category
            </p>
            <div className="flex items-center justify-between flex-wrap gap-2">
              <span className="text-base font-semibold flex items-center gap-2">
                <span>{CATEGORY_ICONS[aiReport.category] ?? "📋"}</span>
                {aiReport.category_label}
              </span>
              <ConfidenceChip value={conf} />
            </div>
            {/* Low-confidence advisory — honest AI uncertainty */}
            {lowConf && (
              <div className="mt-3 flex items-start gap-2 text-xs text-yellow-700 bg-yellow-50 border border-yellow-200 px-3 py-2 rounded-lg">
                <svg className="w-3.5 h-3.5 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
                </svg>
                <span>
                  <strong>AI is not certain about this category.</strong> Please check the category below and correct it if needed.
                </span>
              </div>
            )}
          </div>

          {/* AI description row */}
          {aiReport.description && (
            <div className="flex items-start gap-4 px-5 py-3.5">
              <span className="text-xs font-medium text-muted-foreground w-28 shrink-0 pt-0.5 uppercase tracking-wide">AI description</span>
              <span className="text-sm flex-1 text-muted-foreground italic">{aiReport.description}</span>
            </div>
          )}

          {/* Location row */}
          <div className="flex items-start gap-4 px-5 py-3.5">
            <span className="text-xs font-medium text-muted-foreground w-28 shrink-0 pt-0.5 uppercase tracking-wide">Location</span>
            <span className="text-sm flex-1">{areaText}</span>
          </div>

          {/* Recommended authority row */}
          {aiReport.recommended_authority && (
            <div className="flex items-start gap-4 px-5 py-3.5">
              <span className="text-xs font-medium text-muted-foreground w-28 shrink-0 pt-0.5 uppercase tracking-wide">AI authority</span>
              <div className="text-sm flex-1">
                <span className="font-medium">{aiReport.recommended_authority.short_name}</span>
                {aiReport.match_reason && (
                  <p className="text-xs text-muted-foreground mt-0.5">{aiReport.match_reason}</p>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Duplicate advisory — only if AI flagged it */}
        {isDuplicate && (
          <div className="flex items-start gap-2 text-xs text-orange-700 bg-orange-50 border border-orange-200 px-4 py-3 rounded-xl mb-5">
            <svg className="w-4 h-4 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
            </svg>
            <span>
              <strong>Possible duplicate:</strong> A similar issue may have already been reported nearby. You can still submit — the admin will review and decide.
            </span>
          </div>
        )}

        {/* ── Editable category override ── */}
        <div className="mb-5">
          <label className="block text-sm font-medium mb-2">
            Confirm Issue Category
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              (AI pre-selected — change if incorrect)
            </span>
          </label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {ISSUE_CATEGORIES.map((c) => (
              <button key={c.value} type="button"
                onClick={() => setEditCategory(c.value as IssueCategory)}
                className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-sm font-medium transition-all text-left ${
                  editCategory === c.value
                    ? "border-primary bg-accent text-primary"
                    : "border-border bg-card hover:border-ring/50 text-muted-foreground hover:text-foreground"
                }`}>
                <span className="text-base">{CATEGORY_ICONS[c.value]}</span>
                <span className="text-xs leading-tight">{c.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* ── Editable authority override ── */}
        <div className="mb-5">
          <label className="block text-sm font-medium mb-1.5" htmlFor="authority_select">
            Responsible Authority
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              (AI pre-selected — change if you know the correct authority)
            </span>
          </label>
          <select id="authority_select" value={editAuthorityId}
            onChange={(e) => setEditAuthorityId(e.target.value)}
            className="w-full border border-input rounded-lg px-3 py-2.5 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent">
            <option value="">— Select authority —</option>
            {MANGALURU_AUTHORITIES.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
        </div>

        {/* ── Editable description + voice input ── */}
        <div className="mb-5">
          <div className="flex items-center justify-between mb-1.5">
            <label className="block text-sm font-medium" htmlFor="description">
              Description <span className="text-destructive">*</span>
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                (AI generated — edit or add your own details)
              </span>
            </label>
            {/* Voice input button — only when SpeechRecognition is available */}
            {voiceState !== "unsupported" && (
              <button type="button"
                onClick={voiceState === "listening" ? stopVoice : startVoice}
                className={`inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors ${
                  voiceState === "listening"
                    ? "bg-red-50 border-red-200 text-red-700 hover:bg-red-100"
                    : "bg-primary/5 border-primary/30 text-primary hover:bg-primary/10"
                }`}
                aria-label={voiceState === "listening" ? "Stop voice input" : "Speak your description"}>
                <svg className={`w-3.5 h-3.5 ${voiceState === "listening" ? "animate-pulse" : ""}`}
                  fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 0 0 6-6v-1.5m-6 7.5a6 6 0 0 1-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 0 1-3-3V4.5a3 3 0 1 1 6 0v8.25a3 3 0 0 1-3 3Z" />
                </svg>
                {voiceState === "listening" ? "Stop" : "Speak"}
              </button>
            )}
          </div>

          {voiceState === "listening" && (
            <div className="mb-2 inline-flex items-center gap-1.5 text-xs text-red-700 bg-red-50 border border-red-200 px-3 py-1.5 rounded-lg">
              <svg className="w-3.5 h-3.5 animate-pulse" fill="currentColor" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="10" />
              </svg>
              Listening… speak now. Tap Stop when done.
            </div>
          )}

          <textarea id="description" rows={5}
            placeholder="Describe the issue clearly — severity, duration, any hazards…"
            value={editDescription}
            onChange={(e) => setEditDescription(e.target.value)}
            className="w-full border border-input rounded-lg px-3 py-2.5 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent resize-none transition-shadow"
          />
          <div className="flex items-center justify-between mt-1">
            <span className="text-xs text-muted-foreground">
              {voiceState === "unsupported"
                ? "Voice input not available in this browser"
                : "Tap the microphone to speak your description"}
            </span>
            <span className="text-xs text-muted-foreground">{editDescription.length}/2000</span>
          </div>
        </div>

        {confirmError && (
          <div className="flex items-start gap-2.5 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 mb-4">
            <ErrIcon />
            {confirmError}
          </div>
        )}

        <div className="flex gap-3">
          <button type="button" onClick={() => setStage("capture")} disabled={submittingConfirm}
            className="flex-1 border border-border rounded-xl py-3 text-sm font-medium hover:bg-secondary transition-colors disabled:opacity-50">
            ← Retake Photo
          </button>
          <button type="button" onClick={handleConfirmSubmit} disabled={submittingConfirm}
            className="flex-1 bg-primary text-primary-foreground font-semibold py-3 rounded-xl hover:opacity-90 transition-opacity disabled:opacity-60 flex items-center justify-center gap-2">
            {submittingConfirm ? (
              <><Spinner />Submitting…</>
            ) : (
              <>
                Confirm &amp; Submit
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                </svg>
              </>
            )}
          </button>
        </div>
      </div>
    );
  }

  // ==========================================================================
  // STAGE 3 — success
  // ==========================================================================
  if (stage === "success" && finalReport) {
    const conf = finalReport.confidence;
    return (
      <div className="max-w-2xl mx-auto px-4 py-10">
        <div className="border border-green-200 bg-gradient-to-br from-green-50 to-emerald-50 rounded-2xl p-8 text-center mb-6">
          <div className="w-16 h-16 rounded-full bg-green-100 border-4 border-green-200 flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-green-900 mb-1">Report Submitted!</h1>
          <p className="text-sm text-green-700">Your civic issue has been recorded and routed to the relevant authority.</p>
          <div className="mt-3 inline-flex items-center gap-1.5 bg-green-100 border border-green-200 rounded-lg px-3 py-1.5">
            <span className="text-xs font-medium text-green-700">Report ID:</span>
            <code className="text-xs font-mono text-green-800">#{finalReport.report_id.slice(0, 8).toUpperCase()}</code>
          </div>
        </div>

        <div className="border border-border rounded-xl bg-card divide-y divide-border mb-5">
          {[
            { label: "Category", value: `${CATEGORY_ICONS[finalReport.category] ?? "📋"} ${finalReport.category_label}` },
            { label: "Location", value: finalReport.area_text },
            { label: "Status", value: <StatusBadge status={finalReport.status} /> },
            { label: "Submitted", value: formatDate(finalReport.created_at) },
          ].map(({ label, value }) => (
            <div key={label} className="flex items-start gap-4 px-5 py-3.5">
              <span className="text-xs font-medium text-muted-foreground w-28 shrink-0 pt-0.5 uppercase tracking-wide">{label}</span>
              <span className="text-sm flex-1">{value}</span>
            </div>
          ))}
        </div>

        {finalReport.recommended_authority && (
          <div className="border border-blue-200 bg-blue-50 rounded-xl p-5 mb-6">
            <p className="text-xs font-semibold text-blue-600 uppercase tracking-wide mb-2">Routed to Authority</p>
            <h3 className="font-bold text-blue-900 text-lg mb-0.5">{finalReport.recommended_authority.name}</h3>
            {finalReport.match_reason && (
              <p className="text-sm text-blue-800 mb-3">{finalReport.match_reason}</p>
            )}
            <div className="flex items-center gap-2 mb-3">
              <span className="text-xs text-blue-700 font-medium">AI Confidence:</span>
              <ConfidenceChip value={conf} />
            </div>
            <div className="text-xs text-blue-700 space-y-1">
              <div>📧 {finalReport.recommended_authority.contact_email}</div>
              <div>📞 {finalReport.recommended_authority.phone}</div>
            </div>
          </div>
        )}

        <div className="flex gap-3">
          <Link href="/reports"
            className="flex-1 text-center border border-border rounded-xl py-3 text-sm font-medium hover:bg-secondary transition-colors">
            My Reports
          </Link>
          <button type="button" onClick={resetAll}
            className="flex-1 bg-primary text-primary-foreground font-semibold py-3 rounded-xl hover:opacity-90 transition-opacity text-sm">
            Submit Another Report
          </button>
        </div>
      </div>
    );
  }

  return null;
}
