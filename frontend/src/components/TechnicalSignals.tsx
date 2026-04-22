"use client";
import { useState } from "react";

interface Signal {
  signal: string;
  detail?: string;
  strength: "BULLISH" | "BEARISH" | "NEUTRAL";
  value?: number;
  weight?: number;
  category: string;
}

interface TickerData {
  symbol: string;
  ai_action: "BUY" | "HOLD" | "SELL";
  ai_summary: string;
  ai_outlook?: string;
  ai_score?: number;
  ai_confidence?: string;
  confluence_score?: number;
  confluence_label?: string;
  bull_count?: number;
  bear_count?: number;
  price: number;
  signal_count: number;
  change_pct?: number;
  signals: Signal[];
  indicators: Record<string, number | null>;
  industry?: string;
  returns?: Record<string, number>;
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
  BUY:  "bg-green-700 text-green-100",
  HOLD: "bg-gray-700 text-gray-300",
  SELL: "bg-red-700 text-red-100",
};

const STRENGTH_DOT: Record<string, string> = {
  BULLISH: "text-green-400",
  BEARISH: "text-red-400",
  NEUTRAL: "text-gray-500",
};

const CONF_BAR_COLOR: Record<string, string> = {
  HIGH:   "bg-green-500",
  MEDIUM: "bg-yellow-500",
  LOW:    "bg-gray-500",
};

