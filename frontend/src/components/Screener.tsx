"use client";
import { useState, useMemo } from "react";

export interface Quote {
  symbol: string;
  price: number;
  change: number;
  change_pct: number;
  high: number;
  low: number;
  signal: string;
  // "finnhub" = real-time intraday; "yfinance" = prior-close fallback
  source?: string;
  error?: string;
}

export interface ScreenerData {
  date: string;
  total_screened: number;
  gainers: Quote[];
  losers: Quote[];
  signal_counts: Record<string, number>;
  breadth_pct: number;
  ai_regime: string;
  quotes: Record<string, Quote>;
  // How many quotes came from each source
  sources?: Record<string, number>;
}

const SIGNAL_BADGE: Record<string, string> = {
  strong_buy: "bg-green-700 text-green-100",
  buy: "bg-green-900 text-green-300",
  hold: "bg-gray-800 text-gray-400",
  sell: "bg-red-900 text-red-300",
  strong_sell: "bg-red-700 text-red-100",
};

function Pct({ v }: { v?: number }) {
  if (v === undefined) return <span className="text-gray-500">—</span>;
  const cls = v > 0 ? "text-green-400" : v < 0 ? "text-red-400" : "text-gray-400";
  return <span className={cls}>{v > 0 ? "+" : ""}{v.toFixed(2)}%</span>;
}

const SOURCE_BADGE: Record<string, string> = {
  finnhub: "text-blue-400",
  yfinance: "text-yellow-500",
};

