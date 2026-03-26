"use client";
import { useState } from "react";

interface IndustryRow {
  industry: string;
  sector: string;
  etf: string;
  price?: number;
  change?: number;
  change_pct?: number;
  // Alpha Vantage enrichment — present only when AV quota allows
  return_1m?: number;
  mean_daily_return?: number;
  stddev_daily?: number;
  // Permanent ETF store — populated after seed-etf-history runs
  returns?: Record<string, number | null>;
  "52w_high"?: number;
  "52w_low"?: number;
  error?: string;
}

interface IndustryData {
  date: string;
  total: number;
  rankings: IndustryRow[];
  by_sector: Record<string, IndustryRow[]>;
  leaders: IndustryRow[];
  laggards: IndustryRow[];
}

function Pct({ v }: { v?: number }) {
  if (v === undefined) return <span className="text-gray-500">—</span>;
  const cls = v > 0 ? "text-green-400" : v < 0 ? "text-red-400" : "text-gray-400";
  return <span className={cls}>{v > 0 ? "+" : ""}{v.toFixed(2)}%</span>;
}

function Dollar({ v }: { v?: number }) {
  if (v === undefined) return <span className="text-gray-500">—</span>;
  const cls = v > 0 ? "text-green-400" : v < 0 ? "text-red-400" : "text-gray-400";
  return <span className={cls}>{v > 0 ? "+$" : v < 0 ? "-$" : "$"}{Math.abs(v).toFixed(2)}</span>;
}

// Check if any row has AV enrichment data
function hasEnrichment(rows: IndustryRow[]): boolean {
  return rows.some((r) => r.return_1m !== undefined);
}

