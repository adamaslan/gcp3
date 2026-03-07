"use client";
import { useState } from "react";

interface Holding {
  symbol: string;
  name?: string;
  industry?: string;
  price?: number;
  change_pct?: number;
  change?: number;
  error?: string;
}

interface PortfolioData {
  date: string;
  tickers: string[];
  holdings: Record<string, Holding>;
  ai_grade: string;
  ai_concentration: number;
  ai_avg_change_pct: number;
  ai_insights: string[];
  ai_industry_breakdown: Record<string, string[]>;
  ai_winners_count: number;
  ai_losers_count: number;
}

const GRADE_STYLE: Record<string, string> = {
  A: "text-green-400",
  B: "text-blue-400",
  C: "text-yellow-400",
  D: "text-red-400",
};

function HoldingRow({ h }: { h: Holding }) {
  const chg = h.change_pct;
  const color = chg === undefined ? "text-gray-500" : chg > 0 ? "text-green-400" : chg < 0 ? "text-red-400" : "text-gray-400";
  return (
    <tr className="border-t border-gray-800/60 hover:bg-gray-900/40">
      <td className="px-3 py-2 font-mono text-blue-400 font-semibold">{h.symbol}</td>
      <td className="px-3 py-2 text-gray-400 text-xs max-w-xs truncate">{h.name ?? "—"}</td>
      <td className="px-3 py-2 text-gray-500 text-xs">{h.industry ?? "—"}</td>
      <td className="px-3 py-2 text-right text-gray-300">
        {h.error ? <span className="text-red-400 text-xs">err</span> : `$${h.price?.toFixed(2) ?? "—"}`}
      </td>
      <td className={`px-3 py-2 text-right ${color}`}>
        {chg !== undefined ? `${chg > 0 ? "+" : ""}${chg.toFixed(2)}%` : "—"}
      </td>
    </tr>
  );
}

export function PortfolioAnalyzer({ initialData }: { initialData: PortfolioData }) {
  const [tickerInput, setTickerInput] = useState(initialData.tickers.join(", "));
  const [data, setData] = useState<PortfolioData>(initialData);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function analyze() {
    setLoading(true);
    setError(null);
    try {
      const encoded = encodeURIComponent(tickerInput.replace(/\s/g, ""));
      const res = await fetch(`/api/portfolio-analyzer?tickers=${encoded}`);
      if (!res.ok) throw new Error(`Error ${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  const holdings = Object.values(data.holdings);
  const gradeColor = GRADE_STYLE[data.ai_grade] ?? "text-gray-400";
  const avgColor = data.ai_avg_change_pct > 0 ? "text-green-400" : data.ai_avg_change_pct < 0 ? "text-red-400" : "text-gray-400";

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white">Portfolio Analyzer</h1>
        <p className="text-sm text-gray-500 mt-0.5">AI-powered allocation insights · {data.date}</p>
      </div>

      {/* Input */}
      <div className="flex gap-2">
        <input
          value={tickerInput}
          onChange={(e) => setTickerInput(e.target.value)}
          placeholder="AAPL, MSFT, TSLA, ..."
          className="flex-1 px-3 py-2 rounded-lg bg-gray-900 border border-gray-700 text-gray-200 text-sm focus:outline-none focus:border-blue-500"
        />
        <button
          onClick={analyze}
          disabled={loading}
          className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium disabled:opacity-50 transition-colors"
        >
          {loading ? "Analyzing…" : "Analyze"}
        </button>
      </div>
      {error && <p className="text-red-400 text-sm">{error}</p>}

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-3">
        <div className="p-4 rounded-xl border border-gray-800 text-center">
          <div className={`text-3xl font-bold ${gradeColor}`}>{data.ai_grade}</div>
          <div className="text-xs text-gray-500 mt-1">Diversification Grade</div>
        </div>
        <div className="p-4 rounded-xl border border-gray-800 text-center">
          <div className={`text-2xl font-bold ${avgColor}`}>
            {data.ai_avg_change_pct > 0 ? "+" : ""}{data.ai_avg_change_pct.toFixed(2)}%
          </div>
          <div className="text-xs text-gray-500 mt-1">Avg Change Today</div>
        </div>
        <div className="p-4 rounded-xl border border-green-800/40 text-center">
          <div className="text-2xl font-bold text-green-400">{data.ai_winners_count}</div>
          <div className="text-xs text-gray-500 mt-1">Winners</div>
        </div>
        <div className="p-4 rounded-xl border border-red-800/40 text-center">
          <div className="text-2xl font-bold text-red-400">{data.ai_losers_count}</div>
          <div className="text-xs text-gray-500 mt-1">Losers</div>
        </div>
      </div>

      {/* AI Insights */}
      <div className="p-4 rounded-xl border border-blue-800/40 bg-blue-950/10">
        <div className="text-xs font-semibold text-blue-400 uppercase tracking-wide mb-2">AI Insights</div>
        <ul className="space-y-1">
          {data.ai_insights.map((ins, i) => (
            <li key={i} className="text-sm text-gray-300">• {ins}</li>
          ))}
        </ul>
      </div>

      {/* Holdings table */}
      <div className="rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-900">
            <tr>
              <th className="text-left px-3 py-2 text-gray-400">Symbol</th>
              <th className="text-left px-3 py-2 text-gray-400">Name</th>
              <th className="text-left px-3 py-2 text-gray-400">Industry</th>
              <th className="text-right px-3 py-2 text-gray-400">Price</th>
              <th className="text-right px-3 py-2 text-gray-400">Chg %</th>
            </tr>
          </thead>
          <tbody>
            {holdings.map((h) => <HoldingRow key={h.symbol} h={h} />)}
          </tbody>
        </table>
      </div>
    </div>
  );
}
