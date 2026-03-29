"use client";
import { useRef, useState, useMemo } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";

interface IndustryReturn {
  etf: string;
  industry: string;
  updated?: string;
  "52w_high"?: number;
  "52w_low"?: number;
  returns: {
    "1d"?: number; "3d"?: number;
    "1w"?: number; "2w"?: number; "3w"?: number;
    "1m"?: number; "3m"?: number; "6m"?: number;
    "ytd"?: number;
    "1y"?: number; "2y"?: number; "5y"?: number; "10y"?: number;
  };
}

interface IndustryReturnsData {
  date: string;
  total: number;
  industries: IndustryReturn[];
  leaders: Record<string, { industry: string; etf: string; return: number }[]>;
  laggards: Record<string, { industry: string; etf: string; return: number }[]>;
  periods_available: string[];
}

const PERIODS = ["1d", "3d", "1w", "2w", "3w", "1m", "3m", "6m", "ytd", "1y", "2y", "5y", "10y"] as const;
type Period = typeof PERIODS[number];

const PERIOD_LABELS: Record<Period, string> = {
  "1d": "1D", "3d": "3D",
  "1w": "1W", "2w": "2W", "3w": "3W",
  "1m": "1M", "3m": "3M", "6m": "6M",
  "ytd": "YTD",
  "1y": "1Y", "2y": "2Y", "5y": "5Y", "10y": "10Y",
};

function returnColor(v: number | undefined): string {
  if (v == null) return "text-gray-600";
  if (v >= 5)  return "text-green-300";
  if (v >= 1)  return "text-green-500";
  if (v >= 0)  return "text-green-700";
  if (v >= -1) return "text-red-700";
  if (v >= -5) return "text-red-500";
  return "text-red-300";
}

function fmt(v: number | undefined): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}

