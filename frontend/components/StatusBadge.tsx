import { STATUS_COLORS, STATUS_LABELS } from "@/lib/constants";

interface Props {
  status: string;
}

export default function StatusBadge({ status }: Props) {
  const color = STATUS_COLORS[status] ?? "bg-gray-100 text-gray-600";
  const label = STATUS_LABELS[status] ?? status;
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${color}`}
    >
      {label}
    </span>
  );
}
