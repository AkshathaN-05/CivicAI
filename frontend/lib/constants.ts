export const ISSUE_CATEGORIES = [
  { value: "pothole", label: "Pothole" },
  { value: "waterlogging", label: "Waterlogging" },
  { value: "broken_streetlight", label: "Broken Streetlight" },
  { value: "garbage_overflow", label: "Garbage Overflow" },
  { value: "open_drain", label: "Open Drain" },
  { value: "illegal_construction", label: "Illegal Construction" },
  { value: "water_supply", label: "Water Supply Issue" },
  { value: "sewage", label: "Sewage Problem" },
  { value: "road_damage", label: "Road Damage" },
  { value: "other", label: "Other" },
] as const;

export const STATUS_LABELS: Record<string, string> = {
  SUBMITTED: "Submitted",
  UNDER_REVIEW: "Under Review",
  RESOLVED: "Resolved",
  REJECTED: "Rejected",
  ARCHIVED: "Archived",
};

export const STATUS_COLORS: Record<string, string> = {
  SUBMITTED: "bg-blue-100 text-blue-800",
  UNDER_REVIEW: "bg-yellow-100 text-yellow-800",
  RESOLVED: "bg-green-100 text-green-800",
  REJECTED: "bg-red-100 text-red-800",
  ARCHIVED: "bg-gray-100 text-gray-600",
};

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function confidenceLabel(c: number): string {
  if (c >= 0.95) return "Very High";
  if (c >= 0.8) return "High";
  if (c >= 0.6) return "Medium";
  return "Low";
}

export interface AuthorityOption {
  id: string;
  name: string;
  short_name: string;
}

// Immutable authority list — mirrors backend/data/mangaluru_authorities.json (ADR-001).
// Hardcoded per discovery: the backend has no GET /authorities/ endpoint and the
// data is explicitly declared immutable.
export const MANGALURU_AUTHORITIES: AuthorityOption[] = [
  { id: "auth-001", name: "Mangaluru City Corporation (MCC)", short_name: "MCC" },
  { id: "auth-002", name: "Mangaluru City Corporation — North Zone", short_name: "MCC North" },
  { id: "auth-003", name: "Mangaluru Water Works Department", short_name: "MWWD" },
  { id: "auth-004", name: "National Highways Authority of India — Mangaluru", short_name: "NHAI Mangaluru" },
  { id: "auth-005", name: "MESCOM (Electricity Supply Company)", short_name: "MESCOM" },
  { id: "auth-006", name: "Mangaluru Urban Development Authority (MUDA)", short_name: "MUDA" },
  { id: "auth-007", name: "MCC Drainage Division", short_name: "MCC Drainage" },
];
