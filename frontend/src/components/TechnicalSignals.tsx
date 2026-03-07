"use client";
import { useState } from "react";

interface Signal {
  signal: string;
  strength: "BULLISH" | "BEARISH" | "NEUTRAL";
  value?: number;
  category: string;
}

interface TickerData {
  symbol: string;
  ai_action: "BUY" | "HOLD" | "SELL";
  ai_summary: string;
  ai_outlook?: string;
  ai_score?: number;
  ai_confidence?: string;
  price: number;
  signal_count: number;
  change_pct?: number;
  signals: Signal[];
  indicators: Record<string, number>;
  timestamp?: string;
}

interface SignalSummary {
  buy_count: number;
  sell_count: number;
  hold_count: number;
  ai_regime: string;
}

interface TechnicalSignalsData {
  date: string;
  total: number;
  ranked: TickerData[];
  buys: TickerData[];
  sells: TickerData[];
  holds: TickerData[];
  signal_summary: SignalSummary;
}

const ACTION_STYLE: Record<string, string> = {
  BUY: "bg-green-700 text-green-100",
  HOLD: "bg-gray-700 text-gray-300",
  SELL: "bg-red-700 text-red-100",
};

const STRENGTH_DOT: Record<string, string> = {
  BULLISH: "text-green-400",
  BEARISH: "text-red-400",
  NEUTRAL: "text-gray-500",
};

function TickerCard({ t }: { t: TickerData }) {
  const [expanded, setExpanded] = useState(false);
  const chgColor = (t.change_pct ?? 0) > 0 ? "text-green-400" : (t.change_pct ?? 0) < 0 ? "text-red-400" : "text-gray-400";
  return (
    <div className="rounded-xl border border-gray-800 p-4 hover:border-gray-700 transition-colors">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-mono font-bold text-blue-400 text-lg">{t.symbol}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${ACTION_STYLE[t.ai_action]}`}>
              {t.ai_action}
            </span>
          </div>
          <div className="text-sm text-gray-400 mt-0.5">{t.ai_summary}</div>
        </div>
        <div className="text-right">
          <div className="text-sm font-semibold text-gray-200">${t.price?.toFixed(2)}</div>
          {t.change_pct !== undefined && (
            <div className={`text-xs ${chgColor}`}>{t.change_pct > 0 ? "+" : ""}{t.change_pct.toFixed(2)}%</div>
          )}
        </div>
      </div>

      {/* Indicators bar */}
      <div className="flex gap-3 mt-3 text-xs text-gray-600">
        {t.indicators?.rsi !== undefined && (
          <span className={t.indicators.rsi > 70 ? "text-red-400" : t.indicators.rsi < 30 ? "text-green-400" : "text-gray-500"}>
            RSI {t.indicators.rsi.toFixed(0)}
          </span>
        )}
        {t.indicators?.macd !== undefined && (
          <span className={t.indicators.macd > 0 ? "text-green-400" : "text-red-400"}>
            MACD {t.indicators.macd.toFixed(2)}
          </span>
        )}
        {t.indicators?.adx !== undefined && (
          <span className={t.indicators.adx > 25 ? "text-yellow-400" : "text-gray-600"}>
            ADX {t.indicators.adx.toFixed(0)}
          </span>
        )}
        {t.signal_count > 0 && (
          <button onClick={() => setExpanded(!expanded)} className="ml-auto text-blue-500 hover:text-blue-400">
            {t.signal_count} signal{t.signal_count !== 1 ? "s" : ""} {expanded ? "▲" : "▼"}
          </button>
        )}
      </div>

      {expanded && t.signals?.length > 0 && (
        <div className="mt-2 space-y-1 border-t border-gray-800 pt-2">
          {t.signals.map((s, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              <span className={STRENGTH_DOT[s.strength] ?? "text-gray-500"}>●</span>
              <span className="text-gray-400">{s.signal}</span>
              {s.value !== undefined && <span className="text-gray-600 font-mono">{s.value.toFixed(3)}</span>}
              <span className="text-gray-700 ml-auto">{s.category}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function TechnicalSignals({ data }: { data: TechnicalSignalsData }) {
  const [view, setView] = useState<"all" | "buys" | "sells" | "holds">("all");
  const rows = view === "buys" ? data.buys : view === "sells" ? data.sells : view === "holds" ? data.holds : data.ranked;
  const ss = data.signal_summary;
  const regimeColor = ss.ai_regime === "Bullish" ? "text-green-400" : ss.ai_regime === "Bearish" ? "text-red-400" : "text-yellow-400";

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white">Technical Signals</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          AI signals from MACD, RSI, ADX, trend indicators · {data.total} tickers · {data.date}
        </p>
      </div>

      {/* Regime + counts */}
      <div className="grid grid-cols-4 gap-3">
        <div className="p-4 rounded-xl border border-gray-800 text-center col-span-1">
          <div className={`text-xl font-bold ${regimeColor}`}>{ss.ai_regime}</div>
          <div className="text-xs text-gray-600 mt-1">AI Regime</div>
        </div>
        <div className="p-4 rounded-xl border border-green-800/40 text-center">
          <div className="text-2xl font-bold text-green-400">{ss.buy_count}</div>
          <div className="text-xs text-gray-500 mt-1">Buy</div>
        </div>
        <div className="p-4 rounded-xl border border-gray-800 text-center">
          <div className="text-2xl font-bold text-gray-400">{ss.hold_count}</div>
          <div className="text-xs text-gray-500 mt-1">Hold</div>
        </div>
        <div className="p-4 rounded-xl border border-red-800/40 text-center">
          <div className="text-2xl font-bold text-red-400">{ss.sell_count}</div>
          <div className="text-xs text-gray-500 mt-1">Sell</div>
        </div>
      </div>

      {/* View toggle */}
      <div className="flex gap-1 bg-gray-900 rounded-lg p-1 w-fit">
        {(["all", "buys", "sells", "holds"] as const).map((v) => (
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

      {/* Cards grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {rows.map((t) => <TickerCard key={t.symbol} t={t} />)}
      </div>
    </div>
  );
}