function ConfluenceBar({ score, label }: { score: number; label: string }) {
  // score is [-1, 1]; display as 0–100% centered bar
  const pct = Math.round(Math.abs(score) * 100);
  const positive = score >= 0;
  return (
    <div className="flex items-center gap-2 mt-1">
      <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${positive ? "bg-green-500" : "bg-red-500"} transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`text-xs font-mono w-10 text-right ${positive ? "text-green-400" : "text-red-400"}`}>
        {score >= 0 ? "+" : ""}{score.toFixed(2)}
      </span>
      <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${CONF_BAR_COLOR[label] ?? "bg-gray-700"} text-gray-900`}>
        {label}
      </span>
    </div>
  );
}

function TickerCard({ t, rank }: { t: TickerData; rank?: number }) {
  const [expanded, setExpanded] = useState(false);
  const chgColor = (t.change_pct ?? 0) > 0 ? "text-green-400" : (t.change_pct ?? 0) < 0 ? "text-red-400" : "text-gray-400";
  const score = t.confluence_score ?? t.ai_score ?? 0;
  const label = t.confluence_label ?? t.ai_confidence ?? "LOW";

  return (
    <div className="rounded-xl border border-gray-800 p-4 hover:border-gray-700 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {rank != null && (
              <span className="text-xs text-gray-600 font-mono">#{rank}</span>
            )}
            <span className="font-mono font-bold text-blue-400 text-lg">{t.symbol}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${ACTION_STYLE[t.ai_action]}`}>
              {t.ai_action}
            </span>
            {t.industry && (
              <span className="text-xs text-gray-600 truncate">{t.industry}</span>
            )}
          </div>
          <div className="text-sm text-gray-400 mt-0.5">{t.ai_summary}</div>
          <ConfluenceBar score={score} label={label} />
        </div>
        <div className="text-right shrink-0">
          {t.change_pct != null && (
            <div className={`text-sm font-semibold ${chgColor}`}>
              {t.change_pct > 0 ? "+" : ""}{t.change_pct.toFixed(2)}%
            </div>
          )}
          <div className="text-xs text-gray-600 mt-0.5">
            {t.bull_count ?? 0}B / {t.bear_count ?? 0}S
          </div>
        </div>
      </div>

      {/* Outlook */}
      {t.ai_outlook && (
        <p className="text-xs text-gray-500 mt-2 leading-relaxed">{t.ai_outlook}</p>
      )}

      {/* Expand signals */}
      {t.signal_count > 0 && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-3 text-xs text-blue-500 hover:text-blue-400 flex items-center gap-1"
        >
          {t.signal_count} signal{t.signal_count !== 1 ? "s" : ""} {expanded ? "▲" : "▼"}
        </button>
      )}

      {expanded && t.signals?.length > 0 && (
        <div className="mt-2 space-y-2 border-t border-gray-800 pt-2">
          {t.signals.map((s, i) => (
            <div key={i} className="space-y-0.5">
              <div className="flex items-start gap-2 text-xs">
                <span className={`${STRENGTH_DOT[s.strength] ?? "text-gray-500"} mt-0.5 shrink-0`}>●</span>
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-gray-300 font-medium">{s.signal}</span>
                    {s.weight != null && (
                      <span className="text-gray-700 font-mono">w={s.weight}</span>
                    )}
                    <span className="text-gray-700 ml-auto">{s.category}</span>
                  </div>
                  {s.detail && (
                    <p className="text-gray-500 mt-0.5 leading-relaxed">{s.detail}</p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Top10Panel({ items, action }: { items: TickerData[]; action: "BUY" | "SELL" }) {
  const top10 = items.slice(0, 10);
  const isBuy = action === "BUY";
  const borderColor = isBuy ? "border-green-800/40" : "border-red-800/40";
  const labelColor = isBuy ? "text-green-400" : "text-red-400";
  const barColor = isBuy ? "bg-green-500" : "bg-red-500";

  return (
    <div className={`rounded-xl border ${borderColor} p-4 space-y-3`}>
      <div className={`text-xs font-semibold ${labelColor} uppercase tracking-wide`}>
        Top {top10.length} {action === "BUY" ? "Buys" : "Sells"} by Confluence
      </div>
      {top10.map((t, i) => {
        const score = t.confluence_score ?? t.ai_score ?? 0;
        const pct = Math.round(Math.abs(score) * 100);
        return (
          <div key={t.symbol} className="flex items-center gap-3">
            <span className="text-xs text-gray-600 font-mono w-4 shrink-0">#{i + 1}</span>
            <span className="font-mono text-sm font-bold text-blue-400 w-14 shrink-0">{t.symbol}</span>
            <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
              <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
            </div>
            <span className={`text-xs font-mono w-10 text-right ${isBuy ? "text-green-400" : "text-red-400"}`}>
              {score >= 0 ? "+" : ""}{score.toFixed(2)}
            </span>
            {t.change_pct != null && (
              <span className={`text-xs font-mono w-14 text-right ${t.change_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                {t.change_pct >= 0 ? "+" : ""}{t.change_pct.toFixed(2)}%
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function TechnicalSignals({ data }: { data: TechnicalSignalsData }) {
  const [view, setView] = useState<"all" | "buys" | "sells" | "holds">("all");
  const rows = view === "buys" ? data.buys : view === "sells" ? data.sells : view === "holds" ? data.holds : data.ranked;
  const ss = data.signal_summary;
  const regimeColor = ss.ai_regime === "Bullish" ? "text-green-400" : ss.ai_regime === "Bearish" ? "text-red-400" : "text-yellow-400";

  // Average confluence scores for buy/sell groups
  const avgBuyScore = data.buys.length
    ? data.buys.reduce((a, t) => a + (t.confluence_score ?? 0), 0) / data.buys.length
    : 0;
  const avgSellScore = data.sells.length
    ? data.sells.reduce((a, t) => a + (t.confluence_score ?? 0), 0) / data.sells.length
    : 0;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white">Technical Signals</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Multi-timeframe momentum, trend, and relative strength · {data.total} industry ETFs · {data.date}
        </p>
      </div>

      {/* Regime + counts */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-4 rounded-xl border border-gray-800 text-center col-span-2 sm:col-span-1">
          <div className={`text-xl font-bold ${regimeColor}`}>{ss.ai_regime}</div>
          <div className="text-xs text-gray-600 mt-1">AI Regime</div>
        </div>
        <div className="p-4 rounded-xl border border-green-800/40 text-center">
          <div className="text-2xl font-bold text-green-400">{ss.buy_count}</div>
          <div className="text-xs text-gray-500 mt-0.5">Buy</div>
          {data.buys.length > 0 && (
            <div className="text-xs text-green-600 mt-0.5">avg {avgBuyScore >= 0 ? "+" : ""}{avgBuyScore.toFixed(2)}</div>
          )}
        </div>
        <div className="p-4 rounded-xl border border-gray-800 text-center">
          <div className="text-2xl font-bold text-gray-400">{ss.hold_count}</div>
          <div className="text-xs text-gray-500 mt-1">Hold</div>
        </div>
        <div className="p-4 rounded-xl border border-red-800/40 text-center">
          <div className="text-2xl font-bold text-red-400">{ss.sell_count}</div>
          <div className="text-xs text-gray-500 mt-0.5">Sell</div>
          {data.sells.length > 0 && (
            <div className="text-xs text-red-600 mt-0.5">avg {avgSellScore.toFixed(2)}</div>
          )}
        </div>
      </div>

      {/* Top-10 confluence panels */}
      {(data.buys.length > 0 || data.sells.length > 0) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {data.buys.length > 0 && <Top10Panel items={data.buys} action="BUY" />}
          {data.sells.length > 0 && <Top10Panel items={data.sells} action="SELL" />}
        </div>
      )}

      {/* View toggle */}
      <div className="flex gap-1 bg-gray-900 rounded-lg p-1 w-full sm:w-fit">
        {(["all", "buys", "sells", "holds"] as const).map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={`flex-1 sm:flex-none px-3 py-1.5 text-sm rounded-md transition-colors capitalize text-center ${
              view === v ? "bg-gray-700 text-white" : "text-gray-400 hover:text-white"
            }`}
          >
            {v}
          </button>
        ))}
      </div>

      {/* Cards grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {rows.map((t, i) => (
          <TickerCard
            key={t.symbol}
            t={t}
            rank={view === "buys" || view === "sells" ? i + 1 : undefined}
          />
        ))}
      </div>
    </div>
  );
}