function IndustryTable({ rows, startRank = 1 }: { rows: IndustryRow[]; startRank?: number }) {
  const enriched = hasEnrichment(rows);
  return (
    <table className="w-full text-sm">
      <thead className="bg-gray-900 sticky top-0">
        <tr>
          <th className="text-left px-3 py-2 text-gray-500 font-medium w-8">#</th>
          <th className="text-left px-3 py-2 text-gray-400 font-medium">Industry</th>
          <th className="text-left px-3 py-2 text-gray-400 font-medium">ETF</th>
          <th className="text-right px-3 py-2 text-gray-400 font-medium">Price</th>
          <th className="text-right px-3 py-2 text-gray-400 font-medium">Chg $</th>
          <th className="text-right px-3 py-2 text-gray-400 font-medium">Chg %</th>
          {enriched && <th className="text-right px-3 py-2 text-gray-400 font-medium" title="1-month cumulative return (Alpha Vantage)">1M Return</th>}
          {enriched && <th className="text-right px-3 py-2 text-gray-400 font-medium" title="Mean daily return (Alpha Vantage)">Avg/Day</th>}
          {enriched && <th className="text-right px-3 py-2 text-gray-400 font-medium" title="Daily return standard deviation — higher = more volatile (Alpha Vantage)">Volatility</th>}
          <th className="text-right px-3 py-2 text-amber-500 font-medium text-xs" title="52-week high price (from stored history)">52W Hi</th>
          <th className="text-right px-3 py-2 text-amber-500 font-medium text-xs" title="52-week low price (from stored history)">52W Lo</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={r.industry} className="border-t border-gray-800/60 hover:bg-gray-900/40">
            <td className="px-3 py-2 text-gray-600 text-xs">{startRank + i}</td>
            <td className="px-3 py-2 text-gray-200">{r.industry}</td>
            <td className="px-3 py-2 text-blue-400 font-mono text-xs">{r.etf}</td>
            <td className="px-3 py-2 text-right text-gray-300">
              {r.error ? <span className="text-red-500 text-xs">err</span> : `$${r.price?.toFixed(2) ?? "—"}`}
            </td>
            <td className="px-3 py-2 text-right"><Dollar v={r.change} /></td>
            <td className="px-3 py-2 text-right"><Pct v={r.change_pct} /></td>
            {enriched && (
              <td className="px-3 py-2 text-right">
                {r.return_1m !== undefined
                  ? <Pct v={r.return_1m * 100} />
                  : <span className="text-gray-600 text-xs">—</span>}
              </td>
            )}
            {enriched && (
              <td className="px-3 py-2 text-right">
                {r.mean_daily_return !== undefined
                  ? <Pct v={r.mean_daily_return * 100} />
                  : <span className="text-gray-600 text-xs">—</span>}
              </td>
            )}
            {enriched && (
              <td className="px-3 py-2 text-right text-gray-400 text-xs font-mono">
                {r.stddev_daily !== undefined ? (r.stddev_daily * 100).toFixed(3) + "%" : <span className="text-gray-600">—</span>}
              </td>
            )}
            {/* 52-week range from permanent ETF store */}
            <td className="px-3 py-2 text-right text-xs font-mono text-amber-400">
              {r["52w_high"] != null ? `$${r["52w_high"].toFixed(2)}` : <span className="text-gray-700">—</span>}
            </td>
            <td className="px-3 py-2 text-right text-xs font-mono text-amber-600">
              {r["52w_low"] != null ? `$${r["52w_low"].toFixed(2)}` : <span className="text-gray-700">—</span>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function IndustryTracker({ data }: { data: IndustryData }) {
  const [view, setView] = useState<"ranked" | "sector">("ranked");
  const enriched = hasEnrichment(data.rankings);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Industry Tracker</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {data.total} industries · Finnhub{enriched ? " + Alpha Vantage" : " (yfinance fallback available)"} · {data.date}
          </p>
        </div>
        <div className="flex gap-1 bg-gray-900 rounded-lg p-1">
          {(["ranked", "sector"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`px-3 py-1.5 text-sm rounded-md transition-colors capitalize ${
                view === v ? "bg-gray-700 text-white" : "text-gray-400 hover:text-white"
              }`}
            >
              {v}
            </button>
          ))}
        </div>
      </div>

      {/* AV enrichment notice */}
      {enriched && (
        <div className="px-4 py-2 rounded-lg border border-violet-800/40 bg-violet-950/10 text-xs text-violet-300">
          Alpha Vantage enrichment active — 1-month return, mean daily return, and volatility shown in the table (soft limit: 20 calls/day).
        </div>
      )}

      {/* Top 5 Leaders & Laggards */}
      <div className="grid grid-cols-2 gap-4">
        <div className="p-4 rounded-xl border border-green-800/60 bg-green-950/10">
          <h3 className="text-xs font-semibold text-green-400 uppercase tracking-wide mb-3">Top Leaders</h3>
          {data.leaders.map((r) => (
            <div key={r.industry} className="flex justify-between items-center text-sm py-1">
              <div>
                <span className="text-gray-200">{r.industry}</span>
                <span className="text-gray-600 text-xs ml-1">{r.etf}</span>
              </div>
              <Pct v={r.change_pct} />
            </div>
          ))}
        </div>
        <div className="p-4 rounded-xl border border-red-800/60 bg-red-950/10">
          <h3 className="text-xs font-semibold text-red-400 uppercase tracking-wide mb-3">Top Laggards</h3>
          {data.laggards.map((r) => (
            <div key={r.industry} className="flex justify-between items-center text-sm py-1">
              <div>
                <span className="text-gray-200">{r.industry}</span>
                <span className="text-gray-600 text-xs ml-1">{r.etf}</span>
              </div>
              <Pct v={r.change_pct} />
            </div>
          ))}
        </div>
      </div>

      {/* Main table */}
      <div className="rounded-xl border border-gray-800 overflow-hidden">
        {view === "ranked" ? (
          <IndustryTable rows={data.rankings} startRank={1} />
        ) : (
          Object.entries(data.by_sector).map(([sector, rows]) => (
            <div key={sector}>
              <div className="px-3 py-2 bg-gray-900/80 border-t border-gray-800 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                {sector}
              </div>
              <IndustryTable rows={rows} startRank={1} />
            </div>
          ))
        )}
      </div>
    </div>
  );
}
