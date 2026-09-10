interface DataStatus {
  expected: number;
  available: number;
  failed: number;
  partial: boolean;
  failed_symbols?: string[];
}

interface FreshnessBadgeProps {
  fetchedAt?: string;
  source?: string;
  dataStatus?: DataStatus;
  checkpointStatus?: string;
}

// Data older than this is shown as stale regardless of checkpoint_status
const STALE_THRESHOLD_MS = 60 * 60 * 1000; // 1 hour

export default function FreshnessBadge({
  fetchedAt,
  source,
  dataStatus,
  checkpointStatus,
}: FreshnessBadgeProps) {
  const isPartial = dataStatus?.partial;
  const ageMs = fetchedAt ? Date.now() - new Date(fetchedAt).getTime() : Infinity;
  const isAgedOut = ageMs > STALE_THRESHOLD_MS;
  const isFresh = checkpointStatus === "fetch_ok" && !isAgedOut;
  const isLimited = (checkpointStatus === "fetch_partial" || isPartial) && !isAgedOut;

  const badgeColor = isFresh && !isPartial
    ? "bg-green-900/40 text-green-300 border-green-700"
    : isLimited
    ? "bg-yellow-900/40 text-yellow-300 border-yellow-700"
    : "bg-gray-800 text-gray-400 border-gray-700";

  const label = isFresh && !isPartial
    ? "fresh"
    : isLimited
    ? "partial"
    : "stale";

  const ageLabel = fetchedAt
    ? (() => {
        const diffMs = Date.now() - new Date(fetchedAt).getTime();
        const mins = Math.floor(diffMs / 60000);
        if (mins < 1) return "just now";
        if (mins < 60) return `${mins}m ago`;
        return `${Math.floor(mins / 60)}h ago`;
      })()
    : null;

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className={`border rounded-full px-2 py-0.5 font-medium ${badgeColor}`}>
        {label}
      </span>
      {source && (
        <span className="text-gray-500">
          via <span className="text-gray-400">{source}</span>
        </span>
      )}
      {ageLabel && <span className="text-gray-500">{ageLabel}</span>}
      {dataStatus && (
        <span className="text-gray-500">
          {dataStatus.available}/{dataStatus.expected} symbols
          {isPartial && dataStatus.failed_symbols && dataStatus.failed_symbols.length > 0 && (
            <span className="text-yellow-600 ml-1">
              (missing: {dataStatus.failed_symbols.slice(0, 3).join(", ")}
              {dataStatus.failed_symbols.length > 3
                ? ` +${dataStatus.failed_symbols.length - 3} more`
                : ""})
            </span>
          )}
        </span>
      )}
    </div>
  );
}
