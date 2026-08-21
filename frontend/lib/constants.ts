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