export function IndustryReturns({ data }: { data: IndustryReturnsData }) {
  const [sortPeriod, setSortPeriod] = useState<Period>("1m");
  const [view, setView] = useState<"top" | "bottom" | "all">("all");
  const [show52w, setShow52w] = useState(false);

  const sorted = useMemo(
    () => [...data.industries].sort((a, b) => {
      const av = a.returns[sortPeriod] ?? -Infinity;
      const bv = b.returns[sortPeriod] ?? -Infinity;
      return bv - av;
    }),
    [data.industries, sortPeriod]
  );

  const displayed =
    view === "top" ? sorted.slice(0, 10) :
    view === "bottom" ? sorted.slice(-10).reverse() :
    sorted;

  const topLeaders = data.leaders?.[sortPeriod]?.slice(0, 3) ?? [];
  const topLaggards = data.laggards?.[sortPeriod]?.slice(0, 3) ?? [];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white">Industry Returns</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Multi-period ETF returns across {data.total} industries · {data.date}
        </p>
      </div>

      {/* Leaders / Laggards for selected period */}
      {(topLeaders.length > 0 || topLaggards.length > 0) && (
        <div className="grid grid-cols-2 gap-4">
          <div className="p-3 rounded-xl border border-green-800/60 bg-green-950/10">
            <h3 className="text-xs font-semibold text-green-400 uppercase tracking-wide mb-2">
              Top {PERIOD_LABELS[sortPeriod]} Leaders
            </h3>
            {topLeaders.map((r) => (
              <div key={r.industry} className="flex justify-between text-sm py-0.5">
                <span className="text-gray-300 truncate mr-2">{r.industry}</span>
                <span className="text-green-400 font-mono shrink-0">{fmt(r.return)}</span>
              </div>
            ))}
          </div>
          <div className="p-3 rounded-xl border border-red-800/60 bg-red-950/10">
            <h3 className="text-xs font-semibold text-red-400 uppercase tracking-wide mb-2">
              Top {PERIOD_LABELS[sortPeriod]} Laggards
            </h3>
            {topLaggards.map((r) => (
              <div key={r.industry} className="flex justify-between text-sm py-0.5">
                <span className="text-gray-300 truncate mr-2">{r.industry}</span>
                <span className="text-red-400 font-mono shrink-0">{fmt(r.return)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-xs text-gray-500">Sort by:</span>
        <div className="flex gap-1 bg-gray-900 rounded-lg p-1">
          {PERIODS.map((p) => (
            <button
              key={p}
              onClick={() => setSortPeriod(p)}
              className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                sortPeriod === p ? "bg-blue-700 text-white" : "text-gray-400 hover:text-white"
              }`}
            >
              {PERIOD_LABELS[p]}
            </button>
          ))}
        </div>

        <div className="flex gap-1 bg-gray-900 rounded-lg p-1 ml-auto">
          {(["top", "bottom", "all"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`px-3 py-1 text-xs rounded-md transition-colors capitalize ${
                view === v ? "bg-gray-700 text-white" : "text-gray-400 hover:text-white"
              }`}
            >
              {v === "top" ? "Top 10" : v === "bottom" ? "Bottom 10" : "All"}
            </button>
          ))}
        </div>

        <button
          onClick={() => setShow52w(!show52w)}
          className={`px-3 py-1 text-xs rounded-md border transition-colors ${
            show52w
              ? "border-amber-600 text-amber-400 bg-amber-950/20"
              : "border-gray-700 text-gray-500 hover:text-white"
          }`}
        >
          52W Hi/Lo
        </button>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-gray-800 overflow-x-auto">
        <VirtualReturnsTable
          rows={displayed}
          sortPeriod={sortPeriod}
          show52w={show52w}
        />
      </div>
    </div>
  );
}

function VirtualReturnsTable({
  rows,
  sortPeriod,
  show52w,
}: {
  rows: IndustryReturn[];
  sortPeriod: Period;
  show52w: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => 40,
    overscan: 5,
  });

  const virtualRows = virtualizer.getVirtualItems();
  const paddingTop = virtualRows.length > 0 ? virtualRows[0].start : 0;
  const paddingBottom = virtualRows.length > 0
    ? virtualizer.getTotalSize() - virtualRows[virtualRows.length - 1].end
    : 0;

  return (
    <div ref={containerRef} className="overflow-y-auto max-h-[560px]">
      <table className="w-full text-sm">
        <thead className="sticky top-0 z-10 bg-gray-950">
          <tr className="border-b border-gray-800 text-gray-500 text-xs">
            <th className="text-left p-3 font-medium">ETF</th>
            <th className="text-left p-3 font-medium max-w-[200px]">Industry</th>
            {PERIODS.map((p) => (
              <th
                key={p}
                className={`text-right p-3 font-medium ${sortPeriod === p ? "text-blue-400" : ""}`}
              >
                {PERIOD_LABELS[p]}
              </th>
            ))}
            {show52w && <th className="text-right p-3 font-medium text-amber-500">52W Hi</th>}
            {show52w && <th className="text-right p-3 font-medium text-amber-500">52W Lo</th>}
          </tr>
        </thead>
        <tbody>
          {paddingTop > 0 && <tr><td style={{ height: paddingTop }} /></tr>}
          {virtualRows.map((vr) => {
            const ind = rows[vr.index];
            return (
              <tr
                key={ind.etf + ind.industry}
                className={`border-b border-gray-800/50 hover:bg-gray-900/50 transition-colors ${
                  vr.index % 2 === 0 ? "" : "bg-gray-900/20"
                }`}
              >
                <td className="p-3 font-mono font-bold text-blue-400">{ind.etf}</td>
                <td className="p-3 text-gray-300 text-xs max-w-[200px] truncate">{ind.industry}</td>
                {PERIODS.map((p) => (
                  <td
                    key={p}
                    className={`p-3 text-right font-mono text-xs ${returnColor(ind.returns[p])} ${
                      sortPeriod === p ? "font-semibold" : ""
                    }`}
                  >
                    {fmt(ind.returns[p])}
                  </td>
                ))}
                {show52w && (
                  <td className="p-3 text-right font-mono text-xs text-amber-400">
                    {ind["52w_high"] != null ? `$${ind["52w_high"].toFixed(2)}` : "—"}
                  </td>
                )}
                {show52w && (
                  <td className="p-3 text-right font-mono text-xs text-amber-600">
                    {ind["52w_low"] != null ? `$${ind["52w_low"].toFixed(2)}` : "—"}
                  </td>
                )}
              </tr>
            );
          })}
          {paddingBottom > 0 && <tr><td style={{ height: paddingBottom }} /></tr>}
        </tbody>
      </table>
    </div>
  );
}
