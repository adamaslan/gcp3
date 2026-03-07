"use client";
import { useState } from "react";

interface IndustryReturn {
  etf: string;
  industry: string;
  updated?: string;
  returns: {
    "1w"?: number;
    "2w"?: number;
    "1m"?: number;
    "2m"?: number;
    "3m"?: number;
    "6m"?: number;
    "52w"?: number;
    "2y"?: number;
    "3y"?: number;
    "5y"?: number;
    "10y"?: number;
  };
}

interface IndustryReturnsData {
  date: string;
  total: number;
  industries: IndustryReturn[];
}

const PERIODS = ["1w", "2w", "1m", "3m", "6m", "52w", "2y", "5y"] as const;
type Period = typeof PERIODS[number];

const PERIOD_LABELS: Record<Period, string> = {
  "1w": "1W",
  "2w": "2W",
  "1m": "1M",
  "3m": "3M",
  "6m": "6M",
  "52w": "1Y",
  "2y": "2Y",
  "5y": "5Y",
};

function returnColor(v: number | undefined): string {
  if (v === undefined || v === null) return "text-gray-600";
  if (v >= 5) return "text-green-300";
  if (v >= 1) return "text-green-500";
  if (v >= 0) return "text-green-700";
  if (v >= -1) return "text-red-700";
  if (v >= -5) return "text-red-500";
  return "text-red-300";
}

function fmt(v: number | undefined): string {
  if (v === undefined || v === null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}

export function IndustryReturns({ data }: { data: IndustryReturnsData }) {
  const [sortPeriod, setSortPeriod] = useState<Period>("1m");
  const [view, setView] = useState<"top" | "bottom" | "all">("all");

  const sorted = [...data.industries].sort((a, b) => {
    const av = a.returns[sortPeriod] ?? -Infinity;
    const bv = b.returns[sortPeriod] ?? -Infinity;
    return bv - av;
  });

  const displayed =
    view === "top" ? sorted.slice(0, 10) :
    view === "bottom" ? sorted.slice(-10).reverse() :
    sorted;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white">Industry Returns</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Multi-period ETF returns across {data.total} industries · {data.date}
        </p>
      </div>

      {/* Sort period */}
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
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-gray-800">
        <table className="w-full text-sm">
          <thead>
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
            </tr>
          </thead>
          <tbody>
            {displayed.map((ind, i) => (
              <tr key={ind.etf} className={`border-b border-gray-800/50 hover:bg-gray-900/50 transition-colors ${i % 2 === 0 ? "" : "bg-gray-900/20"}`}>
                <td className="p-3 font-mono font-bold text-blue-400">{ind.etf}</td>
                <td className="p-3 text-gray-300 text-xs max-w-[200px] truncate">{ind.industry}</td>
                {PERIODS.map((p) => (
                  <td key={p} className={`p-3 text-right font-mono text-xs ${returnColor(ind.returns[p])} ${sortPeriod === p ? "font-semibold" : ""}`}>
                    {fmt(ind.returns[p])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