function QuoteRow({ q, rank }: { q: Quote; rank: number }) {
  return (
    <tr className="border-t border-gray-800/60 hover:bg-gray-900/40">
      <td className="px-3 py-2 text-gray-600 text-xs">{rank}</td>
      <td className="px-3 py-2 font-mono text-blue-400 font-semibold">{q.symbol}</td>
      <td className="px-3 py-2 text-right text-gray-300">${q.price?.toFixed(2)}</td>
      <td className="px-3 py-2 text-right text-gray-500 text-xs font-mono">
        {q.high !== undefined && q.low !== undefined ? `${q.low.toFixed(2)}–${q.high.toFixed(2)}` : "—"}
      </td>
      <td className="px-3 py-2 text-right"><Pct v={q.change_pct} /></td>
      <td className="px-3 py-2 text-center">
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${SIGNAL_BADGE[q.signal] ?? SIGNAL_BADGE.hold}`}>
          {q.signal?.replace("_", " ")}
        </span>
      </td>
      <td className="px-3 py-2 text-center">
        <span className={`text-xs font-mono ${SOURCE_BADGE[q.source ?? ""] ?? "text-gray-600"}`} title={q.source === "yfinance" ? "Prior-close fallback — Finnhub unavailable for this symbol" : "Real-time intraday quote"}>
          {q.source ?? "—"}
        </span>
      </td>
    </tr>
  );
}

type ScreenerSortKey = "symbol" | "price" | "change_pct" | "high" | "low" | "signal";
const SIGNAL_ORDER = ["strong_buy", "buy", "hold", "sell", "strong_sell"];

function SortHeader({
  label, sortKey, current, dir, onClick, align = "right",
}: {
  label: string; sortKey: ScreenerSortKey; current: ScreenerSortKey; dir: "asc" | "desc";
  onClick: (k: ScreenerSortKey) => void; align?: "left" | "right" | "center";
}) {
  const active = current === sortKey;
  const alignClass = { left: "text-left", right: "text-right", center: "text-center" }[align];
  return (
    <th
      className={`${alignClass} px-3 py-2 font-medium cursor-pointer select-none hover:text-white ${active ? "text-white" : "text-gray-400"}`}
      onClick={() => onClick(sortKey)}
    >
      {label}{active ? (dir === "desc" ? " ▼" : " ▲") : ""}
    </th>
  );
}

export function Screener({ data }: { data: ScreenerData }) {
  const [view, setView] = useState<"gainers" | "losers" | "all">("gainers");
  const [sortKey, setSortKey] = useState<ScreenerSortKey>("change_pct");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  function handleSort(k: ScreenerSortKey) {
    if (k === sortKey) setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    else { setSortKey(k); setSortDir("desc"); }
  }

  const allRows = Object.values(data.quotes).filter((q) => !q.error);
  const sortedAll = useMemo(() => [...allRows].sort((a, b) => {
    if (sortKey === "symbol") return sortDir === "desc" ? b.symbol.localeCompare(a.symbol) : a.symbol.localeCompare(b.symbol);
    if (sortKey === "signal") {
      const ai = SIGNAL_ORDER.indexOf(a.signal);
      const bi = SIGNAL_ORDER.indexOf(b.signal);
      return sortDir === "desc" ? ai - bi : bi - ai;
    }
    const av = a[sortKey];
    const bv = b[sortKey];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    return sortDir === "desc" ? (bv as number) - (av as number) : (av as number) - (bv as number);
  }), [allRows, sortKey, sortDir]);

  const rows = view === "gainers" ? data.gainers : view === "losers" ? data.losers : sortedAll;
  const breadthColor = data.breadth_pct > 0 ? "text-green-400" : data.breadth_pct < 0 ? "text-red-400" : "text-gray-400";

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Stock Screener</h1>
          <p className="text-sm text-gray-500 mt-0.5">{data.total_screened} symbols screened · {data.date}</p>
        </div>
        <div className="flex gap-1 bg-gray-900 rounded-lg p-1">
          {(["gainers", "losers", "all"] as const).map((v) => (
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

      {/* AI Regime */}
      <div className="p-4 rounded-xl border border-blue-800/40 bg-blue-950/10">
        <div className="flex items-center gap-3 mb-1">
          <span className="text-xs font-semibold text-blue-400 uppercase tracking-wide">AI Regime</span>
          <span className={`text-sm font-semibold ${breadthColor}`}>Breadth {data.breadth_pct > 0 ? "+" : ""}{data.breadth_pct}%</span>
        </div>
        <p className="text-sm text-gray-300">{data.ai_regime}</p>
      </div>

      {/* Signal counts */}
      <div className="grid grid-cols-5 gap-2">
        {Object.entries(data.signal_counts).map(([sig, count]) => (
          <div key={sig} className={`text-center p-2 rounded-lg border ${SIGNAL_BADGE[sig] ? "" : "border-gray-800"}`}>
            <div className="text-lg font-bold">{count}</div>
            <div className="text-xs text-gray-500 capitalize">{sig.replace("_", " ")}</div>
          </div>
        ))}
      </div>

      {/* Source breakdown */}
      {data.sources && Object.keys(data.sources).length > 0 && (
        <div className="flex gap-3 text-xs text-gray-500">
          <span>Data sources:</span>
          {Object.entries(data.sources).map(([src, count]) => (
            <span key={src} className={`font-mono ${SOURCE_BADGE[src] ?? "text-gray-500"}`}>
              {src} ({count})
            </span>
          ))}
          {data.sources.yfinance ? (
            <span className="text-yellow-600">· yfinance = prior-close fallback (Finnhub rate limit)</span>
          ) : null}
        </div>
      )}

      {/* Table */}
      <div className="rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-900 sticky top-0">
            <tr>
              <th className="text-left px-3 py-2 text-gray-500 font-medium w-8">#</th>
              {view === "all" ? (
                <>
                  <SortHeader label="Symbol" sortKey="symbol" current={sortKey} dir={sortDir} onClick={handleSort} align="left" />
                  <SortHeader label="Price" sortKey="price" current={sortKey} dir={sortDir} onClick={handleSort} />
                  <th className="text-right px-3 py-2 text-gray-400 font-medium">Low–High</th>
                  <SortHeader label="Chg %" sortKey="change_pct" current={sortKey} dir={sortDir} onClick={handleSort} />
                  <SortHeader label="Signal" sortKey="signal" current={sortKey} dir={sortDir} onClick={handleSort} align="center" />
                  <th className="text-center px-3 py-2 text-gray-400 font-medium">Source</th>
                </>
              ) : (
                <>
                  <th className="text-left px-3 py-2 text-gray-400 font-medium">Symbol</th>
                  <th className="text-right px-3 py-2 text-gray-400 font-medium">Price</th>
                  <th className="text-right px-3 py-2 text-gray-400 font-medium">Low–High</th>
                  <th className="text-right px-3 py-2 text-gray-400 font-medium">Chg %</th>
                  <th className="text-center px-3 py-2 text-gray-400 font-medium">Signal</th>
                  <th className="text-center px-3 py-2 text-gray-400 font-medium">Source</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((q, i) => <QuoteRow key={q.symbol} q={q} rank={i + 1} />)}
          </tbody>
        </table>
      </div>
    </div>
  );
}
