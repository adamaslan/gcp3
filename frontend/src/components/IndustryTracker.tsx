"use client";
import { useRef, useState, useMemo } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";

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
  returns_stale_as_of?: string;
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

const RETURN_PERIODS = ["1d", "3d", "1w", "2w", "3w", "1m", "3m", "6m", "ytd", "1y", "2y", "5y", "10y"] as const;
type ReturnPeriod = typeof RETURN_PERIODS[number];
const RETURN_PERIOD_LABELS: Record<ReturnPeriod, string> = {
  "1d": "1D", "3d": "3D",
  "1w": "1W", "2w": "2W", "3w": "3W",
  "1m": "1M", "3m": "3M", "6m": "6M",
  "ytd": "YTD",
  "1y": "1Y", "2y": "2Y", "5y": "5Y", "10y": "10Y",
};

function hasStoredReturns(rows: IndustryRow[]): boolean {
  return rows.some((r) => r.returns && Object.keys(r.returns).length > 0);
}

function ReturnCell({ v }: { v?: number | null }) {
  if (v == null) return <span className="text-gray-700">—</span>;
  const cls = v >= 5 ? "text-green-300" : v >= 0 ? "text-green-500" : v >= -5 ? "text-red-500" : "text-red-300";
  return <span className={cls}>{v >= 0 ? "+" : ""}{v.toFixed(2)}%</span>;
}

type SortKey = "industry" | "price" | "change" | "change_pct" | "52w_high" | "52w_low" | ReturnPeriod;

function SortHeader({
  label, sortKey, current, dir, onClick, className,
}: {
  label: string; sortKey: SortKey; current: SortKey; dir: "asc" | "desc";
  onClick: (k: SortKey) => void; className?: string;
}) {
  const active = current === sortKey;
  return (
    <th
      className={`px-4 py-2 font-medium cursor-pointer select-none hover:text-white ${className ?? ""} ${active ? "text-white" : "text-gray-400"}`}
      onClick={() => onClick(sortKey)}
    >
      {label}{active ? (dir === "desc" ? " ▼" : " ▲") : ""}
    </th>
  );
}

