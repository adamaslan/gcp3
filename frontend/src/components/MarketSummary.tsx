"use client";
import React, { useState } from "react";
import { useRouter } from "next/navigation";

interface TickerMention {
  symbol: string;
  score?: number;
  action?: string;
}

interface DaySummary {
  date: string;
  total_analyzed?: number;
  top_bullish?: TickerMention[];
  top_bearish?: TickerMention[];
  high_confidence?: TickerMention[];
  narrative?: string;
  regime?: string;
}

interface MarketSummaryData {
  days_analyzed: number;
  history: DaySummary[];
}

const WINDOW_OPTIONS = [
  { value: "7", label: "7 days" },
  { value: "14", label: "14 days" },
  { value: "30", label: "30 days" },
] as const;

const REGIME_COLOR: Record<string, string> = {
  Bullish: "text-green-400",
  Bearish: "text-red-400",
  Neutral: "text-yellow-400",
};

function ActionBadge({ action }: { action?: string }) {
  if (!action) return null;
  const style =
    action === "BUY" ? "bg-green-700 text-green-100" :
    action === "SELL" ? "bg-red-700 text-red-100" :
    "bg-gray-700 text-gray-300";
  return <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${style}`}>{action}</span>;
}

export function MarketSummary({
  data,
  selectedDays = "7",
}: {
  data: MarketSummaryData;
  selectedDays?: string;
}): React.ReactElement {
  const [selected, setSelected] = useState(0);
  const router = useRouter();
  const summary = data.history[selected];

  if (!summary) {
    return (
      <div className="text-gray-500 text-center py-20">No summary data available.</div>
    );
  }

  const regimeColor = REGIME_COLOR[summary.regime ?? ""] ?? "text-yellow-400";

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white">Market Summary</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {data.days_analyzed}-day trend from AI signal pipeline
          </p>
        </div>
        {/* Window selector */}
        <div className="flex gap-1 bg-gray-900 rounded-lg p-1">
          {WINDOW_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              onClick={() => {
                setSelected(0);
                router.push(`/market-summary?days=${value}`);
              }}
              className={`px-3 py-1 text-xs rounded-md transition-colors ${
                selectedDays === value
                  ? "bg-blue-700 text-white"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Day selector */}
      <div className="flex gap-1 overflow-x-auto pb-1">
        {data.history.map((s, i) => (
          <button
            key={s.date}
            onClick={() => setSelected(i)}
            className={`px-3 py-1.5 text-xs rounded-lg whitespace-nowrap transition-colors ${
              selected === i ? "bg-blue-700 text-white" : "bg-gray-900 text-gray-400 hover:text-white"
            }`}
          >
            {s.date}
          </button>
        ))}
      </div>

      {/* Day summary card */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="col-span-2 sm:col-span-1 p-4 rounded-xl border border-gray-800 text-center">
          <div className={`text-xl font-bold ${regimeColor}`}>{summary.regime ?? "—"}</div>
          <div className="text-xs text-gray-600 mt-1">Regime</div>
        </div>
        <div className="p-4 rounded-xl border border-gray-800 text-center">
          <div className="text-2xl font-bold text-white">{summary.total_analyzed ?? "—"}</div>
          <div className="text-xs text-gray-500 mt-1">Analyzed</div>
        </div>
        <div className="p-4 rounded-xl border border-green-800/40 text-center">
          <div className="text-2xl font-bold text-green-400">{summary.top_bullish?.length ?? 0}</div>
          <div className="text-xs text-gray-500 mt-1">Bullish</div>
        </div>
        <div className="p-4 rounded-xl border border-red-800/40 text-center">
          <div className="text-2xl font-bold text-red-400">{summary.top_bearish?.length ?? 0}</div>
          <div className="text-xs text-gray-500 mt-1">Bearish</div>
        </div>
      </div>

      {/* Narrative */}
      {summary.narrative && (
        <div className="p-4 rounded-xl border border-gray-800 text-sm text-gray-300 leading-relaxed">
          {summary.narrative}
        </div>
      )}

      {/* Bullish / Bearish / High Confidence */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <TickerList title="Top Bullish" tickers={summary.top_bullish} accent="green" />
        <TickerList title="Top Bearish" tickers={summary.top_bearish} accent="red" />
        <TickerList title="High Confidence" tickers={summary.high_confidence} accent="blue" />
      </div>
    </div>
  );
}

function TickerList({
  title,
  tickers,
  accent,
}: {
  title: string;
  tickers?: TickerMention[];
  accent: "green" | "red" | "blue";
}) {
  const borderColor =
    accent === "green" ? "border-green-800/40" :
    accent === "red" ? "border-red-800/40" :
    "border-blue-800/40";
  const titleColor =
    accent === "green" ? "text-green-400" :
    accent === "red" ? "text-red-400" :
    "text-blue-400";

  return (
    <div className={`rounded-xl border ${borderColor} p-4 space-y-2`}>
      <div className={`text-sm font-semibold ${titleColor}`}>{title}</div>
      {!tickers?.length ? (
        <div className="text-xs text-gray-600">No data</div>
      ) : (
        tickers.map((t) => (
          <div key={t.symbol} className="flex items-center justify-between">
            <span className="font-mono text-sm text-gray-200">{t.symbol}</span>
            <div className="flex items-center gap-2">
              {t.score !== undefined && (
                <span className="text-xs text-gray-500">{t.score.toFixed(1)}</span>
              )}
              <ActionBadge action={t.action} />
            </div>
          </div>
        ))
      )}
    </div>
  );
}
