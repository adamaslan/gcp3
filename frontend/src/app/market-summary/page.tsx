"use client";
import { useState, useEffect } from "react";
import { MarketSummary } from "@/components/MarketSummary";

const DAY_OPTIONS = [7, 14, 30] as const;
type Days = typeof DAY_OPTIONS[number];

export default function MarketSummaryPage() {
  const [days, setDays] = useState<Days>(7);
  const [data, setData] = useState<object | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetch(`/api/market-summary?days=${days}`, { signal: controller.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`Error ${r.status}`);
        return r.json();
      })
      .then((d) => { setData(d); setLoading(false); })
      .catch((e) => {
        if (e.name !== "AbortError") { setError(String(e)); setLoading(false); }
      });
    return () => { controller.abort(); };
  }, [days]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-500">Window:</span>
        <div className="flex gap-1 bg-gray-900 rounded-lg p-1">
          {DAY_OPTIONS.map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
                days === d ? "bg-gray-700 text-white" : "text-gray-400 hover:text-white"
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>
      {loading && <div className="text-gray-500 text-sm py-10 text-center">Loading…</div>}
      {error && <div className="text-red-400 text-sm">{error}</div>}
      {data && !loading && <MarketSummary data={data as Parameters<typeof MarketSummary>[0]["data"]} />}
    </div>
  );
}