function IndustryTable({
  rows,
  startRank = 1,
  showReturns,
  selectedPeriods,
}: {
  rows: IndustryRow[];
  startRank?: number;
  showReturns: boolean;
  selectedPeriods?: ReturnPeriod[];
}) {
  const enriched = hasEnrichment(rows);
  const hasReturns = showReturns && hasStoredReturns(rows);
  const periodsToShow = selectedPeriods && selectedPeriods.length > 0 ? selectedPeriods : RETURN_PERIODS;
  const [sortKey, setSortKey] = useState<SortKey>(hasReturns ? "1d" : "change_pct");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  function handleSort(k: SortKey) {
    if (k === sortKey) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(k);
      setSortDir("desc");
    }
  }

  const sorted = useMemo(() => [...rows].sort((a, b) => {
    let av: number | string | undefined;
    let bv: number | string | undefined;
    if (sortKey === "industry") { av = a.industry; bv = b.industry; }
    else if (sortKey === "price") { av = a.price; bv = b.price; }
    else if (sortKey === "change") { av = a.change; bv = b.change; }
    else if (sortKey === "change_pct") { av = a.change_pct; bv = b.change_pct; }
    else if (sortKey === "52w_high") { av = a["52w_high"]; bv = b["52w_high"]; }
    else if (sortKey === "52w_low") { av = a["52w_low"]; bv = b["52w_low"]; }
    else { av = a.returns?.[sortKey as ReturnPeriod] ?? undefined; bv = b.returns?.[sortKey as ReturnPeriod] ?? undefined; }
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === "string" && typeof bv === "string") {
      return sortDir === "desc" ? bv.localeCompare(av) : av.localeCompare(bv);
    }
    return sortDir === "desc" ? (bv as number) - (av as number) : (av as number) - (bv as number);
  }), [rows, sortKey, sortDir]);

  const containerRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: sorted.length,
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
        <thead className="bg-gray-900 sticky top-0 z-10">
          <tr>
            <th className="text-left px-4 py-2 text-gray-500 font-medium w-8">#</th>
            <SortHeader label="Industry" sortKey="industry" current={sortKey} dir={sortDir} onClick={handleSort} className="text-left" />
            <th className="text-left px-4 py-2 text-gray-400 font-medium">ETF</th>
            {!hasReturns && (
              <>
                <SortHeader label="Price" sortKey="price" current={sortKey} dir={sortDir} onClick={handleSort} className="text-right" />
                <SortHeader label="Chg $" sortKey="change" current={sortKey} dir={sortDir} onClick={handleSort} className="text-right" />
                <SortHeader label="Chg %" sortKey="change_pct" current={sortKey} dir={sortDir} onClick={handleSort} className="text-right" />
              </>
            )}
            {enriched && <th className="text-right px-4 py-2 text-gray-400 font-medium text-xs" title="1-month cumulative return (Alpha Vantage)">1M Return</th>}
            {enriched && <th className="text-right px-4 py-2 text-gray-400 font-medium text-xs" title="Mean daily return (Alpha Vantage)">Avg/Day</th>}
            {enriched && <th className="text-right px-4 py-2 text-gray-400 font-medium text-xs" title="Daily return standard deviation — higher = more volatile (Alpha Vantage)">Vol</th>}
            {hasReturns && periodsToShow.map((p) => (
              <SortHeader key={p} label={RETURN_PERIOD_LABELS[p]} sortKey={p} current={sortKey} dir={sortDir} onClick={handleSort} className="text-right text-blue-300 text-sm font-semibold" />
            ))}
            {!hasReturns && (
              <>
                <SortHeader label="52W Hi" sortKey="52w_high" current={sortKey} dir={sortDir} onClick={handleSort} className="text-right text-amber-500 text-xs" />
                <SortHeader label="52W Lo" sortKey="52w_low" current={sortKey} dir={sortDir} onClick={handleSort} className="text-right text-amber-500 text-xs" />
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {paddingTop > 0 && <tr><td style={{ height: paddingTop }} /></tr>}
          {virtualRows.map((vr) => {
            const r = sorted[vr.index];
            return (
              <tr key={r.industry} className="border-t border-gray-800/60 hover:bg-gray-900/40">
                <td className="px-4 py-2 text-gray-600 text-xs">{startRank + vr.index}</td>
                <td className="px-4 py-2 text-gray-200 font-medium">{r.industry}</td>
                <td className="px-4 py-2 text-blue-400 font-mono text-xs">{r.etf}</td>
                {!hasReturns && (
                  <>
                    <td className="px-4 py-2 text-right text-gray-300">
                      {r.error ? <span className="text-red-500 text-xs">err</span> : `$${r.price?.toFixed(2) ?? "—"}`}
                    </td>
                    <td className="px-4 py-2 text-right"><Dollar v={r.change} /></td>
                    <td className="px-4 py-2 text-right"><Pct v={r.change_pct} /></td>
                  </>
                )}
                {enriched && (
                  <td className="px-4 py-2 text-right text-xs">
                    {r.return_1m !== undefined
                      ? <Pct v={r.return_1m * 100} />
                      : <span className="text-gray-600 text-xs">—</span>}
                  </td>
                )}
                {enriched && (
                  <td className="px-4 py-2 text-right text-xs">
                    {r.mean_daily_return !== undefined
                      ? <Pct v={r.mean_daily_return * 100} />
                      : <span className="text-gray-600 text-xs">—</span>}
                  </td>
                )}
                {enriched && (
                  <td className="px-4 py-2 text-right text-gray-400 text-xs font-mono">
                    {r.stddev_daily !== undefined ? (r.stddev_daily * 100).toFixed(3) + "%" : <span className="text-gray-600">—</span>}
                  </td>
                )}
                {hasReturns && periodsToShow.map((p) => (
                  <td key={p} className="px-4 py-2 text-right text-sm font-mono">
                    <ReturnCell v={r.returns?.[p]} />
                  </td>
                ))}
              </tr>
            );
          })}
          {paddingBottom > 0 && <tr><td style={{ height: paddingBottom }} /></tr>}
        </tbody>
      </table>
    </div>
  );
}

export function IndustryTracker({ data }: { data: IndustryData }) {
  const [view, setView] = useState<"ranked" | "sector">("ranked");
  const [showReturns, setShowReturns] = useState(false);
  const [leaderPeriod, setLeaderPeriod] = useState<ReturnPeriod>("1d");
  const [selectedPeriods, setSelectedPeriods] = useState<ReturnPeriod[]>(["1d", "1w", "1m", "3m", "ytd", "1y"]);
  const enriched = hasEnrichment(data.rankings);
  const hasReturns = hasStoredReturns(data.rankings);

  const periodRanked = useMemo(() => {
    if (leaderPeriod === "1d") return data.rankings;
    return [...data.rankings].sort((a, b) => {
      const av = a.returns?.[leaderPeriod] ?? null;
      const bv = b.returns?.[leaderPeriod] ?? null;
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return bv - av;
    });
  }, [data.rankings, leaderPeriod]);

  const leaders = periodRanked.slice(0, 5);
  const laggards = periodRanked.slice(-5).reverse();

  const periodVal = (r: IndustryRow): number | undefined => {
    if (leaderPeriod === "1d") return r.change_pct;
    return r.returns?.[leaderPeriod] ?? undefined;
  };

  const allPeriods = RETURN_PERIODS.map((p) => ({ key: p, label: RETURN_PERIOD_LABELS[p] }));

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Industry Tracker</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {data.total} industries · Finnhub{enriched ? " + Alpha Vantage" : " (yfinance fallback available)"} · {data.date}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {hasReturns && (
            <button
              onClick={() => setShowReturns(!showReturns)}
              className={`px-3 py-1.5 text-xs rounded-md border transition-colors ${
                showReturns
                  ? "border-blue-600 text-blue-400 bg-blue-950/20"
                  : "border-gray-700 text-gray-500 hover:text-white"
              }`}
            >
              Returns
            </button>
          )}
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
      </div>

      {/* Stale returns notice */}
      {data.returns_stale_as_of && (
        <div className="px-4 py-2 rounded-lg border border-gray-700/40 bg-gray-900/40 text-xs text-gray-500" suppressHydrationWarning>
          Returns &amp; 52W data as of {new Date(data.returns_stale_as_of).toLocaleString()} — live update unavailable
        </div>
      )}

      {/* AV enrichment notice */}
      {enriched && (
        <div className="px-4 py-2 rounded-lg border border-violet-800/40 bg-violet-950/10 text-xs text-violet-300">
          Alpha Vantage enrichment active — 1-month return, mean daily return, and volatility shown in the table (soft limit: 20 calls/day).
        </div>
      )}

      {/* 52W data missing notice */}
      {!hasReturns && (
        <div className="px-4 py-2 rounded-lg border border-amber-800/30 bg-amber-950/10 text-xs text-amber-500">
          52W Hi/Lo and multi-period returns require ETF history to be seeded. Run <code className="font-mono bg-gray-900 px-1 rounded">POST /admin/seed-etf-history</code> once to populate.
        </div>
      )}

      {/* Top 5 Leaders & Laggards */}
      <div className="space-y-3">
        {/* Period selector */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-gray-600 mr-1">Period:</span>
          {allPeriods.map(({ key, label }) => {
            const disabled = key !== "1d" && !hasReturns;
            return (
              <button
                key={key}
                disabled={disabled}
                onClick={() => setLeaderPeriod(key)}
                className={`px-2 py-0.5 text-xs rounded transition-colors ${
                  leaderPeriod === key
                    ? "bg-blue-700 text-white"
                    : disabled
                    ? "text-gray-700 cursor-not-allowed"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="p-4 rounded-xl border border-green-800/60 bg-green-950/10">
            <h3 className="text-xs font-semibold text-green-400 uppercase tracking-wide mb-3">Top Leaders</h3>
            {leaders.map((r) => (
              <div key={r.industry} className="flex justify-between items-center text-sm py-1">
                <div>
                  <span className="text-gray-200">{r.industry}</span>
                  <span className="text-gray-600 text-xs ml-1">{r.etf}</span>
                </div>
                <ReturnCell v={periodVal(r)} />
              </div>
            ))}
          </div>
          <div className="p-4 rounded-xl border border-red-800/60 bg-red-950/10">
            <h3 className="text-xs font-semibold text-red-400 uppercase tracking-wide mb-3">Top Laggards</h3>
            {laggards.map((r) => (
              <div key={r.industry} className="flex justify-between items-center text-sm py-1">
                <div>
                  <span className="text-gray-200">{r.industry}</span>
                  <span className="text-gray-600 text-xs ml-1">{r.etf}</span>
                </div>
                <ReturnCell v={periodVal(r)} />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Period column selector (when returns are shown) */}
      {showReturns && hasReturns && (
        <div className="flex items-center gap-2 flex-wrap p-3 rounded-lg border border-gray-800 bg-gray-900/30">
          <span className="text-xs text-gray-500 font-medium mr-1">Columns:</span>
          {RETURN_PERIODS.map((p) => (
            <button
              key={p}
              onClick={() => {
                setSelectedPeriods((prev) =>
                  prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p].sort((a, b) => RETURN_PERIODS.indexOf(a) - RETURN_PERIODS.indexOf(b))
                );
              }}
              className={`px-2.5 py-1 text-xs rounded transition-colors ${
                selectedPeriods.includes(p)
                  ? "bg-blue-700 text-white"
                  : "border border-gray-700 text-gray-400 hover:text-white hover:border-gray-600"
              }`}
            >
              {RETURN_PERIOD_LABELS[p]}
            </button>
          ))}
        </div>
      )}

      {/* Main table */}
      <div className="rounded-xl border border-gray-800 overflow-x-auto">
        {view === "ranked" ? (
          <IndustryTable
            rows={data.rankings}
            startRank={1}
            showReturns={showReturns}
            selectedPeriods={showReturns ? selectedPeriods : undefined}
          />
        ) : (
          Object.entries(data.by_sector).map(([sector, rows]) => (
            <div key={sector} className="overflow-x-auto">
              <div className="px-3 py-2 bg-gray-900/80 border-t border-gray-800 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                {sector}
              </div>
              <IndustryTable
                rows={rows}
                startRank={1}
                showReturns={showReturns}
                selectedPeriods={showReturns ? selectedPeriods : undefined}
              />
            </div>
          ))
        )}
      </div>
    </div>
  );
}
